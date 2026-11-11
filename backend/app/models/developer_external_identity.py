from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class DeveloperExternalIdentity(Base, TimestampMixin):
    __tablename__ = "developer_external_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_user_id",
            "integration_account_id",
            name="uq_developer_external_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    developer_id: Mapped[int] = mapped_column(
        ForeignKey("developers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    integration_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("integration_accounts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    external_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    developer: Mapped["Developer"] = relationship(  # noqa: F821
        "Developer",
        back_populates="external_identities",
    )
    integration_account: Mapped["IntegrationAccount | None"] = relationship(  # noqa: F821
        "IntegrationAccount",
        back_populates="developer_identities",
    )
