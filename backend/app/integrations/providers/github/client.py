from __future__ import annotations

import asyncio
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.core.logging_config import get_logger
from app.infrastructure.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)

_GITHUB_API_BASE = "https://api.github.com"
_PAGE_SIZE = 100


class GitHubClient:
    """Small async GitHub REST client for repositories, issues, PRs, and comments."""

    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._http = httpx.AsyncClient(timeout=30.0)
        self._cb = CircuitBreaker(name="github", failure_threshold=5, success_threshold=2)

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=20),
        reraise=True,
    )
    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        async def _do_request() -> dict[str, Any] | list[Any]:
            resp = await self._http.request(
                method,
                f"{_GITHUB_API_BASE}{path}",
                headers=self._headers(),
                **kwargs,
            )
            if resp.status_code in (403, 429) and resp.headers.get("Retry-After"):
                retry_after = float(resp.headers["Retry-After"])
                logger.warning("github.rate_limited", retry_after=retry_after)
                await asyncio.sleep(retry_after)
                resp = await self._http.request(
                    method,
                    f"{_GITHUB_API_BASE}{path}",
                    headers=self._headers(),
                    **kwargs,
                )
            resp.raise_for_status()
            return resp.json()

        try:
            return await self._cb.call(_do_request())
        except httpx.HTTPStatusError as exc:
            logger.error(
                "github.http_error",
                status=exc.response.status_code,
                path=path,
                body=exc.response.text[:200],
            )
            raise

    async def _paginate(self, path: str, params: dict[str, Any] | None = None, max_pages: int = 10) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page = 1
        while page <= max_pages:
            query = {"per_page": _PAGE_SIZE, "page": page}
            if params:
                query.update(params)
            data = await self._request("GET", path, params=query)
            if not isinstance(data, list):
                break
            out.extend(item for item in data if isinstance(item, dict))
            if len(data) < _PAGE_SIZE:
                break
            page += 1
        return out

    async def get_me(self) -> dict[str, Any]:
        data = await self._request("GET", "/user")
        assert isinstance(data, dict)
        return data

    async def validate(self) -> bool:
        try:
            await self.get_me()
            return True
        except Exception:
            return False

    async def get_repositories(self) -> list[dict[str, Any]]:
        return await self._paginate(
            "/user/repos",
            params={"sort": "updated", "direction": "desc", "affiliation": "owner,collaborator,organization_member"},
        )

    async def get_issues(self, owner: str, repo: str) -> list[dict[str, Any]]:
        return await self._paginate(
            f"/repos/{owner}/{repo}/issues",
            params={"state": "all", "sort": "updated", "direction": "desc"},
        )

    async def get_issue_comments(self, owner: str, repo: str, issue_number: int) -> list[dict[str, Any]]:
        return await self._paginate(f"/repos/{owner}/{repo}/issues/{issue_number}/comments", max_pages=5)

    async def create_issue(self, owner: str, repo: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", f"/repos/{owner}/{repo}/issues", json=payload)
        assert isinstance(data, dict)
        return data

    async def update_issue(self, owner: str, repo: str, issue_number: int, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("PATCH", f"/repos/{owner}/{repo}/issues/{issue_number}", json=payload)
        assert isinstance(data, dict)
        return data

    async def close(self) -> None:
        await self._http.aclose()
