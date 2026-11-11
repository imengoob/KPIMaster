"""
Integration tests for /api/v1/tickets.

Covers:
- Ticket CRUD
- Pagination with project_id filter
- Status & priority values
- Quality score report
- BackendTicket interface contract
"""
import pytest
from httpx import AsyncClient

from tests.conftest import ticket_payload


# ── Create ────────────────────────────────────────────────────────────────────

async def test_create_ticket_returns_201(
    client: AsyncClient, existing_project: dict
) -> None:
    resp = await client.post(
        "/api/v1/tickets", json=ticket_payload(existing_project["id"])
    )
    assert resp.status_code == 201


async def test_create_ticket_response_matches_frontend_contract(
    client: AsyncClient, existing_project: dict
) -> None:
    """Fields must match frontend BackendTicket interface."""
    resp = await client.post(
        "/api/v1/tickets", json=ticket_payload(existing_project["id"])
    )
    data = resp.json()
    expected_fields = {
        "id", "project_id", "sprint_id", "assignee_id", "reporter_id",
        "title", "description", "status", "priority", "ticket_type",
        "estimated_hours", "actual_hours", "story_points",
        "quality_score", "last_activity_at", "created_at", "updated_at",
    }
    assert expected_fields.issubset(data.keys()), (
        f"Missing fields: {expected_fields - data.keys()}"
    )


async def test_create_ticket_persists_values(
    client: AsyncClient, existing_project: dict
) -> None:
    pid = existing_project["id"]
    payload = ticket_payload(
        pid,
        title="Fix auth bug",
        priority="critical",
        ticket_type="bug",
        story_points=3,
    )
    resp = await client.post("/api/v1/tickets", json=payload)
    data = resp.json()
    assert data["title"] == "Fix auth bug"
    assert data["priority"] == "critical"
    assert data["ticket_type"] == "bug"
    assert data["story_points"] == 3
    assert data["project_id"] == pid
    assert data["status"] == "backlog"


async def test_create_ticket_requires_title(
    client: AsyncClient, existing_project: dict
) -> None:
    payload = ticket_payload(existing_project["id"])
    del payload["title"]
    resp = await client.post("/api/v1/tickets", json=payload)
    assert resp.status_code == 422


async def test_create_ticket_title_min_length(
    client: AsyncClient, existing_project: dict
) -> None:
    payload = ticket_payload(existing_project["id"], title="ab")  # < 3 chars
    resp = await client.post("/api/v1/tickets", json=payload)
    assert resp.status_code == 422


# ── Read ──────────────────────────────────────────────────────────────────────

