"""Add companies, RBAC columns, and project visibility links

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_companies_slug", "companies", ["slug"], unique=True)

    op.create_table(
        "company_project_access",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "project_id", name="uq_company_project_access"),
    )
    op.create_index("ix_company_project_access_company_id", "company_project_access", ["company_id"], unique=False)
    op.create_index("ix_company_project_access_project_id", "company_project_access", ["project_id"], unique=False)

    op.add_column("developers", sa.Column("company_id", sa.Integer(), nullable=True))
    op.add_column("developers", sa.Column("trello_member_id", sa.String(length=100), nullable=True))
    op.create_index("ix_developers_company_id", "developers", ["company_id"], unique=False)
    op.create_index("ix_developers_trello_member_id", "developers", ["trello_member_id"], unique=False)
    op.create_foreign_key(None, "developers", "companies", ["company_id"], ["id"])

    op.add_column("users", sa.Column("role", sa.String(length=50), nullable=False, server_default="company_admin"))
    op.add_column("users", sa.Column("company_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("developer_id", sa.Integer(), nullable=True))
    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.create_index("ix_users_company_id", "users", ["company_id"], unique=False)
    op.create_index("ix_users_developer_id", "users", ["developer_id"], unique=True)
    op.create_foreign_key(None, "users", "companies", ["company_id"], ["id"])
    op.create_foreign_key(None, "users", "developers", ["developer_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint(None, "users", type_="foreignkey")
    op.drop_constraint(None, "users", type_="foreignkey")
    op.drop_index("ix_users_developer_id", table_name="users")
    op.drop_index("ix_users_company_id", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "developer_id")
    op.drop_column("users", "company_id")
    op.drop_column("users", "role")

    op.drop_constraint(None, "developers", type_="foreignkey")
    op.drop_index("ix_developers_trello_member_id", table_name="developers")
    op.drop_index("ix_developers_company_id", table_name="developers")
    op.drop_column("developers", "trello_member_id")
    op.drop_column("developers", "company_id")

    op.drop_index("ix_company_project_access_project_id", table_name="company_project_access")
    op.drop_index("ix_company_project_access_company_id", table_name="company_project_access")
    op.drop_table("company_project_access")

    op.drop_index("ix_companies_slug", table_name="companies")
    op.drop_table("companies")
