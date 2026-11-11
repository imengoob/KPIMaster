"""
Unit tests for the TrelloAdapter — covers the normalization logic.

All tests use a fake TrelloClient injected via dependency replacement
so no real Trello API calls are made.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.integrations.base import NormalizedBoard, NormalizedTask, ProviderType
from app.integrations.providers.trello.adapter import TrelloAdapter


# ── Fake Trello data factories ────────────────────────────────────────────────

def _fake_board(
    board_id: str = "board1",
    name: str = "Sprint Board",
    short_url: str = "https://trello.com/b/board1",
    closed: bool = False,
):
    b = MagicMock()
    b.id = board_id
    b.name = name
    b.shortUrl = short_url
    b.closed = closed
    return b


def _fake_list(list_id: str = "list1", name: str = "In Progress"):
    lst = MagicMock()
    lst.id = list_id
    lst.name = name
    return lst


def _fake_label(color: str = "red", name: str = "Blocker"):
    lbl = MagicMock()
    lbl.color = color
    lbl.name = name
    return lbl


def _fake_card(
    card_id: str = "card1",
    name: str = "Build auth module",
    list_id: str = "list1",
    labels: list | None = None,
    due: str | None = None,
    desc: str = "",
    member_ids: list | None = None,
):
    c = MagicMock()
    c.id = card_id
    c.name = name
    c.idList = list_id
    c.labels = labels or []
    c.due = due
    c.desc = desc
    c.idMembers = member_ids or []
    return c


@pytest.fixture
def mock_trello_client():
    client = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def adapter(mock_trello_client):
    a = TrelloAdapter.__new__(TrelloAdapter)
    a._account_id = 1
    a._api_key = "fake-key"
    a._api_token = "fake-token"
    a._client = mock_trello_client
    return a


# ── validate_credentials ──────────────────────────────────────────────────────

async def test_validate_credentials_returns_true_on_success(adapter, mock_trello_client):
    mock_trello_client.get_me = AsyncMock(return_value=MagicMock())
    assert await adapter.validate_credentials() is True


async def test_validate_credentials_returns_false_on_exception(adapter, mock_trello_client):
    mock_trello_client.get_me = AsyncMock(side_effect=Exception("Unauthorized"))
    assert await adapter.validate_credentials() is False


# ── get_boards ────────────────────────────────────────────────────────────────

async def test_get_boards_returns_normalized_boards(adapter, mock_trello_client):
    mock_trello_client.get_my_boards = AsyncMock(return_value=[
        _fake_board("b1", "Alpha"),
        _fake_board("b2", "Beta"),
    ])
    boards = await adapter.get_boards()
    assert len(boards) == 2
    assert all(isinstance(b, NormalizedBoard) for b in boards)
    assert {b.name for b in boards} == {"Alpha", "Beta"}


async def test_get_boards_filters_closed_boards(adapter, mock_trello_client):
    mock_trello_client.get_my_boards = AsyncMock(return_value=[
        _fake_board("b1", "Active", closed=False),
        _fake_board("b2", "Archived", closed=True),
    ])
    boards = await adapter.get_boards()
    assert len(boards) == 1
    assert boards[0].name == "Active"


async def test_get_boards_sets_provider_to_trello(adapter, mock_trello_client):
    mock_trello_client.get_my_boards = AsyncMock(return_value=[_fake_board()])
    boards = await adapter.get_boards()
    assert boards[0].provider == ProviderType.TRELLO


async def test_get_boards_sets_is_active_true_for_open_board(adapter, mock_trello_client):
    mock_trello_client.get_my_boards = AsyncMock(return_value=[_fake_board(closed=False)])
    boards = await adapter.get_boards()
    assert boards[0].is_active is True


async def test_get_boards_uses_shorturl(adapter, mock_trello_client):
    mock_trello_client.get_my_boards = AsyncMock(return_value=[
        _fake_board(short_url="https://trello.com/b/myboard")
    ])
    boards = await adapter.get_boards()
    assert boards[0].url == "https://trello.com/b/myboard"


# ── get_tasks / _map_card ─────────────────────────────────────────────────────

async def test_get_tasks_maps_cards_to_normalized_tasks(adapter, mock_trello_client):
    lst = _fake_list("list1", "Doing")
    card = _fake_card("card1", "Build login", list_id="list1")
    mock_trello_client.get_board_cards = AsyncMock(return_value=[card])
    mock_trello_client.get_board_lists = AsyncMock(return_value=[lst])

    tasks = await adapter.get_tasks("board1")
    assert len(tasks) == 1
    t = tasks[0]
    assert isinstance(t, NormalizedTask)
    assert t.id == "card1"
    assert t.title == "Build login"
    assert t.board_id == "board1"
    assert t.provider == ProviderType.TRELLO


async def test_status_is_in_progress_for_wip_list(adapter, mock_trello_client):
    lst = _fake_list("l1", "In Progress")
    card = _fake_card(list_id="l1")
    mock_trello_client.get_board_cards = AsyncMock(return_value=[card])
    mock_trello_client.get_board_lists = AsyncMock(return_value=[lst])

    tasks = await adapter.get_tasks("board1")
    assert tasks[0].status == "in_progress"


async def test_status_is_done_for_done_list(adapter, mock_trello_client):
    lst = _fake_list("l2", "Done")
    card = _fake_card(list_id="l2")
    mock_trello_client.get_board_cards = AsyncMock(return_value=[card])
    mock_trello_client.get_board_lists = AsyncMock(return_value=[lst])

    tasks = await adapter.get_tasks("board1")
    assert tasks[0].status == "done"


async def test_status_is_done_for_complete_keyword(adapter, mock_trello_client):
    for name in ("Completed", "Finished", "Deployed"):
        lst = _fake_list("l", name)
        card = _fake_card(list_id="l")
        mock_trello_client.get_board_cards = AsyncMock(return_value=[card])
        mock_trello_client.get_board_lists = AsyncMock(return_value=[lst])
        tasks = await adapter.get_tasks("b")
        assert tasks[0].status == "done", f"Expected done for list '{name}'"


async def test_status_is_backlog_for_backlog_list(adapter, mock_trello_client):
    lst = _fake_list("l", "Backlog")
    card = _fake_card(list_id="l")
    mock_trello_client.get_board_cards = AsyncMock(return_value=[card])
    mock_trello_client.get_board_lists = AsyncMock(return_value=[lst])

    tasks = await adapter.get_tasks("board1")
    assert tasks[0].status == "backlog"


async def test_label_priority_red_maps_to_critical(adapter, mock_trello_client):
    lst = _fake_list("l", "Doing")
    card = _fake_card(list_id="l", labels=[_fake_label("red", "Urgent")])
    mock_trello_client.get_board_cards = AsyncMock(return_value=[card])
    mock_trello_client.get_board_lists = AsyncMock(return_value=[lst])

    tasks = await adapter.get_tasks("board1")
    assert tasks[0].priority == "critical"


async def test_label_priority_orange_maps_to_high(adapter, mock_trello_client):
    lst = _fake_list("l", "Doing")
    card = _fake_card(list_id="l", labels=[_fake_label("orange", "High")])
    mock_trello_client.get_board_cards = AsyncMock(return_value=[card])
    mock_trello_client.get_board_lists = AsyncMock(return_value=[lst])

    tasks = await adapter.get_tasks("board1")
    assert tasks[0].priority == "high"


async def test_no_labels_gives_none_priority(adapter, mock_trello_client):
    lst = _fake_list("l", "Doing")
    card = _fake_card(list_id="l", labels=[])
    mock_trello_client.get_board_cards = AsyncMock(return_value=[card])
    mock_trello_client.get_board_lists = AsyncMock(return_value=[lst])

    tasks = await adapter.get_tasks("board1")
    assert tasks[0].priority is None


async def test_due_date_is_parsed_from_iso_string(adapter, mock_trello_client):
    lst = _fake_list("l", "Doing")
    due_str = "2026-05-01T12:00:00.000Z"
    card = _fake_card(list_id="l", due=due_str)
    mock_trello_client.get_board_cards = AsyncMock(return_value=[card])
    mock_trello_client.get_board_lists = AsyncMock(return_value=[lst])

    tasks = await adapter.get_tasks("board1")
    assert tasks[0].due_date is not None
    assert tasks[0].due_date.year == 2026
    assert tasks[0].due_date.month == 5


async def test_due_date_is_none_when_not_set(adapter, mock_trello_client):
    lst = _fake_list("l", "Doing")
    card = _fake_card(list_id="l", due=None)
    mock_trello_client.get_board_cards = AsyncMock(return_value=[card])
    mock_trello_client.get_board_lists = AsyncMock(return_value=[lst])

    tasks = await adapter.get_tasks("board1")
    assert tasks[0].due_date is None


async def test_assignee_ids_mapped_from_member_ids(adapter, mock_trello_client):
    lst = _fake_list("l", "Doing")
    card = _fake_card(list_id="l", member_ids=["user1", "user2"])
    mock_trello_client.get_board_cards = AsyncMock(return_value=[card])
    mock_trello_client.get_board_lists = AsyncMock(return_value=[lst])

    tasks = await adapter.get_tasks("board1")
    assert tasks[0].assignee_ids == ["user1", "user2"]


# ── sync_board ────────────────────────────────────────────────────────────────

async def test_sync_board_returns_task_count(adapter, mock_trello_client):
    lst = _fake_list("l", "Doing")
    cards = [_fake_card(f"c{i}") for i in range(3)]
    mock_trello_client.get_board_cards = AsyncMock(return_value=cards)
    mock_trello_client.get_board_lists = AsyncMock(return_value=[lst])

    count = await adapter.sync_board("board1")
    assert count == 3


# ── close ─────────────────────────────────────────────────────────────────────

async def test_close_delegates_to_client(adapter, mock_trello_client):
    await adapter.close()
    mock_trello_client.close.assert_called_once()
