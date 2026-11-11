from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from app.api.authz import AuthPrincipal


@patch("app.api.v1.analytics.ResponsivenessAnalyticsService")
async def test_responsiveness_passes_provider_to_service(
    mock_service_cls,
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

    mock_service = AsyncMock()
    mock_service.compute_responsiveness_metrics.return_value = {
        "project_id": pid,
        "company_id": None,
        "global_avg_reaction_hours": None,
        "global_avg_response_hours": None,
        "total_developer_comments": 0,
        "total_developer_reactions": 0,
        "active_developers": 0,
        "dormant_developers": 0,
        "total_sla_breaches": 0,
        "trend": [],
        "developers": [],
    }
    mock_service_cls.return_value = mock_service

    resp = await client.get(f"/api/v1/analytics/responsiveness?project_id={pid}&provider=github")
    assert resp.status_code == 200
    mock_service.compute_responsiveness_metrics.assert_awaited_once()
    assert mock_service.compute_responsiveness_metrics.await_args.kwargs["provider"] == "github"
