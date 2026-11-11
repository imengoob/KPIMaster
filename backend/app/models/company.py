from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    tenant_type: Mapped[str] = mapped_column(String(30), default="client", nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    users: Mapped[list["User"]] = relationship("User", back_populates="company")  # noqa: F821
    developers: Mapped[list["Developer"]] = relationship("Developer", back_populates="company")  # noqa: F821
    project_links: Mapped[list["CompanyProjectAccess"]] = relationship(
        "CompanyProjectAccess",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    client_engagements: Mapped[list["Engagement"]] = relationship(  # noqa: F821
        "Engagement",
        foreign_keys="Engagement.client_company_id",
        back_populates="client_company",
        cascade="all, delete-orphan",
    )
    vendor_engagements: Mapped[list["Engagement"]] = relationship(  # noqa: F821
        "Engagement",
        foreign_keys="Engagement.vendor_company_id",
        back_populates="vendor_company",
        cascade="all, delete-orphan",
    )
    client_partnerships: Mapped[list["CompanyPartnership"]] = relationship(
        "CompanyPartnership",
        foreign_keys="CompanyPartnership.client_company_id",
        back_populates="client_company",
        cascade="all, delete-orphan",
    )
    vendor_partnerships: Mapped[list["CompanyPartnership"]] = relationship(
        "CompanyPartnership",
        foreign_keys="CompanyPartnership.vendor_company_id",
        back_populates="vendor_company",
        cascade="all, delete-orphan",
    )


class CompanyProjectAccess(Base, TimestampMixin):
    __tablename__ = "company_project_access"
    __table_args__ = (
        UniqueConstraint("company_id", "project_id", name="uq_company_project_access"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    company: Mapped["Company"] = relationship("Company", back_populates="project_links")  # noqa: F821
    project: Mapped["Project"] = relationship("Project", back_populates="company_links")  # noqa: F821

class CompanyPartnership(Base, TimestampMixin):
    """Tracks B2B approval so a client can legally request ESN visibility/resources outside a project"""
    __tablename__ = "company_partnerships"
    __table_args__ = (
        UniqueConstraint("client_company_id", "vendor_company_id", name="uq_client_vendor_partnership"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    vendor_company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False) # 'pending', 'active', 'rejected'

    client_company: Mapped["Company"] = relationship(
        "Company",
        foreign_keys=[client_company_id],
        back_populates="client_partnerships",
    )
    vendor_company: Mapped["Company"] = relationship(
        "Company",
        foreign_keys=[vendor_company_id],
        back_populates="vendor_partnerships",
    )
