"""
WebSocket Connection Manager
=============================

Manages all active WebSocket connections with support for:
  - Per-project rooms (clients only receive events for their project)
  - Global broadcast (admin dashboards, system-wide alerts)
  - Graceful connection cleanup on disconnect

Each connection is identified by a (connection_id, project_id) pair.
The manager is a singleton, instantiated in main.py and shared via DI.

Real-time event flow:
  Event Bus handler → WebSocketManager.broadcast_to_project()
                    → serialised JSON → all matching WebSocket clients
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect

from app.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Connection:
    id: str
    websocket: WebSocket
    project_id: int | None = None  # None = global listener


class WebSocketManager:
    def __init__(self) -> None:
        # project_id → list[Connection]
        self._project_connections: dict[int, list[Connection]] = defaultdict(list)
        # Global listeners (no project filter)
        self._global_connections: list[Connection] = []
        self._lock = asyncio.Lock()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def connect(
        self, websocket: WebSocket, project_id: int | None = None
    ) -> Connection:
        await websocket.accept()
        conn = Connection(id=str(uuid.uuid4()), websocket=websocket, project_id=project_id)

        async with self._lock:
            if project_id is not None:
                self._project_connections[project_id].append(conn)
            else:
                self._global_connections.append(conn)

        logger.info(
            "ws_client_connected",
            connection_id=conn.id,
            project_id=project_id,
            total_global=len(self._global_connections),
        )
        return conn

    async def disconnect(self, conn: Connection) -> None:
        async with self._lock:
            if conn.project_id is not None:
                conns = self._project_connections.get(conn.project_id, [])
                try:
                    conns.remove(conn)
                except ValueError:
                    pass
            else:
                try:
                    self._global_connections.remove(conn)
                except ValueError:
                    pass

        logger.info("ws_client_disconnected", connection_id=conn.id)

    # ── Broadcast ────────────────────────────────────────────────────────────

    async def broadcast_to_project(self, project_id: int, payload: dict) -> int:
        """Send payload to all clients subscribed to project_id. Returns sent count."""
        message = json.dumps(payload)
        targets = list(self._project_connections.get(project_id, []))
        targets += self._global_connections

        if not targets:
            return 0

        sent = 0
        dead: list[Connection] = []

        for conn in targets:
            try:
                await conn.websocket.send_text(message)
                sent += 1
            except Exception:
                dead.append(conn)

        for conn in dead:
            await self.disconnect(conn)

        logger.debug(
            "ws_broadcast_sent",
            project_id=project_id,
            recipients=sent,
            disconnected=len(dead),
        )
        return sent

    async def broadcast_global(self, payload: dict) -> int:
        """Send to all connected clients regardless of project."""
        all_conns = list(self._global_connections)
        for conns in self._project_connections.values():
            all_conns.extend(conns)

        message = json.dumps(payload)
        sent = 0
        dead: list[Connection] = []

        for conn in all_conns:
            try:
                await conn.websocket.send_text(message)
                sent += 1
            except Exception:
                dead.append(conn)

        for conn in dead:
            await self.disconnect(conn)

        return sent

    async def send_to_connection(self, conn: Connection, payload: dict) -> bool:
        try:
            await conn.websocket.send_text(json.dumps(payload))
            return True
        except Exception:
            await self.disconnect(conn)
            return False

    @property
    def total_connections(self) -> int:
        return len(self._global_connections) + sum(
            len(c) for c in self._project_connections.values()
        )
