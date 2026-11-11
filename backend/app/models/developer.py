from sqlalchemy import ForeignKey, String, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Developer(Base, TimestampMixin):
    __tablename__ = "developers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    trello_member_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    team: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="developer", nullable=False)
    slack_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    github_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False, server_default='[]')
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    company: Mapped["Company | None"] = relationship("Company", back_populates="developers")  # noqa: F821
    user_account: Mapped["User | None"] = relationship(  # noqa: F821
        "User",
        back_populates="developer",
        uselist=False,
    )
    assigned_tickets: Mapped[list["Ticket"]] = relationship(  # noqa: F821
        "Ticket",
        foreign_keys="Ticket.assignee_id",
        back_populates="assignee",
    )
    reported_tickets: Mapped[list["Ticket"]] = relationship(  # noqa: F821
        "Ticket",
        foreign_keys="Ticket.reporter_id",
        back_populates="reporter",
    )
    assignments: Mapped[list["DeveloperAssignment"]] = relationship(  # noqa: F821
        "DeveloperAssignment",
        back_populates="developer",
        cascade="all, delete-orphan",
    )
    external_identities: Mapped[list["DeveloperExternalIdentity"]] = relationship(  # noqa: F821
        "DeveloperExternalIdentity",
        back_populates="developer",
        cascade="all, delete-orphan",
    )
    visibility_grants: Mapped[list["DeveloperClientVisibility"]] = relationship(
        "DeveloperClientVisibility",
        back_populates="developer",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Developer id={self.id} username={self.username!r}>"

class DeveloperClientVisibility(Base, TimestampMixin):
    """Explicit grant by an ESN to allow a Client to view this Developer's recruiting profile/card."""
    __tablename__ = "developer_client_visibility"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    developer_id: Mapped[int] = mapped_column(ForeignKey("developers.id", ondelete="CASCADE"), nullable=False, index=True)
    client_company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    granted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_developer_approval", nullable=False, index=True)

    developer: Mapped["Developer"] = relationship("Developer", back_populates="visibility_grants")
    client_company: Mapped["Company"] = relationship("Company", foreign_keys=[client_company_id])
