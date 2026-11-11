"""
WebSocket API endpoints — real-time sprint tracking.

Clients connect to:
  ws://host/api/v1/ws/projects/{project_id}  — project-scoped feed
  ws://host/api/v1/ws/global                 — all events (admin/ops)

Message format sent to clients:
  {
    "type": "ticket.stalled" | "blocker.detected" | "sprint.health_degraded" | ...,
    "payload": { ...event data... },
    "timestamp": "2026-04-10T18:00:00Z"
  }

The server sends a heartbeat ping every 30s to detect dead connections.
"""
import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.security import decode_access_token

router = APIRouter(prefix="/ws", tags=["WebSocket"])

# The manager is injected from app.state (set in main.py)
_HEARTBEAT_INTERVAL = 30  # seconds


async def _authorize_websocket(websocket: WebSocket) -> str | None:
    if not settings.auth_enabled:
        return None

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return None

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        await websocket.close(code=4401)
        return None

    return str(payload["sub"])


@router.websocket("/projects/{project_id}")
async def project_feed(websocket: WebSocket, project_id: int) -> None:
    """
    Real-time feed for a specific project.

    Clients receive:
      - Ticket updates (status changes, new assignments)
      - Blocker alerts
      - Sprint health warnings
      - KPI updates
    """
    user_id = await _authorize_websocket(websocket)
    if settings.auth_enabled and user_id is None:
        return

    manager = websocket.app.state.ws_manager
    conn = await manager.connect(websocket, project_id=project_id)

    # Send initial connection ack
    await websocket.send_text(json.dumps({
        "type": "connection.established",
        "payload": {"project_id": project_id, "connection_id": conn.id, "user_id": user_id},
        "timestamp": datetime.now(UTC).isoformat(),
    }))

    heartbeat_task = asyncio.create_task(_heartbeat(websocket, conn.id))

    try:
        while True:
            # Keep connection alive; also process any incoming client messages
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        await manager.disconnect(conn)


@router.websocket("/global")
async def global_feed(websocket: WebSocket) -> None:
    """Global admin feed — receives all events across all projects."""
    user_id = await _authorize_websocket(websocket)
    if settings.auth_enabled and user_id is None:
        return

    manager = websocket.app.state.ws_manager
    conn = await manager.connect(websocket, project_id=None)

    await websocket.send_text(json.dumps({
        "type": "connection.established",
        "payload": {"scope": "global", "connection_id": conn.id, "user_id": user_id},
        "timestamp": datetime.now(UTC).isoformat(),
    }))

    heartbeat_task = asyncio.create_task(_heartbeat(websocket, conn.id))

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        await manager.disconnect(conn)


async def _heartbeat(websocket: WebSocket, conn_id: str) -> None:
    """Sends a periodic ping to detect stale connections."""
    while True:
        await asyncio.sleep(_HEARTBEAT_INTERVAL)
        try:
            await websocket.send_text(json.dumps({
                "type": "heartbeat",
                "timestamp": datetime.now(UTC).isoformat(),
            }))
        except Exception:
            break
