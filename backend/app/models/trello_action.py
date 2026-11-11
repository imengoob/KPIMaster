"""
TrelloAction — raw Trello activity record for a card.

Stores the subset of Trello action types we care about:
  createCard, updateCard, commentCard, deleteCard,
  addMemberToCard, removeMemberFromCard, addLabelToCard

We keep this table to power the activity feed and to detect stalled cards
(last action older than stall threshold).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column, relationship

from app.models.base import Base


TRACKED_ACTION_TYPES = frozenset(
    {
        "createCard",
        "updateCard",
        "commentCard",
        "deleteCard",
        "addMemberToCard",
        "removeMemberFromCard",
        "addLabelToCard",
        "moveCardToBoard",
        "moveCardFromBoard",
    }
)


class TrelloAction(Base):
    __tablename__ = "trello_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trello_cards.id", ondelete="CASCADE"), nullable=True, index=True
    )

    trello_action_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Raw payload slice (data portion of Trello action)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Member who performed the action
    trello_member_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    member_name: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # ── relationships ──────────────────────────────────────────────────────────
    card: Mapped["TrelloCard | None"] = relationship(  # noqa: F821
        "TrelloCard", back_populates="actions"
    )
