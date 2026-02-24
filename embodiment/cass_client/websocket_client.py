"""
WebSocket client for Cass backend.

Handles connection, message sending, and response handling.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    logger.warning("websockets not available - install with: pip install websockets")


class ConnectionState(Enum):
    """WebSocket connection state."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


@dataclass
class CassMessage:
    """A message from Cass."""
    type: str  # "connected", "thinking", "response", "audio", "system", "error"
    content: Optional[str] = None
    audio: Optional[str] = None  # Base64 WAV
    metadata: Optional[dict] = None


class CassClient:
    """
    WebSocket client for Cass backend.

    Connects to the vessel backend and handles bidirectional communication.
    """

    def __init__(
        self,
        url: str = "ws://localhost:8000/ws",
        user_id: str = "sensor-module",
        daemon_id: str = "cass",
        device_name: str = "Embodiment",
        reconnect_interval: float = 5.0,
    ):
        """
        Args:
            url: WebSocket URL for Cass backend
            user_id: User identifier
            daemon_id: Daemon identifier
            reconnect_interval: Seconds between reconnection attempts
        """
        self.url = url
        self.user_id = user_id
        self.daemon_id = daemon_id
        self.device_name = device_name
        self.reconnect_interval = reconnect_interval

        self._ws = None
        self._state = ConnectionState.DISCONNECTED
        self._running = False
        self._conversation_id: Optional[str] = None

        # Callbacks
        self.on_state_change: Optional[Callable[[ConnectionState], None]] = None
        self.on_message: Optional[Callable[[CassMessage], None]] = None
        self.on_thinking: Optional[Callable[[], None]] = None
        self.on_response: Optional[Callable[[str], None]] = None
        self.on_audio: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    @property
    def available(self) -> bool:
        """Check if WebSocket client is available."""
        return WEBSOCKETS_AVAILABLE

    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state

    @property
    def connected(self) -> bool:
        """Check if connected."""
        return self._state == ConnectionState.CONNECTED

    def _set_state(self, state: ConnectionState):
        """Update connection state and notify."""
        if self._state != state:
            self._state = state
            if self.on_state_change:
                self.on_state_change(state)

    async def connect(self):
        """Connect to Cass backend."""
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets not available")
            return False

        self._running = True
        self._set_state(ConnectionState.CONNECTING)

        try:
            self._ws = await websockets.connect(self.url)
            self._set_state(ConnectionState.CONNECTED)
            logger.info(f"Connected to {self.url}")

            # Start receive loop
            asyncio.create_task(self._receive_loop())
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._set_state(ConnectionState.DISCONNECTED)
            return False

    async def disconnect(self):
        """Disconnect from Cass backend."""
        self._running = False

        if self._ws:
            await self._ws.close()
            self._ws = None

        self._set_state(ConnectionState.DISCONNECTED)
        logger.info("Disconnected")

    async def _receive_loop(self):
        """Receive messages from backend."""
        try:
            async for message in self._ws:
                await self._handle_message(message)
        except websockets.ConnectionClosed:
            logger.warning("Connection closed")
            self._set_state(ConnectionState.DISCONNECTED)

            # Attempt reconnection
            if self._running:
                asyncio.create_task(self._reconnect())
        except Exception as e:
            logger.error(f"Receive error: {e}")
            self._set_state(ConnectionState.DISCONNECTED)

    async def _reconnect(self):
        """Attempt to reconnect."""
        self._set_state(ConnectionState.RECONNECTING)

        while self._running and self._state != ConnectionState.CONNECTED:
            logger.info(f"Reconnecting in {self.reconnect_interval}s...")
            await asyncio.sleep(self.reconnect_interval)

            if await self.connect():
                break

    async def _handle_message(self, raw_message: str):
        """Handle incoming message from backend."""
        try:
            data = json.loads(raw_message)
            msg_type = data.get("type", "unknown")

            msg = CassMessage(
                type=msg_type,
                content=data.get("text") or data.get("content") or data.get("message"),
                audio=data.get("audio"),
                metadata=data.get("metadata"),
            )

            # Generic callback
            if self.on_message:
                self.on_message(msg)

            # Type-specific callbacks
            if msg_type == "thinking" and self.on_thinking:
                self.on_thinking()
            elif msg_type == "response" and self.on_response:
                self.on_response(msg.content or "")
            elif msg_type == "audio" and self.on_audio and msg.audio:
                self.on_audio(msg.audio)
            elif msg_type == "error" and self.on_error:
                self.on_error(msg.content or "Unknown error")
            elif msg_type == "connected":
                self._conversation_id = data.get("conversation_id")
                logger.info(f"Conversation ID: {self._conversation_id}")

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON: {raw_message[:100]}")
        except Exception as e:
            logger.error(f"Message handling error: {e}")

    async def send_message(self, text: str, request_audio: bool = True):
        """
        Send a message to Cass.

        Args:
            text: Message text
            request_audio: Whether to request TTS audio in response
        """
        if not self.connected or not self._ws:
            logger.warning("Not connected - message not sent")
            return False

        message = {
            "type": "chat",
            "message": text,
            "request_audio": request_audio,
            "source_device": self.device_name,
        }

        if self._conversation_id:
            message["conversation_id"] = self._conversation_id

        try:
            await self._ws.send(json.dumps(message))
            logger.debug(f"Sent: {text[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

    async def send_audio(self, audio_data: bytes, sample_rate: int = 16000):
        """
        Send audio data for speech-to-text processing.

        Note: This requires backend support for audio messages.
        Currently the backend expects text, so this would need
        local STT or backend STT endpoint.

        Args:
            audio_data: Raw audio bytes
            sample_rate: Audio sample rate
        """
        # TODO: Implement when backend supports audio input
        # For now, we'd do STT locally and send text
        logger.warning("Audio sending not yet implemented")
        pass

    async def run(self):
        """Run the client (connect and maintain connection)."""
        await self.connect()

        # Keep running while connected or reconnecting
        while self._running:
            await asyncio.sleep(1)

        await self.disconnect()
