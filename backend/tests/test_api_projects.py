"""
Integration tests for /api/v1/projects and related sprint sub-resources.

Covers:
- CRUD lifecycle for Project
- Pagination
- Duplicate key rejection
- Active sprint retrieval and 404 when absent
- Velocity history
- Matches frontend BackendProject interface
"""
import pytest
from httpx import AsyncClient

from app.api.authz import AuthPrincipal
from app.models.company import Company, CompanyProjectAccess
from tests.conftest import project_payload, sprint_payload


# ── Create ────────────────────────────────────────────────────────────────────

async def test_create_project_returns_201(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/projects", json=project_payload())
    assert resp.status_code == 201


async def test_create_project_response_matches_frontend_contract(client: AsyncClient) -> None:
    """All fields expected by BackendProject must be present."""
    resp = await client.post("/api/v1/projects", json=project_payload(key="CONT"))
    data = resp.json()
    expected_fields = {
        "id", "name", "key", "description",
        "repository_url", "slack_channel", "is_active",
        "created_at", "updated_at",
    }
    assert expected_fields.issubset(data.keys()), (
        f"Missing fields: {expected_fields - data.keys()}"
    )


async def test_create_project_persists_fields(client: AsyncClient) -> None:
    payload = project_payload(name="My App", key="MAP", description="Desc")
    resp = await client.post("/api/v1/projects", json=payload)
    data = resp.json()
    assert data["name"] == "My App"
    assert data["key"] == "MAP"
    assert data["description"] == "Desc"
    assert data["is_active"] is True


async def test_create_project_duplicate_key_returns_409(client: AsyncClient) -> None:
    await client.post("/api/v1/projects", json=project_payload(key="DUP"))
    resp = await client.post("/api/v1/projects", json=project_payload(key="DUP"))
    assert resp.status_code == 409


# ── Read ──────────────────────────────────────────────────────────────────────

async def test_get_project_by_id(client: AsyncClient, existing_project: dict) -> None:
    pid = existing_project["id"]
    resp = await client.get(f"/api/v1/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == pid


async def test_get_nonexistent_project_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/projects/99999")
    assert resp.status_code == 404


# ── List ──────────────────────────────────────────────────────────────────────

async def test_list_projects_returns_paginated_response(client: AsyncClient) -> None:
    await client.post("/api/v1/projects", json=project_payload(key="P1"))
    await client.post("/api/v1/projects", json=project_payload(key="P2"))
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    # Must match frontend PaginatedResponse<BackendProject>
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert isinstance(data["items"], list)
    assert data["total"] >= 2


async def test_list_projects_pagination(client: AsyncClient) -> None:
    for i in range(5):
        await client.post("/api/v1/projects", json=project_payload(key=f"PG{i}"))
    resp = await client.get("/api/v1/projects?page=1&page_size=2")
    data = resp.json()
    assert len(data["items"]) <= 2


async def test_list_projects_is_scoped_to_company_visibility(
    client: AsyncClient,
    db,
    principal_override,
) -> None:
    company = Company(name="Visible Co", slug="visible-co", is_active=True)
    db.add(company)
    await db.flush()

    visible = (await client.post("/api/v1/projects", json=project_payload(key="VIS"))).json()
    hidden = (await client.post("/api/v1/projects", json=project_payload(key="HID"))).json()

    db.add(CompanyProjectAccess(company_id=company.id, project_id=visible["id"]))
    await db.flush()

    principal_override(
        AuthPrincipal(
            user_id=55,
            username="company-user",
            email="company@example.com",
            role="company_manager",
            company_id=company.id,
            developer_id=None,
        )
    )

    resp = await client.get("/api/v1/projects?page_size=100")
    assert resp.status_code == 200
    keys = {item["key"] for item in resp.json()["items"]}
    assert "VIS" in keys
    assert "HID" not in keys


# ── Update ────────────────────────────────────────────────────────────────────

async def test_update_project_name(client: AsyncClient, existing_project: dict) -> None:
    pid = existing_project["id"]
    resp = await client.patch(f"/api/v1/projects/{pid}", json={"name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


async def test_update_nonexistent_project_returns_404(client: AsyncClient) -> None:
    resp = await client.patch("/api/v1/projects/99999", json={"name": "Valid Name"})
    assert resp.status_code == 404


# ── Sprint sub-resources ──────────────────────────────────────────────────────

async def test_get_current_sprint_404_when_none(
    client: AsyncClient, existing_project: dict
) -> None:
    pid = existing_project["id"]
    resp = await client.get(f"/api/v1/projects/{pid}/sprints/current")
    assert resp.status_code == 404


async def test_get_current_sprint_returns_active_sprint(
    client: AsyncClient, existing_project: dict
) -> None:
    pid = existing_project["id"]
    await client.post("/api/v1/sprints", json=sprint_payload(pid, status="active"))
    resp = await client.get(f"/api/v1/projects/{pid}/sprints/current")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    assert resp.json()["project_id"] == pid


async def test_velocity_history_returns_list(
    client: AsyncClient, existing_project: dict
) -> None:
    pid = existing_project["id"]
    resp = await client.get(f"/api/v1/projects/{pid}/sprints/velocity")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_velocity_history_shape(
    client: AsyncClient, existing_project: dict
) -> None:
    """Each velocity point must have 'sprint' and 'points' keys (BackendVelocityPoint)."""
    pid = existing_project["id"]
    # Create + complete a sprint to have data
    sprint_resp = await client.post(
        "/api/v1/sprints",
        json=sprint_payload(pid, status="active"),
    )
    sprint_id = sprint_resp.json()["id"]
    await client.patch(f"/api/v1/sprints/{sprint_id}", json={"status": "completed"})

    resp = await client.get(f"/api/v1/projects/{pid}/sprints/velocity")
    data = resp.json()
    for point in data:
        assert "sprint" in point
        assert "points" in point
