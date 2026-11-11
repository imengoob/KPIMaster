from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DeveloperSprintKPI(Base):
    """
    Historical KPI snapshot for a Developer at the end of a specific Sprint.
    Used for historical velocity, completion rate, and comparison analytics.
    """

    __tablename__ = "developer_sprint_kpis"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    developer_id: Mapped[int] = mapped_column(
        ForeignKey("developers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sprint_id: Mapped[int | None] = mapped_column(
        ForeignKey("sprints.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Core Delivery KPIs
    completion_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_cycle_time_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimation_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Volumes
    tickets_total: Mapped[int] = mapped_column(Integer, default=0)
    tickets_done: Mapped[int] = mapped_column(Integer, default=0)
    story_points_completed: Mapped[int] = mapped_column(Integer, default=0)
    story_points_total: Mapped[int] = mapped_column(Integer, default=0)

    # Blocker/Quality metrics
    blocker_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_blocker_age_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    blocker_count: Mapped[int] = mapped_column(Integer, default=0)

    # Collab metrics
    question_response_time_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    unanswered_question_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Store complete metadata in case formulas change
    raw_snapshot_data: Mapped[dict] = mapped_column(JSON, default=dict)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    developer: Mapped["Developer"] = relationship("Developer")  # noqa: F821
    project: Mapped["Project"] = relationship("Project")  # noqa: F821
    sprint: Mapped["Sprint | None"] = relationship("Sprint")  # noqa: F821

    def __repr__(self) -> str:
        return f"<DeveloperSprintKPI dev_id={self.developer_id} sprint_id={self.sprint_id} pts={self.story_points_completed}>"
