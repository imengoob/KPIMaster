from datetime import datetime

from app.schemas.common import OrmBase


class KPIResponse(OrmBase):
    """Full KPI response for a project/sprint."""

    id: int
    project_id: int
    sprint_id: int | None

    # Time-based KPIs (hours)
    cycle_time_hours: float | None
    lead_time_hours: float | None

    # Throughput KPIs
    velocity: float | None
    completion_rate: float | None
    throughput: float | None  # tickets/day

    # Quality KPIs
    estimation_accuracy: float | None
    bug_rate: float | None

    computed_at: datetime

    # Derived labels
    @property
    def cycle_time_days(self) -> float | None:
        if self.cycle_time_hours is None:
            return None
        return round(self.cycle_time_hours / 24, 2)

    @property
    def lead_time_days(self) -> float | None:
        if self.lead_time_hours is None:
            return None
        return round(self.lead_time_hours / 24, 2)


class KPIDashboard(OrmBase):
    """Aggregated dashboard payload — everything in one call."""

    project_id: int
    sprint_id: int | None
    current_kpis: KPIResponse | None
    velocity_trend: list[float]   # last N sprint velocities
    completion_trend: list[float] # last N sprint completion rates
    open_blockers: int
    stalled_tickets: int
    repo_mismatches: int
