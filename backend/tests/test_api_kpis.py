"""
Integration tests for /api/v1/kpis.

Covers:
- KPI dashboard shape (project with no sprint, then with an active sprint)
- KPI history list
- Forced KPI recomputation
- BackendKPIDashboard and BackendKPISnapshot interface contracts
"""
import pytest
from httpx import AsyncClient

from tests.conftest import sprint_payload, ticket_payload


# ── Dashboard ─────────────────────────────────────────────────────────────────

async def test_get_kpis_returns_200(
    client: AsyncClient, existing_project: dict
) -> None:
    resp = await client.get(
        f"/api/v1/kpis?project_id={existing_project['id']}"
    )
    assert resp.status_code == 200


async def test_kpis_response_matches_frontend_contract(
    client: AsyncClient, existing_project: dict
) -> None:
    """Shape must match frontend BackendKPIDashboard interface."""
    resp = await client.get(
        f"/api/v1/kpis?project_id={existing_project['id']}"
    )
    data = resp.json()
    expected_top = {
        "project_id", "sprint_id", "current_kpis",
        "velocity_trend", "completion_trend",
        "open_blockers", "stalled_tickets", "repo_mismatches",
    }
    assert expected_top.issubset(data.keys()), (
        f"Missing top-level fields: {expected_top - data.keys()}"
    )
    assert isinstance(data["velocity_trend"], list)
    assert isinstance(data["completion_trend"], list)


async def test_kpis_current_kpis_is_none_without_sprint(
    client: AsyncClient, existing_project: dict
) -> None:
    resp = await client.get(
        f"/api/v1/kpis?project_id={existing_project['id']}"
    )
    data = resp.json()
    # No sprint yet — current_kpis should be null (no snapshot exists)
    assert data["current_kpis"] is None


async def test_kpis_snapshot_shape_when_computed(
    client: AsyncClient, existing_project: dict
) -> None:
    """After forcing computation, current_kpis must match BackendKPISnapshot."""
    pid = existing_project["id"]
    sprint_resp = await client.post(
        "/api/v1/sprints", json=sprint_payload(pid, status="active")
    )
    sprint_id = sprint_resp.json()["id"]

    # Force compute
    await client.post(
        f"/api/v1/kpis/compute?project_id={pid}&sprint_id={sprint_id}"
    )

    resp = await client.get(f"/api/v1/kpis?project_id={pid}&sprint_id={sprint_id}")
    snapshot = resp.json()["current_kpis"]

    assert snapshot is not None
    expected = {
        "id", "project_id", "sprint_id",
        "cycle_time_hours", "lead_time_hours",
        "velocity", "completion_rate", "throughput",
        "estimation_accuracy", "bug_rate",
        "computed_at",
    }
    assert expected.issubset(snapshot.keys()), (
        f"Missing snapshot fields: {expected - snapshot.keys()}"
    )


# ── Compute ───────────────────────────────────────────────────────────────────

async def test_compute_kpis_returns_snapshot(
    client: AsyncClient, existing_project: dict
) -> None:
    pid = existing_project["id"]
    sprint_resp = await client.post(
        "/api/v1/sprints", json=sprint_payload(pid, status="active")
    )
    sprint_id = sprint_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/kpis/compute?project_id={pid}&sprint_id={sprint_id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == pid
    assert data["sprint_id"] == sprint_id


async def test_compute_kpis_unknown_sprint_returns_404(
    client: AsyncClient, existing_project: dict
) -> None:
    pid = existing_project["id"]
    resp = await client.post(
        f"/api/v1/kpis/compute?project_id={pid}&sprint_id=99999"
    )
    assert resp.status_code == 404


# ── History ───────────────────────────────────────────────────────────────────

async def test_kpi_history_returns_list(
    client: AsyncClient, existing_project: dict
) -> None:
    resp = await client.get(
        f"/api/v1/kpis/history?project_id={existing_project['id']}"
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_kpi_history_grows_after_compute(
    client: AsyncClient, existing_project: dict
) -> None:
    pid = existing_project["id"]
    sprint_resp = await client.post(
        "/api/v1/sprints", json=sprint_payload(pid, status="active")
    )
    sprint_id = sprint_resp.json()["id"]

    history_before = len(
        (await client.get(f"/api/v1/kpis/history?project_id={pid}")).json()
    )
    await client.post(f"/api/v1/kpis/compute?project_id={pid}&sprint_id={sprint_id}")
    history_after = len(
        (await client.get(f"/api/v1/kpis/history?project_id={pid}")).json()
    )
    assert history_after == history_before + 1


async def test_kpi_history_completion_rate_range(
    client: AsyncClient, existing_project: dict
) -> None:
    """completion_rate must be in [0.0, 1.0] or None."""
    pid = existing_project["id"]
    sprint_resp = await client.post(
        "/api/v1/sprints", json=sprint_payload(pid, status="active")
    )
    sprint_id = sprint_resp.json()["id"]
    await client.post(f"/api/v1/kpis/compute?project_id={pid}&sprint_id={sprint_id}")

    history = (await client.get(f"/api/v1/kpis/history?project_id={pid}")).json()
    for snapshot in history:
        rate = snapshot.get("completion_rate")
        if rate is not None:
            assert 0.0 <= rate <= 1.0
