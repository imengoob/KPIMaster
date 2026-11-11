"""Add multi-provider integration tables

2 new tables:
  integration_accounts  — one row per connected provider account per user
  integration_sync_logs — immutable audit log for every sync run

Revision ID: 0004
Revises:     0003
Create Date: 2026-04-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | tuple[str, ...] | None = None
depends_on:    str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ── integration_accounts ─────────────────────────────────────────────────
    op.create_table(
        "integration_accounts",
        sa.Column("id",      sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # "jira" | "microsoft" | "trello"
        sa.Column("provider",             sa.String(32),  nullable=False),
        sa.Column("account_name",         sa.String(255), nullable=False, server_default=""),
        sa.Column("external_account_id",  sa.String(255), nullable=False, server_default=""),
        # Encrypted Fernet ciphertext — never plain text
        sa.Column("encrypted_access_token",  sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at",    sa.DateTime(timezone=True), nullable=True),
        # JSON columns
        sa.Column("scopes",     sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("extra_data", sa.JSON(), nullable=False, server_default="{}"),
        # State
        sa.Column("is_active",    sa.Boolean(),           nullable=False, server_default=sa.true()),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_integration_accounts_user_id",  "integration_accounts", ["user_id"])
    op.create_index("ix_integration_accounts_provider", "integration_accounts", ["provider"])
    op.create_unique_constraint(
        "uq_integration_user_provider_account",
        "integration_accounts",
        ["user_id", "provider", "external_account_id"],
    )

    # ── integration_sync_logs ─────────────────────────────────────────────────
    op.create_table(
        "integration_sync_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("integration_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider",  sa.String(32), nullable=False),
        sa.Column("board_id",  sa.String(255), nullable=True),
        sa.Column("sync_type", sa.String(32), nullable=False, server_default="full"),
        sa.Column("status",    sa.String(32), nullable=False, server_default="running"),
        sa.Column("items_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_integration_sync_logs_account_id",
        "integration_sync_logs",
        ["account_id"],
    )
    op.create_index(
        "ix_integration_sync_logs_started_at",
        "integration_sync_logs",
        ["started_at"],
    )


def downgrade() -> None:
    op.drop_table("integration_sync_logs")
    op.drop_table("integration_accounts")
