from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class BurndownEntry(Base):
    """
    One data point in the sprint burndown chart.

    One entry per sprint per calendar day.
    The burndown generator creates or upserts this daily.
    """

    __tablename__ = "burndown_entries"
    __table_args__ = (
        UniqueConstraint("sprint_id", "date", name="uq_burndown_sprint_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sprint_id: Mapped[int] = mapped_column(
        ForeignKey("sprints.id", ondelete="CASCADE"), nullable=False, index=True
    )

    date: Mapped[date] = mapped_column(Date, nullable=False)
    remaining_points: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_points: Mapped[int] = mapped_column(Integer, nullable=False)
    ideal_remaining: Mapped[float] = mapped_column(Float, nullable=False)
    # Linear interpolation from committed_points → 0 across sprint duration

    # Cumulative completed up to this date (for velocity chart)
    cumulative_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    sprint: Mapped["Sprint"] = relationship("Sprint", back_populates="burndown_entries")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<BurndownEntry sprint_id={self.sprint_id} date={self.date} "
            f"remaining={self.remaining_points}>"
        )
