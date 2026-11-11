from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Engagement(Base, TimestampMixin):
    __tablename__ = "engagements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)
    client_company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vendor_company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    sla_response_hours: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    client_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    client_company: Mapped["Company"] = relationship(
        "Company",
        foreign_keys=[client_company_id],
        back_populates="client_engagements",
    )
    vendor_company: Mapped["Company"] = relationship(
        "Company",
        foreign_keys=[vendor_company_id],
        back_populates="vendor_engagements",
    )
    project: Mapped["Project"] = relationship("Project", back_populates="engagements")  # noqa: F821
    assignments: Mapped[list["DeveloperAssignment"]] = relationship(
        "DeveloperAssignment",
        back_populates="engagement",
        cascade="all, delete-orphan",
    )


class DeveloperAssignment(Base, TimestampMixin):
    __tablename__ = "developer_assignments"
    __table_args__ = (
        UniqueConstraint(
            "developer_id",
            "engagement_id",
            "start_date",
            name="uq_developer_assignment_engagement_start",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    developer_id: Mapped[int] = mapped_column(
        ForeignKey("developers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    engagement_id: Mapped[int] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignment_role: Mapped[str] = mapped_column(String(100), default="developer", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)
    allocation_percentage: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    developer: Mapped["Developer"] = relationship("Developer", back_populates="assignments")  # noqa: F821
    engagement: Mapped["Engagement"] = relationship("Engagement", back_populates="assignments")
