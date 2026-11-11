"""
TrelloCard — current state of a Trello card.

Stores denormalised list-type flags (entered_wip_at, entered_done_at) so
analytics queries avoid scanning the full action history.

card_movements child table records every list transition to allow
historical cycle-time analysis.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TrelloCard(Base, TimestampMixin):
    __tablename__ = "trello_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    board_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trello_boards.id", ondelete="CASCADE"), nullable=False
    )
    list_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trello_lists.id", ondelete="SET NULL"), nullable=True
    )

    trello_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    trello_short_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Members assigned (stored as JSON array of Trello member IDs)
    member_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Labels as JSON [{id, name, color}]
    labels: Mapped[list | None] = mapped_column(JSON, nullable=True)

    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    trello_last_activity: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Denormalised analytics anchors ─────────────────────────────────────────
    # First time the card entered a WIP-type list
    entered_wip_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # First time the card entered a Done-type list
    entered_done_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Time the card was created on Trello (from createCard action)
    trello_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Computed analytics (updated by analytics service)
    cycle_time_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    lead_time_hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Blocker flag — set by blocker detection task
    is_stalled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stalled_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── relationships ──────────────────────────────────────────────────────────
    board: Mapped["TrelloBoard"] = relationship("TrelloBoard", back_populates="cards")  # noqa: F821
    current_list: Mapped["TrelloList | None"] = relationship(  # noqa: F821
        "TrelloList", back_populates="cards"
    )
    movements: Mapped[list["TrelloCardMovement"]] = relationship(  # noqa: F821
        "TrelloCardMovement",
        back_populates="card",
        cascade="all, delete-orphan",
        order_by="TrelloCardMovement.moved_at",
    )
    actions: Mapped[list["TrelloAction"]] = relationship(  # noqa: F821
        "TrelloAction",
        back_populates="card",
        cascade="all, delete-orphan",
        order_by="TrelloAction.action_date.desc()",
    )


class TrelloCardMovement(Base):
    """
    Every list transition is recorded here.

    from_list_id can be NULL for the initial card creation.
    This table is the source of truth for cycle-time / lead-time histograms.
    """

    __tablename__ = "trello_card_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trello_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_list_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trello_lists.id", ondelete="SET NULL"), nullable=True
    )
    to_list_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trello_lists.id", ondelete="SET NULL"), nullable=True
    )

    # Trello action IDs used for idempotency
    trello_action_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    moved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    card: Mapped["TrelloCard"] = relationship("TrelloCard", back_populates="movements")
