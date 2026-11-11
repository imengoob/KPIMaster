from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket
from tests.conftest import ticket_payload


pytestmark = pytest.mark.anyio


async def _seed_low_quality_ticket(
    client: AsyncClient,
    db: AsyncSession,
    project_id: int,
) -> int:
    resp = await client.post(
        "/api/v1/tickets",
        json=ticket_payload(
            project_id,
            title="Weak ticket needs detail",
            status="in_progress",
            priority="high",
        ),
    )
    assert resp.status_code == 201, resp.text
    ticket_id = resp.json()["id"]
    ticket = await db.get(Ticket, ticket_id)
    assert ticket is not None
    ticket.quality_score = 40
    db.add(ticket)
    await db.flush()
    return ticket_id


async def test_generate_actions_from_ticket_quality_is_deduplicated(
    client: AsyncClient,
    db: AsyncSession,
    existing_project: dict,
) -> None:
    await _seed_low_quality_ticket(client, db, existing_project["id"])

    first = await client.post(f"/api/v1/actions/generate?project_id={existing_project['id']}")
    assert first.status_code == 200, first.text
    first_data = first.json()
    assert first_data["generated"] == 1
    assert first_data["total_open"] == 1

    second = await client.post(f"/api/v1/actions/generate?project_id={existing_project['id']}")
    assert second.status_code == 200, second.text
    second_data = second.json()
    assert second_data["generated"] == 0
    assert second_data["refreshed"] == 1
    assert second_data["total_open"] == 1


async def test_action_lifecycle_records_events(
    client: AsyncClient,
    db: AsyncSession,
    existing_project: dict,
) -> None:
    await _seed_low_quality_ticket(client, db, existing_project["id"])
    generated = await client.post(f"/api/v1/actions/generate?project_id={existing_project['id']}")
    action_id = generated.json()["action_ids"][0]

    listed = await client.get(f"/api/v1/actions?project_id={existing_project['id']}")
    assert listed.status_code == 200
    assert listed.json()[0]["status"] == "open"

    ack = await client.post(f"/api/v1/actions/{action_id}/acknowledge", json={"note": "On it"})
    assert ack.status_code == 200, ack.text
    assert ack.json()["status"] == "acknowledged"

    resolved = await client.post(f"/api/v1/actions/{action_id}/resolve", json={"note": "Fixed"})
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] is not None
    assert [event["event_type"] for event in body["events"]] == [
        "generated",
        "acknowledged",
        "resolved",
    ]

    hidden = await client.get(f"/api/v1/actions?project_id={existing_project['id']}")
    assert hidden.status_code == 200
    assert hidden.json() == []

    visible = await client.get(f"/api/v1/actions?project_id={existing_project['id']}&include_resolved=true")
    assert visible.status_code == 200
    assert len(visible.json()) == 1

