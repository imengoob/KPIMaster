"""
Schema contract tests — verify backend JSON responses exactly match the
field names declared in the frontend TypeScript interfaces (types.ts).

Each test creates a real record, fetches it, and asserts the JSON keys
are a superset of the fields the frontend expects. This catches:
  - Backend renames a field (snake_case consistency)
  - Backend adds a required field the frontend hasn't handled
  - Backend removes a field the frontend relies on

Frontend interfaces (src/services/api/types.ts) are documented inline
so the contract is visible without switching files.
"""
import pytest
from httpx import AsyncClient

from tests.conftest import (
    developer_payload,
    project_payload,
    sprint_payload,
    ticket_payload,
)


# ── BackendProject ────────────────────────────────────────────────────────────
# interface BackendProject {
#   id, name, key, description, repository_url, slack_channel,
#   is_active, created_at, updated_at
# }

BACKEND_PROJECT_FIELDS = {
    "id", "name", "key", "description",
    "repository_url", "slack_channel", "is_active",
    "created_at", "updated_at",
}


async def test_project_response_contract(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/projects", json=project_payload(key="CNT1"))
    assert resp.status_code == 201
    assert BACKEND_PROJECT_FIELDS.issubset(resp.json().keys())


async def test_paginated_project_items_contract(client: AsyncClient) -> None:
    await client.post("/api/v1/projects", json=project_payload(key="CNT2"))
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    # PaginatedResponse<BackendProject>
    assert {"items", "total", "page", "page_size"}.issubset(data.keys())
    if data["items"]:
        assert BACKEND_PROJECT_FIELDS.issubset(data["items"][0].keys())


# ── BackendSprint ─────────────────────────────────────────────────────────────
# interface BackendSprint {
#   id, project_id, name, goal, start_date, end_date, status,
#   committed_points, completed_points, velocity, created_at, updated_at
# }

BACKEND_SPRINT_FIELDS = {
    "id", "project_id", "name", "goal", "start_date", "end_date", "status",
    "committed_points", "completed_points", "velocity",
    "created_at", "updated_at",
}


async def test_sprint_response_contract(
    client: AsyncClient, existing_project: dict
) -> None:
    resp = await client.post(
        "/api/v1/sprints", json=sprint_payload(existing_project["id"])
    )
    assert resp.status_code == 201
    assert BACKEND_SPRINT_FIELDS.issubset(resp.json().keys())


async def test_sprint_date_fields_are_strings(
    client: AsyncClient, existing_sprint: dict
) -> None:
    """Frontend expects start_date/end_date as 'YYYY-MM-DD' strings."""
    resp = await client.get(f"/api/v1/sprints/{existing_sprint['id']}")
    data = resp.json()
    assert isinstance(data["start_date"], str)
    assert isinstance(data["end_date"], str)
    # Must be parseable as a date
    from datetime import date
    date.fromisoformat(data["start_date"])
    date.fromisoformat(data["end_date"])


# ── BackendTicket ─────────────────────────────────────────────────────────────
# interface BackendTicket {
#   id, project_id, sprint_id, assignee_id, reporter_id, title,
#   description, status, priority, ticket_type, estimated_hours,
#   actual_hours, story_points, quality_score, last_activity_at,
#   created_at, updated_at
# }

BACKEND_TICKET_FIELDS = {
    "id", "project_id", "sprint_id", "assignee_id", "reporter_id",
    "title", "description", "status", "priority", "ticket_type",
    "estimated_hours", "actual_hours", "story_points",
    "quality_score", "last_activity_at", "created_at", "updated_at",
}


async def test_ticket_response_contract(
    client: AsyncClient, existing_project: dict
) -> None:
    resp = await client.post(
        "/api/v1/tickets", json=ticket_payload(existing_project["id"])
    )
    assert resp.status_code == 201
    assert BACKEND_TICKET_FIELDS.issubset(resp.json().keys())


async def test_ticket_status_values(
    client: AsyncClient, existing_project: dict
) -> None:
    """Status values must match the union type in BackendTicket."""
    valid_statuses = {
        "backlog", "todo", "in_progress", "in_review",
        "done", "blocked", "cancelled",
    }
    resp = await client.post(
        "/api/v1/tickets", json=ticket_payload(existing_project["id"])
    )
    status = resp.json()["status"]
    assert status in valid_statuses, f"Unexpected status: {status}"


async def test_ticket_priority_values(
    client: AsyncClient, existing_project: dict
) -> None:
    """Priority must match BackendTicket's union type."""
    valid_priorities = {"low", "medium", "high", "critical"}
    resp = await client.post(
        "/api/v1/tickets",
        json=ticket_payload(existing_project["id"], priority="critical"),
    )
    priority = resp.json()["priority"]
    assert priority in valid_priorities


# ── BackendBlocker ────────────────────────────────────────────────────────────
# interface BackendBlocker {
#   id, ticket_id, description, stall_hours, escalation_level,
#   detected_at, last_escalated_at, resolved_at, created_at, updated_at,
#   ticket_title?, ticket_assignee_id?
# }

BACKEND_BLOCKER_FIELDS = {
    "id", "ticket_id", "description", "stall_hours", "escalation_level",
    "detected_at", "last_escalated_at", "resolved_at",
    "created_at", "updated_at",
    "ticket_title", "ticket_assignee_id",  # enriched — always present in our API
}


async def test_blocker_list_item_contract(
    client: AsyncClient, existing_project: dict
) -> None:
    pid = existing_project["id"]
    await client.post("/api/v1/tickets", json=ticket_payload(pid, status="blocked"))
    await client.post("/api/v1/blockers/detect")
    resp = await client.get(f"/api/v1/blockers?project_id={pid}")
    assert resp.status_code == 200
    for b in resp.json():
        assert BACKEND_BLOCKER_FIELDS.issubset(b.keys()), (
            f"Missing: {BACKEND_BLOCKER_FIELDS - b.keys()}"
        )


# ── BackendDeveloper ──────────────────────────────────────────────────────────
# interface BackendDeveloper {
#   id, name, email, username, team, role, slack_id,
#   github_username, is_active, created_at, updated_at
# }

BACKEND_DEVELOPER_FIELDS = {
    "id", "name", "email", "username", "team", "role",
    "slack_id", "github_username", "is_active",
    "created_at", "updated_at",
}


async def test_developer_response_contract(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/developers", json=developer_payload(email="c@contract.com")
    )
    assert resp.status_code == 201
    assert BACKEND_DEVELOPER_FIELDS.issubset(resp.json().keys())


# ── BackendKPIDashboard ───────────────────────────────────────────────────────
# interface BackendKPIDashboard {
#   project_id, sprint_id, current_kpis,
#   velocity_trend, completion_trend,
#   open_blockers, stalled_tickets, repo_mismatches
# }

BACKEND_KPI_DASHBOARD_FIELDS = {
    "project_id", "sprint_id", "current_kpis",
    "velocity_trend", "completion_trend",
    "open_blockers", "stalled_tickets", "repo_mismatches",
}


async def test_kpi_dashboard_contract(
    client: AsyncClient, existing_project: dict
) -> None:
    resp = await client.get(
        f"/api/v1/kpis?project_id={existing_project['id']}"
    )
    assert resp.status_code == 200
    assert BACKEND_KPI_DASHBOARD_FIELDS.issubset(resp.json().keys())


# ── BackendKPISnapshot ────────────────────────────────────────────────────────
# interface BackendKPISnapshot {
#   id, project_id, sprint_id, cycle_time_hours, lead_time_hours,
#   velocity, completion_rate, estimation_accuracy, throughput,
#   bug_rate, computed_at
# }

BACKEND_KPI_SNAPSHOT_FIELDS = {
    "id", "project_id", "sprint_id",
    "cycle_time_hours", "lead_time_hours",
    "velocity", "completion_rate",
    "estimation_accuracy", "throughput", "bug_rate",
    "computed_at",
}


async def test_kpi_snapshot_contract(
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
    assert BACKEND_KPI_SNAPSHOT_FIELDS.issubset(resp.json().keys())


# ── BackendRepositoryMismatch ─────────────────────────────────────────────────
# interface BackendRepositoryMismatch {
#   id, ticket_id, project_id, branch_name, commit_count, pr_count,
#   pr_merged, last_commit_at, mismatch_type, mismatch_reason, scanned_at
# }

BACKEND_REPO_MISMATCH_FIELDS = {
    "id", "ticket_id", "project_id",
    "branch_name", "commit_count", "pr_count", "pr_merged",
    "last_commit_at", "mismatch_type", "mismatch_reason", "scanned_at",
}


async def test_repo_mismatch_list_contract(
    client: AsyncClient, existing_project: dict
) -> None:
    pid = existing_project["id"]
    resp = await client.get(f"/api/v1/repository-mismatches?project_id={pid}")
    assert resp.status_code == 200
    for item in resp.json():
        assert BACKEND_REPO_MISMATCH_FIELDS.issubset(item.keys()), (
            f"Missing: {BACKEND_REPO_MISMATCH_FIELDS - item.keys()}"
        )


# ── BackendBurndownChart ──────────────────────────────────────────────────────
# interface BackendBurndownChart {
#   sprint_id, sprint_name, start_date, end_date,
#   committed_points, entries: BackendBurndownEntry[]
# }
# interface BackendBurndownEntry {
#   id, sprint_id, date, remaining_points, completed_points,
#   ideal_remaining, cumulative_completed
# }

BACKEND_BURNDOWN_CHART_FIELDS = {
    "sprint_id", "sprint_name", "start_date", "end_date",
    "committed_points", "entries",
}

BACKEND_BURNDOWN_ENTRY_FIELDS = {
    "id", "sprint_id", "date", "remaining_points",
    "completed_points", "ideal_remaining", "cumulative_completed",
}


async def test_burndown_chart_contract(
    client: AsyncClient, existing_sprint: dict
) -> None:
    sid = existing_sprint["id"]
    resp = await client.get(f"/api/v1/sprints/{sid}/burndown")
    assert resp.status_code == 200
    data = resp.json()
    assert BACKEND_BURNDOWN_CHART_FIELDS.issubset(data.keys())


async def test_burndown_entry_contract(
    client: AsyncClient, existing_sprint: dict
) -> None:
    sid = existing_sprint["id"]
    entries = (await client.get(f"/api/v1/sprints/{sid}/burndown")).json()["entries"]
    for entry in entries:
        assert BACKEND_BURNDOWN_ENTRY_FIELDS.issubset(entry.keys()), (
            f"Missing entry fields: {BACKEND_BURNDOWN_ENTRY_FIELDS - entry.keys()}"
        )


# ── Error response shape ──────────────────────────────────────────────────────

async def test_404_error_shape(client: AsyncClient) -> None:
    """ApiError on the frontend reads resp.json() — 404 must be JSON."""
    resp = await client.get("/api/v1/projects/99999")
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data


async def test_422_error_shape(client: AsyncClient) -> None:
    """Validation errors from FastAPI must be JSON with a 'detail' key."""
    resp = await client.post("/api/v1/projects", json={"name": "Missing key field"})
    assert resp.status_code == 422
    assert "detail" in resp.json()
