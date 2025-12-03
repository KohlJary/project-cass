"""
WebSocket Connection Manager
Handles active connections for broadcasting messages
"""
from typing import List
from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections for real-time communication"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Send a message to all connected clients"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Connection might be closed, will be cleaned up on next message
                pass

    @property
    def connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)
