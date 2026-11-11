from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class KPISnapshot(Base):
    """
    Point-in-time KPI computation for a project/sprint pair.

    A new snapshot is created every time the KPI engine runs.
    The most recent snapshot for a sprint is treated as authoritative.
    """

    __tablename__ = "kpi_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sprint_id: Mapped[int | None] = mapped_column(
        ForeignKey("sprints.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # ── Core KPIs ─────────────────────────────────────────────────────────
    cycle_time_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Average time from IN_PROGRESS → DONE

    lead_time_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Average time from BACKLOG/TODO → DONE

    velocity: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Story points completed in this sprint

    completion_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # completed / committed  (0.0 – 1.0)

    estimation_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 1 - abs(actual - estimated) / estimated  (0.0 – 1.0)

    throughput: Mapped[float | None] = mapped_column(Float, nullable=True)
    # tickets completed per day

    bug_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # bugs / total tickets

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="kpi_snapshots")  # noqa: F821
    sprint: Mapped["Sprint | None"] = relationship("Sprint", back_populates="kpi_snapshots")  # noqa: F821

    def __repr__(self) -> str:
        return f"<KPISnapshot id={self.id} sprint_id={self.sprint_id} velocity={self.velocity}>"
