"""
Jira Cloud REST API v3 client.

Features
────────
  • Bearer-token auth (OAuth 2.0 access token)
  • Automatic access-token refresh before expiry (via refresh callback)
  • Rate-limit awareness: 429 → exponential back-off
  • Retry with jitter via tenacity (network errors + 5xx)
  • Circuit breaker: opens after 5 consecutive failures
  • JQL-based issue pagination (maxResults + startAt cursor)

Base URL pattern
────────────────
  https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Awaitable
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
)

from app.core.exceptions import CircuitBreakerOpenError
from app.core.logging_config import get_logger
from app.infrastructure.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)

_JIRA_API_BASE = "https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
_PAGE_SIZE     = 100  # max Jira allows per page
_RATE_LIMIT_PAUSE = 60.0  # seconds to pause on 429


class JiraClient:
    """
    Async Jira Cloud REST API client.

    Parameters
    ──────────
    access_token   — current OAuth 2.0 Bearer token
    cloud_id       — Atlassian cloud site ID (from accessible-resources)
    refresh_cb     — async callable() → new access_token (called on 401)
    """

    def __init__(
        self,
        access_token: str,
        cloud_id:     str,
        refresh_cb:   Callable[[], Awaitable[str]] | None = None,
    ) -> None:
        self._token    = access_token
        self._cloud_id = cloud_id
        self._refresh  = refresh_cb
        self._base     = _JIRA_API_BASE.format(cloud_id=cloud_id)
        self._http     = httpx.AsyncClient(timeout=30.0)
        self._cb       = CircuitBreaker(
            failure_threshold=5,
            success_threshold=2,
            name=f"jira:{cloud_id[:8]}",
        )

    # ── HTTP core ─────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept":        "application/json",
            "Content-Type":  "application/json",
        }

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
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Execute an authenticated request; handles 401 refresh and 429 back-off."""
        if not self._cb.allow_request():
            raise RuntimeError(f"JiraClient circuit breaker open for {self._cloud_id}")

        url = f"{self._base}{path}"
        try:
            resp = await self._http.request(method, url, headers=self._headers(), **kwargs)

            if resp.status_code == 401 and self._refresh:
                logger.info("jira.token_expired", cloud_id=self._cloud_id)
                self._token = await self._refresh()
                resp = await self._http.request(method, url, headers=self._headers(), **kwargs)

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", _RATE_LIMIT_PAUSE))
                logger.warning("jira.rate_limited", retry_after=retry_after)
                await asyncio.sleep(retry_after)
                resp = await self._http.request(method, url, headers=self._headers(), **kwargs)

            resp.raise_for_status()
            return resp.json()

        
        except httpx.HTTPStatusError as exc:
            logger.error(
                "jira.http_error",
                status=exc.response.status_code,
                path=path,
                body=exc.response.text[:200],
            )
            raise

    # ── Projects (boards in Jira language) ───────────────────────────────────

    async def get_projects(self, max_results: int = 200) -> list[dict[str, Any]]:
        """GET /project/search — paginated list of all visible projects."""
        results: list[dict] = []
        start = 0
        while True:
            data = await self._request(
                "GET",
                "/project/search",
                params={"startAt": start, "maxResults": _PAGE_SIZE, "expand": "description"},
            )
            assert isinstance(data, dict)
            values = data.get("values", [])
            results.extend(values)
            if data.get("isLast", True) or len(results) >= max_results:
                break
            start += len(values)
        return results

    # ── Issues ────────────────────────────────────────────────────────────────

    async def search_issues(self, jql: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
        """
        GET /search — paginated JQL issue search.
        Default fields include: summary, status, priority, assignee, labels,
        story_points, created, updated, description, issuetype, comment.
        """
        _fields = fields or [
            "summary", "description", "status", "priority", "assignee",
            "labels", "created", "updated", "issuetype", "comment",
            "customfield_10016",  # Story Points (common custom field)
            "customfield_10028",  # Story Points (next-gen projects)
            "duedate", "resolution",
        ]
        results: list[dict] = []
        start = 0
        while True:
            data = await self._request(
                "GET",
                "/search",
                params={
                    "jql":        jql,
                    "startAt":    start,
                    "maxResults": _PAGE_SIZE,
                    "fields":     ",".join(_fields),
                },
            )
            assert isinstance(data, dict)
            issues = data.get("issues", [])
            results.extend(issues)
            total = data.get("total", 0)
            if start + len(issues) >= total:
                break
            start += len(issues)
        return results

    async def get_issue(self, issue_id_or_key: str) -> dict[str, Any]:
        data = await self._request("GET", f"/issue/{issue_id_or_key}")
        assert isinstance(data, dict)
        return data

    async def create_issue(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "/issue", json=payload)
        assert isinstance(data, dict)
        return data

    async def update_issue(self, issue_id_or_key: str, payload: dict[str, Any]) -> None:
        await self._request("PUT", f"/issue/{issue_id_or_key}", json=payload)

    # ── Comments ─────────────────────────────────────────────────────────────

    async def get_comments(self, issue_id_or_key: str) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            f"/issue/{issue_id_or_key}/comment",
            params={"orderBy": "created", "maxResults": 100},
        )
        assert isinstance(data, dict)
        return data.get("comments", [])

    # ── Boards (Jira Software) ────────────────────────────────────────────────

    async def get_boards(self) -> list[dict[str, Any]]:
        """
        GET /rest/agile/1.0/board — list all Scrum/Kanban boards.
        Uses the Agile REST API (different base path).
        """
        agile_base = (
            f"https://api.atlassian.com/ex/jira/{self._cloud_id}"
            "/rest/agile/1.0/board"
        )
        results: list[dict] = []
        start = 0
        while True:
            resp = await self._http.get(
                agile_base,
                headers=self._headers(),
                params={"startAt": start, "maxResults": 50},
            )
            if resp.status_code == 401 and self._refresh:
                self._token = await self._refresh()
                resp = await self._http.get(
                    agile_base,
                    headers=self._headers(),
                    params={"startAt": start, "maxResults": 50},
                )
            resp.raise_for_status()
            data = resp.json()
            values = data.get("values", [])
            results.extend(values)
            if data.get("isLast", True):
                break
        return results

    async def get_board_sprints(self, board_id: int) -> list[dict[str, Any]]:
        """
        GET /rest/agile/1.0/board/{boardId}/sprint — list sprints for a board.
        """
        agile_base = (
            f"https://api.atlassian.com/ex/jira/{self._cloud_id}"
            f"/rest/agile/1.0/board/{board_id}/sprint"
        )
        results: list[dict] = []
        start = 0
        while True:
            resp = await self._http.get(
                agile_base,
                headers=self._headers(),
                params={"startAt": start, "maxResults": 50},
            )
            if resp.status_code == 401 and self._refresh:
                self._token = await self._refresh()
                resp = await self._http.get(
                    agile_base,
                    headers=self._headers(),
                    params={"startAt": start, "maxResults": 50},
                )
            if resp.status_code == 404:
                # Board does not support sprints (e.g. Kanban or Business)
                break
            resp.raise_for_status()
            data = resp.json()
            values = data.get("values", [])
            results.extend(values)
            if data.get("isLast", True):
                break
            start += len(values)
        return results

    # ── Webhooks ──────────────────────────────────────────────────────────────

    async def register_webhook(
        self,
        url:    str,
        events: list[str],
        jql:    str = "",
    ) -> dict[str, Any]:
        """
        POST /webhook — register a Jira webhook.
        Common events: jira:issue_created, jira:issue_updated, comment_created
        """
        payload: dict[str, Any] = {
            "url":    url,
            "events": events,
        }
        if jql:
            payload["filters"] = {"issue-related-events-section": jql}
        data = await self._request("POST", "/webhook", json=payload)
        assert isinstance(data, dict)
        return data

    async def delete_webhook(self, webhook_id: int) -> None:
        """DELETE /webhook/{webhookId}"""
        await self._request("DELETE", f"/webhook/{webhook_id}")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "JiraClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # ── Validate ─────────────────────────────────────────────────────────────

    async def validate(self) -> bool:
        """Probe /myself — cheap credential check."""
        try:
            data = await self._request("GET", "/myself")
            return isinstance(data, dict) and "accountId" in data
        except Exception:
            return False
