"""
Redis Pub/Sub Event Bus — production implementation.

Architecture
────────────
  Publisher  → redis.publish("sprintpulse:events", json_payload)
  Consumer   → redis.subscribe("sprintpulse:events") in a background task
               → deserialise → dispatch to registered handlers

The bus runs a single background asyncio task that listens on the Redis
channel and fans out to all matching handlers in the same process.

For multi-process fan-out (multiple API pods), all pods subscribe to the
same Redis channel — each receives every event.  Handlers must be
idempotent (use event_id for deduplication where needed).
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict

import redis.asyncio as aioredis

from app.config import settings
from app.core.logging_config import get_logger
from app.core.metrics import EVENTS_PUBLISHED_TOTAL
from app.domain.events.base import BaseEvent
from app.domain.events.ticket_events import (
    BlockerDetectedEvent,
    BlockerEscalatedEvent,
    RepoActivityUpdatedEvent,
    TicketStalledEvent,
    TicketUpdatedEvent,
)
from app.domain.events.sprint_events import (
    SprintCompletedEvent,
    SprintHealthDegradedEvent,
    SprintStartedEvent,
)
from app.infrastructure.event_bus.base import AbstractEventBus, EventHandler

logger = get_logger(__name__)

# Registry: event_type → Pydantic model class
_EVENT_TYPE_MAP: dict[str, type[BaseEvent]] = {
    "ticket.updated": TicketUpdatedEvent,
    "ticket.stalled": TicketStalledEvent,
    "blocker.detected": BlockerDetectedEvent,
    "blocker.escalated": BlockerEscalatedEvent,
    "repo.activity.updated": RepoActivityUpdatedEvent,
    "sprint.started": SprintStartedEvent,
    "sprint.completed": SprintCompletedEvent,
    "sprint.health_degraded": SprintHealthDegradedEvent,
}

_CHANNEL = f"{settings.redis_pubsub_channel_prefix}:events"


class RedisEventBus(AbstractEventBus):
    def __init__(self, redis_url: str = settings.redis_url) -> None:
        self._redis_url = redis_url
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._client: aioredis.Redis | None = None
        self._listener_task: asyncio.Task | None = None

    async def publish(self, event: BaseEvent) -> None:
        if self._client is None:
            raise RuntimeError("RedisEventBus not started. Call start() first.")

        payload = event.to_bus_payload()
        await self._client.publish(_CHANNEL, payload)

        EVENTS_PUBLISHED_TOTAL.labels(event_type=event.event_type).inc()
        logger.debug(
            "event_published_redis",
            event_type=event.event_type,
            event_id=event.event_id,
            channel=_CHANNEL,
        )

    async def subscribe(self, pattern: str, handler: EventHandler) -> None:
        self._handlers[pattern].append(handler)

    async def start(self) -> None:
        self._client = aioredis.from_url(
            self._redis_url, decode_responses=True, max_connections=10
        )
        self._listener_task = asyncio.create_task(
            self._listener_loop(), name="redis_event_bus_listener"
        )
        logger.info("redis_event_bus_started", channel=_CHANNEL)

    async def stop(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
        logger.info("redis_event_bus_stopped")

    # ── Internal listener ────────────────────────────────────────────────────

    async def _listener_loop(self) -> None:
        """Long-running task: subscribe → receive → dispatch."""
        pubsub = self._client.pubsub()  # type: ignore[union-attr]
        await pubsub.subscribe(_CHANNEL)
        logger.info("redis_pubsub_subscribed", channel=_CHANNEL)

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                await self._dispatch(message["data"])
        except asyncio.CancelledError:
            logger.info("redis_pubsub_listener_cancelled")
        except Exception as exc:
            logger.error("redis_pubsub_listener_error", error=str(exc))
        finally:
            await pubsub.unsubscribe(_CHANNEL)
            await pubsub.aclose()

    async def _dispatch(self, raw: str) -> None:
        try:
            data = json.loads(raw)
            event_type = data.get("event_type", "")
            model_class = _EVENT_TYPE_MAP.get(event_type, BaseEvent)
            event = model_class.model_validate(data)
        except Exception as exc:
            logger.error("event_deserialisation_failed", raw=raw[:200], error=str(exc))
            return

        handlers = self._match_handlers(event.event_type, self._handlers)
        if not handlers:
            return

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
