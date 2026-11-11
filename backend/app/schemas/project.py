from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import OrmBase


class ProjectCreate(OrmBase):
    name: str = Field(..., min_length=2, max_length=255)
    key: str = Field(..., min_length=2, max_length=10, pattern=r"^[A-Z0-9]+$")
    description: str | None = None
    repository_url: str | None = None
    slack_channel: str | None = None

    @field_validator("key")
    @classmethod
    def key_uppercase(cls, v: str) -> str:
        return v.upper()


class ProjectUpdate(OrmBase):
    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = None
    repository_url: str | None = None
    slack_channel: str | None = None
    is_active: bool | None = None


class ProjectResponse(OrmBase):
    id: int
    name: str
    key: str
    description: str | None
    repository_url: str | None
    slack_channel: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProjectSummary(OrmBase):
    """Lightweight projection used in list responses."""

    id: int
    name: str
    key: str
    is_active: bool
