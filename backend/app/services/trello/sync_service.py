"""
TrelloSyncService — full and incremental board sync.

Strategy
────────
Full sync:   fetches all lists + all open cards + up to 1000 recent actions.
             Triggered on first connect and manually.
Incremental: fetches board actions since `last_action_id`.
             Triggered every N minutes by a Celery beat task.

Idempotency
───────────
All upserts use `ON CONFLICT (trello_id) DO UPDATE` so replaying the same
data is safe. Card movements keyed on `trello_action_id`.

List classification
───────────────────
Uses keyword regex against list names. Users can override via the API.
"""
from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.domain.events.trello_events import TrelloBoardSyncedEvent
from app.models.trello_action import TrelloAction, TRACKED_ACTION_TYPES
from app.models.trello_board import TrelloBoard
from app.models.trello_card import TrelloCard, TrelloCardMovement
from app.models.trello_credential import TrelloCredential
from app.models.trello_list import ListType, TrelloList
from app.schemas.trello import TrelloAPIAction, TrelloAPICard, TrelloAPIList
from app.services.trello.client import TrelloClient

logger = get_logger(__name__)

# ── List-type classification patterns ─────────────────────────────────────────

_BACKLOG_PAT = re.compile(
    r"\b(backlog|todo|to[\s\-]?do|icebox|new|open|planned|planning|queue|inbox|"
    r"user[\s\-]?stories?|requirements?|wishlist|ideas?|grooming|refinement)\b",
    re.IGNORECASE,
)
_DONE_PAT = re.compile(
    r"\b(done|complete[d]?|shipped|deployed|released|closed|archived|accepted|finished|resolved)\b",
    re.IGNORECASE,
)
_WIP_PAT = re.compile(
    r"\b(in[\s\-]?progress|doing|wip|dev|development|implementation|building|review|"
    r"testing|qa|staging|uat|waiting|blocked|hold|on[\s\-]?hold|"
    r"sprint|to[\s\-]?test|verify|verification|validation|validated?)\b",
    re.IGNORECASE,
)


def classify_list(name: str) -> ListType:
    if _DONE_PAT.search(name):
        return ListType.DONE
    if _WIP_PAT.search(name):
        return ListType.WIP
    if _BACKLOG_PAT.search(name):
        return ListType.BACKLOG
    return ListType.UNKNOWN


