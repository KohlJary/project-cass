"""
Home Assistant Calendar Client for Cass.

Provides unified interface to HA calendar entities, supporting:
- Multiple calendar providers (Google, CalDAV, Local) via HA's unified interface
- Read/write detection for calendar entities
- Event CRUD operations
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from home_assistant import get_ha_client

logger = logging.getLogger(__name__)


@dataclass
class HACalendarEvent:
    """A calendar event from Home Assistant."""
    uid: str
    summary: str
    start: datetime
    end: datetime
    description: Optional[str] = None
    location: Optional[str] = None
    recurrence_id: Optional[str] = None
    rrule: Optional[str] = None
    calendar_entity: Optional[str] = None  # Which calendar this came from

    @classmethod
    def from_api(cls, data: Dict[str, Any], calendar_entity: str = None) -> "HACalendarEvent":
        """Parse from HA calendar event API response."""
        # HA returns start/end as either date or dateTime objects
        start_data = data.get("start", {})
        end_data = data.get("end", {})

        # Handle both date (all-day) and dateTime formats
        if isinstance(start_data, dict):
            start_str = start_data.get("dateTime") or start_data.get("date")
        else:
            start_str = start_data

        if isinstance(end_data, dict):
            end_str = end_data.get("dateTime") or end_data.get("date")
        else:
            end_str = end_data

        # Parse datetime strings
        start = datetime.fromisoformat(start_str.replace("Z", "+00:00")) if start_str else datetime.now()
        end = datetime.fromisoformat(end_str.replace("Z", "+00:00")) if end_str else start + timedelta(hours=1)

        return cls(
            uid=data.get("uid", "") or data.get("id", ""),
            summary=data.get("summary", "Untitled"),
            start=start,
            end=end,
            description=data.get("description"),
            location=data.get("location"),
            recurrence_id=data.get("recurrence_id"),
            rrule=data.get("rrule"),
            calendar_entity=calendar_entity,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "uid": self.uid,
            "summary": self.summary,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "description": self.description,
            "location": self.location,
            "rrule": self.rrule,
            "calendar_entity": self.calendar_entity,
        }


@dataclass
class CalendarInfo:
    """Information about a Home Assistant calendar entity."""
    entity_id: str
    friendly_name: str
    supports_write: bool = False
    provider: str = "unknown"  # google, caldav, local, etc.

    @classmethod
    def from_entity(cls, entity_id: str, attributes: Dict[str, Any]) -> "CalendarInfo":
        """Create from HA entity attributes."""
        # Infer provider from entity_id pattern
        provider = "unknown"
        if "google" in entity_id.lower():
            provider = "google"
        elif "caldav" in entity_id.lower():
            provider = "caldav"
        elif "local_calendar" in entity_id.lower() or "local" in entity_id.lower():
            provider = "local"
        elif "ical" in entity_id.lower():
            provider = "ical"

        # Local calendars are always writable
        # Google calendars are writable if we have write scope
        # CalDAV depends on the server config
        supports_write = provider == "local"

        return cls(
            entity_id=entity_id,
            friendly_name=attributes.get("friendly_name", entity_id),
            supports_write=supports_write,
            provider=provider,
        )


class HACalendarClient:
    """
    Client for Home Assistant calendar entities.

    Uses the HA REST API and service calls to manage calendar events.
    Works with any calendar integration (Google, CalDAV, Local, etc.).
    """

    def __init__(self):
        self._ha_client = get_ha_client()

    @property
    def is_configured(self) -> bool:
        """Check if HA is configured."""
        return self._ha_client.is_configured

    async def list_calendars(self) -> List[CalendarInfo]:
        """
        List all available calendar entities in Home Assistant.

        Returns:
            List of CalendarInfo objects
        """
        if not self.is_configured:
            return []

        try:
            entities = await self._ha_client.get_entities_by_domain("calendar")
            return [
                CalendarInfo.from_entity(e.entity_id, e.attributes)
                for e in entities
            ]
        except Exception as e:
            logger.error(f"Failed to list calendars: {e}")
            return []

    async def get_events(
        self,
        entity_id: str,
        start: datetime,
        end: datetime,
    ) -> List[HACalendarEvent]:
        """
        Get events from a calendar within a date range.

        Args:
            entity_id: Calendar entity ID (e.g., "calendar.personal")
            start: Start of range
            end: End of range

        Returns:
            List of HACalendarEvent objects
        """
        if not self.is_configured:
            return []

        try:
            client = await self._ha_client._get_client()

            # HA calendar.get_events service via API
            response = await client.post(
                f"/api/calendars/{entity_id}",
                params={
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                }
            )

            if response.status_code == 404:
                logger.warning(f"Calendar {entity_id} not found")
                return []

            response.raise_for_status()
            events_data = response.json()

            return [
                HACalendarEvent.from_api(e, entity_id)
                for e in events_data
            ]

        except Exception as e:
            logger.error(f"Failed to get events from {entity_id}: {e}")
            return []

    async def get_all_events(
        self,
        calendar_entity_ids: List[str],
        start: datetime,
        end: datetime,
    ) -> List[HACalendarEvent]:
        """
        Get events from multiple calendars.

        Args:
            calendar_entity_ids: List of calendar entity IDs
            start: Start of range
            end: End of range

        Returns:
            List of HACalendarEvent objects, sorted by start time
        """
        all_events = []
        for entity_id in calendar_entity_ids:
            events = await self.get_events(entity_id, start, end)
            all_events.extend(events)

        # Sort by start time
        all_events.sort(key=lambda e: e.start)
        return all_events

    async def create_event(
        self,
        entity_id: str,
        summary: str,
        start: datetime,
        end: datetime,
        description: Optional[str] = None,
        location: Optional[str] = None,
    ) -> bool:
        """
        Create an event in a calendar.

        Args:
            entity_id: Calendar entity ID
            summary: Event title
            start: Start time
            end: End time
            description: Optional description
            location: Optional location

        Returns:
            True if successful
        """
        if not self.is_configured:
            return False

        try:
            # Build service data
            service_data = {
                "entity_id": entity_id,
                "summary": summary,
                "start_date_time": start.isoformat(),
                "end_date_time": end.isoformat(),
            }

            if description:
                service_data["description"] = description
            if location:
                service_data["location"] = location

            result = await self._ha_client.call_service(
                "calendar",
                "create_event",
                data=service_data,
            )

            if result.get("success"):
                logger.info(f"Created event '{summary}' in {entity_id}")
                return True
            else:
                logger.error(f"Failed to create event: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"Failed to create event in {entity_id}: {e}")
            return False

    async def delete_event(
        self,
        entity_id: str,
        uid: str,
    ) -> bool:
        """
        Delete an event from a calendar.

        Note: HA calendar.delete_event is available in newer versions.
        For older versions, this may not be supported.

        Args:
            entity_id: Calendar entity ID
            uid: Event UID to delete

        Returns:
            True if successful
        """
        if not self.is_configured:
            return False

        try:
            # calendar.delete_event service (HA 2024.1+)
            result = await self._ha_client.call_service(
                "calendar",
                "delete_event",
                data={
                    "entity_id": entity_id,
                    "uid": uid,
                },
            )

            if result.get("success"):
                logger.info(f"Deleted event {uid} from {entity_id}")
                return True
            else:
                logger.warning(f"Failed to delete event: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"Failed to delete event from {entity_id}: {e}")
            return False

    async def update_event(
        self,
        entity_id: str,
        uid: str,
        summary: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
    ) -> bool:
        """
        Update an existing event.

        Note: HA's calendar.update_event is limited - we may need to
        delete and recreate for some providers.

        Args:
            entity_id: Calendar entity ID
            uid: Event UID to update
            summary: New title (optional)
            start: New start time (optional)
            end: New end time (optional)
            description: New description (optional)
            location: New location (optional)

        Returns:
            True if successful
        """
        if not self.is_configured:
            return False

        try:
            service_data = {
                "entity_id": entity_id,
                "uid": uid,
            }

            if summary:
                service_data["summary"] = summary
            if start:
                service_data["start_date_time"] = start.isoformat()
            if end:
                service_data["end_date_time"] = end.isoformat()
            if description:
                service_data["description"] = description
            if location:
                service_data["location"] = location

            result = await self._ha_client.call_service(
                "calendar",
                "update_event",
                data=service_data,
            )

            if result.get("success"):
                logger.info(f"Updated event {uid} in {entity_id}")
                return True
            else:
                logger.warning(f"Failed to update event: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"Failed to update event in {entity_id}: {e}")
            return False

    async def supports_write(self, entity_id: str) -> bool:
        """
        Check if a calendar supports write operations.

        Currently checks based on provider type:
        - Local calendars: Always writable
        - Google: Usually writable (with correct scope)
        - CalDAV: Depends on server
        - iCal: Read-only

        Args:
            entity_id: Calendar entity ID

        Returns:
            True if calendar likely supports writes
        """
        calendars = await self.list_calendars()
        for cal in calendars:
            if cal.entity_id == entity_id:
                return cal.supports_write

        # If we can't find it, assume read-only to be safe
        return False

    async def calendar_exists(self, entity_id: str) -> bool:
        """Check if a calendar entity exists."""
        entity = await self._ha_client.get_state(entity_id)
        return entity is not None

    async def create_local_calendar(self, name: str) -> Optional[str]:
        """
        Create a new Local Calendar in Home Assistant.

        Note: This requires the Local Calendar integration.
        The entity_id will be auto-generated based on the name.

        Args:
            name: Name for the new calendar

        Returns:
            Entity ID of new calendar if successful, None otherwise
        """
        if not self.is_configured:
            return None

        try:
            # Local Calendar uses a different setup flow
            # We can create via the config entry API
            client = await self._ha_client._get_client()

            # Check if local_calendar integration is loaded
            response = await client.get("/api/config")
            config = response.json()
            components = config.get("components", [])

            if "local_calendar" not in components:
                logger.warning("Local Calendar integration not installed in HA")
                return None

            # Create via config flow
            # This is a simplified approach - full implementation would
            # need to handle the config flow properly
            response = await client.post(
                "/api/config/config_entries/flow",
                json={
                    "handler": "local_calendar",
                    "show_advanced_options": False,
                }
            )

            if response.status_code != 200:
                logger.error(f"Failed to start local calendar config flow: {response.status_code}")
                return None

            flow_id = response.json().get("flow_id")
            if not flow_id:
                return None

            # Submit calendar name
            response = await client.post(
                f"/api/config/config_entries/flow/{flow_id}",
                json={"calendar_name": name}
            )

            if response.status_code != 200:
                return None

            # Extract entity_id from response
            result = response.json()
            if result.get("type") == "create_entry":
                # Entity ID is typically calendar.<name_slugified>
                slug = name.lower().replace(" ", "_").replace("-", "_")
                entity_id = f"calendar.{slug}"
                logger.info(f"Created local calendar: {entity_id}")
                return entity_id

            return None

        except Exception as e:
            logger.error(f"Failed to create local calendar: {e}")
            return None


# =============================================================================
# Module-level singleton
# =============================================================================

_ha_calendar_client: Optional[HACalendarClient] = None


def get_ha_calendar_client() -> HACalendarClient:
    """Get or create the global HA calendar client."""
    global _ha_calendar_client
    if _ha_calendar_client is None:
        _ha_calendar_client = HACalendarClient()
    return _ha_calendar_client
