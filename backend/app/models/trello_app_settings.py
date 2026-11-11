from __future__ import annotations

from sqlalchemy import Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

class TrelloAppSettings(Base, TimestampMixin):
    __tablename__ = "trello_app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, unique=True)
    api_key: Mapped[str] = mapped_column(String(64), nullable=False)
    api_token: Mapped[str] = mapped_column(Text, nullable=False)
    # Trello board IDs (native string IDs) selected by the user
    selected_board_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, server_default="[]"
    )

    def __repr__(self) -> str:
        return f"<TrelloAppSettings for company={self.company_id}>"
