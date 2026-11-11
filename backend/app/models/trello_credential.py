"""
TrelloCredential stores per-project Trello API key + OAuth token.

One project can have one active credential set.
The token is stored as-is (encrypt at rest with a KMS in production).
"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TrelloCredential(Base, TimestampMixin):
    __tablename__ = "trello_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    api_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # OAuth token or personal token — mask in logs
    api_token: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional OAuth access token secret (OAuth 1.0a)
    oauth_token_secret: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── relationships ──────────────────────────────────────────────────────────
    boards: Mapped[list["TrelloBoard"]] = relationship(  # noqa: F821
        "TrelloBoard", back_populates="credential", cascade="all, delete-orphan"
    )
