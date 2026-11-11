from datetime import date, datetime

from pydantic import Field, model_validator

from app.domain.value_objects.priority import SprintStatus
from app.schemas.common import OrmBase


class SprintCreate(OrmBase):
    project_id: int
    name: str = Field(..., min_length=2, max_length=255)
    goal: str | None = None
    start_date: date
    end_date: date
    status: SprintStatus = SprintStatus.PLANNING
    committed_points: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_dates(self) -> "SprintCreate":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class SprintUpdate(OrmBase):
    name: str | None = None
    goal: str | None = None
    end_date: date | None = None
    status: SprintStatus | None = None
    committed_points: int | None = Field(None, ge=0)


class SprintResponse(OrmBase):
    id: int
    project_id: int
    name: str
    goal: str | None
    start_date: date
    end_date: date
    status: str
    committed_points: int
    completed_points: int
    velocity: float
    created_at: datetime
    updated_at: datetime

    @property
    def completion_rate(self) -> float:
        if self.committed_points == 0:
            return 0.0
        return round(self.completed_points / self.committed_points, 4)

    @property
    def days_remaining(self) -> int:
        from datetime import date as d
        delta = self.end_date - d.today()
        return max(0, delta.days)