class TrelloSyncService:
    """Orchestrates full and incremental Trello board syncs."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Public interface ───────────────────────────────────────────────────────

    async def full_sync(self, board: TrelloBoard, credential: TrelloCredential) -> TrelloBoardSyncedEvent:
        """
        Full sync: lists → cards → last 1 000 actions.
        Returns a domain event with sync stats.
        """
        t0 = time.monotonic()
        logger.info("trello_full_sync_start", board_id=board.id, trello_id=board.trello_id)

        async with TrelloClient(
            api_key=credential.api_key,
            api_token=credential.api_token,
        ) as client:
            api_board = await client.get_board(board.trello_id)
            lists = await client.get_board_lists(board.trello_id)
            cards = await client.get_board_cards(board.trello_id, include_closed=False)
            actions = await client.get_board_actions(board.trello_id)

        await self._upsert_board_metadata(board, api_board)
        list_map = await self._upsert_lists(board.id, lists)
        card_map = await self._upsert_cards(board.id, cards, list_map)
        actions_count = await self._process_actions(board.id, actions, list_map, card_map)

        # Record latest action id for incremental syncs
        if actions:
            board.last_action_id = actions[0].id   # newest first
        board.last_synced_at = datetime.now(UTC)
        await self._db.flush()

        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "trello_full_sync_done",
            board_id=board.id,
            cards=len(cards),
            actions=actions_count,
            ms=round(elapsed_ms),
        )

        return TrelloBoardSyncedEvent(
            board_id=board.id,
            board_name=board.name,
            cards_upserted=len(cards),
            actions_processed=actions_count,
            sync_duration_ms=elapsed_ms,
        )

    async def incremental_sync(
        self, board: TrelloBoard, credential: TrelloCredential
    ) -> TrelloBoardSyncedEvent:
        """
        Incremental: fetch only actions newer than last_action_id.
        Re-upserts only the affected cards.
        """
        t0 = time.monotonic()

        async with TrelloClient(
            api_key=credential.api_key,
            api_token=credential.api_token,
        ) as client:
            actions = await client.get_board_actions(
                board.trello_id, since=board.last_action_id
            )

        if not actions:
            board.last_synced_at = datetime.now(UTC)
            return TrelloBoardSyncedEvent(
                board_id=board.id,
                board_name=board.name,
                cards_upserted=0,
                actions_processed=0,
                sync_duration_ms=(time.monotonic() - t0) * 1000,
            )

        # Collect affected card IDs then refresh just those cards
        affected_trello_card_ids: set[str] = set()
        for action in actions:
            if action.data.card:
                affected_trello_card_ids.add(action.data.card.get("id", ""))

        list_map = await self._load_list_map(board.id)

        async with TrelloClient(
            api_key=credential.api_key,
            api_token=credential.api_token,
        ) as client:
            refreshed_cards: list[TrelloAPICard] = []
            for cid in affected_trello_card_ids:
                if not cid:
                    continue
                try:
                    card_data = await client._get(
                        f"/cards/{cid}",
                        fields="id,idShort,name,desc,idList,idBoard,idMembers,labels,due,dueComplete,closed,dateLastActivity",
                    )
                    refreshed_cards.append(TrelloAPICard.model_validate(card_data))
                except Exception:
                    pass  # card may have been deleted

        card_map = await self._upsert_cards(board.id, refreshed_cards, list_map)
        actions_count = await self._process_actions(board.id, actions, list_map, card_map)

        if actions:
            board.last_action_id = actions[0].id
        board.last_synced_at = datetime.now(UTC)
        await self._db.flush()

        elapsed_ms = (time.monotonic() - t0) * 1000
        return TrelloBoardSyncedEvent(
            board_id=board.id,
            board_name=board.name,
            cards_upserted=len(refreshed_cards),
            actions_processed=actions_count,
            sync_duration_ms=elapsed_ms,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _upsert_board_metadata(self, board: TrelloBoard, api_board: Any) -> None:
        board.name = api_board.name
        board.description = api_board.desc or None
        board.short_url = api_board.shortUrl or None
        board.is_closed = api_board.closed
        await self._db.flush()

    async def _upsert_lists(
        self, board_id: int, api_lists: list[TrelloAPIList]
    ) -> dict[str, int]:
        """Upsert lists; return {trello_list_id → db_list_id}."""
        if not api_lists:
            return {}

        stmt = pg_insert(TrelloList).values(
            [
                {
                    "board_id": board_id,
                    "trello_id": lst.id,
                    "name": lst.name,
                    "pos": lst.pos,
                    "is_closed": lst.closed,
                    # Persist lowercase enum values so Postgres receives
                    # the exact labels created by Alembic.
                    "list_type": classify_list(lst.name).value,
                }
                for lst in api_lists
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["trello_id"],
            set_={
                "name": stmt.excluded.name,
                "pos": stmt.excluded.pos,
                "is_closed": stmt.excluded.is_closed,
                "list_type": stmt.excluded.list_type,
            },
        ).returning(TrelloList.trello_id, TrelloList.id)

        result = await self._db.execute(stmt)
        return {row.trello_id: row.id for row in result.fetchall()}

    async def _load_list_map(self, board_id: int) -> dict[str, int]:
        rows = await self._db.execute(
            select(TrelloList.trello_id, TrelloList.id).where(TrelloList.board_id == board_id)
        )
        return {r.trello_id: r.id for r in rows.fetchall()}

    async def _upsert_cards(
        self,
        board_id: int,
        api_cards: list[TrelloAPICard],
        list_map: dict[str, int],
    ) -> dict[str, int]:
        """Upsert cards; return {trello_card_id → db_card_id}."""
        if not api_cards:
            return {}

        values = [
            {
                "board_id": board_id,
                "list_id": list_map.get(card.idList),
                "trello_id": card.id,
                "trello_short_id": card.idShort,
                "name": card.name,
                "description": card.desc or None,
                "member_ids": card.idMembers,
                "labels": [lbl.model_dump() for lbl in card.labels],
                "due_date": card.due,
                "due_complete": card.dueComplete,
                "is_closed": card.closed,
                "trello_last_activity": card.dateLastActivity,
            }
            for card in api_cards
        ]

        stmt = pg_insert(TrelloCard).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["trello_id"],
            set_={
                "list_id": stmt.excluded.list_id,
                "name": stmt.excluded.name,
                "description": stmt.excluded.description,
                "member_ids": stmt.excluded.member_ids,
                "labels": stmt.excluded.labels,
                "due_date": stmt.excluded.due_date,
                "due_complete": stmt.excluded.due_complete,
                "is_closed": stmt.excluded.is_closed,
                "trello_last_activity": stmt.excluded.trello_last_activity,
            },
        ).returning(TrelloCard.trello_id, TrelloCard.id)

        result = await self._db.execute(stmt)
        return {row.trello_id: row.id for row in result.fetchall()}

    async def _process_actions(
        self,
        board_id: int,
        actions: list[TrelloAPIAction],
        list_map: dict[str, int],
        card_map: dict[str, int],
    ) -> int:
        """Persist actions + extract card movements. Returns count processed."""
        if not actions:
            return 0

        action_rows = []
        movement_rows = []

        for action in actions:
            if action.type not in TRACKED_ACTION_TYPES:
                continue

            card_data = action.data.card or {}
            trello_card_id = card_data.get("id")
            db_card_id = card_map.get(trello_card_id) if trello_card_id else None

            action_rows.append(
                {
                    "card_id": db_card_id,
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

            # Extract card movements
            if (
                action.type == "updateCard"
                and action.data.listBefore
                and action.data.listAfter
                and db_card_id
            ):
                from_tid = action.data.listBefore.get("id")
                to_tid = action.data.listAfter.get("id")
                movement_rows.append(
                    {
                        "card_id": db_card_id,
                        "from_list_id": list_map.get(from_tid) if from_tid else None,
                        "to_list_id": list_map.get(to_tid) if to_tid else None,
                        "trello_action_id": action.id,
                        "moved_at": action.date,
                    }
                )

            # Record creation movement (createCard → sets entered_wip_at baseline)
            elif action.type == "createCard" and db_card_id:
                dest_tid = (action.data.list or {}).get("id")
                movement_rows.append(
                    {
                        "card_id": db_card_id,
                        "from_list_id": None,
                        "to_list_id": list_map.get(dest_tid) if dest_tid else None,
                        "trello_action_id": action.id,
                        "moved_at": action.date,
                    }
                )

        # Bulk upsert actions (idempotent)
        if action_rows:
            stmt = pg_insert(TrelloAction).values(action_rows)
            await self._db.execute(
                stmt.on_conflict_do_nothing(index_elements=["trello_action_id"])
            )

        # Bulk upsert movements (idempotent)
        if movement_rows:
            stmt = pg_insert(TrelloCardMovement).values(movement_rows)
            await self._db.execute(
                stmt.on_conflict_do_nothing(index_elements=["trello_action_id"])
            )

        # Back-fill trello_created_at on cards from createCard actions
        await self._backfill_card_created_at(card_map, actions)

        return len(action_rows)

    async def _backfill_card_created_at(
        self, card_map: dict[str, int], actions: list[TrelloAPIAction]
    ) -> None:
        for action in actions:
            if action.type != "createCard":
                continue
            card_data = action.data.card or {}
            trello_card_id = card_data.get("id")
            db_card_id = card_map.get(trello_card_id)
            if not db_card_id:
                continue
            await self._db.execute(
                update(TrelloCard)
                .where(TrelloCard.id == db_card_id, TrelloCard.trello_created_at.is_(None))
                .values(trello_created_at=action.date)
            )