async def test_get_ticket_by_id(
    client: AsyncClient, existing_project: dict
) -> None:
    create_resp = await client.post(
        "/api/v1/tickets", json=ticket_payload(existing_project["id"])
    )
    tid = create_resp.json()["id"]
    resp = await client.get(f"/api/v1/tickets/{tid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == tid


async def test_get_nonexistent_ticket_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/tickets/99999")
    assert resp.status_code == 404


# ── List ──────────────────────────────────────────────────────────────────────

async def test_list_tickets_returns_paginated_response(
    client: AsyncClient, existing_project: dict
) -> None:
    pid = existing_project["id"]
    for i in range(3):
        await client.post(
            "/api/v1/tickets", json=ticket_payload(pid, title=f"Ticket {i+1}")
        )
    resp = await client.get(f"/api/v1/tickets?project_id={pid}")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 3


async def test_list_tickets_filtered_by_project(
    client: AsyncClient, existing_project: dict
) -> None:
    """Tickets from a different project must not appear."""
    pid = existing_project["id"]
    # Create a second project
    other_resp = await client.post(
        "/api/v1/projects", json={"name": "Other", "key": "OTH"}
    )
    other_pid = other_resp.json()["id"]

    await client.post("/api/v1/tickets", json=ticket_payload(pid, title="Mine"))
    await client.post("/api/v1/tickets", json=ticket_payload(other_pid, title="Theirs"))

    resp = await client.get(f"/api/v1/tickets?project_id={pid}")
    items = resp.json()["items"]
    assert all(t["project_id"] == pid for t in items)


async def test_list_tickets_pagination(
    client: AsyncClient, existing_project: dict
) -> None:
    pid = existing_project["id"]
    for i in range(10):
        await client.post(
            "/api/v1/tickets", json=ticket_payload(pid, title=f"T{i}")
        )
    resp = await client.get(f"/api/v1/tickets?project_id={pid}&page_size=3")
    assert len(resp.json()["items"]) <= 3


async def test_list_tickets_returns_empty_for_non_trello_provider(
    client: AsyncClient,
    existing_project: dict,
) -> None:
    pid = existing_project["id"]
    await client.post("/api/v1/tickets", json=ticket_payload(pid, title="Provider limited"))

    resp = await client.get(f"/api/v1/tickets?project_id={pid}&provider=github")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


# ── Update ────────────────────────────────────────────────────────────────────

async def test_update_ticket_status(
    client: AsyncClient, existing_project: dict
) -> None:
    create_resp = await client.post(
        "/api/v1/tickets", json=ticket_payload(existing_project["id"])
    )
    tid = create_resp.json()["id"]
    resp = await client.patch(
        f"/api/v1/tickets/{tid}", json={"status": "in_progress"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


async def test_update_ticket_actual_hours(
    client: AsyncClient, existing_project: dict
) -> None:
    create_resp = await client.post(
        "/api/v1/tickets", json=ticket_payload(existing_project["id"])
    )
    tid = create_resp.json()["id"]
    resp = await client.patch(f"/api/v1/tickets/{tid}", json={"actual_hours": 6.5})
    assert resp.status_code == 200
    assert resp.json()["actual_hours"] == 6.5


async def test_update_nonexistent_ticket_returns_404(client: AsyncClient) -> None:
    resp = await client.patch("/api/v1/tickets/99999", json={"status": "done"})
    assert resp.status_code == 404


# ── Quality report ────────────────────────────────────────────────────────────

async def test_get_ticket_quality_returns_report(
    client: AsyncClient, existing_project: dict
) -> None:
    create_resp = await client.post(
        "/api/v1/tickets", json=ticket_payload(existing_project["id"])
    )
    tid = create_resp.json()["id"]
    resp = await client.get(f"/api/v1/tickets/{tid}/quality")
    assert resp.status_code == 200
    data = resp.json()
    assert "ticket_id" in data
    assert "quality_score" in data
    assert "issues" in data
    assert "has_description" in data
    assert "has_assignee" in data
    assert "has_priority" in data
    assert "has_estimation" in data
    assert "recommendations" in data


async def test_quality_score_range(
    client: AsyncClient, existing_project: dict
) -> None:
    """Quality score must be in [0, 100]."""
    create_resp = await client.post(
        "/api/v1/tickets", json=ticket_payload(existing_project["id"])
    )
    tid = create_resp.json()["id"]
    resp = await client.get(f"/api/v1/tickets/{tid}/quality")
    score = resp.json()["quality_score"]
    assert 0.0 <= score <= 100.0


async def test_complete_ticket_has_high_quality(
    client: AsyncClient, existing_project: dict, existing_developer: dict
) -> None:
    """A ticket with all fields filled should score higher than one without."""
    pid = existing_project["id"]
    dev_id = existing_developer["id"]

    good = await client.post(
        "/api/v1/tickets",
        json=ticket_payload(
            pid,
            title="Well-described feature ticket",
            description="Detailed description with acceptance criteria",
            assignee_id=dev_id,
            estimated_hours=8.0,
            story_points=5,
            priority="high",
        ),
    )
    bare = await client.post(
        "/api/v1/tickets",
        json={
            "project_id": pid,
            "title": "Bare ticket",
            "status": "backlog",
            "priority": "low",
            "ticket_type": "task",
        },
    )
    good_score = (
        await client.get(f"/api/v1/tickets/{good.json()['id']}/quality")
    ).json()["quality_score"]
    bare_score = (
        await client.get(f"/api/v1/tickets/{bare.json()['id']}/quality")
    ).json()["quality_score"]
    assert good_score >= bare_score
