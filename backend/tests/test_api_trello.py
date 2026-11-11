from datetime import UTC, datetime

from httpx import AsyncClient

from app.models.trello_action import TrelloAction
from app.models.trello_board import TrelloBoard
from app.models.trello_card import TrelloCard
from app.models.trello_credential import TrelloCredential
from app.models.trello_list import ListType, TrelloList
from app.domain.events.trello_events import TrelloBoardSyncedEvent
from app.schemas.trello import TrelloAPIBoard
from app.services.trello.client import TrelloClient
from app.services.trello.sync_service import TrelloSyncService
from tests.conftest import project_payload


async def test_import_trello_boards_creates_projects_and_syncs(
    client: AsyncClient,
    monkeypatch,
) -> None:
    boards = [
        TrelloAPIBoard(
            id="board_123",
            name="Platform Delivery",
            desc="Live Trello board",
            shortUrl="https://trello.com/b/board123/platform",
            closed=False,
            idOrganization=None,
        )
    ]

    async def fake_get_my_boards(self):
        return boards

    async def fake_full_sync(self, board, credential):
        return TrelloBoardSyncedEvent(
            board_id=board.id,
            board_name=board.name,
            cards_upserted=0,
            actions_processed=0,
            sync_duration_ms=0.0,
        )

    monkeypatch.setattr(TrelloClient, "get_my_boards", fake_get_my_boards)
    monkeypatch.setattr(TrelloSyncService, "full_sync", fake_full_sync)

    resp = await client.post(
        "/api/v1/trello/import-boards",
        json={
            "api_key": "a" * 32,
            "api_token": "b" * 64,
            "board_ids": ["board_123"],
        },
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert len(data) == 1
    assert data[0]["board_name"] == "Platform Delivery"
    assert data[0]["project_key"]

    projects = await client.get("/api/v1/projects")
    assert projects.status_code == 200
    assert any(item["name"] == "Platform Delivery" for item in projects.json()["items"])


async def test_available_trello_boards_lists_accessible_boards_without_syncing(
    client: AsyncClient,
    monkeypatch,
) -> None:
    boards = [
        TrelloAPIBoard(
            id="board_123",
            name="Platform Delivery",
            desc="Live Trello board",
            shortUrl="https://trello.com/b/board123/platform",
            closed=False,
            idOrganization="org_1",
        ),
        TrelloAPIBoard(
            id="board_999",
            name="Archive",
            desc="Closed board",
            shortUrl="https://trello.com/b/board999/archive",
            closed=True,
            idOrganization=None,
        ),
    ]

    async def fake_get_my_boards(self):
        return boards

    sync_called = False

    async def fake_full_sync(self, board, credential):
        nonlocal sync_called
        sync_called = True
        return TrelloBoardSyncedEvent(
            board_id=board.id,
            board_name=board.name,
            cards_upserted=0,
            actions_processed=0,
            sync_duration_ms=0.0,
        )

    monkeypatch.setattr(TrelloClient, "get_my_boards", fake_get_my_boards)
    monkeypatch.setattr(TrelloSyncService, "full_sync", fake_full_sync)

    resp = await client.post(
        "/api/v1/trello/available-boards",
        json={
            "api_key": "a" * 32,
            "api_token": "b" * 64,
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 2
    assert data[0]["id"] == "board_123"
    assert data[0]["short_url"] == "https://trello.com/b/board123/platform"
    assert data[1]["is_closed"] is True
    assert sync_called is False


async def test_available_trello_boards_accepts_atta_prefixed_tokens_when_trello_validates(
    client: AsyncClient,
    monkeypatch,
) -> None:
    async def fake_get_my_boards(self):
        return [
            TrelloAPIBoard(
                id="board_atta",
                name="ATTA Token Board",
                desc="",
                shortUrl="https://trello.com/b/board_atta",
                closed=False,
                idOrganization=None,
            )
        ]

    monkeypatch.setattr(TrelloClient, "get_my_boards", fake_get_my_boards)

    resp = await client.post(
        "/api/v1/trello/available-boards",
        json={
            "api_key": "a" * 32,
            "api_token": "ATTAexampletokenforjiraandnottrello123456",
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()[0]["id"] == "board_atta"


async def test_tickets_endpoint_falls_back_to_trello_live_data(
    client: AsyncClient,
    db,
) -> None:
    project_resp = await client.post("/api/v1/projects", json=project_payload(key="TRL1"))
    project_id = project_resp.json()["id"]

    credential = TrelloCredential(
        project_id=project_id,
        api_key="a" * 32,
        api_token="b" * 64,
        is_active=True,
    )
    db.add(credential)
    await db.flush()

    board = TrelloBoard(
        credential_id=credential.id,
        trello_id="trello_board_1",
        name="Board 1",
        description="",
        short_url="https://trello.com/b/example",
        trello_org_id=None,
        is_closed=False,
        last_synced_at=datetime.now(UTC),
        last_action_id=None,
    )
    db.add(board)
    await db.flush()

    trello_list = TrelloList(
        board_id=board.id,
        trello_id="list_1",
        name="Doing",
        pos=1.0,
        is_closed=False,
        list_type=ListType.WIP,
    )
    db.add(trello_list)
    await db.flush()

    card = TrelloCard(
        board_id=board.id,
        list_id=trello_list.id,
        trello_id="card_1",
        trello_short_id=7,
        name="Build live sync",
        description="Implement a real Trello sync path for the dashboard.",
        member_ids=["member_1"],
        labels=[{"id": "l1", "name": "feature"}, {"id": "l2", "name": "5sp"}],
        due_date=None,
        due_complete=False,
        is_closed=False,
        trello_last_activity=datetime.now(UTC),
        entered_wip_at=datetime.now(UTC),
        entered_done_at=None,
        trello_created_at=datetime.now(UTC),
        cycle_time_hours=6.0,
        lead_time_hours=8.0,
        is_stalled=False,
        stalled_since=None,
    )
    db.add(card)
    await db.commit()

    resp = await client.get(f"/api/v1/tickets?project_id={project_id}")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "Build live sync"
    assert payload["items"][0]["status"] == "in_progress"


async def test_project_comment_insights_detects_blockers_and_unanswered_questions(
    client: AsyncClient,
    db,
) -> None:
    project_resp = await client.post(
        "/api/v1/projects",
        json=project_payload(key="CMT1", name="Comment Signals"),
    )
    project_id = project_resp.json()["id"]

    credential = TrelloCredential(
        project_id=project_id,
        api_key="a" * 32,
        api_token="b" * 64,
        is_active=True,
    )
    db.add(credential)
    await db.flush()

    board = TrelloBoard(
        credential_id=credential.id,
        trello_id="trello_board_comments",
        name="Comment Board",
        description="",
        short_url="https://trello.com/b/comments",
        trello_org_id=None,
        is_closed=False,
        last_synced_at=datetime.now(UTC),
        last_action_id=None,
    )
    db.add(board)
    await db.flush()

    card = TrelloCard(
        board_id=board.id,
        list_id=None,
        trello_id="card_comments_1",
        trello_short_id=42,
        name="Integrate payments",
        description="Investigate API handoff",
        member_ids=["dev_1"],
        labels=[],
        due_date=None,
        due_complete=False,
        is_closed=False,
        trello_last_activity=datetime.now(UTC),
        entered_wip_at=datetime.now(UTC),
        entered_done_at=None,
        trello_created_at=datetime.now(UTC),
        cycle_time_hours=None,
        lead_time_hours=None,
        is_stalled=False,
        stalled_since=None,
    )
    db.add(card)
    await db.flush()

    old_time = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)
    db.add_all([
        TrelloAction(
            card_id=card.id,
            trello_action_id="act_1",
            action_type="commentCard",
            action_date=old_time,
            data={"text": "I am blocked waiting for payment API access. @backend-team please help https://example.com/spec"},
            trello_member_id="dev_1",
            member_name="Alice",
        ),
        TrelloAction(
            card_id=card.id,
            trello_action_id="act_2",
            action_type="commentCard",
            action_date=old_time,
            data={"text": "Should this endpoint return a list or a single object?"},
            trello_member_id="dev_1",
            member_name="Alice",
        ),
    ])
    await db.commit()

    resp = await client.get(f"/api/v1/trello/projects/{project_id}/comment-insights")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["tickets_analyzed"] == 1
    assert payload["blocker_comments"] >= 1
    assert payload["unanswered_questions_over_24h"] >= 1
    assert payload["tickets"][0]["potentially_blocked"] is True
    assert payload["tickets"][0]["needs_clarification"] is True
    assert "waiting for" in payload["tickets"][0]["detected_blockers"]
    assert payload["tickets"][0]["comments"][0]["mentioned_users"] == ["backend-team"]
    assert payload["tickets"][0]["comments"][0]["attachments_or_links"] == ["https://example.com/spec"]
