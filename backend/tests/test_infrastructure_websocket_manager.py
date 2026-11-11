import pytest
from unittest.mock import AsyncMock

from app.infrastructure.websocket_manager import WebSocketManager, Connection


@pytest.fixture
def ws_manager():
    return WebSocketManager()


def make_mock_websocket():
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect_project(ws_manager):
    ws = make_mock_websocket()
    conn = await ws_manager.connect(ws, project_id=10)
    
    ws.accept.assert_awaited_once()
    assert conn.project_id == 10
    assert ws_manager.total_connections == 1
    assert conn in ws_manager._project_connections[10]


@pytest.mark.asyncio
async def test_connect_global(ws_manager):
    ws = make_mock_websocket()
    conn = await ws_manager.connect(ws, project_id=None)
    
    assert conn.project_id is None
    assert ws_manager.total_connections == 1
    assert conn in ws_manager._global_connections


@pytest.mark.asyncio
async def test_disconnect(ws_manager):
    ws1 = make_mock_websocket()
    conn1 = await ws_manager.connect(ws1, project_id=10)
    
    ws2 = make_mock_websocket()
    conn2 = await ws_manager.connect(ws2, project_id=None)
    
    assert ws_manager.total_connections == 2
    
    await ws_manager.disconnect(conn1)
    assert ws_manager.total_connections == 1
    assert conn1 not in ws_manager._project_connections[10]
    
    await ws_manager.disconnect(conn2)
    assert ws_manager.total_connections == 0
    assert conn2 not in ws_manager._global_connections


@pytest.mark.asyncio
async def test_broadcast_to_project(ws_manager):
    ws_proj = make_mock_websocket()
    conn_proj = await ws_manager.connect(ws_proj, project_id=10)
    
    ws_global = make_mock_websocket()
    conn_global = await ws_manager.connect(ws_global, project_id=None)
    
    ws_other = make_mock_websocket()
    conn_other = await ws_manager.connect(ws_other, project_id=11)
    
    sent = await ws_manager.broadcast_to_project(10, {"msg": "hello"})
    
    assert sent == 2  # proj_id 10 + global
    ws_proj.send_text.assert_awaited_once()
    ws_global.send_text.assert_awaited_once()
    ws_other.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_to_project_disconnects_dead_clients(ws_manager):
    ws_proj = make_mock_websocket()
    ws_proj.send_text.side_effect = Exception("Connection closed")
    conn_proj = await ws_manager.connect(ws_proj, project_id=10)
    
    sent = await ws_manager.broadcast_to_project(10, {"msg": "hello"})
    assert sent == 0
    assert ws_manager.total_connections == 0  # was removed


@pytest.mark.asyncio
async def test_broadcast_global(ws_manager):
    ws_proj = make_mock_websocket()
    conn_proj = await ws_manager.connect(ws_proj, project_id=10)
    
    ws_global = make_mock_websocket()
    conn_global = await ws_manager.connect(ws_global, project_id=None)
    
    sent = await ws_manager.broadcast_global({"msg": "hello to all"})
    
    assert sent == 2
    ws_proj.send_text.assert_awaited_once()
    ws_global.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_global_disconnects_dead_clients(ws_manager):
    ws_global = make_mock_websocket()
    ws_global.send_text.side_effect = Exception("Dead")
    conn_global = await ws_manager.connect(ws_global, project_id=None)
    
    ws_proj = make_mock_websocket()
    ws_proj.send_text.side_effect = Exception("Dead")
    conn_proj = await ws_manager.connect(ws_proj, project_id=10)
    
    sent = await ws_manager.broadcast_global({"msg": "boom"})
    
    assert sent == 0
    assert ws_manager.total_connections == 0


@pytest.mark.asyncio
async def test_send_to_connection(ws_manager):
    ws = make_mock_websocket()
    conn = await ws_manager.connect(ws, project_id=10)
    
    res = await ws_manager.send_to_connection(conn, {"msg": "hello"})
    assert res is True
    ws.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_to_connection_failure(ws_manager):
    ws = make_mock_websocket()
    ws.send_text.side_effect = Exception("Fail")
    conn = await ws_manager.connect(ws, project_id=10)
    
    res = await ws_manager.send_to_connection(conn, {"msg": "hello"})
    assert res is False
    assert ws_manager.total_connections == 0
