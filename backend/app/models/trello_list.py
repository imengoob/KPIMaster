"""
TrelloList — mirrors a Trello list within a board.

list_type classifies the list for analytics purposes:
  - backlog    : not yet started (Todo, Icebox, Backlog)
  - wip        : actively being worked (In Progress, Doing, Review, QA)
  - done       : completed (Done, Shipped, Deployed)
  - unknown    : unclassified

list_type drives cycle-time and lead-time calculations:
  - cycle time  : first entry into 'wip' → first entry into 'done'
  - lead time   : card creation → first entry into 'done'
  - wip count   : cards currently in 'wip' lists
"""
from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ListType(str, enum.Enum):
    BACKLOG = "backlog"
    WIP     = "wip"
    DONE    = "done"
    UNKNOWN = "unknown"


class TrelloList(Base, TimestampMixin):
    __tablename__ = "trello_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    board_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trello_boards.id", ondelete="CASCADE"), nullable=False
    )

    trello_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    pos: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    list_type: Mapped[ListType] = mapped_column(
        Enum(
            ListType,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        default=ListType.UNKNOWN,
        nullable=False,
    )

    # ── relationships ──────────────────────────────────────────────────────────
    board: Mapped["TrelloBoard"] = relationship("TrelloBoard", back_populates="lists")  # noqa: F821
    cards: Mapped[list["TrelloCard"]] = relationship(  # noqa: F821
        "TrelloCard", back_populates="current_list"
    )
