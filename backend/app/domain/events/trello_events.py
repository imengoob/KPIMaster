"""
Trello domain events — emitted to the internal event bus.

Subscribers (notification service, WebSocket manager, etc.) react to these
without knowing anything about Trello internals.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.domain.events.base import BaseEvent


class TrelloCardMovedEvent(BaseEvent):
    """A card was moved from one list to another."""

    EVENT_TYPE = "trello.card.moved"
    EVENT_VERSION = 1

    board_id: int
    trello_board_id: str
    board_name: str

    card_id: int
    trello_card_id: str
    card_name: str
    card_short_id: int

    from_list_name: str | None
    to_list_name: str
    to_list_type: str       # "backlog" | "wip" | "done" | "unknown"
    moved_at: datetime
    moved_by: str | None    # Trello member display name


class TrelloCardStalledEvent(BaseEvent):
    """A card has been in a WIP list without activity beyond the threshold."""

    EVENT_TYPE = "trello.card.stalled"
    EVENT_VERSION = 1

    board_id: int
    board_name: str
    card_id: int
    trello_card_id: str
    card_name: str
    card_short_id: int
    list_name: str
    stalled_hours: float
    escalation_level: int   # 1, 2, or 3
    member_ids: list[str] = Field(default_factory=list)


class TrelloCardCommentedEvent(BaseEvent):
    """A comment was added to a card."""

    EVENT_TYPE = "trello.card.commented"
    EVENT_VERSION = 1

    board_id: int
    card_id: int
    trello_card_id: str
    card_name: str
    author_name: str
    comment_text: str
    commented_at: datetime


class TrelloBoardSyncedEvent(BaseEvent):
    """A full board sync completed."""

    EVENT_TYPE = "trello.board.synced"
    EVENT_VERSION = 1

    board_id: int
    board_name: str
    cards_upserted: int
    actions_processed: int
    sync_duration_ms: float


class TrelloWebhookReceivedEvent(BaseEvent):
    """A raw webhook payload was received and queued for processing."""

    EVENT_TYPE = "trello.webhook.received"
    EVENT_VERSION = 1

    board_id: int
    trello_action_type: str
    trello_action_id: str


class TrelloAnalyticsUpdatedEvent(BaseEvent):
    """Analytics were recomputed for a board."""

    EVENT_TYPE = "trello.analytics.updated"
    EVENT_VERSION = 1

    board_id: int
    board_name: str
    avg_cycle_time_hours: float | None
    stalled_count: int
    current_wip: int
