"""
TrelloWebhookService — incoming webhook processing and registration.

Responsibilities
────────────────
1. Register / deregister webhooks with the Trello API, persisting the
   Trello-assigned webhook ID in `trello_webhooks`.
2. Verify the HMAC-SHA1 signature on every incoming request (delegated to
   TrelloClient.verify_webhook_signature).
3. Process each action type idempotently:
     - updateCard (list change) → update card.list_id, record movement,
                                  update entered_wip_at / entered_done_at,
                                  emit TrelloCardMovedEvent
     - commentCard              → emit TrelloCardCommentedEvent
     - createCard               → set trello_created_at, emit movement record
     - all other tracked types  → persist TrelloAction for the activity feed
4. Increment the webhook's `events_received` counter and `last_ping_at`.
5. Publish resulting domain events via WebSocketManager for live dashboards.

Idempotency
───────────
Every action is keyed on `trello_action_id`. We do an early SELECT before
processing; if the action already exists we return immediately.
This makes replays / duplicate deliveries safe.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.domain.events.trello_events import (
    TrelloCardCommentedEvent,
    TrelloCardMovedEvent,
    TrelloWebhookReceivedEvent,
)
from app.infrastructure.websocket_manager import WebSocketManager
from app.models.trello_action import TrelloAction, TRACKED_ACTION_TYPES
from app.models.trello_board import TrelloBoard
from app.models.trello_card import TrelloCard, TrelloCardMovement
from app.models.trello_credential import TrelloCredential
from app.models.trello_list import ListType, TrelloList
from app.models.trello_webhook import TrelloWebhook
from app.schemas.trello import TrelloAPIWebhookPayload
from app.services.trello.client import TrelloClient

logger = get_logger(__name__)


class TrelloWebhookService:
    """
    Handles incoming Trello webhook payloads and manages webhook lifecycle.

    Usage (registration)::

        svc = TrelloWebhookService(db, ws_manager)
        webhook = await svc.register_webhook(board, credential, callback_url)

    Usage (incoming payload)::

        svc = TrelloWebhookService(db, ws_manager)
        events = await svc.handle_payload(webhook, payload)
    """

    def __init__(self, db: AsyncSession, ws_manager: WebSocketManager) -> None:
        self._db = db
        self._ws = ws_manager

    # ── Registration ──────────────────────────────────────────────────────────

    async def register_webhook(
        self,
        board: TrelloBoard,
        credential: TrelloCredential,
        callback_url: str,
        description: str | None = None,
    ) -> TrelloWebhook:
        """
        Register a webhook on Trello for the given board and persist it locally.
        If an active webhook already exists for this board, return it unchanged.
        """
        # Check for existing active webhook
        existing = await self._db.scalar(
            select(TrelloWebhook)
            .where(TrelloWebhook.board_id == board.id, TrelloWebhook.is_active.is_(True))
        )
        if existing:
            logger.info(
                "trello_webhook_already_registered",
                board_id=board.id,
                webhook_id=existing.trello_webhook_id,
            )
            return existing

        async with TrelloClient(
            api_key=credential.api_key,
            api_token=credential.api_token,
        ) as client:
            trello_resp = await client.register_webhook(
                model_id=board.trello_id,
                callback_url=callback_url,
                description=description or f"KPIMaster — board {board.name}",
            )

        webhook = TrelloWebhook(
            board_id=board.id,
            trello_webhook_id=trello_resp["id"],
            trello_model_id=board.trello_id,
            callback_url=callback_url,
            description=description,
            is_active=True,
        )
        self._db.add(webhook)
        await self._db.flush()

        logger.info(
            "trello_webhook_registered",
            board_id=board.id,
            trello_webhook_id=trello_resp["id"],
        )
        return webhook

    async def deregister_webhook(
        self,
        webhook: TrelloWebhook,
        credential: TrelloCredential,
    ) -> None:
        """Delete the webhook from Trello and mark it inactive locally."""
        try:
            async with TrelloClient(
                api_key=credential.api_key,
                api_token=credential.api_token,
            ) as client:
                await client.delete_webhook(webhook.trello_webhook_id)
        except Exception as exc:
            # Log but don't raise — still mark inactive so we stop sending
            logger.warning(
                "trello_webhook_delete_failed",
                webhook_id=webhook.id,
                error=str(exc),
            )

        await self._db.execute(
            update(TrelloWebhook)
            .where(TrelloWebhook.id == webhook.id)
            .values(is_active=False)
        )
        await self._db.flush()
        logger.info("trello_webhook_deregistered", webhook_id=webhook.id)

    # ── Incoming payload processing ───────────────────────────────────────────

    async def handle_payload(
        self,
        webhook: TrelloWebhook,
        payload: TrelloAPIWebhookPayload,
    ) -> list[dict]:
        """
        Process a verified webhook payload.

        Returns a list of serialised domain event dicts that were emitted.
        Callers can use these for testing / logging; the events are also
        broadcast to WebSocket clients before returning.
        """
        action = payload.action
        if not action:
            return []

        # ── Idempotency guard ────────────────────────────────────────────────
        already_exists = await self._db.scalar(
            select(TrelloAction.id).where(TrelloAction.trello_action_id == action.id)
        )
        if already_exists:
            logger.debug("trello_webhook_duplicate_action", action_id=action.id)
            await self._bump_webhook_counter(webhook)
            return []

        if action.type not in TRACKED_ACTION_TYPES:
            await self._bump_webhook_counter(webhook)
            return []

        # ── Load board context ────────────────────────────────────────────────
        board = await self._db.get(TrelloBoard, webhook.board_id)
        if not board:
            logger.error("trello_webhook_board_not_found", webhook_id=webhook.id)
            return []

        emitted_events: list[dict] = []

        # ── Dispatch by action type ───────────────────────────────────────────
        if action.type == "updateCard" and action.data.listBefore and action.data.listAfter:
            event = await self._handle_card_move(board, action)
            if event:
                emitted_events.append(event.model_dump())

        elif action.type == "commentCard":
            event = await self._handle_comment(board, action)
            if event:
                emitted_events.append(event.model_dump())

        elif action.type == "createCard":
            await self._handle_card_create(board, action)

        # Persist the raw action regardless of type
        await self._persist_action(action)

        # ── Update webhook counters ───────────────────────────────────────────
        await self._bump_webhook_counter(webhook)

        # ── Emit received-event (for observability) ───────────────────────────
        recv_event = TrelloWebhookReceivedEvent(
            board_id=board.id,
            trello_action_type=action.type,
            trello_action_id=action.id,
        )
        emitted_events.insert(0, recv_event.model_dump())

        # ── WebSocket broadcast ───────────────────────────────────────────────
        for evt_dict in emitted_events:
            await self._ws.broadcast_to_project(
                board.credential.project_id if board.credential else 0,
                evt_dict,
            )

        return emitted_events

    # ── Action handlers ───────────────────────────────────────────────────────

    async def _handle_card_move(self, board: TrelloBoard, action) -> TrelloCardMovedEvent | None:
        """
        Process a card-list-change action:
          1. Resolve DB IDs for the card and both lists.
          2. Update card.list_id.
          3. Update entered_wip_at / entered_done_at if this is the first entry.
          4. Insert a card movement record (idempotent).
          5. Return a TrelloCardMovedEvent.
        """
        card_trello_id = (action.data.card or {}).get("id")
        from_trello_id = action.data.listBefore.get("id")
        to_trello_id = action.data.listAfter.get("id")

        if not card_trello_id or not to_trello_id:
            return None

        # Resolve DB rows
        card = await self._db.scalar(
            select(TrelloCard).where(TrelloCard.trello_id == card_trello_id)
        )
        to_list = await self._db.scalar(
            select(TrelloList).where(TrelloList.trello_id == to_trello_id)
        )
        from_list = None
        if from_trello_id:
            from_list = await self._db.scalar(
                select(TrelloList).where(TrelloList.trello_id == from_trello_id)
            )

        if not card:
            logger.warning(
                "trello_webhook_card_not_found",
                trello_card_id=card_trello_id,
                action_id=action.id,
            )
            return None

        # Update card's current list
        new_list_id = to_list.id if to_list else None
        await self._db.execute(
            update(TrelloCard)
            .where(TrelloCard.id == card.id)
            .values(list_id=new_list_id, trello_last_activity=action.date)
        )

        # Update analytics anchors
        if to_list:
            if to_list.list_type == ListType.WIP and card.entered_wip_at is None:
                await self._db.execute(
                    update(TrelloCard)
                    .where(TrelloCard.id == card.id)
                    .values(entered_wip_at=action.date)
                )
            elif to_list.list_type == ListType.DONE and card.entered_done_at is None:
                await self._db.execute(
                    update(TrelloCard)
                    .where(TrelloCard.id == card.id)
                    .values(entered_done_at=action.date, is_stalled=False, stalled_since=None)
                )

        # Idempotent movement insert
        stmt = pg_insert(TrelloCardMovement).values(
            {
                "card_id": card.id,
                "from_list_id": from_list.id if from_list else None,
                "to_list_id": new_list_id,
                "trello_action_id": action.id,
                "moved_at": action.date,
            }
        )
        await self._db.execute(stmt.on_conflict_do_nothing(index_elements=["trello_action_id"]))
        await self._db.flush()

        return TrelloCardMovedEvent(
            board_id=board.id,
            trello_board_id=board.trello_id,
            board_name=board.name,
            card_id=card.id,
            trello_card_id=card.trello_id,
            card_name=card.name,
            card_short_id=card.trello_short_id,
            from_list_name=from_list.name if from_list else None,
            to_list_name=to_list.name if to_list else action.data.listAfter.get("name", ""),
            to_list_type=to_list.list_type.value if to_list else "unknown",
            moved_at=action.date,
            moved_by=action.memberCreator.fullName if action.memberCreator else None,
        )

    async def _handle_comment(self, board: TrelloBoard, action) -> TrelloCardCommentedEvent | None:
        card_trello_id = (action.data.card or {}).get("id")
        if not card_trello_id:
            return None

        card = await self._db.scalar(
            select(TrelloCard).where(TrelloCard.trello_id == card_trello_id)
        )
        if not card:
            return None

        # Touch last-activity timestamp
        await self._db.execute(
            update(TrelloCard)
            .where(TrelloCard.id == card.id)
            .values(trello_last_activity=action.date)
        )
        await self._db.flush()

        return TrelloCardCommentedEvent(
            board_id=board.id,
            card_id=card.id,
            trello_card_id=card.trello_id,
            card_name=card.name,
            author_name=action.memberCreator.fullName if action.memberCreator else "Unknown",
            comment_text=action.data.text or "",
            commented_at=action.date,
        )

    async def _handle_card_create(self, board: TrelloBoard, action) -> None:
        """Back-fill trello_created_at and create the initial movement record."""
        card_trello_id = (action.data.card or {}).get("id")
        if not card_trello_id:
            return

        card = await self._db.scalar(
            select(TrelloCard).where(TrelloCard.trello_id == card_trello_id)
        )
        if not card:
            return

        # Fill creation timestamp if not set
        if card.trello_created_at is None:
            await self._db.execute(
                update(TrelloCard)
                .where(TrelloCard.id == card.id)
                .values(trello_created_at=action.date)
            )

        # Initial placement movement
        dest_trello_id = (action.data.list or {}).get("id")
        to_list_id: int | None = None
        if dest_trello_id:
            dest_list = await self._db.scalar(
                select(TrelloList).where(TrelloList.trello_id == dest_trello_id)
            )
            to_list_id = dest_list.id if dest_list else None

        stmt = pg_insert(TrelloCardMovement).values(
            {
                "card_id": card.id,
                "from_list_id": None,
                "to_list_id": to_list_id,
                "trello_action_id": action.id,
                "moved_at": action.date,
            }
        )
        await self._db.execute(stmt.on_conflict_do_nothing(index_elements=["trello_action_id"]))
        await self._db.flush()

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _persist_action(self, action) -> None:
        stmt = pg_insert(TrelloAction).values(
            {
                "card_id": None,  # card FK resolved by analytics later if needed
                "trello_action_id": action.id,
                "action_type": action.type,
                "action_date": action.date,
                "data": {
                    "card": action.data.card,
                    "list": action.data.list,
                    "listBefore": action.data.listBefore,
                    "listAfter": action.data.listAfter,
                    "text": action.data.text,
                    "old": action.data.old,
                },
                "trello_member_id": action.idMemberCreator,
                "member_name": action.memberCreator.fullName if action.memberCreator else None,
            }
        )
        await self._db.execute(stmt.on_conflict_do_nothing(index_elements=["trello_action_id"]))

    async def _bump_webhook_counter(self, webhook: TrelloWebhook) -> None:
        await self._db.execute(
            update(TrelloWebhook)
            .where(TrelloWebhook.id == webhook.id)
            .values(
                events_received=TrelloWebhook.events_received + 1,
                last_ping_at=datetime.now(UTC),
            )
        )
        await self._db.flush()
