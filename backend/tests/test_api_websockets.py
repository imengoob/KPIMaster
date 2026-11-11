import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_websocket_connect():
    """
    Test that the websocket endpoint accepts connections.
    We use Starlette's TestClient to easily test websocket routes.
    """
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws/global") as websocket:
            # Initial ack msg should be received
            data = websocket.receive_json()
            assert data["type"] == "connection.established"
            assert data["payload"]["scope"] == "global"
            
            websocket.close()
