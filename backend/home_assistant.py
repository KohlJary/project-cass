"""
Home Assistant API client for Cass.

Enables Cass to query state and control devices in Home Assistant.
Uses long-lived access token authentication.
"""

import os
import asyncio
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)

# Configuration from environment
HA_URL = os.getenv("HOME_ASSISTANT_URL", "http://homeassistant.local:8123")
HA_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN", "")


@dataclass
class HAEntity:
    """Represents a Home Assistant entity."""
    entity_id: str
    state: str
    attributes: Dict[str, Any]
    friendly_name: Optional[str] = None
    domain: Optional[str] = None
    area_id: Optional[str] = None

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "HAEntity":
        attrs = data.get("attributes", {})
        entity_id = data.get("entity_id", "")
        return cls(
            entity_id=entity_id,
            state=data.get("state", "unknown"),
            attributes=attrs,
            friendly_name=attrs.get("friendly_name"),
            domain=entity_id.split(".")[0] if "." in entity_id else None,
            area_id=attrs.get("area_id"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "state": self.state,
            "friendly_name": self.friendly_name,
            "domain": self.domain,
            "area_id": self.area_id,
            "attributes": self.attributes,
        }

    def summary(self) -> str:
        """Human-readable summary."""
        name = self.friendly_name or self.entity_id
        return f"{name}: {self.state}"


class HomeAssistantClient:
    """Client for Home Assistant REST API."""

    def __init__(self, url: str = None, token: str = None):
        self.url = (url or HA_URL).rstrip("/")
        self.token = token or HA_TOKEN
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        """Check if HA connection is configured."""
        return bool(self.url and self.token)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def check_connection(self) -> Dict[str, Any]:
        """Check if HA is reachable and get config."""
        if not self.is_configured:
            return {"connected": False, "error": "Not configured"}

        try:
            client = await self._get_client()
            response = await client.get("/api/config")
            response.raise_for_status()
            config = response.json()
            return {
                "connected": True,
                "location_name": config.get("location_name"),
                "version": config.get("version"),
                "components": len(config.get("components", [])),
            }
        except Exception as e:
            logger.error(f"HA connection check failed: {e}")
            return {"connected": False, "error": str(e)}

    # =========================================================================
    # State Queries
    # =========================================================================

    async def get_states(self) -> List[HAEntity]:
        """Get all entity states."""
        if not self.is_configured:
            return []

        try:
            client = await self._get_client()
            response = await client.get("/api/states")
            response.raise_for_status()
            return [HAEntity.from_api(s) for s in response.json()]
        except Exception as e:
            logger.error(f"Failed to get HA states: {e}")
            return []

    async def get_state(self, entity_id: str) -> Optional[HAEntity]:
        """Get state of a specific entity."""
        if not self.is_configured:
            return None

        try:
            client = await self._get_client()
            response = await client.get(f"/api/states/{entity_id}")
            response.raise_for_status()
            return HAEntity.from_api(response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error(f"Failed to get state for {entity_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get state for {entity_id}: {e}")
            return None

    async def get_entities_by_domain(self, domain: str) -> List[HAEntity]:
        """Get all entities of a specific domain (light, switch, etc.)."""
        states = await self.get_states()
        return [s for s in states if s.domain == domain]

    async def get_entities_by_area(self, area_id: str) -> List[HAEntity]:
        """Get all entities in a specific area."""
        states = await self.get_states()
        return [s for s in states if s.area_id == area_id]

    # =========================================================================
    # Areas
    # =========================================================================

    async def get_areas(self) -> List[Dict[str, Any]]:
        """Get all areas."""
        if not self.is_configured:
            return []

        try:
            client = await self._get_client()
            # Areas require WebSocket API, but we can get them via template
            response = await client.post(
                "/api/template",
                json={"template": "{{ areas() | list }}"}
            )
            response.raise_for_status()
            area_ids = response.json()

            # Get area names
            areas = []
            for area_id in area_ids:
                name_resp = await client.post(
                    "/api/template",
                    json={"template": f"{{{{ area_name('{area_id}') }}}}"}
                )
                if name_resp.status_code == 200:
                    areas.append({
                        "area_id": area_id,
                        "name": name_resp.json(),
                    })
            return areas
        except Exception as e:
            logger.error(f"Failed to get areas: {e}")
            return []

    # =========================================================================
    # Service Calls (Device Control)
    # =========================================================================

    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Call a Home Assistant service.

        Examples:
            call_service("light", "turn_on", "light.living_room")
            call_service("light", "turn_on", "light.living_room", {"brightness": 128})
            call_service("climate", "set_temperature", "climate.thermostat", {"temperature": 72})
        """
        if not self.is_configured:
            return {"success": False, "error": "Not configured"}

        try:
            client = await self._get_client()

            payload = data or {}
            if entity_id:
                payload["entity_id"] = entity_id

            response = await client.post(
                f"/api/services/{domain}/{service}",
                json=payload,
            )
            response.raise_for_status()

            # Service calls return list of changed states
            result = response.json()
            logger.info(f"HA service call: {domain}.{service} on {entity_id}")

            return {
                "success": True,
                "changed_entities": len(result),
                "result": result,
            }
        except httpx.HTTPStatusError as e:
            error_msg = f"Service call failed: {e.response.status_code}"
            try:
                error_body = e.response.json()
                error_msg = error_body.get("message", error_msg)
            except Exception:
                pass
            logger.error(f"HA service call failed: {error_msg}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            logger.error(f"HA service call failed: {e}")
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    async def turn_on(self, entity_id: str, **kwargs) -> Dict[str, Any]:
        """Turn on an entity."""
        domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
        return await self.call_service(domain, "turn_on", entity_id, kwargs or None)

    async def turn_off(self, entity_id: str) -> Dict[str, Any]:
        """Turn off an entity."""
        domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
        return await self.call_service(domain, "turn_off", entity_id)

    async def toggle(self, entity_id: str) -> Dict[str, Any]:
        """Toggle an entity."""
        domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
        return await self.call_service(domain, "toggle", entity_id)

    # =========================================================================
    # Home Summary (for context injection)
    # =========================================================================

    async def get_home_summary(self) -> str:
        """
        Get a human-readable summary of the home state.
        Useful for injecting into Cass's context.
        """
        if not self.is_configured:
            return "Home Assistant not configured."

        try:
            states = await self.get_states()
            areas = await self.get_areas()

            # Group by domain
            by_domain: Dict[str, List[HAEntity]] = {}
            for entity in states:
                if entity.domain:
                    by_domain.setdefault(entity.domain, []).append(entity)

            lines = ["## Home State\n"]

            # Lights
            lights = by_domain.get("light", [])
            lights_on = [l for l in lights if l.state == "on"]
            if lights:
                lines.append(f"**Lights**: {len(lights_on)}/{len(lights)} on")
                if lights_on:
                    lines.append("  - " + ", ".join(l.friendly_name or l.entity_id for l in lights_on[:5]))
                    if len(lights_on) > 5:
                        lines.append(f"  - ...and {len(lights_on) - 5} more")

            # Climate
            climate = by_domain.get("climate", [])
            for c in climate[:3]:
                temp = c.attributes.get("current_temperature", "?")
                target = c.attributes.get("temperature", "?")
                lines.append(f"**{c.friendly_name or c.entity_id}**: {temp}°, target {target}°, {c.state}")

            # Locks
            locks = by_domain.get("lock", [])
            if locks:
                locked = [l for l in locks if l.state == "locked"]
                lines.append(f"**Locks**: {len(locked)}/{len(locks)} locked")

            # Sensors (temperature, humidity)
            sensors = by_domain.get("sensor", [])
            temp_sensors = [s for s in sensors if "temperature" in s.entity_id.lower() or
                          s.attributes.get("device_class") == "temperature"]
            for s in temp_sensors[:3]:
                lines.append(f"**{s.friendly_name or s.entity_id}**: {s.state}°")

            # Binary sensors (motion, doors)
            binary = by_domain.get("binary_sensor", [])
            motion = [b for b in binary if b.attributes.get("device_class") == "motion" and b.state == "on"]
            doors = [b for b in binary if b.attributes.get("device_class") == "door" and b.state == "on"]
            if motion:
                lines.append(f"**Motion detected**: {', '.join(m.friendly_name or m.entity_id for m in motion[:3])}")
            if doors:
                lines.append(f"**Doors open**: {', '.join(d.friendly_name or d.entity_id for d in doors[:3])}")

            # Areas summary
            if areas:
                lines.append(f"\n**Areas**: {', '.join(a['name'] for a in areas[:10])}")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Failed to get home summary: {e}")
            return f"Failed to get home state: {e}"


# =============================================================================
# Module-level singleton with cached state
# =============================================================================

_ha_client: Optional[HomeAssistantClient] = None
_cached_home_summary: Optional[str] = None
_cache_timestamp: Optional[float] = None
_CACHE_TTL_SECONDS = 60  # Refresh home state every 60 seconds


def get_ha_client() -> HomeAssistantClient:
    """Get or create the global HA client."""
    global _ha_client
    if _ha_client is None:
        _ha_client = HomeAssistantClient()
    return _ha_client


async def check_ha_connection() -> Dict[str, Any]:
    """Check HA connection status."""
    client = get_ha_client()
    return await client.check_connection()


async def get_cached_home_summary() -> Optional[str]:
    """
    Get cached home summary, refreshing if stale.

    Returns cached summary if fresh, or fetches new one if expired.
    Used for context injection without blocking.
    """
    global _cached_home_summary, _cache_timestamp
    import time

    now = time.time()

    # Check if cache is fresh
    if _cached_home_summary and _cache_timestamp:
        if now - _cache_timestamp < _CACHE_TTL_SECONDS:
            return _cached_home_summary

    # Refresh cache
    client = get_ha_client()
    if not client.is_configured:
        return None

    try:
        summary = await client.get_home_summary()
        if summary and summary != "Home Assistant not configured.":
            _cached_home_summary = summary
            _cache_timestamp = now
            return summary
    except Exception as e:
        logger.warning(f"Failed to refresh home summary cache: {e}")
        # Return stale cache if available
        return _cached_home_summary

    return None


def get_cached_home_summary_sync() -> Optional[str]:
    """
    Get cached home summary synchronously (no refresh).

    Returns the last cached summary without attempting to refresh.
    Use this in sync contexts where you can't await.
    """
    return _cached_home_summary


async def refresh_home_summary_cache() -> None:
    """Force refresh of home summary cache."""
    await get_cached_home_summary()


# =============================================================================
# WebSocket State Subscription
# =============================================================================

_ws_task: Optional[asyncio.Task] = None
_ws_connected: bool = False


async def subscribe_to_state_changes():
    """
    Subscribe to Home Assistant state changes via WebSocket.

    Feeds state changes to HomeIntelligence for pattern learning and anomaly detection.
    """
    global _ws_connected
    import websockets
    import json

    client = get_ha_client()
    if not client.is_configured:
        logger.info("HA not configured, skipping state subscription")
        return

    ws_url = client.url.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
    msg_id = 1

    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                # Wait for auth_required
                auth_req = await ws.recv()
                auth_data = json.loads(auth_req)

                if auth_data.get("type") == "auth_required":
                    # Send auth
                    await ws.send(json.dumps({
                        "type": "auth",
                        "access_token": client.token
                    }))

                    auth_result = await ws.recv()
                    result = json.loads(auth_result)

                    if result.get("type") != "auth_ok":
                        logger.error(f"HA WebSocket auth failed: {result}")
                        await asyncio.sleep(30)
                        continue

                logger.info("HA WebSocket connected and authenticated")
                _ws_connected = True

                # Subscribe to state changes
                await ws.send(json.dumps({
                    "id": msg_id,
                    "type": "subscribe_events",
                    "event_type": "state_changed"
                }))
                msg_id += 1

                # Process events
                async for message in ws:
                    try:
                        data = json.loads(message)

                        if data.get("type") == "event":
                            event = data.get("event", {})
                            event_data = event.get("data", {})

                            entity_id = event_data.get("entity_id")
                            old_state = event_data.get("old_state", {})
                            new_state = event_data.get("new_state", {})

                            if entity_id and new_state:
                                # Feed to intelligence system
                                try:
                                    from home_intelligence import process_ha_state_change
                                    await process_ha_state_change(
                                        entity_id=entity_id,
                                        old_state=old_state.get("state", "") if old_state else "",
                                        new_state=new_state.get("state", ""),
                                        attributes=new_state.get("attributes", {}),
                                    )
                                except ImportError:
                                    pass  # Intelligence module not available
                                except Exception as e:
                                    logger.debug(f"Intelligence processing error: {e}")

                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logger.debug(f"Error processing HA event: {e}")

        except Exception as e:
            logger.warning(f"HA WebSocket error: {e}")
            _ws_connected = False
            await asyncio.sleep(10)  # Retry after 10 seconds


async def start_state_subscription():
    """Start the state change subscription in the background."""
    global _ws_task
    if _ws_task is None or _ws_task.done():
        _ws_task = asyncio.create_task(subscribe_to_state_changes())
        logger.info("Started HA state subscription task")


def is_ws_connected() -> bool:
    """Check if WebSocket is connected."""
    return _ws_connected
