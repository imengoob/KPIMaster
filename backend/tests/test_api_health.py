"""Health and readiness endpoint tests."""
import pytest
from httpx import AsyncClient


async def test_health_endpoint_returns_200(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200


async def test_health_response_shape(client: AsyncClient) -> None:
    resp = await client.get("/health")
    data = resp.json()
    assert "status" in data
    assert "version" in data
    assert "database" in data
    assert "redis" in data
    assert "timestamp" in data


async def test_health_status_is_string(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert isinstance(resp.json()["status"], str)


async def test_docs_accessible_in_dev(client: AsyncClient) -> None:
    """OpenAPI docs should be reachable in non-production mode."""
    resp = await client.get("/docs")
    assert resp.status_code == 200
