"""
Abstract TaskProvider interface + normalized data models.

Every provider adapter (Jira, Microsoft, Trello) implements TaskProvider.
All external data is mapped to these normalized dataclasses before any
internal service touches it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# ─── Provider identity ────────────────────────────────────────────────────────

class ProviderType(str, Enum):
    TRELLO    = "trello"
    JIRA      = "jira"
    MICROSOFT = "microsoft"
    GITHUB    = "github"


# ─── Normalized data models ───────────────────────────────────────────────────

@dataclass
class NormalizedBoard:
    """Represents a project / board / plan across providers."""
    id:        str
    name:      str
    provider:  ProviderType
    url:       str | None = None
    is_active: bool = True
    extra:     dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedTask:
    """
    Normalized representation of a Jira issue / Trello card / Planner task.

    Status values (normalized):
      backlog | todo | in_progress | in_review | done | blocked | cancelled

    Priority values (normalized):
      low | medium | high | critical

    task_type values (normalized):
      feature | bug | task | story | epic | investigation
    """
    id:          str
    title:       str
    status:      str
    board_id:    str
    provider:    ProviderType

    description:    str | None = None
    priority:       str | None = None
    task_type:      str = "task"
    assignee_ids:   list[str] = field(default_factory=list)
    labels:         list[str] = field(default_factory=list)
    story_points:   float | None = None
    due_date:       datetime | None = None
    created_at:     datetime | None = None
    updated_at:     datetime | None = None
    # Original provider payload — stored for audit/debugging
    raw:            dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedComment:
    """A single comment/activity on a task."""
    id:          str
    task_id:     str
    author_id:   str
    author_name: str
    body:        str
    created_at:  datetime
    provider:    ProviderType


@dataclass
class OAuthTokens:
    """Tokens returned after completing an OAuth2 flow."""
    access_token:  str
    refresh_token: str | None
    expires_at:    datetime | None
    scopes:        list[str] = field(default_factory=list)
    # Provider-specific extras (e.g., Jira cloud_id, MS tenant_id)
    extra:         dict[str, Any] = field(default_factory=dict)


# ─── Abstract provider interface ──────────────────────────────────────────────

class TaskProvider(ABC):
    """
    Unified interface all integration adapters must implement.

    Each adapter is initialised with decrypted credentials from
    IntegrationAccount and a configured httpx.AsyncClient.
    """

    provider_type: ProviderType

    # ── Credentials ──────────────────────────────────────────────────────────

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """Return True if stored credentials are still valid (cheap probe)."""

    # ── Read ─────────────────────────────────────────────────────────────────

    @abstractmethod
    async def get_boards(self) -> list[NormalizedBoard]:
        """List all accessible boards/projects/plans."""

    @abstractmethod
    async def get_tasks(self, board_id: str) -> list[NormalizedTask]:
        """Return all non-archived tasks for a board."""

    @abstractmethod
    async def get_comments(self, task_id: str) -> list[NormalizedComment]:
        """Fetch comments/activity for a task."""

    # ── Write ────────────────────────────────────────────────────────────────

    @abstractmethod
    async def create_task(self, board_id: str, data: dict[str, Any]) -> NormalizedTask:
        """
        Create a task.  Recognised keys in `data`:
          title, description, priority, assignee_id, labels, story_points, due_date
        """

    @abstractmethod
    async def update_task(self, task_id: str, data: dict[str, Any]) -> NormalizedTask:
        """Update task fields. Only provided keys are changed."""

    # ── Sync ─────────────────────────────────────────────────────────────────

    @abstractmethod
    async def sync_board(self, board_id: str) -> int:
        """Full sync of one board. Returns count of upserted tasks."""

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Optional cleanup (close HTTP clients, release connections)."""
