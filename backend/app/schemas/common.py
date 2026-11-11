"""Shared schema primitives."""
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class OrmBase(BaseModel):
    """Base for all schemas that map from ORM models."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 50

    @property
    def pages(self) -> int:
        if self.page_size == 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size


class HealthResponse(BaseModel):
    status: str
    version: str
    database: bool
    redis: bool
    timestamp: datetime
