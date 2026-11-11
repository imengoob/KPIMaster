import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
from sqlalchemy.exc import SQLAlchemyError
import httpx

from app.core.exceptions import ConflictError

from httpx import ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_global_exception_handler_triggers(existing_project: dict):
    # Mocking a core repository to raise a raw Exception
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch("app.services.trello.live_project_service.TrelloLiveProjectService.list_developers", side_effect=Exception("Raw Crash!")):
            pid = existing_project["id"]
            response = await client.get(f"/api/v1/developers?project_id={pid}")
            assert response.status_code == 500
            assert response.json()["error_code"] == "INTERNAL_SERVER_ERROR"

@pytest.mark.asyncio
async def test_domain_exception_handler_triggers(existing_project: dict):
    # Mocking to raise a SprintPulseError directly
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch("app.services.trello.live_project_service.TrelloLiveProjectService.list_developers", side_effect=ConflictError(message="Domain Error", error_code="CONFLICT")):
            pid = existing_project["id"]
            response = await client.get(f"/api/v1/developers?project_id={pid}")
            assert response.status_code == 409
            assert response.json()["error_code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_trello_import_boards_httpx_status_error(client: AsyncClient, existing_project: dict):
    # Test our newly replaced exception logic inside /api/v1/trello/import-boards
    request = httpx.Request("GET", "https://trello.com")
    response = httpx.Response(401, request=request)
    with patch("app.services.trello.client.TrelloClient.get_my_boards", side_effect=httpx.HTTPStatusError("Auth fail", request=request, response=response)):
        pay = {"api_key": "12345678", "api_token": "123456789012345678"}
        resp = await client.post("/api/v1/trello/import-boards", json=pay)
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_trello_import_boards_httpx_request_error(client: AsyncClient, existing_project: dict):
    request = httpx.Request("GET", "https://trello.com")
    with patch("app.services.trello.client.TrelloClient.get_my_boards", side_effect=httpx.RequestError("Network drop", request=request)):
        pay = {"api_key": "12345678", "api_token": "123456789012345678"}
        resp = await client.post("/api/v1/trello/import-boards", json=pay)
        assert resp.status_code == 503


from app.schemas.trello import TrelloAPIBoard

@pytest.mark.asyncio
async def test_trello_connect_sqlalchemy_error(client: AsyncClient, existing_project: dict):
    # Test line 353 fallback
    mock_board = TrelloAPIBoard(id="b1", name="Board", closed=False, idOrganization="org", shortUrl="http://", desc="desc")
    with patch("app.services.trello.client.TrelloClient.get_my_boards", return_value=[mock_board]):
        with patch("app.services.trello.sync_service.TrelloSyncService.full_sync", side_effect=SQLAlchemyError("DB Issue")):
            pid = existing_project["id"]
            pay = {"project_id": pid, "api_key": "12345678", "api_token": "123456789012345678"}
            resp = await client.post("/api/v1/trello/connect", json=pay)
            assert resp.status_code == 502


@pytest.mark.asyncio
async def test_trello_available_boards_filters(client: AsyncClient, existing_project: dict):
    mock_board = TrelloAPIBoard(id="b1", name="Board", desc="Test", shortUrl="http://", closed=False, idOrganization="org")
    with patch("app.services.trello.client.TrelloClient.get_my_boards", return_value=[mock_board]):
        pay = {"api_key": "12345678", "api_token": "123456789012345678", "board_ids": ["b2"]}
        resp = await client.post("/api/v1/trello/available-boards", json=pay)
        # Should raise 404 because "b2" doesn't match available board "b1"
        assert resp.status_code == 404
