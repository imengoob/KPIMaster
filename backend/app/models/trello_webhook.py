"""
TrelloWebhook — tracks registered Trello webhooks.

Trello webhooks are registered per board (model_id = board trello_id).
The callback_url must be publicly reachable; in dev use ngrok or similar.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TrelloWebhook(Base, TimestampMixin):
    __tablename__ = "trello_webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    board_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trello_boards.id", ondelete="CASCADE"), nullable=False
    )

    # Trello-assigned webhook ID (returned by POST /1/webhooks)
    trello_webhook_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    # The board's Trello ID this webhook is attached to
    trello_model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    callback_url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_ping_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Counts for observability
    events_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── relationships ──────────────────────────────────────────────────────────
    board: Mapped["TrelloBoard"] = relationship(  # noqa: F821
        "TrelloBoard", back_populates="webhooks"
    )
