import pytest
from unittest.mock import AsyncMock, patch

from app.services.trello.client import TrelloClient
from app.services.trello.live_project_service import TrelloLiveProjectService
from app.services.trello.sync_service import TrelloSyncService

@pytest.fixture
def mock_client():
    client = TrelloClient("dummy_key", "dummy_token")
    client._get = AsyncMock()
    return client

async def test_trello_client_get_boards(mock_client):
    mock_client._get.return_value = [{"id": "1", "name": "board1", "closed": False}]
    res = await mock_client.get_my_boards()
    assert len(res) == 1
    assert res[0].id == "1"

async def test_trello_client_get_board_lists(mock_client):
    mock_client._get.return_value = [{"id": "1", "name": "To Do", "closed": False, "pos": 0, "idBoard": "b1"}]
    res = await mock_client.get_board_lists("board_id")
    assert res[0].name == "To Do"

async def test_trello_client_get_board_cards(mock_client):
    mock_client._get.return_value = [{"id": "c1", "name": "Task", "idShort": 1, "idList": "1", "idBoard": "b1", "labels": [], "idMembers": []}]
    res = await mock_client.get_board_cards("board_id")
    assert res[0].id == "c1"

async def test_trello_client_get_board_actions(mock_client):
    mock_client._get.return_value = [{"id": "a1", "type": "createCard", "date": "2026-04-20T00:00:00Z", "idMemberCreator": "x", "data": {}}]
    res = await mock_client.get_board_actions("board_id")
    assert res[0].id == "a1"

async def test_trello_client_get_members(mock_client):
    mock_client._get.return_value = [{"id": "m1", "fullName": "John Doc", "username": "doc"}]
    res = await mock_client.get_board_members("board_id")
    assert res[0].id == "m1"

@pytest.mark.asyncio
async def test_live_project_service_instantiation(db):
    svc = TrelloLiveProjectService(db)
    assert svc is not None

