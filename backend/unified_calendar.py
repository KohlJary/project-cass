"""
Unified Calendar Manager for Cass.

Orchestrates between multiple calendar backends:
- SQLite (local fallback)
- Home Assistant calendars (Google, CalDAV, Local)

Each user can configure their preferred calendar setup.
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from database import get_db, json_serialize, json_deserialize
from calendar_manager import CalendarManager, Event, RecurrenceType
from ha_calendar import (
    get_ha_calendar_client,
    HACalendarClient,
    HACalendarEvent,
)

logger = logging.getLogger(__name__)


@dataclass
class UnifiedEvent:
    """
    Normalized event format across all backends.

    Provides a common interface for events regardless of source.
    """
    id: str
    source: str  # "sqlite" or "ha:<calendar.entity_id>"
    title: str
    start_time: datetime
    end_time: Optional[datetime]
    description: Optional[str] = None
    location: Optional[str] = None
    is_reminder: bool = False
    completed: bool = False
    recurrence: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_sqlite_event(cls, event: Event) -> "UnifiedEvent":
        """Convert SQLite Event to UnifiedEvent."""
        return cls(
            id=event.id,
            source="sqlite",
            title=event.title,
            start_time=datetime.fromisoformat(event.start_time),
            end_time=datetime.fromisoformat(event.end_time) if event.end_time else None,
            description=event.description,
            location=event.location,
            is_reminder=event.is_reminder,
            completed=event.completed,
            recurrence=event.recurrence.value if event.recurrence else None,
            tags=event.tags or [],
        )

    @classmethod
    def from_ha_event(cls, event: HACalendarEvent) -> "UnifiedEvent":
        """Convert HA calendar event to UnifiedEvent."""
        return cls(
            id=event.uid,
            source=f"ha:{event.calendar_entity}" if event.calendar_entity else "ha:unknown",
            title=event.summary,
            start_time=event.start,
            end_time=event.end,
            description=event.description,
            location=event.location,
            is_reminder=False,  # HA doesn't have reminder concept
            completed=False,
            recurrence=event.rrule,
            tags=[],
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "description": self.description,
            "location": self.location,
            "is_reminder": self.is_reminder,
            "completed": self.completed,
            "recurrence": self.recurrence,
            "tags": self.tags,
        }


@dataclass
class UserCalendarConfig:
    """
    Per-user calendar configuration.

    Determines which calendars are used for reading and writing.
    """
    daemon_id: str
    user_id: str
    primary_calendar: str = "sqlite"  # "sqlite" or "calendar.<entity_id>"
    write_calendar: str = "sqlite"    # Where new events are created
    read_calendars: List[str] = field(default_factory=list)  # Additional calendars to aggregate

    @classmethod
    def from_db(cls, row) -> "UserCalendarConfig":
        """Create from database row."""
        return cls(
            daemon_id=row["daemon_id"],
            user_id=row["user_id"],
            primary_calendar=row["primary_calendar"] or "sqlite",
            write_calendar=row["write_calendar"] or "sqlite",
            read_calendars=json_deserialize(row["read_calendars"]) or [],
        )

    def to_db(self) -> tuple:
        """Convert to database tuple."""
        return (
            self.daemon_id,
            self.user_id,
            self.primary_calendar,
            self.write_calendar,
            json_serialize(self.read_calendars),
        )


class UnifiedCalendarManager:
    """
    Orchestrates calendar operations across multiple backends.

    Provides a unified interface for:
    - Creating events (routes to configured write calendar)
    - Reading events (aggregates from all configured calendars)
    - Managing calendar configuration per user
    """

    def __init__(self, daemon_id: str, user_id: str):
        """
        Initialize the unified calendar manager.

        Args:
            daemon_id: The daemon context
            user_id: The user context
        """
        self._daemon_id = daemon_id
        self._user_id = user_id
        self._sqlite = CalendarManager(daemon_id)
        self._ha: Optional[HACalendarClient] = None
        self._config: Optional[UserCalendarConfig] = None

    @property
    def ha(self) -> HACalendarClient:
        """Get HA calendar client (lazy init)."""
        if self._ha is None:
            self._ha = get_ha_calendar_client()
        return self._ha

    @property
    def config(self) -> UserCalendarConfig:
        """Get user's calendar configuration (lazy init)."""
        if self._config is None:
            self._config = self._load_config()
        return self._config

    def _load_config(self) -> UserCalendarConfig:
        """Load user's calendar configuration from database."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT daemon_id, user_id, primary_calendar, write_calendar, read_calendars
                FROM user_calendar_config
                WHERE daemon_id = ? AND user_id = ?
            """, (self._daemon_id, self._user_id))
            row = cursor.fetchone()

            if row:
                return UserCalendarConfig.from_db(row)
            else:
                # Return default config
                return UserCalendarConfig(
                    daemon_id=self._daemon_id,
                    user_id=self._user_id,
                )

    def _save_config(self) -> None:
        """Save user's calendar configuration to database."""
        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_calendar_config
                (daemon_id, user_id, primary_calendar, write_calendar, read_calendars, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                self.config.daemon_id,
                self.config.user_id,
                self.config.primary_calendar,
                self.config.write_calendar,
                json_serialize(self.config.read_calendars),
                datetime.now().isoformat(),
            ))
            conn.commit()

    # =========================================================================
    # Configuration
    # =========================================================================

    async def get_available_calendars(self) -> List[Dict[str, Any]]:
        """
        Get all available calendars (SQLite + HA).

        Returns list of calendar info dicts.
        """
        calendars = [{
            "entity_id": "sqlite",
            "friendly_name": "Local (Built-in)",
            "supports_write": True,
            "provider": "sqlite",
        }]

        if self.ha.is_configured:
            ha_calendars = await self.ha.list_calendars()
            for cal in ha_calendars:
                calendars.append({
                    "entity_id": cal.entity_id,
                    "friendly_name": cal.friendly_name,
                    "supports_write": cal.supports_write,
                    "provider": cal.provider,
                })

        return calendars

    def get_config(self) -> Dict[str, Any]:
        """Get current calendar configuration."""
        return {
            "primary_calendar": self.config.primary_calendar,
            "write_calendar": self.config.write_calendar,
            "read_calendars": self.config.read_calendars,
        }

    def set_primary_calendar(self, calendar_id: str) -> None:
        """Set the primary calendar."""
        self._config = UserCalendarConfig(
            daemon_id=self._daemon_id,
            user_id=self._user_id,
            primary_calendar=calendar_id,
            write_calendar=self.config.write_calendar,
            read_calendars=self.config.read_calendars,
        )
        self._save_config()

    def set_write_calendar(self, calendar_id: str) -> None:
        """Set the write calendar."""
        self._config = UserCalendarConfig(
            daemon_id=self._daemon_id,
            user_id=self._user_id,
            primary_calendar=self.config.primary_calendar,
            write_calendar=calendar_id,
            read_calendars=self.config.read_calendars,
        )
        self._save_config()

    def set_read_calendars(self, calendar_ids: List[str]) -> None:
        """Set the read calendars."""
        self._config = UserCalendarConfig(
            daemon_id=self._daemon_id,
            user_id=self._user_id,
            primary_calendar=self.config.primary_calendar,
            write_calendar=self.config.write_calendar,
            read_calendars=calendar_ids,
        )
        self._save_config()

    # =========================================================================
    # Event Operations
    # =========================================================================

    async def get_agenda(self, date: Optional[datetime] = None) -> List[UnifiedEvent]:
        """
        Get events for a specific date.

        Aggregates from primary calendar + all read calendars.
        """
        if date is None:
            date = datetime.now()

        # Define date range (full day)
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        return await self._get_events_in_range(start, end)

    async def get_upcoming(self, days: int = 7) -> List[UnifiedEvent]:
        """
        Get upcoming events for the next N days.

        Args:
            days: Number of days to look ahead

        Returns:
            List of events sorted by start time
        """
        now = datetime.now()
        end = now + timedelta(days=days)
        return await self._get_events_in_range(now, end)

    async def _get_events_in_range(
        self,
        start: datetime,
        end: datetime,
    ) -> List[UnifiedEvent]:
        """Get events from all configured calendars within a date range."""
        events: List[UnifiedEvent] = []

        # Determine which calendars to query
        calendars_to_query = set()
        calendars_to_query.add(self.config.primary_calendar)
        calendars_to_query.update(self.config.read_calendars)

        # Fetch from each source
        for calendar_id in calendars_to_query:
            if calendar_id == "sqlite":
                sqlite_events = self._sqlite.get_events_in_range(
                    self._user_id, start, end
                )
                events.extend(
                    UnifiedEvent.from_sqlite_event(e) for e in sqlite_events
                )
            elif calendar_id.startswith("calendar.") and self.ha.is_configured:
                ha_events = await self.ha.get_events(calendar_id, start, end)
                events.extend(
                    UnifiedEvent.from_ha_event(e) for e in ha_events
                )

        # Sort by start time
        events.sort(key=lambda e: e.start_time)
        return events

    async def create_event(
        self,
        title: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        is_reminder: bool = False,
        recurrence: RecurrenceType = RecurrenceType.NONE,
        tags: Optional[List[str]] = None,
        conversation_id: Optional[str] = None,
    ) -> Optional[UnifiedEvent]:
        """
        Create a new event in the configured write calendar.

        Falls back to SQLite if HA calendar is unavailable or doesn't support writes.
        """
        write_cal = self.config.write_calendar

        if write_cal == "sqlite":
            return await self._create_sqlite_event(
                title, start_time, end_time, description, location,
                is_reminder, recurrence, tags, conversation_id
            )
        elif write_cal.startswith("calendar."):
            # Try HA calendar, fall back to SQLite
            if self.ha.is_configured:
                success = await self._create_ha_event(
                    write_cal, title, start_time, end_time, description, location
                )
                if success:
                    # Return a unified event representation
                    return UnifiedEvent(
                        id=f"ha-{datetime.now().timestamp()}",  # HA doesn't return ID
                        source=f"ha:{write_cal}",
                        title=title,
                        start_time=start_time,
                        end_time=end_time,
                        description=description,
                        location=location,
                        is_reminder=is_reminder,
                        tags=tags or [],
                    )

            # Fall back to SQLite
            logger.warning(f"HA calendar {write_cal} unavailable, falling back to SQLite")
            return await self._create_sqlite_event(
                title, start_time, end_time, description, location,
                is_reminder, recurrence, tags, conversation_id
            )

        return None

    async def _create_sqlite_event(
        self,
        title: str,
        start_time: datetime,
        end_time: Optional[datetime],
        description: Optional[str],
        location: Optional[str],
        is_reminder: bool,
        recurrence: RecurrenceType,
        tags: Optional[List[str]],
        conversation_id: Optional[str],
    ) -> UnifiedEvent:
        """Create event in SQLite."""
        if is_reminder:
            event = self._sqlite.create_reminder(
                user_id=self._user_id,
                title=title,
                remind_at=start_time,
                description=description,
                conversation_id=conversation_id,
            )
        else:
            event = self._sqlite.create_event(
                user_id=self._user_id,
                title=title,
                start_time=start_time,
                end_time=end_time,
                description=description,
                location=location,
                recurrence=recurrence,
                tags=tags,
                conversation_id=conversation_id,
            )
        return UnifiedEvent.from_sqlite_event(event)

    async def _create_ha_event(
        self,
        calendar_id: str,
        title: str,
        start_time: datetime,
        end_time: Optional[datetime],
        description: Optional[str],
        location: Optional[str],
    ) -> bool:
        """Create event in HA calendar."""
        # Default end time if not provided
        if end_time is None:
            end_time = start_time + timedelta(hours=1)

        return await self.ha.create_event(
            entity_id=calendar_id,
            summary=title,
            start=start_time,
            end=end_time,
            description=description,
            location=location,
        )

    async def search(self, query: str, limit: int = 10) -> List[UnifiedEvent]:
        """
        Search events across all configured calendars.

        Currently only searches SQLite (HA doesn't support search).
        """
        # Search SQLite
        events = self._sqlite.search_events(self._user_id, query, limit)
        return [UnifiedEvent.from_sqlite_event(e) for e in events]

    def complete_reminder(self, event_id: str) -> Optional[UnifiedEvent]:
        """Mark a reminder as complete (SQLite only)."""
        event = self._sqlite.complete_reminder(self._user_id, event_id)
        if event:
            return UnifiedEvent.from_sqlite_event(event)
        return None

    def delete_event(self, event_id: str, source: str = "sqlite") -> bool:
        """
        Delete an event.

        Args:
            event_id: The event ID
            source: Where the event is ("sqlite" or "ha:<calendar>")
        """
        if source == "sqlite":
            return self._sqlite.delete_event(self._user_id, event_id)
        elif source.startswith("ha:"):
            # HA event deletion would require async call
            # For now, not supported directly
            logger.warning(f"HA event deletion not yet supported: {event_id}")
            return False
        return False

    def update_event(
        self,
        event_id: str,
        title: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        completed: Optional[bool] = None,
        tags: Optional[List[str]] = None,
        source: str = "sqlite",
    ) -> Optional[UnifiedEvent]:
        """
        Update an event.

        Currently only supports SQLite events.
        """
        if source == "sqlite":
            event = self._sqlite.update_event(
                user_id=self._user_id,
                event_id=event_id,
                title=title,
                start_time=start_time,
                end_time=end_time,
                description=description,
                location=location,
                completed=completed,
                tags=tags,
            )
            if event:
                return UnifiedEvent.from_sqlite_event(event)
        return None

    def get_event(self, event_id: str, source: str = "sqlite") -> Optional[UnifiedEvent]:
        """Get a specific event by ID."""
        if source == "sqlite":
            event = self._sqlite.get_event(self._user_id, event_id)
            if event:
                return UnifiedEvent.from_sqlite_event(event)
        return None


# =============================================================================
# Factory function
# =============================================================================

def get_unified_calendar(daemon_id: str, user_id: str) -> UnifiedCalendarManager:
    """Get a unified calendar manager for a specific user."""
    return UnifiedCalendarManager(daemon_id, user_id)
