from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class RepositoryActivity(Base, TimestampMixin):
    """
    Snapshot of git/PR activity associated with a ticket.

    The repository analyzer runs periodically, updates these records, and
    raises a RepoActivityUpdatedEvent when it detects a mismatch between
    the ticket status and the observed commit/PR activity.
    """

    __tablename__ = "repository_activity"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pr_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pr_merged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_commit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_pr_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Mismatch detection
    mismatch_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mismatch_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    mismatch_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # e.g. "no_commits_in_progress" | "pr_not_merged_done" | "stale_branch"

    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="repository_activity")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<RepositoryActivity id={self.id} ticket_id={self.ticket_id} "
            f"mismatch={self.mismatch_detected}>"
        )
