"""Sprint lifecycle domain events."""
from datetime import date

from app.domain.events.base import BaseEvent
from app.domain.value_objects.priority import SprintStatus


class SprintStartedEvent(BaseEvent):
    EVENT_TYPE: str = "sprint.started"

    sprint_id: int
    project_id: int
    start_date: date
    end_date: date
    committed_points: int


class SprintCompletedEvent(BaseEvent):
    EVENT_TYPE: str = "sprint.completed"

    sprint_id: int
    project_id: int
    total_points_committed: int
    total_points_completed: int
    completion_rate: float  # 0.0 – 1.0
    velocity: float


class SprintHealthDegradedEvent(BaseEvent):
    """
    Fired when the burndown trajectory indicates the sprint goal is at risk.
    Triggered when remaining work exceeds the ideal burndown line by more
    than 20%.
    """

    EVENT_TYPE: str = "sprint.health_degraded"

    sprint_id: int
    project_id: int
    ideal_remaining_points: int
    actual_remaining_points: int
    deviation_percent: float
    days_remaining: int
