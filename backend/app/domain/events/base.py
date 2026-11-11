"""
Domain event base classes.

Every event is an immutable Pydantic model. Events are serialised to JSON
before being written to the event bus, and deserialised on consumption.

Events use a flat hierarchy: BaseEvent → concrete event.
"""
import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    """
    Root for all domain events.

    Fields:
        event_id   — unique identifier; used for idempotency checks.
        event_type — dot-separated name (e.g. "ticket.stalled").
        occurred_at — wall-clock time the event was raised.
        version    — schema version; consumers reject mismatched versions.
        payload    — arbitrary event data; set by concrete sub-classes.
    """

    model_config = {"frozen": True}  # Events are immutable

    EVENT_TYPE: ClassVar[str] = "base.event"
    EVENT_VERSION: ClassVar[int] = 1

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = Field(default="")
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: int = 1

    def model_post_init(self, __context: Any) -> None:
        # Backfill event_type from the class-level constant
        if not self.event_type:
            object.__setattr__(self, "event_type", self.__class__.EVENT_TYPE)
        if self.version == 1:
            object.__setattr__(self, "version", self.__class__.EVENT_VERSION)

    def to_bus_payload(self) -> str:
        """Serialise to JSON string for the event bus."""
        return self.model_dump_json()

    @classmethod
    def from_bus_payload(cls, raw: str) -> "BaseEvent":
        return cls.model_validate_json(raw)
