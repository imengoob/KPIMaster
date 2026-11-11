"""
Trello schemas — three groups:

1. TrelloAPI*   — raw shapes returned by Trello REST API (snake_case aliases)
2. Trello*      — internal read models returned by our API
3. TrelloAnalytics* — analytics results
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, AliasPath, model_validator

from app.models.trello_list import ListType


# ─────────────────────────────────────────────────────────────────────────────
# 1. Raw Trello API response shapes
# ─────────────────────────────────────────────────────────────────────────────

class TrelloAPILabel(BaseModel):
    id: str
    name: str
    color: str | None = None


class TrelloAPIMember(BaseModel):
    id: str
    fullName: str
    username: str
    avatarUrl: str | None = None


class TrelloAPIList(BaseModel):
    id: str
    name: str
    closed: bool = False
    pos: float = 0.0
    idBoard: str


class TrelloAPICard(BaseModel):
    id: str
    idShort: int
    name: str
    desc: str = ""
    idList: str
    idBoard: str
    idMembers: list[str] = Field(default_factory=list)
    labels: list[TrelloAPILabel] = Field(default_factory=list)
    due: datetime | None = None
    dueComplete: bool = False
    closed: bool = False
    dateLastActivity: datetime | None = None


class TrelloAPIBoard(BaseModel):
    id: str
    name: str
    desc: str = ""
    shortUrl: str = ""
    closed: bool = False
    idOrganization: str | None = None


class TrelloAPIActionData(BaseModel):
    """Typed subset of action.data that we use."""
    card: dict[str, Any] | None = None
    list: dict[str, Any] | None = None          # destination list (on updateCard)
    listBefore: dict[str, Any] | None = None    # source list (on move)
    listAfter: dict[str, Any] | None = None     # dest list (on move)
    board: dict[str, Any] | None = None
    text: str | None = None                     # comment text
    old: dict[str, Any] | None = None           # previous value (updateCard)


class TrelloAPIAction(BaseModel):
    id: str
    type: str
    date: datetime
    data: TrelloAPIActionData
    idMemberCreator: str
    memberCreator: TrelloAPIMember | None = None


class TrelloAPIWebhookPayload(BaseModel):
    """Incoming webhook POST body from Trello."""
    action: TrelloAPIAction
    model: dict[str, Any]  # The board/list/card the webhook watches


# ─────────────────────────────────────────────────────────────────────────────
# 2. Our internal read models
# ─────────────────────────────────────────────────────────────────────────────

class TrelloBoardRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    trello_id: str
    name: str
    description: str | None
    short_url: str | None
    is_closed: bool
    last_synced_at: datetime | None

    list_count: int = 0
    card_count: int = 0


class TrelloListRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    trello_id: str
    name: str
    pos: float
    is_closed: bool
    list_type: ListType
    card_count: int = 0


class TrelloCardRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    trello_id: str
    trello_short_id: int
    name: str
    description: str | None
    member_ids: list[str] = Field(default_factory=list)
    labels: list[dict] = Field(default_factory=list)
    due_date: datetime | None
    due_complete: bool
    is_closed: bool
    is_stalled: bool
    stalled_since: datetime | None
    entered_wip_at: datetime | None
    entered_done_at: datetime | None
    trello_created_at: datetime | None
    cycle_time_hours: float | None
    lead_time_hours: float | None
    list_name: str | None = None
    list_type: ListType | None = None


class TrelloBlockerRead(BaseModel):
    """Cards identified as stalled/blocked."""
    card_id: int
    trello_card_id: str
    card_name: str
    card_short_id: int
    list_name: str | None
    stalled_since: datetime | None
    stalled_hours: float
    escalation_level: int = 1  # 1 | 2 | 3
    member_ids: list[str] = Field(default_factory=list)


class TrelloWebhookRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    trello_webhook_id: str
    trello_model_id: str
    callback_url: str
    is_active: bool
    events_received: int
    last_ping_at: datetime | None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Analytics
# ─────────────────────────────────────────────────────────────────────────────

class CycleTimeHistogram(BaseModel):
    """Bucket distribution for a single time metric (cycle or lead time)."""
    label: str                     # e.g. "Cycle Time"
    bucket_labels: list[str]       # e.g. ["0–8h", "8–24h", ..., ">240h"]
    counts: list[int]              # parallel array — count per bucket


class CardMovementFlow(BaseModel):
    """Sankey-style movement counts between list pairs."""
    from_list: str
    to_list: str
    count: int


class TrelloAnalytics(BaseModel):
    """Board-level analytics snapshot."""
    board_id: int
    board_name: str
    computed_at: datetime

    # Cycle / Lead time  (hours)
    avg_cycle_time_hours: float | None
    p50_cycle_time_hours: float | None
    p90_cycle_time_hours: float | None
    avg_lead_time_hours: float | None

    # Throughput
    throughput_cards: int              # cards completed in the window
    throughput_days: int               # window size (e.g. 7)

    # WIP
    current_wip: int                   # cards in WIP lists right now

    # Flow efficiency  = cycle_time / lead_time × 100
    flow_efficiency_pct: float | None

    # Blockers
    stalled_count: int
    blockers: list[TrelloBlockerRead] = Field(default_factory=list)

    # Histograms + flow
    cycle_time_histogram: CycleTimeHistogram | None = None
    lead_time_histogram: CycleTimeHistogram | None = None
    movement_flow: list[CardMovementFlow] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Request bodies
# ─────────────────────────────────────────────────────────────────────────────

class ConnectTrelloRequest(BaseModel):
    """Connect a project to Trello."""
    project_id: int
    api_key: str = Field(min_length=8, max_length=128)
    api_token: str = Field(min_length=16, max_length=512)


class ImportTrelloBoardsRequest(BaseModel):
    """
    Import one or more Trello boards as local projects.

    Credentials default to server-side environment variables when omitted.
    """

    api_key: str | None = Field(default=None, min_length=8, max_length=128)
    api_token: str | None = Field(default=None, min_length=16, max_length=512)
    board_ids: list[str] = Field(default_factory=list)


class AvailableTrelloBoardRead(BaseModel):
    id: str
    name: str
    description: str | None = None
    short_url: str | None = None
    is_closed: bool = False
    organization_id: str | None = None


class ImportedTrelloProjectRead(BaseModel):
    project_id: int
    project_key: str
    board_id: int
    board_name: str
    trello_board_id: str
    short_url: str | None = None


class RegisterWebhookRequest(BaseModel):
    callback_url: str
    description: str | None = "KPIMaster Trello webhook"


class ListTypeOverrideRequest(BaseModel):
    """Manually override the auto-classified list type."""
    list_id: int
    list_type: ListType


# ─────────────────────────────────────────────────────────────────────────────
# 5. App-level settings (singleton)
# ─────────────────────────────────────────────────────────────────────────────

class TrelloAppSettingsRead(BaseModel):
    """Returned by GET /trello/settings."""
    model_config = {"from_attributes": True}

    has_credentials: bool
    api_key: str        # full value — stored locally, returned for form pre-fill
    api_token: str
    selected_board_ids: list[str] = Field(default_factory=list)


class SaveTrelloSettingsRequest(BaseModel):
    """Body for POST /trello/settings — saves without triggering any sync."""
    api_key: str | None = Field(default=None, min_length=8, max_length=128)
    api_token: str | None = Field(default=None, min_length=16, max_length=512)
    selected_board_ids: list[str] = Field(default_factory=list)


class BoardListSummaryItem(BaseModel):
    """Per-list breakdown row returned by GET /trello/projects/{id}/board-summary."""
    list_id: int
    name: str
    list_type: str          # "backlog" | "wip" | "done" | "unknown"
    card_count: int
    position: float


class BoardSummaryResponse(BaseModel):
    """Returned by GET /trello/projects/{project_id}/board-summary."""
    project_id: int
    board_id: int
    board_name: str
    lists: list[BoardListSummaryItem]
    # Derived KPI totals
    total_cards: int
    backlog_count: int
    wip_count: int
    done_count: int
    completion_rate: float   # done / (done + wip + backlog), 0–1


class ReclassifyListsResponse(BaseModel):
    """Returned by POST /trello/boards/{board_id}/reclassify-lists."""
    board_id: int
    lists_updated: int
    lists: list[dict]        # [{list_id, name, old_type, new_type}]


class TrelloCommentRead(BaseModel):
    action_id: str
    author: str | None = None
    author_member_id: str | None = None
    timestamp: datetime
    content: str
    mentioned_users: list[str] = Field(default_factory=list)
    attachments_or_links: list[str] = Field(default_factory=list)
    classification: str
    sentiment: str
    blocker_signals: list[str] = Field(default_factory=list)
    response_time_hours: float | None = None
    unanswered_for_hours: float | None = None


class TicketCommentInsightRead(BaseModel):
    ticket_id: int
    ticket_title: str
    ticket_short_id: int
    board_id: int
    comment_count: int
    blocker_comment_count: int
    unresolved_discussion_count: int
    average_response_time_hours: float | None = None
    potentially_blocked: bool = False
    needs_clarification: bool = False
    repeated_negative_sentiment: bool = False
    communication_issues: list[str] = Field(default_factory=list)
    detected_blockers: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    ai_summary: str
    comments: list[TrelloCommentRead] = Field(default_factory=list)


class ProjectCommentMetricsRead(BaseModel):
    project_id: int
    board_id: int
    board_name: str
    tickets_analyzed: int
    blocker_comments: int
    unanswered_questions_over_24h: int
    ignored_blockers_over_24h: int
    average_response_time_hours: float | None = None
    unresolved_discussion_tickets: int
    most_active_discussion_tickets: list[dict] = Field(default_factory=list)
    developers_reporting_blockers: list[dict] = Field(default_factory=list)
    comment_insights_summary: list[str] = Field(default_factory=list)
    tickets: list[TicketCommentInsightRead] = Field(default_factory=list)
