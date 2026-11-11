from datetime import datetime

from app.schemas.common import OrmBase


class BlockerResponse(OrmBase):
    id: int
    ticket_id: int
    description: str | None
    stall_hours: float
    escalation_level: int
    detected_at: datetime
    last_escalated_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EnrichedBlockerResponse(OrmBase):
    """
    BlockerResponse enriched with ticket info — returned by GET /blockers.

    Matches the frontend's BackendBlocker interface exactly so the
    frontend can render blocker cards without a second round-trip.
    """
    id: int
    ticket_id: int
    description: str | None
    stall_hours: float
    escalation_level: int
    detected_at: datetime
    last_escalated_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # Enriched fields (joined from Ticket)
    ticket_title: str
    ticket_assignee_id: int | None

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None

    @property
    def escalation_label(self) -> str:
        labels = {1: "Developer", 2: "Team Lead", 3: "Management"}
        return labels.get(self.escalation_level, "Unknown")


class BlockerSummary(OrmBase):
    total_open: int
    level_1: int
    level_2: int
    level_3: int
    avg_stall_hours: float
    oldest_stall_hours: float
