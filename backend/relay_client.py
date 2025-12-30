"""
Relay Client - WebSocket client for connecting to the relay server.

Maintains outbound connection to the relay server, enabling communication
with mobile clients without port forwarding.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Optional
import aiohttp
import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)

# Backend base URL for local HTTP requests
BACKEND_BASE_URL = "http://localhost:8000"

# Global relay client instance
_relay_client: Optional["RelayClient"] = None


class RelayClient:
    """WebSocket client that connects to the relay server."""

    def __init__(
        self,
        relay_url: str,
        relay_secret: str,
        message_handler: Callable[[dict], Coroutine[Any, Any, None]],
        daemon_id: str = "",
    ):
        self.relay_url = relay_url
        self.relay_secret = relay_secret
        self.message_handler = message_handler
        self.daemon_id = daemon_id
        self.ws: Optional[WebSocketClientProtocol] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._running = False
        self._reconnect_delays = [1, 2, 5, 10, 30, 60]
        self._reconnect_attempt = 0

    async def connect(self) -> bool:
        """Establish connection to the relay server."""
        try:
            self.ws = await websockets.connect(
                f"{self.relay_url}/home",
                additional_headers={"Authorization": f"Bearer {self.relay_secret}"},
                ping_interval=30,
                ping_timeout=10,
            )
            self._running = True
            self._reconnect_attempt = 0

            # Send auth message
            await self.ws.send(json.dumps({
                "type": "auth",
                "secret": self.relay_secret,
                "daemon_id": self.daemon_id,
            }))

            logger.info("Connected to relay server")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to relay: {e}")
            return False

    async def start(self) -> None:
        """Start the relay client with auto-reconnection."""
        self._running = True
        while self._running:
            if await self.connect():
                await self._listen()

            if self._running:
                delay = self._reconnect_delays[
                    min(self._reconnect_attempt, len(self._reconnect_delays) - 1)
                ]
                logger.info(f"Reconnecting to relay in {delay}s...")
                await asyncio.sleep(delay)
                self._reconnect_attempt += 1

    async def _listen(self) -> None:
        """Listen for messages from the relay server."""
        try:
            async for message in self.ws:  # type: ignore
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    if msg_type == "chat_message":
                        # Extract fields for the handler
                        client_id = data.get("client_id", "")
                        user_id = data.get("user_id", "")
                        payload = data.get("payload", {})
                        await self.message_handler(client_id, user_id, payload)
                    elif msg_type == "auth_success":
                        logger.info("Relay authentication successful")
                    elif msg_type == "error":
                        logger.error(f"Relay error: {data.get('message')}")
                    elif msg_type == "http_request":
                        # Proxy HTTP request to local backend
                        asyncio.create_task(self._handle_http_request(data))
                    elif msg_type == "status_request":
                        # Respond with status
                        await self.send({"type": "status", "status": "online"})
                    else:
                        logger.debug(f"Unhandled relay message type: {msg_type}")
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from relay: {message}")
                except Exception as e:
                    logger.error(f"Error handling relay message: {e}")
        except websockets.ConnectionClosed as e:
            logger.warning(f"Relay connection closed: {e}")
        except Exception as e:
            logger.error(f"Relay listener error: {e}")

    async def stop(self) -> None:
        """Stop the relay client."""
        self._running = False
        if self.ws:
            await self.ws.close()
            self.ws = None

    async def send(self, message: dict) -> bool:
        """Send a message to the relay server."""
        if not self.ws or self.ws.closed:
            logger.warning("Cannot send - not connected to relay")
            return False

        try:
            await self.ws.send(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Failed to send to relay: {e}")
            return False

    async def send_response(self, client_id: str, payload: dict) -> bool:
        """Send a chat response to a specific mobile client."""
        return await self.send({
            "type": "chat_response",
            "client_id": client_id,
            "payload": payload,
        })

    async def send_push(
        self,
        user_id: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
    ) -> bool:
        """Request the relay to send a push notification."""
        return await self.send({
            "type": "push_request",
            "user_id": user_id,
            "title": title,
            "body": body,
            "data": data or {},
        })

    async def _handle_http_request(self, data: dict) -> None:
        """Handle an HTTP request proxied from the relay."""
        request_id = data.get("request_id", "")
        method = data.get("method", "GET")
        path = data.get("path", "/")
        headers = data.get("headers", {})
        body = data.get("body")

        logger.debug(f"Proxying HTTP {method} {path}")

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{BACKEND_BASE_URL}{path}"

                # Prepare request kwargs
                kwargs: dict = {"headers": headers}
                if body and method not in ("GET", "HEAD"):
                    kwargs["data"] = body

                async with session.request(method, url, **kwargs) as resp:
                    response_body = await resp.text()
                    response_headers = dict(resp.headers)

                    await self.send({
                        "type": "http_response",
                        "request_id": request_id,
                        "status": resp.status,
                        "headers": response_headers,
                        "body": response_body,
                    })
        except Exception as e:
            logger.error(f"HTTP proxy error: {e}")
            await self.send({
                "type": "http_response",
                "request_id": request_id,
                "status": 502,
                "headers": {"content-type": "application/json"},
                "body": json.dumps({"error": str(e)}),
            })

    @property
    def is_connected(self) -> bool:
        """Check if connected to the relay."""
        return self.ws is not None and not self.ws.closed


async def init_relay_client(
    url: str,
    secret: str,
    daemon_id: str,
    message_handler: Callable[[dict], Coroutine[Any, Any, None]],
) -> RelayClient:
    """Initialize and start the global relay client.

    Args:
        url: WebSocket URL of the relay server
        secret: Shared secret for authentication
        daemon_id: This daemon's unique identifier
        message_handler: Async callback for handling messages from relay
    """
    global _relay_client

    _relay_client = RelayClient(url, secret, message_handler, daemon_id)

    # Start in background task
    asyncio.create_task(_relay_client.start())

    return _relay_client


def get_relay_client() -> Optional[RelayClient]:
    """Get the global relay client instance."""
    return _relay_client
