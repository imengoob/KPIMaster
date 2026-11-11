"""Add tenant types, engagements, and developer assignments

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("tenant_type", sa.String(length=30), nullable=False, server_default="client"),
    )
    op.create_index("ix_companies_tenant_type", "companies", ["tenant_type"], unique=False)

    op.create_table(
        "engagements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("client_company_id", sa.Integer(), nullable=False),
        sa.Column("vendor_company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("sla_response_hours", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("client_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["client_company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_engagements_status", "engagements", ["status"], unique=False)
    op.create_index("ix_engagements_client_company_id", "engagements", ["client_company_id"], unique=False)
    op.create_index("ix_engagements_vendor_company_id", "engagements", ["vendor_company_id"], unique=False)
    op.create_index("ix_engagements_project_id", "engagements", ["project_id"], unique=False)

    op.create_table(
        "developer_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("developer_id", sa.Integer(), nullable=False),
        sa.Column("engagement_id", sa.Integer(), nullable=False),
        sa.Column("assignment_role", sa.String(length=100), nullable=False, server_default="developer"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("allocation_percentage", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["developer_id"], ["developers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "developer_id",
            "engagement_id",
            "start_date",
            name="uq_developer_assignment_engagement_start",
        ),
    )
    op.create_index(
        "ix_developer_assignments_developer_id",
        "developer_assignments",
        ["developer_id"],
        unique=False,
    )
    op.create_index(
        "ix_developer_assignments_engagement_id",
        "developer_assignments",
        ["engagement_id"],
        unique=False,
    )
    op.create_index(
        "ix_developer_assignments_status",
        "developer_assignments",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_developer_assignments_status", table_name="developer_assignments")
    op.drop_index("ix_developer_assignments_engagement_id", table_name="developer_assignments")
    op.drop_index("ix_developer_assignments_developer_id", table_name="developer_assignments")
    op.drop_table("developer_assignments")

    op.drop_index("ix_engagements_project_id", table_name="engagements")
    op.drop_index("ix_engagements_vendor_company_id", table_name="engagements")
    op.drop_index("ix_engagements_client_company_id", table_name="engagements")
    op.drop_index("ix_engagements_status", table_name="engagements")
    op.drop_table("engagements")

    op.drop_index("ix_companies_tenant_type", table_name="companies")
    op.drop_column("companies", "tenant_type")
