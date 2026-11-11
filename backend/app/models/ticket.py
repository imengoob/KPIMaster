from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Ticket(Base, TimestampMixin):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign keys
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sprint_id: Mapped[int | None] = mapped_column(
        ForeignKey("sprints.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("developers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reporter_id: Mapped[int | None] = mapped_column(
        ForeignKey("developers.id", ondelete="SET NULL"), nullable=True
    )

    # Core fields
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Enums stored as strings (validated at service layer)
    status: Mapped[str] = mapped_column(String(20), default="backlog", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False, index=True)
    ticket_type: Mapped[str] = mapped_column(String(20), default="task", nullable=False)

    # Estimation & tracking
    estimated_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    story_points: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Quality scoring — 0-100, computed by the monitoring engine
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Stall detection — updated on every field change
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="tickets")  # noqa: F821
    sprint: Mapped["Sprint | None"] = relationship("Sprint", back_populates="tickets")  # noqa: F821
    assignee: Mapped["Developer | None"] = relationship(  # noqa: F821
        "Developer", foreign_keys=[assignee_id], back_populates="assigned_tickets"
    )
    reporter: Mapped["Developer | None"] = relationship(  # noqa: F821
        "Developer", foreign_keys=[reporter_id], back_populates="reported_tickets"
    )
    blockers: Mapped[list["Blocker"]] = relationship(  # noqa: F821
        "Blocker", back_populates="ticket", cascade="all, delete-orphan"
    )
    repository_activity: Mapped[list["RepositoryActivity"]] = relationship(  # noqa: F821
        "RepositoryActivity", back_populates="ticket", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Ticket id={self.id} status={self.status!r} priority={self.priority!r}>"
