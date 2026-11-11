"""Add normalized integration work items and developer identities

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "developer_external_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("developer_id", sa.Integer(), nullable=False),
        sa.Column("integration_account_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_user_id", sa.String(length=255), nullable=False),
        sa.Column("external_display_name", sa.String(length=255), nullable=True),
        sa.Column("external_email", sa.String(length=320), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["developer_id"], ["developers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["integration_account_id"], ["integration_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "external_user_id",
            "integration_account_id",
            name="uq_developer_external_identity",
        ),
    )
    op.create_index("ix_developer_external_identities_developer_id", "developer_external_identities", ["developer_id"])
    op.create_index("ix_developer_external_identities_integration_account_id", "developer_external_identities", ["integration_account_id"])
    op.create_index("ix_developer_external_identities_provider", "developer_external_identities", ["provider"])
    op.create_index("ix_developer_external_identities_external_user_id", "developer_external_identities", ["external_user_id"])

    op.create_table(
        "integration_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("board_id", sa.String(length=255), nullable=False),
        sa.Column("external_task_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=50), nullable=True),
        sa.Column("task_type", sa.String(length=50), nullable=False, server_default="task"),
        sa.Column("assignee_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("labels", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("story_points", sa.Float(), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("raw", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["account_id"], ["integration_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "board_id", "external_task_id", name="uq_integration_task_external"),
    )
    op.create_index("ix_integration_tasks_account_id", "integration_tasks", ["account_id"])
    op.create_index("ix_integration_tasks_project_id", "integration_tasks", ["project_id"])
    op.create_index("ix_integration_tasks_provider", "integration_tasks", ["provider"])
    op.create_index("ix_integration_tasks_board_id", "integration_tasks", ["board_id"])
    op.create_index("ix_integration_tasks_external_task_id", "integration_tasks", ["external_task_id"])
    op.create_index("ix_integration_tasks_status", "integration_tasks", ["status"])

    op.create_table(
        "integration_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_comment_id", sa.String(length=255), nullable=False),
        sa.Column("external_task_id", sa.String(length=255), nullable=False),
        sa.Column("author_external_id", sa.String(length=255), nullable=False),
        sa.Column("author_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("external_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["account_id"], ["integration_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["integration_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "external_comment_id", name="uq_integration_comment_external"),
    )
    op.create_index("ix_integration_comments_task_id", "integration_comments", ["task_id"])
    op.create_index("ix_integration_comments_account_id", "integration_comments", ["account_id"])
    op.create_index("ix_integration_comments_provider", "integration_comments", ["provider"])
    op.create_index("ix_integration_comments_external_comment_id", "integration_comments", ["external_comment_id"])
    op.create_index("ix_integration_comments_external_task_id", "integration_comments", ["external_task_id"])
    op.create_index("ix_integration_comments_author_external_id", "integration_comments", ["author_external_id"])


def downgrade() -> None:
    op.drop_table("integration_comments")
    op.drop_table("integration_tasks")
    op.drop_table("developer_external_identities")
