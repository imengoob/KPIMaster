"""Create initial application schema

Revision ID: 0000
Revises:
Create Date: 2026-04-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0000"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(bind: sa.engine.Connection, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()

    projects = sa.Table(
        "projects",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key", sa.String(length=10), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("repository_url", sa.String(length=512), nullable=True),
        sa.Column("slack_channel", sa.String(length=100), nullable=True),
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
        ),
    )

    developers = sa.Table(
        "developers",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("username", sa.String(length=100), nullable=False, unique=True),
        sa.Column("team", sa.String(length=100), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="developer"),
        sa.Column("slack_id", sa.String(length=50), nullable=True),
        sa.Column("github_username", sa.String(length=100), nullable=True),
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
        ),
    )

    sprints = sa.Table(
        "sprints",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planning"),
        sa.Column("committed_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("velocity", sa.Float(), nullable=False, server_default="0"),
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
        ),
    )

    tickets = sa.Table(
        "tickets",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sprint_id",
            sa.Integer(),
            sa.ForeignKey("sprints.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assignee_id",
            sa.Integer(),
            sa.ForeignKey("developers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reporter_id",
            sa.Integer(),
            sa.ForeignKey("developers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="backlog"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("ticket_type", sa.String(length=20), nullable=False, server_default="task"),
        sa.Column("estimated_hours", sa.Float(), nullable=True),
        sa.Column("actual_hours", sa.Float(), nullable=True),
        sa.Column("story_points", sa.Integer(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
        ),
    )

    blockers = sa.Table(
        "blockers",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "ticket_id",
            sa.Integer(),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("stall_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_developer_ids", sa.String(length=500), nullable=True),
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
        ),
    )

    repository_activity = sa.Table(
        "repository_activity",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "ticket_id",
            sa.Integer(),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("branch_name", sa.String(length=255), nullable=True),
        sa.Column("commit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pr_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pr_merged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_commit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_pr_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mismatch_detected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mismatch_reason", sa.Text(), nullable=True),
        sa.Column("mismatch_type", sa.String(length=50), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
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
        ),
    )

    kpi_snapshots = sa.Table(
        "kpi_snapshots",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sprint_id",
            sa.Integer(),
            sa.ForeignKey("sprints.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("cycle_time_hours", sa.Float(), nullable=True),
        sa.Column("lead_time_hours", sa.Float(), nullable=True),
        sa.Column("velocity", sa.Float(), nullable=True),
        sa.Column("completion_rate", sa.Float(), nullable=True),
        sa.Column("estimation_accuracy", sa.Float(), nullable=True),
        sa.Column("throughput", sa.Float(), nullable=True),
        sa.Column("bug_rate", sa.Float(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    burndown_entries = sa.Table(
        "burndown_entries",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "sprint_id",
            sa.Integer(),
            sa.ForeignKey("sprints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("remaining_points", sa.Integer(), nullable=False),
        sa.Column("completed_points", sa.Integer(), nullable=False),
        sa.Column("ideal_remaining", sa.Float(), nullable=False),
        sa.Column("cumulative_completed", sa.Integer(), nullable=False, server_default="0"),
    )

    for table in (
        projects,
        developers,
        sprints,
        tickets,
        blockers,
        repository_activity,
        kpi_snapshots,
        burndown_entries,
    ):
        table.create(bind=bind, checkfirst=True)

    indexes = (
        ("ix_sprints_project_id", "sprints", ["project_id"]),
        ("ix_tickets_project_id", "tickets", ["project_id"]),
        ("ix_tickets_sprint_id", "tickets", ["sprint_id"]),
        ("ix_tickets_assignee_id", "tickets", ["assignee_id"]),
        ("ix_tickets_status", "tickets", ["status"]),
        ("ix_tickets_priority", "tickets", ["priority"]),
        ("ix_blockers_ticket_id", "blockers", ["ticket_id"]),
        ("ix_repository_activity_ticket_id", "repository_activity", ["ticket_id"]),
        ("ix_repository_activity_project_id", "repository_activity", ["project_id"]),
        ("ix_kpi_snapshots_project_id", "kpi_snapshots", ["project_id"]),
        ("ix_kpi_snapshots_sprint_id", "kpi_snapshots", ["sprint_id"]),
        ("ix_burndown_entries_sprint_id", "burndown_entries", ["sprint_id"]),
    )

    for index_name, table_name, columns in indexes:
        if not _table_exists(bind, table_name) or _index_exists(bind, table_name, index_name):
            continue
        op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    bind = op.get_bind()

    for index_name, table_name in (
        ("ix_burndown_entries_sprint_id", "burndown_entries"),
        ("ix_kpi_snapshots_sprint_id", "kpi_snapshots"),
        ("ix_kpi_snapshots_project_id", "kpi_snapshots"),
        ("ix_repository_activity_project_id", "repository_activity"),
        ("ix_repository_activity_ticket_id", "repository_activity"),
        ("ix_blockers_ticket_id", "blockers"),
        ("ix_tickets_priority", "tickets"),
        ("ix_tickets_status", "tickets"),
        ("ix_tickets_assignee_id", "tickets"),
        ("ix_tickets_sprint_id", "tickets"),
        ("ix_tickets_project_id", "tickets"),
        ("ix_sprints_project_id", "sprints"),
    ):
        if _table_exists(bind, table_name) and _index_exists(bind, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name in (
        "burndown_entries",
        "kpi_snapshots",
        "repository_activity",
        "blockers",
        "tickets",
        "sprints",
        "developers",
        "projects",
    ):
        if _table_exists(bind, table_name):
            op.drop_table(table_name)
