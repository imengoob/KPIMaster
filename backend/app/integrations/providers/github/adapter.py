from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.core.logging_config import get_logger
from app.integrations.base import (
    NormalizedBoard,
    NormalizedComment,
    NormalizedTask,
    ProviderType,
    TaskProvider,
)
from app.integrations.providers.github.client import GitHubClient

logger = get_logger(__name__)

_BLOCKED_LABELS = {"blocked", "blocker", "on hold", "impediment"}
_REVIEW_LABELS = {"review", "code review", "needs review", "in review"}
_TODO_LABELS = {"todo", "to do", "ready", "backlog"}
_PRIORITY_LABELS = {
    "priority: critical": "critical",
    "p0": "critical",
    "critical": "critical",
    "priority: high": "high",
    "p1": "high",
    "high": "high",
    "priority: medium": "medium",
    "p2": "medium",
    "medium": "medium",
    "priority: low": "low",
    "p3": "low",
    "low": "low",
}
_POINTS_RE = re.compile(r"^(?:story\s*)?points?\s*[:=]\s*(\d+(?:\.\d+)?)$", re.IGNORECASE)


class GitHubAdapter(TaskProvider):
    """Adapts GitHub repositories, issues, and pull requests to TaskProvider."""

    provider_type = ProviderType.GITHUB

    def __init__(self, access_token: str, account_id: int) -> None:
        self._account_id = account_id
        self._client = GitHubClient(access_token=access_token)

    async def validate_credentials(self) -> bool:
        return await self._client.validate()

    async def get_boards(self) -> list[NormalizedBoard]:
        repos = await self._client.get_repositories()
        return [self._map_repo(repo) for repo in repos if not repo.get("archived")]

    @staticmethod
    def _map_repo(raw: dict[str, Any]) -> NormalizedBoard:
        full_name = raw.get("full_name") or f"{raw.get('owner', {}).get('login', '')}/{raw.get('name', '')}"
        return NormalizedBoard(
            id=str(full_name),
            name=str(raw.get("name") or full_name),
            provider=ProviderType.GITHUB,
            url=raw.get("html_url"),
            is_active=not bool(raw.get("archived")),
            extra={
                "description": raw.get("description"),
                "full_name": full_name,
                "private": raw.get("private"),
                "fork": raw.get("fork"),
                "default_branch": raw.get("default_branch"),
            },
        )

    async def get_tasks(self, board_id: str) -> list[NormalizedTask]:
        owner, repo = _split_repo(board_id)
        issues = await self._client.get_issues(owner, repo)
        return [self._map_issue(item, board_id) for item in issues]

    @staticmethod
    def _map_issue(raw: dict[str, Any], board_id: str) -> NormalizedTask:
        labels = _label_names(raw)
        issue_number = raw.get("number")
        task_id = f"{board_id}#{issue_number}" if issue_number is not None else str(raw.get("id", ""))
        is_pr = "pull_request" in raw
        return NormalizedTask(
            id=task_id,
            title=str(raw.get("title") or "(no title)"),
            status=_status(raw, labels, is_pr),
            board_id=board_id,
            provider=ProviderType.GITHUB,
            description=raw.get("body") or None,
            priority=_priority(labels),
            task_type="pull_request" if is_pr else "issue",
            assignee_ids=_assignee_logins(raw),
            labels=labels,
            story_points=_story_points(labels),
            due_date=None,
            created_at=_parse_dt(raw.get("created_at")),
            updated_at=_parse_dt(raw.get("closed_at") or raw.get("updated_at")),
            raw=raw,
        )

    async def get_comments(self, task_id: str) -> list[NormalizedComment]:
        owner, repo, number = _split_task_id(task_id)
        raw_comments = await self._client.get_issue_comments(owner, repo, number)
        return [self._map_comment(comment, task_id) for comment in raw_comments]

    @staticmethod
    def _map_comment(raw: dict[str, Any], task_id: str) -> NormalizedComment:
        user = raw.get("user") or {}
        return NormalizedComment(
            id=str(raw.get("id") or ""),
            task_id=task_id,
            author_id=str(user.get("login") or user.get("id") or ""),
            author_name=str(user.get("login") or ""),
            body=str(raw.get("body") or ""),
            created_at=_parse_dt(raw.get("created_at")) or datetime.now(timezone.utc),
            provider=ProviderType.GITHUB,
        )

    async def create_task(self, board_id: str, data: dict[str, Any]) -> NormalizedTask:
        owner, repo = _split_repo(board_id)
        payload: dict[str, Any] = {"title": data.get("title", "New Issue")}
        if data.get("description"):
            payload["body"] = data["description"]
        if data.get("assignee_id"):
            payload["assignees"] = [data["assignee_id"]]
        labels = list(data.get("labels") or [])
        if data.get("priority"):
            labels.append(f"priority: {data['priority']}")
        if data.get("story_points") is not None:
            labels.append(f"points: {data['story_points']}")
        if labels:
            payload["labels"] = labels

        raw = await self._client.create_issue(owner, repo, payload)
        return self._map_issue(raw, board_id)

    async def update_task(self, task_id: str, data: dict[str, Any]) -> NormalizedTask:
        owner, repo, number = _split_task_id(task_id)
        payload: dict[str, Any] = {}
        if "title" in data:
            payload["title"] = data["title"]
        if "description" in data:
            payload["body"] = data["description"]
        if "status" in data:
            payload["state"] = "closed" if data["status"] in {"done", "cancelled"} else "open"
        if "assignee_id" in data:
            payload["assignees"] = [data["assignee_id"]] if data["assignee_id"] else []
        if "labels" in data:
            payload["labels"] = data["labels"] or []

        raw = await self._client.update_issue(owner, repo, number, payload)
        return self._map_issue(raw, f"{owner}/{repo}")

    async def sync_board(self, board_id: str) -> int:
        tasks = await self.get_tasks(board_id)
        logger.info("github.sync_complete", board_id=board_id, count=len(tasks))
        return len(tasks)

    async def close(self) -> None:
        await self._client.close()


