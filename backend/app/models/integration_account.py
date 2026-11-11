"""
IntegrationAccount — one row per provider connection per user.

Design decisions
────────────────
  • Tokens are stored encrypted (Fernet). Never store plaintext.
  • `extra_data` (JSON) carries provider-specific context:
      Jira      → {"cloud_id": "...", "cloud_name": "...", "site_url": "..."}
      Microsoft → {"tenant_id": "...", "user_id": "...", "user_email": "..."}
      Trello    → {}  (api_key lives in encrypted_access_token)
  • One user can have multiple accounts per provider (multi-workspace support).
  • `external_account_id` is the provider's own identifier for the account
    (Jira accountId, Microsoft userId, Trello memberId).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class IntegrationAccount(Base, TimestampMixin):
    __tablename__ = "integration_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "external_account_id",
                         name="uq_integration_user_provider_account"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The KPIMaster user who owns this connection
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "jira" | "microsoft" | "trello"
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # Human-readable label (e.g. "Acme Jira", "Work Microsoft 365")
    account_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # Provider's own account identifier (stable across token refreshes)
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # ── Encrypted tokens ──────────────────────────────────────────────────────
    # Always encrypted via app.integrations.encryption
    encrypted_access_token:  Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    # UTC datetime when the access_token expires (for proactive refresh)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Granted OAuth scopes (space-separated string or JSON list)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Provider-specific metadata (cloud_id, tenant_id, etc.)
    extra_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # ── State ─────────────────────────────────────────────────────────────────
    is_active:    Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Convenience property for registry ────────────────────────────────────
    @property
    def db_account_id(self) -> int:
        return self.id

    # ── Relationships ─────────────────────────────────────────────────────────
    sync_logs: Mapped[list["IntegrationSyncLog"]] = relationship(  # noqa: F821
        "IntegrationSyncLog",
        back_populates="account",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    tasks: Mapped[list["IntegrationTask"]] = relationship(  # noqa: F821
        "IntegrationTask",
        back_populates="account",
        cascade="all, delete-orphan",
    )
    comments: Mapped[list["IntegrationComment"]] = relationship(  # noqa: F821
        "IntegrationComment",
        back_populates="account",
        cascade="all, delete-orphan",
    )
    developer_identities: Mapped[list["DeveloperExternalIdentity"]] = relationship(  # noqa: F821
        "DeveloperExternalIdentity",
        back_populates="integration_account",
        cascade="all, delete-orphan",
    )
