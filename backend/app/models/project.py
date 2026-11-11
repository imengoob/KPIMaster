from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    repository_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    slack_channel: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    sprints: Mapped[list["Sprint"]] = relationship(  # noqa: F821
        "Sprint", back_populates="project", cascade="all, delete-orphan"
    )
    tickets: Mapped[list["Ticket"]] = relationship(  # noqa: F821
        "Ticket", back_populates="project", cascade="all, delete-orphan"
    )
    kpi_snapshots: Mapped[list["KPISnapshot"]] = relationship(  # noqa: F821
        "KPISnapshot", back_populates="project", cascade="all, delete-orphan"
    )
    company_links: Mapped[list["CompanyProjectAccess"]] = relationship(  # noqa: F821
        "CompanyProjectAccess",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    engagements: Mapped[list["Engagement"]] = relationship(  # noqa: F821
        "Engagement",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} key={self.key!r}>"
