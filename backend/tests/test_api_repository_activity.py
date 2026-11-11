from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.api.authz import AuthPrincipal


async def test_list_mismatches_returns_empty_when_no_data(client: AsyncClient, existing_project: dict, principal_override) -> None:
    pid = existing_project["id"]

    principal_override(
        AuthPrincipal(
            user_id=1,
            username="admin",
            email="admin@example.com",
            role="super_admin",
            company_id=None,
            developer_id=None,
        )
    )

    resp = await client.get(f"/api/v1/repository-mismatches?project_id={pid}")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_mismatches_returns_empty_for_jira_provider(
    client: AsyncClient,
    existing_project: dict,
    principal_override,
) -> None:
    pid = existing_project["id"]

    principal_override(
        AuthPrincipal(
            user_id=1,
            username="admin",
            email="admin@example.com",
            role="super_admin",
            company_id=None,
            developer_id=None,
        )
    )

    resp = await client.get(f"/api/v1/repository-mismatches?project_id={pid}&provider=jira")
    assert resp.status_code == 200
    assert resp.json() == []


@patch("app.services.repository_analyzer_service.RepositoryAnalyzerService")
async def test_trigger_scan_returns_mocked_result(mock_analyzer_cls, client: AsyncClient, existing_project: dict, principal_override) -> None:
    pid = existing_project["id"]

    # Mock the internal service
    mock_instance = AsyncMock()
    mock_instance.scan_project.return_value = {"status": "ok", "mismatches_found": 1}
    mock_analyzer_cls.return_value = mock_instance

    principal_override(
        AuthPrincipal(
            user_id=1,
            username="admin",
            email="admin@example.com",
            role="super_admin",
            company_id=None,
            developer_id=None,
        )
    )

    resp = await client.post(f"/api/v1/repository-mismatches/scan?project_id={pid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["mismatches_found"] == 1
    mock_instance.scan_project.assert_awaited_once_with(pid)
