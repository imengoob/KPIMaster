from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Sprint(Base, TimestampMixin):
    __tablename__ = "sprints"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    # planning | active | completed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="planning", nullable=False)

    committed_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    velocity: Mapped[float] = mapped_column(default=0.0, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="sprints")  # noqa: F821
    tickets: Mapped[list["Ticket"]] = relationship(  # noqa: F821
        "Ticket", back_populates="sprint", cascade="all, delete-orphan"
    )
    burndown_entries: Mapped[list["BurndownEntry"]] = relationship(  # noqa: F821
        "BurndownEntry", back_populates="sprint", cascade="all, delete-orphan"
    )
    kpi_snapshots: Mapped[list["KPISnapshot"]] = relationship(  # noqa: F821
        "KPISnapshot", back_populates="sprint", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Sprint id={self.id} name={self.name!r} status={self.status!r}>"
