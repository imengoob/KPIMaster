from datetime import date

from app.schemas.common import OrmBase


class BurndownEntryResponse(OrmBase):
    id: int
    sprint_id: int
    date: date
    remaining_points: int
    completed_points: int
    ideal_remaining: float
    cumulative_completed: int


class BurndownChart(OrmBase):
    """Full burndown dataset for a sprint — ready for chart rendering."""

    sprint_id: int
    sprint_name: str
    start_date: date
    end_date: date
    committed_points: int
    entries: list[BurndownEntryResponse]

    @property
    def is_on_track(self) -> bool:
        """True when actual remaining <= ideal remaining on the last entry."""
        if not self.entries:
            return True
        last = self.entries[-1]
        return last.remaining_points <= last.ideal_remaining
