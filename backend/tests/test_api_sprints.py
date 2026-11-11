"""
Integration tests for /api/v1/sprints.

Covers:
- Sprint CRUD
- Date validation (end_date must be after start_date)
- Status transitions
- Burndown chart retrieval
- BackendSprint interface contract
"""
import pytest
from httpx import AsyncClient

from tests.conftest import sprint_payload


# ── Create ────────────────────────────────────────────────────────────────────

async def test_create_sprint_returns_201(
    client: AsyncClient, existing_project: dict
) -> None:
    resp = await client.post(
        "/api/v1/sprints", json=sprint_payload(existing_project["id"])
    )
    assert resp.status_code == 201


async def test_create_sprint_response_matches_frontend_contract(
    client: AsyncClient, existing_project: dict
) -> None:
    """Fields must match frontend BackendSprint interface."""
    resp = await client.post(
        "/api/v1/sprints", json=sprint_payload(existing_project["id"])
    )
    data = resp.json()
    expected_fields = {
        "id", "project_id", "name", "goal",
        "start_date", "end_date", "status",
        "committed_points", "completed_points", "velocity",
        "created_at", "updated_at",
    }
    assert expected_fields.issubset(data.keys()), (
        f"Missing fields: {expected_fields - data.keys()}"
    )


async def test_create_sprint_persists_values(
    client: AsyncClient, existing_project: dict
) -> None:
    pid = existing_project["id"]
    payload = sprint_payload(pid, name="Q1 Sprint", committed_points=60)
    resp = await client.post("/api/v1/sprints", json=payload)
    data = resp.json()
    assert data["name"] == "Q1 Sprint"
    assert data["committed_points"] == 60
    assert data["project_id"] == pid
    assert data["completed_points"] == 0
    assert data["velocity"] == 0


async def test_create_sprint_invalid_dates_returns_422(
    client: AsyncClient, existing_project: dict
) -> None:
    """end_date before start_date must be rejected."""
    payload = sprint_payload(
        existing_project["id"],
        start_date="2026-01-14",
        end_date="2026-01-01",
    )
    resp = await client.post("/api/v1/sprints", json=payload)
    assert resp.status_code == 422


# ── Read ──────────────────────────────────────────────────────────────────────

async def test_get_sprint_by_id(client: AsyncClient, existing_sprint: dict) -> None:
    sid = existing_sprint["id"]
    resp = await client.get(f"/api/v1/sprints/{sid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == sid


async def test_get_nonexistent_sprint_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/sprints/99999")
    assert resp.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────

async def test_update_sprint_name(
    client: AsyncClient, existing_sprint: dict
) -> None:
    sid = existing_sprint["id"]
    resp = await client.patch(f"/api/v1/sprints/{sid}", json={"name": "Renamed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"


async def test_update_sprint_status_to_completed(
    client: AsyncClient, existing_sprint: dict
) -> None:
    sid = existing_sprint["id"]
    resp = await client.patch(f"/api/v1/sprints/{sid}", json={"status": "completed"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


async def test_update_nonexistent_sprint_returns_404(client: AsyncClient) -> None:
    resp = await client.patch("/api/v1/sprints/99999", json={"name": "Renamed Sprint"})
    assert resp.status_code == 404


# ── Burndown ──────────────────────────────────────────────────────────────────

async def test_get_burndown_returns_chart(
    client: AsyncClient, existing_sprint: dict
) -> None:
    sid = existing_sprint["id"]
    resp = await client.get(f"/api/v1/sprints/{sid}/burndown")
    assert resp.status_code == 200


async def test_get_burndown_response_shape(
    client: AsyncClient, existing_sprint: dict
) -> None:
    """Shape must match frontend BackendBurndownChart interface."""
    sid = existing_sprint["id"]
    resp = await client.get(f"/api/v1/sprints/{sid}/burndown")
    data = resp.json()
    assert "sprint_id" in data
    assert "sprint_name" in data
    assert "start_date" in data
    assert "end_date" in data
    assert "committed_points" in data
    assert "entries" in data
    assert isinstance(data["entries"], list)


async def test_burndown_entry_shape(
    client: AsyncClient, existing_sprint: dict
) -> None:
    """Each entry must match BackendBurndownEntry interface."""
    sid = existing_sprint["id"]
    resp = await client.get(f"/api/v1/sprints/{sid}/burndown")
    entries = resp.json()["entries"]
    # Sprint has duration so there should be entries after refresh
    for entry in entries:
        assert "date" in entry
        assert "remaining_points" in entry
        assert "completed_points" in entry
        assert "ideal_remaining" in entry

async def test_create_sprint_active_collision(client: AsyncClient, existing_sprint: dict) -> None:
    # Attempt to create another active sprint for the same project
    payload = existing_sprint.copy()
    payload["status"] = "active"
    del payload["id"]
    resp = await client.post("/api/v1/sprints", json=payload)
    assert resp.status_code == 409

async def test_refresh_burndown(client: AsyncClient, existing_sprint: dict) -> None:
    sid = existing_sprint["id"]
    resp = await client.post(f"/api/v1/sprints/{sid}/burndown/refresh")
    assert resp.status_code == 200

async def test_refresh_burndown_404(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/sprints/99999/burndown/refresh")
    assert resp.status_code == 404

