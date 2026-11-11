from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Blocker(Base, TimestampMixin):
    """
    Represents an active or resolved blocker on a ticket.

    escalation_level:
        1 = notified the developer
        2 = notified the team lead
        3 = notified management
    """

    __tablename__ = "blockers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    stall_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    escalation_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Who was notified at each level (stored as comma-separated IDs for simplicity)
    notified_developer_ids: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="blockers")  # noqa: F821

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None

    def __repr__(self) -> str:
        return (
            f"<Blocker id={self.id} ticket_id={self.ticket_id} "
            f"level={self.escalation_level} resolved={self.is_resolved}>"
        )
