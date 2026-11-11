from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import OrmBase

ActionStatus = Literal[
    "open",
    "acknowledged",
    "in_progress",
    "awaiting_approval",
    "approved",
    "rejected",
    "resolved",
    "dismissed",
]

ActionPriority = Literal["low", "medium", "high", "critical"]


class ActionEventResponse(OrmBase):
    id: int
    action_item_id: int
    actor_user_id: int | None
    event_type: str
    previous_status: str | None
    next_status: str | None
    note: str | None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ActionItemResponse(OrmBase):
    id: int
    project_id: int
    source_type: str
    source_id: str
    source_url: str | None
    title: str
    description: str | None
    recommended_action: str
    priority: str
    owner_user_id: int | None
    owner_role: str | None
    status: str
    approval_required: bool
    due_at: datetime | None
    resolved_at: datetime | None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ActionItemDetailResponse(ActionItemResponse):
    events: list[ActionEventResponse] = Field(default_factory=list)


class ActionItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    recommended_action: str | None = None
    priority: ActionPriority | None = None
    owner_user_id: int | None = None
    owner_role: str | None = None
    status: ActionStatus | None = None
    approval_required: bool | None = None
    due_at: datetime | None = None
    note: str | None = None


class ActionNoteRequest(BaseModel):
    note: str | None = None


class ActionGenerationResponse(BaseModel):
    project_id: int
    generated: int
    refreshed: int
    total_open: int
    action_ids: list[int]

