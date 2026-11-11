"""
Circuit Breaker
===============

Classic three-state machine: CLOSED → OPEN → HALF_OPEN → CLOSED

  CLOSED    — all calls pass through; failure counter incremented on error
  OPEN      — calls rejected immediately; re-evaluated after reset_timeout
  HALF_OPEN — one probe call allowed; success → CLOSED, failure → OPEN

Usage
─────
    cb = CircuitBreaker(name="github_api", failure_threshold=5, reset_timeout=60)

    @cb.protect
    async def call_github():
        ...

    # or inline:
    result = await cb.call(some_coro)
"""
from __future__ import annotations

import asyncio
import enum
import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from app.core.exceptions import CircuitBreakerOpenError
from app.core.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Async circuit breaker.

    Args:
        name              — identifier for logging/metrics
        failure_threshold — consecutive failures before opening
        reset_timeout     — seconds to wait before trying half-open
        success_threshold — consecutive successes in half-open to close
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        success_threshold: int = 2,
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_opened_at: float | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, coro: Awaitable[T]) -> T:
        async with self._lock:
            self._maybe_transition_half_open()
            if self._state == CircuitState.OPEN:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry after {self._seconds_until_reset():.0f}s."
                )

        try:
            result = await coro
            async with self._lock:
                self._on_success()
            return result
        except CircuitBreakerOpenError:
            raise
        except Exception as exc:
            async with self._lock:
                self._on_failure(exc)
            raise

    def protect(
        self, func: Callable[..., Awaitable[T]]
    ) -> Callable[..., Awaitable[T]]:
        """Decorator version."""
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await self.call(func(*args, **kwargs))
        return wrapper

    # ── State transitions ────────────────────────────────────────────────────

    def _on_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._success_threshold:
                self._close()
        else:
            self._failure_count = 0

    def _on_failure(self, exc: Exception) -> None:
        self._failure_count += 1
        self._success_count = 0
        logger.warning(
            "circuit_breaker_failure",
            name=self.name,
            failure_count=self._failure_count,
            error=str(exc),
        )
        if self._failure_count >= self._failure_threshold:
            self._open()

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._last_opened_at = time.monotonic()
        logger.error("circuit_breaker_opened", name=self.name)

    def _close(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        logger.info("circuit_breaker_closed", name=self.name)

    def _maybe_transition_half_open(self) -> None:
        if (
            self._state == CircuitState.OPEN
            and self._last_opened_at is not None
            and time.monotonic() - self._last_opened_at >= self._reset_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            self._success_count = 0
            logger.info("circuit_breaker_half_open", name=self.name)

    def _seconds_until_reset(self) -> float:
        if self._last_opened_at is None:
            return 0.0
        return max(
            0.0,
            self._reset_timeout - (time.monotonic() - self._last_opened_at),
        )
