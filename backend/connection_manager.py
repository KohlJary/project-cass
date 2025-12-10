"""Extracted from main_sdk.py"""


from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request, BackgroundTasks
from typing import Optional, List, Dict

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # Map websocket to user_id for per-connection user state
        self.connection_users: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, user_id: Optional[str] = None):
        await websocket.accept()
        self.active_connections.append(websocket)
        if user_id:
            self.connection_users[websocket] = user_id

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.connection_users:
            del self.connection_users[websocket]

    def get_user_id(self, websocket: WebSocket) -> Optional[str]:
        """Get user_id for a specific connection"""
        return self.connection_users.get(websocket)

    def set_user_id(self, websocket: WebSocket, user_id: str):
        """Set user_id for a specific connection"""
        self.connection_users[websocket] = user_id

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)
