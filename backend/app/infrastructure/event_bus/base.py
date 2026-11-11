"""
Event Bus abstraction.

All event bus implementations must satisfy this interface.
Consumers register handlers by event_type pattern.

Pattern: "ticket.*" matches "ticket.updated", "ticket.stalled", etc.
Pattern: "*"        matches all events.
"""
from __future__ import annotations

import abc
import asyncio
import fnmatch
from collections import defaultdict
from typing import Awaitable, Callable

from app.domain.events.base import BaseEvent

EventHandler = Callable[[BaseEvent], Awaitable[None]]


class AbstractEventBus(abc.ABC):
    @abc.abstractmethod
    async def publish(self, event: BaseEvent) -> None:
        """Publish an event to the bus."""
        ...

    @abc.abstractmethod
    async def subscribe(self, pattern: str, handler: EventHandler) -> None:
        """Register a handler for events matching a glob pattern."""
        ...

    @abc.abstractmethod
    async def start(self) -> None:
        """Start consuming (open connections, spawn listener tasks)."""
        ...

    @abc.abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down."""
        ...

    def _match_handlers(
        self,
        event_type: str,
        handlers: dict[str, list[EventHandler]],
    ) -> list[EventHandler]:
        matched: list[EventHandler] = []
        for pattern, handler_list in handlers.items():
            if fnmatch.fnmatch(event_type, pattern):
                matched.extend(handler_list)
        return matched
