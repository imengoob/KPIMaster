"""
Trello → TaskProvider adapter.

Wraps the existing TrelloClient so Trello fits into the unified TaskProvider
interface without duplicating any sync logic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.integrations.base import (
    NormalizedBoard,
    NormalizedComment,
    NormalizedTask,
    ProviderType,
    TaskProvider,
)
from app.core.logging_config import get_logger

logger = get_logger(__name__)

_TRELLO_LABEL_PRIORITY: dict[str, str] = {
    "red":    "critical",
    "orange": "high",
    "yellow": "medium",
    "green":  "low",
    "blue":   "medium",
    "purple": "medium",
}

# TrelloList.list_type (enum set by sync_service) → normalized status
_LIST_TYPE_STATUS: dict[str, str] = {
    "backlog": "backlog",
    "wip":     "in_progress",
    "done":    "done",
    "unknown": "backlog",
}


def _label_priority(labels: list[Any]) -> str | None:
    """Pick the highest-severity label color as the task priority."""
    for label in labels:
        color = (getattr(label, "color", None) or (label.get("color") if isinstance(label, dict) else None) or "").lower()
        if color in _TRELLO_LABEL_PRIORITY:
            return _TRELLO_LABEL_PRIORITY[color]
    return None


class TrelloAdapter(TaskProvider):
    """Adapts the existing Trello integration to the unified TaskProvider interface."""

    provider_type = ProviderType.TRELLO

    def __init__(self, api_key: str, api_token: str, account_id: int) -> None:
        from app.services.trello.client import TrelloClient
        self._account_id = account_id
        self._api_key    = api_key
        self._api_token  = api_token
        self._client     = TrelloClient(api_key=api_key, api_token=api_token)

    # ── Credentials ──────────────────────────────────────────────────────────

    async def validate_credentials(self) -> bool:
        try:
            await self._client.get_me()
            return True
        except Exception:
            return False

    # ── Boards ───────────────────────────────────────────────────────────────

    async def get_boards(self) -> list[NormalizedBoard]:
        boards = await self._client.get_my_boards()
        return [
            NormalizedBoard(
                id=b.id,
                name=b.name,
                provider=ProviderType.TRELLO,
                url=b.shortUrl,
                is_active=not b.closed,
                extra={"shortUrl": b.shortUrl},
            )
            for b in boards
            if not b.closed
        ]

    # ── Tasks ─────────────────────────────────────────────────────────────────

    async def get_tasks(self, board_id: str) -> list[NormalizedTask]:
        cards = await self._client.get_board_cards(board_id)
        lists = await self._client.get_board_lists(board_id)
        # Build id → list mapping (TrelloAPIList objects)
        list_map = {lst.id: lst for lst in lists}
        return [self._map_card(c, list_map, board_id) for c in cards]

    @staticmethod
    def _map_card(raw: Any, list_map: dict[str, Any], board_id: str) -> NormalizedTask:
        lst       = list_map.get(raw.idList)
        # TrelloAPIList has no list_type at this layer (that's in the DB model).
        # Default to in_progress if it's a non-closed card in any WIP-ish list.
        list_name = (lst.name if lst else "").lower()
        if any(kw in list_name for kw in ("done", "complete", "finished", "deployed")):
            status = "done"
        elif any(kw in list_name for kw in ("backlog", "todo", "to do", "ready", "icebox")):
            status = "backlog"
        else:
            status = "in_progress"

        labels      = raw.labels or []
        label_names = [lbl.name for lbl in labels if lbl.name]

        due_dt: datetime | None = None
        if raw.due:
            try:
                due_dt = datetime.fromisoformat(raw.due.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return NormalizedTask(
            id=raw.id,
            title=raw.name,
            status=status,
            board_id=board_id,
            provider=ProviderType.TRELLO,
            description=raw.desc or None,
            priority=_label_priority(labels),
            task_type="task",
            assignee_ids=raw.idMembers or [],
            labels=label_names,
            due_date=due_dt,
            created_at=None,
            updated_at=None,
        )

    # ── Comments ─────────────────────────────────────────────────────────────

    async def get_comments(self, task_id: str) -> list[NormalizedComment]:
        actions = await self._client.get_card_actions(task_id)
        out: list[NormalizedComment] = []
        for a in actions:
            if a.type != "commentCard":
                continue
            data    = a.data or {}
            text    = data.get("text") or (data.get("comment", {}) or {}).get("text", "")
            creator = a.memberCreator
            date_s  = a.date or ""
            try:
                created = datetime.fromisoformat(date_s.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                created = datetime.now(timezone.utc)
            out.append(
                NormalizedComment(
                    id=a.id,
                    task_id=task_id,
                    author_id=creator.id if creator else "",
                    author_name=(creator.fullName or creator.username or "") if creator else "",
                    body=text,
                    created_at=created,
                    provider=ProviderType.TRELLO,
                )
            )
        return out

    # ── Create / Update ───────────────────────────────────────────────────────

    async def create_task(self, board_id: str, data: dict[str, Any]) -> NormalizedTask:
        lists = await self._client.get_board_lists(board_id)
        # Pick the first non-done list as the target
        target = next(
            (l for l in lists if not any(kw in l.name.lower()
             for kw in ("done", "complete", "finished"))),
            lists[0] if lists else None,
        )
        if not target:
            raise RuntimeError(f"No lists found on board {board_id}")

        raw = await self._client._post(
            "/cards",
            json={
                "idList": target.id,
                "name":   data.get("title", "New Task"),
                "desc":   data.get("description", ""),
                "due":    data.get("due_date"),
            },
        )
        list_map = {l.id: l for l in lists}
        return self._map_card(_DictView(raw), list_map, board_id)

    async def update_task(self, task_id: str, data: dict[str, Any]) -> NormalizedTask:
        payload: dict[str, Any] = {}
        if "title" in data:
            payload["name"] = data["title"]
        if "description" in data:
            payload["desc"] = data["description"]
        if "due_date" in data:
            payload["due"] = data["due_date"]

        await self._client._post(f"/cards/{task_id}", json=payload)
        raw_card  = await self._client._get(f"/cards/{task_id}")
        board_id  = raw_card.get("idBoard", "")
        lists     = await self._client.get_board_lists(board_id)
        list_map  = {l.id: l for l in lists}
        return self._map_card(_DictView(raw_card), list_map, board_id)

    # ── Sync ─────────────────────────────────────────────────────────────────

    async def sync_board(self, board_id: str) -> int:
        tasks = await self.get_tasks(board_id)
        logger.info("trello.adapter_sync", board_id=board_id, count=len(tasks))
        return len(tasks)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._client.close()


class _DictView:
    """Lightweight wrapper so dict-based raw responses work with _map_card."""
    def __init__(self, d: dict[str, Any]) -> None:
        self._d = d

    def __getattr__(self, name: str) -> Any:
        return self._d.get(name)
