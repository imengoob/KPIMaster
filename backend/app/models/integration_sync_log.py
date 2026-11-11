"""
IntegrationSyncLog — immutable audit record for every sync run.

Used for monitoring sync health: frequency, item counts, errors.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SyncType(str, Enum):
    FULL        = "full"
    INCREMENTAL = "incremental"
    WEBHOOK     = "webhook"


class SyncStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED  = "failed"
    PARTIAL = "partial"


class IntegrationSyncLog(Base):
    __tablename__ = "integration_sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("integration_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider:  Mapped[str] = mapped_column(String(32), nullable=False)
    board_id:  Mapped[str | None] = mapped_column(String(255), nullable=True)
    sync_type: Mapped[str] = mapped_column(String(32), nullable=False, default=SyncType.FULL)
    status:    Mapped[str] = mapped_column(String(32), nullable=False, default=SyncStatus.RUNNING)

    items_synced:  Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors_count:  Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_detail:  Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    account: Mapped["IntegrationAccount"] = relationship(  # noqa: F821
        "IntegrationAccount", back_populates="sync_logs"
    )
