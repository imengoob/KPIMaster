"""Add Action Center tables

Revision ID: 9f4a1c2d3e4b
Revises: 123456789abc
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f4a1c2d3e4b"
down_revision: Union[str, None] = "123456789abc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "action_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("recommended_action", sa.String(length=500), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("owner_role", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "source_type",
            "source_id",
            "recommended_action",
            name="uq_action_items_signal_recommendation",
        ),
    )
    op.create_index(op.f("ix_action_items_due_at"), "action_items", ["due_at"], unique=False)
    op.create_index(op.f("ix_action_items_owner_role"), "action_items", ["owner_role"], unique=False)
    op.create_index(op.f("ix_action_items_owner_user_id"), "action_items", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_action_items_priority"), "action_items", ["priority"], unique=False)
    op.create_index(op.f("ix_action_items_project_id"), "action_items", ["project_id"], unique=False)
    op.create_index(op.f("ix_action_items_source_id"), "action_items", ["source_id"], unique=False)
    op.create_index(op.f("ix_action_items_source_type"), "action_items", ["source_type"], unique=False)
    op.create_index(op.f("ix_action_items_status"), "action_items", ["status"], unique=False)

    op.create_table(
        "action_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action_item_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("previous_status", sa.String(length=30), nullable=True),
        sa.Column("next_status", sa.String(length=30), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["action_item_id"], ["action_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_action_events_action_item_id"), "action_events", ["action_item_id"], unique=False)
    op.create_index(op.f("ix_action_events_actor_user_id"), "action_events", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_action_events_event_type"), "action_events", ["event_type"], unique=False)


def downgrade() -> None:
    op.drop_table("action_events")
    op.drop_table("action_items")

