from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class IntegrationTask(Base, TimestampMixin):
    __tablename__ = "integration_tasks"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "board_id",
            "external_task_id",
            name="uq_integration_task_external",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("integration_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sprint_id: Mapped[int | None] = mapped_column(
        ForeignKey("sprints.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    board_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    external_task_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, default="task")
    assignee_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    labels: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    story_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    raw: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    account: Mapped["IntegrationAccount"] = relationship(  # noqa: F821
        "IntegrationAccount",
        back_populates="tasks",
    )
    comments: Mapped[list["IntegrationComment"]] = relationship(  # noqa: F821
        "IntegrationComment",
        back_populates="task",
        cascade="all, delete-orphan",
    )


class IntegrationComment(Base, TimestampMixin):
    __tablename__ = "integration_comments"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "external_comment_id",
            name="uq_integration_comment_external",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("integration_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("integration_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_comment_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    external_task_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    author_external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    author_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    external_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    task: Mapped["IntegrationTask"] = relationship(  # noqa: F821
        "IntegrationTask",
        back_populates="comments",
    )
    account: Mapped["IntegrationAccount"] = relationship(  # noqa: F821
        "IntegrationAccount",
        back_populates="comments",
    )
