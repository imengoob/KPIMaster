"""
Microsoft Graph API client (Planner + To Do).

Covers
──────
  • Microsoft Planner: plans, tasks, buckets (team-oriented, sprint tracking)
  • Microsoft To Do:   task lists, tasks (personal tasks)
  • Graph subscriptions for real-time change notifications

Auth: OAuth 2.0 Bearer token  (access_token from MicrosoftOAuth)
Docs: https://learn.microsoft.com/en-us/graph/api/overview
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Awaitable
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.logging_config import get_logger
from app.infrastructure.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class MicrosoftGraphClient:
    """
    Async Microsoft Graph API client with retry and 429 back-off.

    Parameters
    ──────────
    access_token  — OAuth 2.0 Bearer token from Microsoft identity platform
    refresh_cb    — async callable() → new access_token  (called on 401)
    """

    def __init__(
        self,
        access_token: str,
        refresh_cb:   Callable[[], Awaitable[str]] | None = None,
    ) -> None:
        self._token   = access_token
        self._refresh = refresh_cb
        self._http    = httpx.AsyncClient(timeout=30.0)
        self._cb      = CircuitBreaker(
            failure_threshold=5,
            success_threshold=2,
            name="microsoft_graph",
        )

    # ── Core HTTP ─────────────────────────────────────────────────────────────

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }
        if extra:
            h.update(extra)
        return h

    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=30),
        reraise=True,
    )
    async def _request(
        self,
        method:  str,
        path:    str,
        extra_headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any] | None:
        if not self._cb.allow_request():
            raise RuntimeError("MicrosoftGraphClient circuit breaker open")

        url = f"{_GRAPH_BASE}{path}" if not path.startswith("http") else path

        try:
            resp = await self._http.request(
                method, url, headers=self._headers(extra_headers), **kwargs
            )

            if resp.status_code == 401 and self._refresh:
                logger.info("graph.token_expired")
                self._token = await self._refresh()
                resp = await self._http.request(
                    method, url, headers=self._headers(extra_headers), **kwargs
                )

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 60))
                logger.warning("graph.rate_limited", retry_after=retry_after)
                await asyncio.sleep(retry_after)
                resp = await self._http.request(
                    method, url, headers=self._headers(extra_headers), **kwargs
                )

            if resp.status_code == 204:
                self._cb.record_success()
                return None  # No content

            resp.raise_for_status()
            self._cb.record_success()
            return resp.json()

        except httpx.HTTPStatusError as exc:
            self._cb.record_failure()
            logger.error(
                "graph.http_error",
                status=exc.response.status_code,
                path=path,
                body=exc.response.text[:200],
            )
            raise

    # ── User ─────────────────────────────────────────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        data = await self._request("GET", "/me")
        assert isinstance(data, dict)
        return data

    # ── Planner Plans ─────────────────────────────────────────────────────────

    async def get_my_plans(self) -> list[dict[str, Any]]:
        """GET /me/planner/plans — all plans accessible by the user."""
        data = await self._request("GET", "/me/planner/plans")
        assert isinstance(data, dict)
        return data.get("value", [])

    async def get_group_plans(self, group_id: str) -> list[dict[str, Any]]:
        """GET /groups/{groupId}/planner/plans — plans in a team."""
        data = await self._request("GET", f"/groups/{group_id}/planner/plans")
        assert isinstance(data, dict)
        return data.get("value", [])

    async def get_plan(self, plan_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/planner/plans/{plan_id}")
        assert isinstance(data, dict)
        return data

    # ── Planner Buckets ───────────────────────────────────────────────────────

    async def get_buckets(self, plan_id: str) -> list[dict[str, Any]]:
        """GET /planner/plans/{planId}/buckets — columns/stages in a plan."""
        data = await self._request("GET", f"/planner/plans/{plan_id}/buckets")
        assert isinstance(data, dict)
        return data.get("value", [])

    # ── Planner Tasks ─────────────────────────────────────────────────────────

    async def get_plan_tasks(self, plan_id: str) -> list[dict[str, Any]]:
        """GET /planner/plans/{planId}/tasks — all tasks in a plan."""
        data = await self._request("GET", f"/planner/plans/{plan_id}/tasks")
        assert isinstance(data, dict)
        return data.get("value", [])

    async def get_my_tasks(self) -> list[dict[str, Any]]:
        """GET /me/planner/tasks — tasks assigned to the user."""
        data = await self._request("GET", "/me/planner/tasks")
        assert isinstance(data, dict)
        return data.get("value", [])

    async def get_task(self, task_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/planner/tasks/{task_id}")
        assert isinstance(data, dict)
        return data

    async def get_task_details(self, task_id: str) -> dict[str, Any]:
        """GET /planner/tasks/{taskId}/details — description, checklist, references."""
        data = await self._request("GET", f"/planner/tasks/{task_id}/details")
        assert isinstance(data, dict)
        return data

    async def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /planner/tasks"""
        data = await self._request("POST", "/planner/tasks", json=payload)
        assert isinstance(data, dict)
        return data

    async def update_task(
        self,
        task_id: str,
        etag:    str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        PATCH /planner/tasks/{taskId}
        Requires If-Match: {etag} header — Planner enforces optimistic concurrency.
        """
        data = await self._request(
            "PATCH",
            f"/planner/tasks/{task_id}",
            extra_headers={"If-Match": etag},
            json=payload,
        )
        assert isinstance(data, dict)
        return data

    # ── Microsoft To Do ───────────────────────────────────────────────────────

    async def get_todo_lists(self) -> list[dict[str, Any]]:
        """GET /me/todo/lists"""
        data = await self._request("GET", "/me/todo/lists")
        assert isinstance(data, dict)
        return data.get("value", [])

    async def get_todo_tasks(self, list_id: str) -> list[dict[str, Any]]:
        """GET /me/todo/lists/{listId}/tasks"""
        data = await self._request("GET", f"/me/todo/lists/{list_id}/tasks")
        assert isinstance(data, dict)
        return data.get("value", [])

    async def create_todo_task(self, list_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", f"/me/todo/lists/{list_id}/tasks", json=payload)
        assert isinstance(data, dict)
        return data

    # ── Graph Subscriptions (real-time webhooks) ──────────────────────────────

    async def create_subscription(
        self,
        change_type:         str,
        notification_url:    str,
        resource:            str,
        expiration_datetime: str,
        client_state:        str = "",
    ) -> dict[str, Any]:
        """
        POST /subscriptions — register a real-time Graph notification.

        resource examples:
          "me/planner/tasks"
          "groups/{id}/planner/plans"
          "/users/{id}/todo/lists/{listId}/tasks"

        change_type: "created,updated,deleted"
        expiration_datetime: ISO 8601, max 4230 minutes from now for Planner.
        """
        payload = {
            "changeType":          change_type,
            "notificationUrl":     notification_url,
            "resource":            resource,
            "expirationDateTime":  expiration_datetime,
        }
        if client_state:
            payload["clientState"] = client_state
        data = await self._request("POST", "/subscriptions", json=payload)
        assert isinstance(data, dict)
        return data

    async def renew_subscription(self, subscription_id: str, expiration_datetime: str) -> dict[str, Any]:
        data = await self._request(
            "PATCH",
            f"/subscriptions/{subscription_id}",
            json={"expirationDateTime": expiration_datetime},
        )
        assert isinstance(data, dict)
        return data

    async def delete_subscription(self, subscription_id: str) -> None:
        await self._request("DELETE", f"/subscriptions/{subscription_id}")

    # ── Groups (teams) ────────────────────────────────────────────────────────

    async def get_joined_groups(self) -> list[dict[str, Any]]:
        """GET /me/joinedTeams — Microsoft Teams that the user belongs to."""
        data = await self._request("GET", "/me/joinedTeams")
        assert isinstance(data, dict)
        return data.get("value", [])

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "MicrosoftGraphClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def validate(self) -> bool:
        """Probe /me — cheap credential check."""
        try:
            data = await self.get_me()
            return bool(data.get("id"))
        except Exception:
            return False
