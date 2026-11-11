from datetime import datetime

from pydantic import Field, field_validator

from app.domain.value_objects.priority import Priority, TicketType
from app.domain.value_objects.ticket_status import TicketStatus
from app.schemas.common import OrmBase


class TicketCreate(OrmBase):
    project_id: int
    sprint_id: int | None = None
    assignee_id: int | None = None
    reporter_id: int | None = None
    title: str = Field(..., min_length=3, max_length=500)
    description: str | None = None
    status: TicketStatus = TicketStatus.BACKLOG
    priority: Priority = Priority.MEDIUM
    ticket_type: TicketType = TicketType.TASK
    estimated_hours: float | None = Field(None, gt=0)
    story_points: int | None = Field(None, ge=1, le=100)


class TicketUpdate(OrmBase):
    sprint_id: int | None = None
    assignee_id: int | None = None
    title: str | None = Field(None, min_length=3, max_length=500)
    description: str | None = None
    status: TicketStatus | None = None
    priority: Priority | None = None
    estimated_hours: float | None = Field(None, gt=0)
    actual_hours: float | None = Field(None, ge=0)
    story_points: int | None = Field(None, ge=1, le=100)


class TicketResponse(OrmBase):
    id: int
    project_id: int
    sprint_id: int | None
    assignee_id: int | None
    reporter_id: int | None
    title: str
    description: str | None
    status: str
    priority: str
    ticket_type: str
    estimated_hours: float | None
    actual_hours: float | None
    story_points: int | None
    quality_score: float | None
    last_activity_at: datetime
    created_at: datetime
    updated_at: datetime


class TicketQualityReport(OrmBase):
    """Result of the ticket monitoring engine scan."""

    ticket_id: int
    quality_score: float
    issues: list[str]
    has_description: bool
    has_assignee: bool
    has_priority: bool
    has_estimation: bool
    recommendations: list[str]