def _split_repo(board_id: str) -> tuple[str, str]:
    if "/" not in board_id:
        raise ValueError("GitHub board_id must be in owner/repo format")
    owner, repo = board_id.split("/", 1)
    if not owner or not repo:
        raise ValueError("GitHub board_id must be in owner/repo format")
    return owner, repo


def _split_task_id(task_id: str) -> tuple[str, str, int]:
    if "#" not in task_id:
        raise ValueError("GitHub task_id must be in owner/repo#number format")
    board_id, number_raw = task_id.rsplit("#", 1)
    owner, repo = _split_repo(board_id)
    return owner, repo, int(number_raw)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _label_names(raw: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for label in raw.get("labels") or []:
        if isinstance(label, dict) and label.get("name"):
            out.append(str(label["name"]))
        elif isinstance(label, str):
            out.append(label)
    return out


def _label_set(labels: list[str]) -> set[str]:
    return {label.strip().lower() for label in labels}


def _status(raw: dict[str, Any], labels: list[str], is_pr: bool) -> str:
    lower = _label_set(labels)
    if lower & _BLOCKED_LABELS:
        return "blocked"
    if raw.get("state") == "closed":
        return "done"
    if lower & _REVIEW_LABELS or (is_pr and raw.get("draft") is False):
        return "in_review"
    if lower & _TODO_LABELS:
        return "todo"
    return "in_progress" if is_pr else "todo"


def _priority(labels: list[str]) -> str | None:
    lower = _label_set(labels)
    for label, priority in _PRIORITY_LABELS.items():
        if label in lower:
            return priority
    return None


def _story_points(labels: list[str]) -> float | None:
    for label in labels:
        match = _POINTS_RE.match(label.strip())
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
    return None


def _assignee_logins(raw: dict[str, Any]) -> list[str]:
    assignees = raw.get("assignees") or []
    out = [str(item.get("login")) for item in assignees if isinstance(item, dict) and item.get("login")]
    if out:
        return out
    assignee = raw.get("assignee")
    if isinstance(assignee, dict) and assignee.get("login"):
        return [str(assignee["login"])]
    return []

