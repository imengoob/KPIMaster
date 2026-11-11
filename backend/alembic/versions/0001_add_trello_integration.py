"""Add Trello integration tables

7 new tables:
  trello_credentials    — API key / token per project
  trello_boards         — mirror of Trello boards
  trello_lists          — lists within a board, with list_type classification
  trello_cards          — cards with denormalised analytics anchors
  trello_card_movements — every list transition (cycle-time source of truth)
  trello_actions        — raw activity log
  trello_webhooks       — registered Trello webhooks

Revision ID: 0001
Revises:
Create Date: 2026-04-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0001"
down_revision: str | None = "0000"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ── trello_credentials ────────────────────────────────────────────────────
    op.create_table(
        "trello_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("api_key", sa.String(64), nullable=False),
        sa.Column("api_token", sa.Text(), nullable=False),
        sa.Column("oauth_token_secret", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
    op.create_index("ix_trello_credentials_project_id", "trello_credentials", ["project_id"])

    # ── trello_boards ─────────────────────────────────────────────────────────
    op.create_table(
        "trello_boards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "credential_id",
            sa.Integer(),
            sa.ForeignKey("trello_credentials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trello_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("short_url", sa.String(256), nullable=True),
        sa.Column("trello_org_id", sa.String(64), nullable=True),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_action_id", sa.String(64), nullable=True),
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
    op.create_index("ix_trello_boards_trello_id", "trello_boards", ["trello_id"])

    # ── list_type enum ────────────────────────────────────────────────────────
    list_type_enum = postgresql.ENUM(
        "backlog", "wip", "done", "unknown", name="listtype", create_type=False
    )
    list_type_enum.create(op.get_bind(), checkfirst=True)

    # ── trello_lists ──────────────────────────────────────────────────────────
    op.create_table(
        "trello_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "board_id",
            sa.Integer(),
            sa.ForeignKey("trello_boards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trello_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("pos", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "list_type",
            list_type_enum,
            nullable=False,
            server_default="unknown",
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
    op.create_index("ix_trello_lists_trello_id", "trello_lists", ["trello_id"])
    op.create_index("ix_trello_lists_board_id", "trello_lists", ["board_id"])

    # ── trello_cards ──────────────────────────────────────────────────────────
    op.create_table(
        "trello_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "board_id",
            sa.Integer(),
            sa.ForeignKey("trello_boards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "list_id",
            sa.Integer(),
            sa.ForeignKey("trello_lists.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trello_id", sa.String(64), nullable=False, unique=True),
        sa.Column("trello_short_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("member_ids", postgresql.JSON(), nullable=True),
        sa.Column("labels", postgresql.JSON(), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trello_last_activity", sa.DateTime(timezone=True), nullable=True),
        # Analytics anchors
        sa.Column("entered_wip_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entered_done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trello_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cycle_time_hours", sa.Float(), nullable=True),
        sa.Column("lead_time_hours", sa.Float(), nullable=True),
        # Stall detection
        sa.Column("is_stalled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stalled_since", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_trello_cards_trello_id", "trello_cards", ["trello_id"])
    op.create_index("ix_trello_cards_board_id", "trello_cards", ["board_id"])

    # ── trello_card_movements ─────────────────────────────────────────────────
    op.create_table(
        "trello_card_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "card_id",
            sa.Integer(),
            sa.ForeignKey("trello_cards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_list_id",
            sa.Integer(),
            sa.ForeignKey("trello_lists.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "to_list_id",
            sa.Integer(),
            sa.ForeignKey("trello_lists.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trello_action_id", sa.String(64), nullable=False, unique=True),
        sa.Column("moved_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trello_card_movements_card_id", "trello_card_movements", ["card_id"])
    op.create_index(
        "ix_trello_card_movements_trello_action_id",
        "trello_card_movements",
        ["trello_action_id"],
    )

    # ── trello_actions ────────────────────────────────────────────────────────
    op.create_table(
        "trello_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "card_id",
            sa.Integer(),
            sa.ForeignKey("trello_cards.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("trello_action_id", sa.String(64), nullable=False, unique=True),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("action_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column("trello_member_id", sa.String(64), nullable=True),
        sa.Column("member_name", sa.String(256), nullable=True),
    )
    op.create_index("ix_trello_actions_card_id", "trello_actions", ["card_id"])
    op.create_index("ix_trello_actions_trello_action_id", "trello_actions", ["trello_action_id"])

    # ── trello_webhooks ───────────────────────────────────────────────────────
    op.create_table(
        "trello_webhooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "board_id",
            sa.Integer(),
            sa.ForeignKey("trello_boards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trello_webhook_id", sa.String(64), nullable=False, unique=True),
        sa.Column("trello_model_id", sa.String(64), nullable=False),
        sa.Column("callback_url", sa.Text(), nullable=False),
        sa.Column("description", sa.String(256), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_ping_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("events_received", sa.Integer(), nullable=False, server_default="0"),
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
    op.create_index("ix_trello_webhooks_trello_webhook_id", "trello_webhooks", ["trello_webhook_id"])


def downgrade() -> None:
    op.drop_table("trello_webhooks")
    op.drop_table("trello_actions")
    op.drop_table("trello_card_movements")
    op.drop_table("trello_cards")
    op.drop_table("trello_lists")
    op.drop_table("trello_boards")
    op.drop_table("trello_credentials")

    # Drop the enum type last
    postgresql.ENUM(name="listtype").drop(op.get_bind(), checkfirst=True)
