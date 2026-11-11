"""
Jira → TaskProvider adapter.

Responsibilities
────────────────
  1. Map Jira projects / boards to NormalizedBoard
  2. Map Jira issues to NormalizedTask (status, priority, task_type normalization)
  3. Map Jira comments to NormalizedComment
  4. Implement create_task / update_task (translate normalized → Jira payload)
  5. sync_board — full JQL sweep of one project and upsert to DB (via JiraSyncService)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.integrations.base import (
    NormalizedBoard,
    NormalizedComment,
    NormalizedTask,
    ProviderType,
    TaskProvider,
)
from app.integrations.providers.jira.client import JiraClient
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# ── Status normalization ──────────────────────────────────────────────────────
# Jira status category → our status. The category is more reliable than the
# display name (which varies per project workflow).
_JIRA_CATEGORY_MAP: dict[str, str] = {
    "new":           "todo",
    "indeterminate": "in_progress",
    "done":          "done",
}

_JIRA_STATUS_NAME_MAP: dict[str, str] = {
    "backlog":     "backlog",
    "to do":       "todo",
    "in progress": "in_progress",
    "in review":   "in_review",
    "code review": "in_review",
    "done":        "done",
    "resolved":    "done",
    "closed":      "done",
    "blocked":     "blocked",
    "on hold":     "blocked",
    "cancelled":   "cancelled",
}

# ── Priority normalization ────────────────────────────────────────────────────
_JIRA_PRIORITY_MAP: dict[str, str] = {
    "highest": "critical",
    "high":    "high",
    "medium":  "medium",
    "low":     "low",
    "lowest":  "low",
}

# ── Issue type → task_type ────────────────────────────────────────────────────
_JIRA_TYPE_MAP: dict[str, str] = {
    "story":       "story",
    "bug":         "bug",
    "epic":        "epic",
    "task":        "task",
    "sub-task":    "task",
    "subtask":     "task",
    "feature":     "feature",
    "improvement": "feature",
    "technical debt": "task",
    "spike":       "investigation",
}

# ── Story points: common Jira custom field IDs ───────────────────────────────
_SP_FIELDS = ["story_points", "customfield_10016", "customfield_10028", "customfield_10014"]


def _normalize_status(fields: dict[str, Any]) -> str:
    status_obj = fields.get("status", {})
    category   = (status_obj.get("statusCategory", {}).get("key", "") or "").lower()
    if category in _JIRA_CATEGORY_MAP:
        return _JIRA_CATEGORY_MAP[category]
    name = (status_obj.get("name", "") or "").lower()
    for key, val in _JIRA_STATUS_NAME_MAP.items():
        if key in name:
            return val
    return "todo"


def _normalize_priority(fields: dict[str, Any]) -> str:
    name = (fields.get("priority", {}) or {}).get("name", "medium") or "medium"
    return _JIRA_PRIORITY_MAP.get(name.lower(), "medium")


def _normalize_type(fields: dict[str, Any]) -> str:
    name = (fields.get("issuetype", {}) or {}).get("name", "task") or "task"
    return _JIRA_TYPE_MAP.get(name.lower(), "task")


def _extract_story_points(fields: dict[str, Any]) -> float | None:
    for field in _SP_FIELDS:
        val = fields.get(field)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _assignee_ids(fields: dict[str, Any]) -> list[str]:
    assignee = fields.get("assignee")
    if assignee and isinstance(assignee, dict):
        aid = assignee.get("accountId")
        if aid:
            return [aid]
    return []


def _labels(fields: dict[str, Any]) -> list[str]:
    return [str(lbl) for lbl in fields.get("labels", []) if lbl]


# ── Adapter ───────────────────────────────────────────────────────────────────

class JiraAdapter(TaskProvider):
    """Adapts Jira Cloud to the unified TaskProvider interface."""

    provider_type = ProviderType.JIRA

    def __init__(
        self,
        access_token:  str,
        cloud_id:      str,
        account_id:    int,
        refresh_token: str | None = None,
    ) -> None:
        self._account_id = account_id
        self._client = JiraClient(
            access_token=access_token,
            cloud_id=cloud_id,
            refresh_cb=self._make_refresh_cb(refresh_token, cloud_id),
        )

    # ── Credentials ──────────────────────────────────────────────────────────

    async def validate_credentials(self) -> bool:
        return await self._client.validate()

    # ── Boards ───────────────────────────────────────────────────────────────

    async def get_boards(self) -> list[NormalizedBoard]:
        try:
            boards = await self._client.get_boards()
            return [self._map_board(b) for b in boards]
        except Exception:
            # Agile board API might not be available; fall back to projects
            projects = await self._client.get_projects()
            return [self._map_project(p) for p in projects]

    @staticmethod
    def _map_board(raw: dict[str, Any]) -> NormalizedBoard:
        return NormalizedBoard(
            id=str(raw["id"]),
            name=raw.get("name", f"Board {raw['id']}"),
            provider=ProviderType.JIRA,
            url=raw.get("self"),
            extra={"type": raw.get("type", "scrum"), "location": raw.get("location", {})},
        )

    @staticmethod
    def _map_project(raw: dict[str, Any]) -> NormalizedBoard:
        return NormalizedBoard(
            id=raw["key"],
            name=raw.get("name", raw["key"]),
            provider=ProviderType.JIRA,
            url=raw.get("self"),
            extra={"project_type": raw.get("projectTypeKey", "software")},
        )

    # ── Tasks ─────────────────────────────────────────────────────────────────

    async def get_tasks(self, board_id: str) -> list[NormalizedTask]:
        jql = f'project = "{board_id}" AND statusCategory != Done ORDER BY updated DESC'
        issues = await self._client.search_issues(jql)
        return [self._map_issue(issue, board_id) for issue in issues]

    @staticmethod
    def _map_issue(raw: dict[str, Any], board_id: str) -> NormalizedTask:
        fields = raw.get("fields", {})
        return NormalizedTask(
            id=str(raw["id"]),
            title=fields.get("summary", "(no title)"),
            status=_normalize_status(fields),
            board_id=board_id,
            provider=ProviderType.JIRA,
            description=fields.get("description") or None,
            priority=_normalize_priority(fields),
            task_type=_normalize_type(fields),
            assignee_ids=_assignee_ids(fields),
            labels=_labels(fields),
            story_points=_extract_story_points(fields),
            due_date=_parse_dt(fields.get("duedate")),
            created_at=_parse_dt(fields.get("created")),
            updated_at=_parse_dt(fields.get("updated")),
            raw=raw,
        )

    # ── Comments ──────────────────────────────────────────────────────────────

    async def get_comments(self, task_id: str) -> list[NormalizedComment]:
        raw_comments = await self._client.get_comments(task_id)
        return [self._map_comment(c, task_id) for c in raw_comments]

    @staticmethod
    def _map_comment(raw: dict[str, Any], task_id: str) -> NormalizedComment:
        author = raw.get("author", {})
        body_obj = raw.get("body", {})
        # Jira uses Atlassian Document Format (ADF); extract plain text
        body_text = _adf_to_text(body_obj) if isinstance(body_obj, dict) else str(body_obj)
        return NormalizedComment(
            id=str(raw.get("id", "")),
            task_id=task_id,
            author_id=author.get("accountId", ""),
            author_name=author.get("displayName", ""),
            body=body_text,
            created_at=_parse_dt(raw.get("created")) or datetime.now(timezone.utc),
            provider=ProviderType.JIRA,
        )

    # ── Create / Update ───────────────────────────────────────────────────────

    async def create_task(self, board_id: str, data: dict[str, Any]) -> NormalizedTask:
        payload = {
            "fields": {
                "project":   {"key": board_id},
                "summary":   data.get("title", "New Task"),
                "issuetype": {"name": _task_type_to_jira(data.get("task_type", "task"))},
            }
        }
        if data.get("description"):
            payload["fields"]["description"] = {"type": "doc", "version": 1,
                "content": [{"type": "paragraph",
                             "content": [{"type": "text", "text": data["description"]}]}]}
        if data.get("priority"):
            payload["fields"]["priority"] = {"name": _priority_to_jira(data["priority"])}
        if data.get("assignee_id"):
            payload["fields"]["assignee"] = {"accountId": data["assignee_id"]}
        if data.get("story_points") is not None:
            payload["fields"]["customfield_10016"] = data["story_points"]
        if data.get("labels"):
            payload["fields"]["labels"] = data["labels"]

        created = await self._client.create_issue(payload)
        # Fetch full issue back for consistent normalized output
        full = await self._client.get_issue(created["key"])
        return self._map_issue(full, board_id)

    async def update_task(self, task_id: str, data: dict[str, Any]) -> NormalizedTask:
        fields: dict[str, Any] = {}
        if "title" in data:
            fields["summary"] = data["title"]
        if "description" in data:
            fields["description"] = {"type": "doc", "version": 1,
                "content": [{"type": "paragraph",
                             "content": [{"type": "text", "text": data["description"]}]}]}
        if "priority" in data:
            fields["priority"] = {"name": _priority_to_jira(data["priority"])}
        if "assignee_id" in data:
            fields["assignee"] = {"accountId": data["assignee_id"]}
        if "story_points" in data:
            fields["customfield_10016"] = data["story_points"]
        if "labels" in data:
            fields["labels"] = data["labels"]
        if "status" in data:
            logger.warning("jira.update_task", note="status transitions require a separate transition call")

        if fields:
            await self._client.update_issue(task_id, {"fields": fields})

        full = await self._client.get_issue(task_id)
        board_id = full.get("fields", {}).get("project", {}).get("key", "")
        return self._map_issue(full, board_id)

    # ── Sync ─────────────────────────────────────────────────────────────────

    async def sync_board(self, board_id: str) -> int:
        """Full sync: pull all open issues and return count."""
        tasks = await self.get_tasks(board_id)
        logger.info("jira.sync_complete", board_id=board_id, count=len(tasks))
        return len(tasks)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._client.close()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _make_refresh_cb(self, refresh_token: str | None, cloud_id: str):
        if not refresh_token:
            return None

        async def _refresh() -> str:
            from app.integrations.oauth.jira import get_jira_oauth
            from app.config import settings
            oauth  = get_jira_oauth()
            tokens = await oauth.refresh_access_token(refresh_token)
            self._client._token = tokens.access_token
            logger.info("jira.token_refreshed", account_id=self._account_id)
            return tokens.access_token

        return _refresh


# ── Helpers ───────────────────────────────────────────────────────────────────

def _adf_to_text(adf: dict[str, Any]) -> str:
    """Recursively extract plain text from Atlassian Document Format."""
    texts: list[str] = []
    for node in adf.get("content", []):
        if node.get("type") == "text":
            texts.append(node.get("text", ""))
        elif "content" in node:
            texts.append(_adf_to_text(node))
    return " ".join(texts).strip()


def _priority_to_jira(normalized: str) -> str:
    return {"critical": "Highest", "high": "High", "medium": "Medium", "low": "Low"}.get(
        normalized, "Medium"
    )


def _task_type_to_jira(normalized: str) -> str:
    return {
        "bug":           "Bug",
        "story":         "Story",
        "epic":          "Epic",
        "feature":       "Story",
        "investigation": "Task",
        "task":          "Task",
    }.get(normalized, "Task")
