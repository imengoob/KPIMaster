"""
Trello REST API client.

Responsibilities
────────────────
1. Auth — appends key/token to every request
2. Rate limiting — sliding-window counter in Redis; backs off at 280/10s
   (Trello hard limit is 300/10s)
3. Retry — exponential back-off with jitter via tenacity
4. Circuit Breaker — stops hammering Trello when it's unhealthy
5. Pagination — transparently fetches all pages via the `before` cursor

Usage
─────
    from app.services.trello.client import TrelloClient

    async with TrelloClient(api_key="...", api_token="...") as client:
        board = await client.get_board("abc123")
        cards = await client.get_board_cards("abc123")
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TypeVar

import httpx
import redis.asyncio as aioredis

from app.config import settings
from app.core.exceptions import InfrastructureError
from app.core.logging_config import get_logger
from app.infrastructure.circuit_breaker import CircuitBreaker
from app.infrastructure.retry import retry_async
from app.schemas.trello import (
    TrelloAPIAction,
    TrelloAPIBoard,
    TrelloAPICard,
    TrelloAPIList,
    TrelloAPIMember,
)

logger = get_logger(__name__)

BASE_URL = "https://api.trello.com/1"
# Stay under Trello's 300/10s rate limit with a safety margin
_RATE_LIMIT_MAX = 280
_RATE_LIMIT_WINDOW = 10          # seconds
_RATE_LIMIT_REDIS_KEY = "trello:rate_limit:{key}"

T = TypeVar("T")


class TrelloRateLimiter:
    """
    Sliding-window rate limiter backed by Redis.

    If Redis is unavailable falls back to in-process asyncio.sleep.
    Each API key has its own counter (multiple tokens share the key budget).
    """

    def __init__(self, redis_url: str, api_key: str) -> None:
        self._redis_url = redis_url
        self._key = _RATE_LIMIT_REDIS_KEY.format(key=api_key[:8])  # prefix only
        self._redis: aioredis.Redis | None = None
        # Fallback in-process token bucket
        self._tokens = _RATE_LIMIT_MAX
        self._last_refill = time.monotonic()

    async def _get_redis(self) -> aioredis.Redis | None:
        if self._redis is None:
            try:
                self._redis = await aioredis.from_url(self._redis_url, decode_responses=True)
            except Exception:
                pass
        return self._redis

    async def acquire(self) -> None:
        """Block until a request slot is available."""
        redis = await self._get_redis()
        if redis:
            await self._redis_acquire(redis)
        else:
            await self._local_acquire()

    async def _redis_acquire(self, redis: aioredis.Redis) -> None:
        while True:
            now_ms = int(time.time() * 1000)
            window_start = now_ms - (_RATE_LIMIT_WINDOW * 1000)

            pipe = redis.pipeline()
            pipe.zremrangebyscore(self._key, "-inf", window_start)
            pipe.zcard(self._key)
            pipe.zadd(self._key, {str(now_ms): now_ms})
            pipe.expire(self._key, _RATE_LIMIT_WINDOW + 1)
            _, count, *_ = await pipe.execute()

            if count < _RATE_LIMIT_MAX:
                return

            # Back off for remaining window
            oldest = await redis.zrange(self._key, 0, 0, withscores=True)
            if oldest:
                wait_ms = (_RATE_LIMIT_WINDOW * 1000) - (now_ms - oldest[0][1])
                await asyncio.sleep(max(0.05, wait_ms / 1000))
            else:
                await asyncio.sleep(0.1)

    async def _local_acquire(self) -> None:
        """Simple token bucket fallback."""
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                _RATE_LIMIT_MAX,
                self._tokens + elapsed * (_RATE_LIMIT_MAX / _RATE_LIMIT_WINDOW),
            )
            self._last_refill = now
            if self._tokens >= 1:
                self._tokens -= 1
                return
            await asyncio.sleep(0.05)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


class TrelloClient:
    """
    Async Trello API client.

    Thread-safe; share a single instance per credential set per process.
    """

    _circuit_breaker = CircuitBreaker(
        name="trello_api",
        failure_threshold=5,
        reset_timeout=60.0,
        success_threshold=2,
    )

    def __init__(
        self,
        api_key: str,
        api_token: str,
        redis_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._key = api_key
        self._token = api_token
        self._rate_limiter = TrelloRateLimiter(redis_url or settings.redis_url, api_key)
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(timeout),
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )

    async def __aenter__(self) -> "TrelloClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()
        await self._rate_limiter.close()

    # ── Core request helper ───────────────────────────────────────────────────

    @retry_async(
        max_attempts=3,
        base_delay=1.0,
        max_delay=30.0,
        retry_on=(httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError),
    )
    async def _get(self, path: str, **params: Any) -> Any:
        await self._rate_limiter.acquire()
        params.update(key=self._key, token=self._token)

        async def _do_request() -> Any:
            resp = await self._http.get(path, params=params)
            if resp.status_code == 401:
                raise InfrastructureError("Trello authentication failed — check API key/token")
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "5"))
                logger.warning("trello_rate_limited", retry_after=retry_after)
                await asyncio.sleep(retry_after)
                raise httpx.TimeoutException("Rate limited")  # trigger retry
            if resp.status_code == 404:
                raise InfrastructureError(f"Trello resource not found: {path}")
            resp.raise_for_status()
            return resp.json()

        return await self._circuit_breaker.call(_do_request())

    @retry_async(max_attempts=3, base_delay=1.0, max_delay=30.0)
    async def _post(self, path: str, json: dict | None = None, **params: Any) -> Any:
        await self._rate_limiter.acquire()
        params.update(key=self._key, token=self._token)

        async def _do() -> Any:
            resp = await self._http.post(path, params=params, json=json or {})
            resp.raise_for_status()
            return resp.json()

        return await self._circuit_breaker.call(_do())

    @retry_async(max_attempts=2, base_delay=1.0)
    async def _delete(self, path: str, **params: Any) -> None:
        await self._rate_limiter.acquire()
        params.update(key=self._key, token=self._token)
        resp = await self._http.delete(path, params=params)
        resp.raise_for_status()

    # ── Pagination helper ─────────────────────────────────────────────────────

    async def _get_paginated(
        self, path: str, page_size: int = 1000, **params: Any
    ) -> list[dict]:
        """Fetches all pages using the `before` cursor (oldest action id)."""
        results: list[dict] = []
        before: str | None = None

        while True:
            kw = dict(params)
            kw["limit"] = page_size
            if before:
                kw["before"] = before
            page: list[dict] = await self._get(path, **kw)
            if not page:
                break
            results.extend(page)
            if len(page) < page_size:
                break
            before = page[-1]["id"]  # cursor: oldest id in this page

        return results

    # ── Public methods ────────────────────────────────────────────────────────

    async def get_me(self) -> TrelloAPIMember:
        data = await self._get("/members/me")
        return TrelloAPIMember.model_validate(data)

    async def get_my_boards(self) -> list[TrelloAPIBoard]:
        data = await self._get("/members/me/boards", fields="id,name,desc,shortUrl,closed,idOrganization")
        return [TrelloAPIBoard.model_validate(b) for b in data]

    async def get_board_members(self, board_id: str) -> list[TrelloAPIMember]:
        data = await self._get(
            f"/boards/{board_id}/members",
            fields="id,fullName,username,avatarUrl",
        )
        return [TrelloAPIMember.model_validate(member) for member in data]

    async def get_board(self, board_id: str) -> TrelloAPIBoard:
        data = await self._get(f"/boards/{board_id}", fields="id,name,desc,shortUrl,closed,idOrganization")
        return TrelloAPIBoard.model_validate(data)

    async def get_board_lists(self, board_id: str) -> list[TrelloAPIList]:
        data = await self._get(
            f"/boards/{board_id}/lists",
            filter="all",
            fields="id,name,closed,pos,idBoard",
        )
        return [TrelloAPIList.model_validate(lst) for lst in data]

    async def get_board_cards(
        self, board_id: str, include_closed: bool = False
    ) -> list[TrelloAPICard]:
        filter_ = "all" if include_closed else "open"
        data = await self._get(
            f"/boards/{board_id}/cards/{filter_}",
            fields="id,idShort,name,desc,idList,idBoard,idMembers,labels,due,dueComplete,closed,dateLastActivity",
        )
        return [TrelloAPICard.model_validate(c) for c in data]

    async def get_board_actions(
        self,
        board_id: str,
        since: str | None = None,
        action_filter: str = "createCard,updateCard,commentCard,deleteCard,addMemberToCard,removeMemberFromCard,addLabelToCard,moveCardToBoard,moveCardFromBoard",
    ) -> list[TrelloAPIAction]:
        """Fetch board-level actions, newest first, paginated."""
        params: dict[str, Any] = {
            "filter": action_filter,
            "fields": "id,type,date,data,idMemberCreator,memberCreator",
            "memberCreator_fields": "id,fullName,username",
            "limit": 1000,
        }
        if since:
            params["since"] = since

        data = await self._get_paginated(f"/boards/{board_id}/actions", **params)
        return [TrelloAPIAction.model_validate(a) for a in data]

    async def get_card_actions(
        self, card_id: str, since: str | None = None
    ) -> list[TrelloAPIAction]:
        params: dict[str, Any] = {
            "filter": "createCard,updateCard,commentCard",
            "fields": "id,type,date,data,idMemberCreator,memberCreator",
            "limit": 1000,
        }
        if since:
            params["since"] = since
        data = await self._get_paginated(f"/cards/{card_id}/actions", **params)
        return [TrelloAPIAction.model_validate(a) for a in data]

    async def register_webhook(
        self, callback_url: str, model_id: str, description: str = "KPIMaster"
    ) -> dict:
        return await self._post(
            "/webhooks",
            json={
                "callbackURL": callback_url,
                "idModel": model_id,
                "description": description,
            },
        )

    async def delete_webhook(self, webhook_id: str) -> None:
        await self._delete(f"/webhooks/{webhook_id}")

    async def get_webhook(self, webhook_id: str) -> dict:
        return await self._get(f"/webhooks/{webhook_id}")

    # ── Webhook signature verification ───────────────────────────────────────

    @staticmethod
    def verify_webhook_signature(
        body: bytes,
        callback_url: str,
        x_trello_webhook: str,
        api_secret: str,
    ) -> bool:
        """
        Trello signs webhooks with HMAC-SHA1 over (body + callbackURL).
        The signature is base64-encoded and sent in X-Trello-Webhook header.
        """
        import base64

        content = body + callback_url.encode()
        expected = base64.b64encode(
            hmac.new(api_secret.encode(), content, hashlib.sha1).digest()
        ).decode()
        return hmac.compare_digest(expected, x_trello_webhook)
