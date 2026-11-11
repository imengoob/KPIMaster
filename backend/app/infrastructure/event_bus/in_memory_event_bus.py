"""
In-memory event bus — used in development and testing.

Events are dispatched synchronously within the same process.
Not suitable for multi-process deployments.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict

from app.core.logging_config import get_logger
from app.core.metrics import EVENTS_PUBLISHED_TOTAL
from app.domain.events.base import BaseEvent
from app.infrastructure.event_bus.base import AbstractEventBus, EventHandler

logger = get_logger(__name__)


class InMemoryEventBus(AbstractEventBus):
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._started = False

    async def publish(self, event: BaseEvent) -> None:
        EVENTS_PUBLISHED_TOTAL.labels(event_type=event.event_type).inc()
        handlers = self._match_handlers(event.event_type, self._handlers)

        if not handlers:
            logger.debug("event_no_handlers", event_type=event.event_type)
            return

        logger.debug(
            "event_published",
            event_type=event.event_type,
            event_id=event.event_id,
            handlers=len(handlers),
        )

        # Dispatch all handlers concurrently; log but don't swallow errors
        results = await asyncio.gather(
            *[h(event) for h in handlers], return_exceptions=True
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "event_handler_failed",
                    event_type=event.event_type,
                    handler=handlers[i].__qualname__,
                    error=str(result),
                )

    async def subscribe(self, pattern: str, handler: EventHandler) -> None:
        self._handlers[pattern].append(handler)
        logger.debug("event_handler_registered", pattern=pattern, handler=handler.__qualname__)

    async def start(self) -> None:
        self._started = True
        logger.info("in_memory_event_bus_started")

    async def stop(self) -> None:
        self._started = False
        self._handlers.clear()
        logger.info("in_memory_event_bus_stopped")
