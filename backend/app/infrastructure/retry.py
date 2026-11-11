"""
Retry utility with exponential backoff + full jitter.

Uses tenacity under the hood, wrapped in a clean async decorator.

Usage
─────
    @retry_async(max_attempts=3, base_delay=1.0)
    async def call_external_api():
        ...

    # Or with a custom retry condition:
    @retry_async(
        max_attempts=5,
        retry_on=(httpx.TimeoutException, httpx.NetworkError),
    )
    async def flaky_call():
        ...
"""
from __future__ import annotations

import functools
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from tenacity import (
    AsyncRetrying,
    RetryError,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.logging_config import get_logger

logger = get_logger(__name__)
T = TypeVar("T")


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator factory for async functions.

    Args:
        max_attempts  — total attempts (including the first)
        base_delay    — base seconds for exponential backoff
        max_delay     — cap on wait time between retries
        jitter        — random jitter range (seconds)
        retry_on      — exception types that trigger a retry
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential_jitter(
                    initial=base_delay,
                    max=max_delay,
                    jitter=jitter,
                ),
                retry=retry_if_exception_type(retry_on),
                before_sleep=before_sleep_log(
                    logging.getLogger(func.__module__), logging.WARNING
                ),
                reraise=True,
            ):
                with attempt:
                    return await func(*args, **kwargs)
            # Should never reach here due to reraise=True
            raise RuntimeError("retry_async: unexpected state")

        return wrapper

    return decorator
