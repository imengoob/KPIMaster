"""
Pydantic request/response schemas for the integrations API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Provider enum (string literal) ───────────────────────────────────────────

ProviderLiteral = Literal["jira", "microsoft", "trello", "github"]


# ── Request schemas ───────────────────────────────────────────────────────────

class ConnectTrelloRequest(BaseModel):
    api_key:   str = Field(..., min_length=1, description="Trello API key")
    api_token: str = Field(..., min_length=1, description="Trello API token")
    label:     str = Field("Trello", description="Friendly name for this connection")


class ConnectGitHubRequest(BaseModel):
    access_token: str = Field(..., min_length=1, description="GitHub personal access token")
    label:        str = Field("GitHub", description="Friendly name for this connection")


class OAuthCallbackRequest(BaseModel):
    code:  str
    state: str


class CreateTaskRequest(BaseModel):
    provider:   ProviderLiteral
    account_id: int
    board_id:   str
    title:      str
    description: str | None = None
    priority:   Literal["low", "medium", "high", "critical"] | None = None
    task_type:  str | None = None
    assignee_id: str | None = None
    labels:     list[str] = Field(default_factory=list)
    story_points: float | None = None
    due_date:   datetime | None = None


class UpdateTaskRequest(BaseModel):
    provider:   ProviderLiteral
    account_id: int
    title:      str | None = None
    description: str | None = None
    status:     str | None = None
    priority:   str | None = None
    assignee_id: str | None = None
    labels:     list[str] | None = None
    story_points: float | None = None
    due_date:   datetime | None = None


# ── Response schemas ──────────────────────────────────────────────────────────

class IntegrationAccountResponse(BaseModel):
    id:                   int
    user_id:              int
    provider:             str
    account_name:         str
    external_account_id:  str
    is_active:            bool
    last_sync_at:         datetime | None
    token_expires_at:     datetime | None
    scopes:               list[str]
    extra_data:           dict[str, Any]
    created_at:           datetime
    updated_at:           datetime

    model_config = {"from_attributes": True}


class SyncLogResponse(BaseModel):
    id:           int
    account_id:   int
    provider:     str
    board_id:     str | None
    sync_type:    str
    status:       str
    items_synced: int
    errors_count: int
    error_detail: str | None
    started_at:   datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class NormalizedBoardResponse(BaseModel):
    id:        str
    name:      str
    provider:  str
    url:       str | None
    is_active: bool
    extra:     dict[str, Any]


class NormalizedTaskResponse(BaseModel):
    id:           str
    title:        str
    status:       str
    board_id:     str
    provider:     str
    description:  str | None
    priority:     str | None
    task_type:    str
    assignee_ids: list[str]
    labels:       list[str]
    story_points: float | None
    due_date:     datetime | None
    created_at:   datetime | None
    updated_at:   datetime | None


class OAuthInitResponse(BaseModel):
    authorization_url: str
    state:             str
    provider:          str


class SyncResultResponse(BaseModel):
    account_id:  int
    board_id:    str
    provider:    str
    synced:      int
    incremental: bool


class ProviderHealthResponse(BaseModel):
    account_id:      int
    provider:        str
    account_name:    str
    is_active:       bool
    credentials_ok:  bool
    last_sync_at:    datetime | None
    token_expires_at: datetime | None


class ImportedProjectResponse(BaseModel):
    project_id:   int
    project_key:  str
    board_id:     str
    board_name:   str
