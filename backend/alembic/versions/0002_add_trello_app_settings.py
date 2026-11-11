"""Add trello_app_settings singleton table

Stores the user's Trello API credentials and their selected board IDs so
the Settings page can be pre-populated without re-entering them.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "trello_app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("api_key", sa.String(64), nullable=False),
        sa.Column("api_token", sa.Text(), nullable=False),
        sa.Column(
            "selected_board_ids",
            postgresql.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("trello_app_settings")
