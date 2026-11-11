"""
Microsoft Graph (Planner) → TaskProvider adapter.

Maps Microsoft Planner plans → NormalizedBoard,
and Planner tasks → NormalizedTask.

Status logic
────────────
  Planner uses a percentComplete (0–100) integer with no canonical status
  enum.  We map it as:
    0              → todo
    1–99           → in_progress
    100            → done
  Additionally the task `appliedCategories` labels can signal "Blocked".
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
from app.integrations.providers.microsoft.client import MicrosoftGraphClient
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Category labels that map to "blocked" status
_BLOCKED_LABELS = {"blocked", "blocker", "on hold", "impediment"}

# Planner priority: 0=Urgent, 1=Important, 3=Medium, 5=Low, 9=None
_MS_PRIORITY_MAP: dict[int, str] = {
    0: "critical",
    1: "high",
    2: "high",
    3: "medium",
    4: "medium",
    5: "low",
    9: "low",
}


def _ms_status(pct: int, category_labels: list[str]) -> str:
    labels_lower = [l.lower() for l in category_labels]
    if any(bl in labels_lower for bl in _BLOCKED_LABELS):
        return "blocked"
    if pct == 0:
        return "todo"
    if pct == 100:
        return "done"
    return "in_progress"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _extract_labels(applied_categories: dict[str, bool] | None) -> list[str]:
    """Planner appliedCategories is {category1: True, category2: False, ...}"""
    if not applied_categories:
        return []
    return [k for k, v in applied_categories.items() if v]


class MicrosoftAdapter(TaskProvider):
    """Adapts Microsoft Planner to the unified TaskProvider interface."""

    provider_type = ProviderType.MICROSOFT

    def __init__(
        self,
        access_token:  str,
        account_id:    int,
        refresh_token: str | None = None,
        tenant_id:     str = "common",
    ) -> None:
        self._account_id = account_id
        self._tenant_id  = tenant_id
        self._client = MicrosoftGraphClient(
            access_token=access_token,
            refresh_cb=self._make_refresh_cb(refresh_token),
        )

    # ── Credentials ──────────────────────────────────────────────────────────

    async def validate_credentials(self) -> bool:
        return await self._client.validate()

    # ── Boards (Planner Plans) ────────────────────────────────────────────────

    async def get_boards(self) -> list[NormalizedBoard]:
        plans = await self._client.get_my_plans()
        return [self._map_plan(p) for p in plans]

    @staticmethod
    def _map_plan(raw: dict[str, Any]) -> NormalizedBoard:
        return NormalizedBoard(
            id=raw["id"],
            name=raw.get("title", f"Plan {raw['id']}"),
            provider=ProviderType.MICROSOFT,
            url=None,
            extra={
                "owner":   raw.get("owner"),
                "created": raw.get("createdDateTime"),
            },
        )

    # ── Tasks (Planner Tasks) ─────────────────────────────────────────────────

    async def get_tasks(self, board_id: str) -> list[NormalizedTask]:
        raw_tasks = await self._client.get_plan_tasks(board_id)
        return [self._map_task(t, board_id) for t in raw_tasks]

    @staticmethod
    def _map_task(raw: dict[str, Any], board_id: str) -> NormalizedTask:
        pct        = raw.get("percentComplete", 0)
        categories = _extract_labels(raw.get("appliedCategories"))
        assignees  = list((raw.get("assignments") or {}).keys())
        priority   = raw.get("priority", 5)
        due_raw    = raw.get("dueDateTime")

        return NormalizedTask(
            id=raw["id"],
            title=raw.get("title", "(no title)"),
            status=_ms_status(pct, categories),
            board_id=board_id,
            provider=ProviderType.MICROSOFT,
            priority=_MS_PRIORITY_MAP.get(int(priority), "medium"),
            task_type="task",
            assignee_ids=assignees,
            labels=categories,
            due_date=_parse_dt(due_raw),
            created_at=_parse_dt(raw.get("createdDateTime")),
            updated_at=None,  # Planner doesn't expose updatedDateTime at task level
            raw=raw,
        )

    # ── Comments ─────────────────────────────────────────────────────────────

    async def get_comments(self, task_id: str) -> list[NormalizedComment]:
        """
        Planner doesn't have a native comments API.
        Task details include a description but no threaded comments.
        Return empty list — override in subclass if using Teams conversation.
        """
        return []

    # ── Create Task ───────────────────────────────────────────────────────────

    async def create_task(self, board_id: str, data: dict[str, Any]) -> NormalizedTask:
        """
        POST /planner/tasks
        Required: planId, title
        Optional: dueDateTime, assignments (dict of userId → assignment obj), priority
        """
        payload: dict[str, Any] = {
            "planId": board_id,
            "title":  data.get("title", "New Task"),
        }
        if data.get("due_date"):
            payload["dueDateTime"] = data["due_date"].isoformat() if isinstance(
                data["due_date"], datetime
            ) else data["due_date"]

        if data.get("assignee_id"):
            payload["assignments"] = {
                data["assignee_id"]: {
                    "@odata.type":      "#microsoft.graph.plannerAssignment",
                    "orderHint":        " !",
                }
            }
        if data.get("priority"):
            reverse = {"critical": 0, "high": 1, "medium": 3, "low": 5}
            payload["priority"] = reverse.get(data["priority"], 3)

        raw = await self._client.create_task(payload)
        return self._map_task(raw, board_id)

    # ── Update Task ───────────────────────────────────────────────────────────

    async def update_task(self, task_id: str, data: dict[str, Any]) -> NormalizedTask:
        """
        PATCH /planner/tasks/{taskId}
        Planner requires the If-Match ETag — fetch the task first to get it.
        """
        current = await self._client.get_task(task_id)
        etag    = current.get("@odata.etag", "*")

        payload: dict[str, Any] = {}
        if "title" in data:
            payload["title"] = data["title"]
        if "status" in data:
            pct_map = {
                "todo": 0, "backlog": 0, "in_progress": 50,
                "in_review": 75, "done": 100, "blocked": 0,
            }
            payload["percentComplete"] = pct_map.get(data["status"], 0)
        if "priority" in data:
            reverse = {"critical": 0, "high": 1, "medium": 3, "low": 5}
            payload["priority"] = reverse.get(data["priority"], 3)
        if "due_date" in data:
            payload["dueDateTime"] = (
                data["due_date"].isoformat()
                if isinstance(data["due_date"], datetime)
                else data["due_date"]
            )
        if "assignee_id" in data:
            payload["assignments"] = {
                data["assignee_id"]: {
                    "@odata.type": "#microsoft.graph.plannerAssignment",
                    "orderHint":   " !",
                }
            }

        if payload:
            board_id = current.get("planId", "")
            updated = await self._client.update_task(task_id, etag, payload)
            return self._map_task(updated, board_id)

        board_id = current.get("planId", "")
        return self._map_task(current, board_id)

    # ── Sync ─────────────────────────────────────────────────────────────────

    async def sync_board(self, board_id: str) -> int:
        tasks = await self.get_tasks(board_id)
        logger.info("microsoft.sync_complete", board_id=board_id, count=len(tasks))
        return len(tasks)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._client.close()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _make_refresh_cb(self, refresh_token: str | None):
        if not refresh_token:
            return None

        async def _refresh() -> str:
            from app.integrations.oauth.microsoft import get_microsoft_oauth
            oauth  = get_microsoft_oauth()
            tokens = await oauth.refresh_access_token(refresh_token)
            self._client._token = tokens.access_token
            logger.info("microsoft.token_refreshed", account_id=self._account_id)
            return tokens.access_token

        return _refresh
