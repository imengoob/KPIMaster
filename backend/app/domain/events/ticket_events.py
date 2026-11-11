"""Ticket domain events."""
from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.domain.events.base import BaseEvent
from app.domain.value_objects.priority import EscalationLevel
from app.domain.value_objects.ticket_status import TicketStatus


class TicketUpdatedEvent(BaseEvent):
    """Fired whenever a ticket's status, assignee, or fields change."""

    EVENT_TYPE: str = "ticket.updated"

    ticket_id: int
    project_id: int
    sprint_id: int | None
    previous_status: TicketStatus | None
    new_status: TicketStatus
    changed_by: int | None = None  # developer_id
    changed_fields: list[str] = Field(default_factory=list)


class TicketStalledEvent(BaseEvent):
    """
    Fired when a ticket has had no activity for longer than the configured
    threshold.  The stall_hours field carries the actual idle duration.
    """

    EVENT_TYPE: str = "ticket.stalled"

    ticket_id: int
    project_id: int
    sprint_id: int | None
    assignee_id: int | None
    stall_hours: float
    ticket_status: TicketStatus
    priority: str


class BlockerDetectedEvent(BaseEvent):
    """Fired when the blocker detection engine classifies a ticket as blocked."""

    EVENT_TYPE: str = "blocker.detected"

    blocker_id: int
    ticket_id: int
    project_id: int
    sprint_id: int | None
    escalation_level: EscalationLevel
    stall_hours: float
    assignee_id: int | None
    team_lead_ids: list[int] = Field(default_factory=list)


class BlockerEscalatedEvent(BaseEvent):
    """Fired when a blocker moves to the next escalation level."""

    EVENT_TYPE: str = "blocker.escalated"

    blocker_id: int
    ticket_id: int
    previous_level: EscalationLevel
    new_level: EscalationLevel
    notified_user_ids: list[int] = Field(default_factory=list)


class RepoActivityUpdatedEvent(BaseEvent):
    """Fired when a repository scan detects new or changed activity."""

    EVENT_TYPE: str = "repo.activity.updated"

    ticket_id: int
    project_id: int
    commit_count: int
    pr_count: int
    mismatch_detected: bool
    mismatch_reason: str | None = None
