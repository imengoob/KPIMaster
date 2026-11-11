"""
TrelloBoard — mirrors a Trello board.

trello_id is the native Trello string ID (24-char hex).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TrelloBoard(Base, TimestampMixin):
    __tablename__ = "trello_boards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    credential_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trello_credentials.id", ondelete="CASCADE"), nullable=False
    )

    # Native Trello identifiers
    trello_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    trello_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Sync state
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Actions are paginated by `since` (last action ID fetched)
    last_action_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── relationships ──────────────────────────────────────────────────────────
    credential: Mapped["TrelloCredential"] = relationship(  # noqa: F821
        "TrelloCredential", back_populates="boards"
    )
    lists: Mapped[list["TrelloList"]] = relationship(  # noqa: F821
        "TrelloList", back_populates="board", cascade="all, delete-orphan"
    )
    cards: Mapped[list["TrelloCard"]] = relationship(  # noqa: F821
        "TrelloCard", back_populates="board", cascade="all, delete-orphan"
    )
    webhooks: Mapped[list["TrelloWebhook"]] = relationship(  # noqa: F821
        "TrelloWebhook", back_populates="board", cascade="all, delete-orphan"
    )
