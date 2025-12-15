"""
Cass Vessel - Calendar Manager
Handles events, reminders, and scheduling
"""
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
from pathlib import Path
import uuid
from enum import Enum

from database import get_db, json_serialize, json_deserialize


class RecurrenceType(str, Enum):
    """How an event repeats"""
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


@dataclass
class Event:
    """A calendar event or reminder"""
    id: str
    title: str
    start_time: str  # ISO format datetime
    end_time: Optional[str] = None  # ISO format, None for reminders/all-day
    description: Optional[str] = None
    location: Optional[str] = None

    # Reminder settings
    is_reminder: bool = False  # True for simple reminders vs calendar events
    reminder_minutes: int = 15  # Minutes before event to remind

    # Recurrence
    recurrence: RecurrenceType = RecurrenceType.NONE
    recurrence_end: Optional[str] = None  # When recurrence stops

    # Metadata
    created_at: str = ""
    updated_at: str = ""
    completed: bool = False  # For reminders that have been acknowledged
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None  # Link to conversation where it was created

    # Tags for organization
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Event':
        """Create from dictionary"""
        # Handle recurrence enum
        if isinstance(data.get("recurrence"), str):
            data["recurrence"] = RecurrenceType(data["recurrence"])
        # Handle tags default
        if "tags" not in data:
            data["tags"] = []
        return cls(**data)

    def is_all_day(self) -> bool:
        """Check if this is an all-day event"""
        return self.end_time is None and not self.is_reminder

    def get_datetime(self) -> datetime:
        """Get start time as datetime object"""
        return datetime.fromisoformat(self.start_time)

    def is_upcoming(self, within_minutes: int = 60) -> bool:
        """Check if event is coming up soon"""
        now = datetime.now()
        event_time = self.get_datetime()
        delta = event_time - now
        return timedelta(0) <= delta <= timedelta(minutes=within_minutes)

    def is_past(self) -> bool:
        """Check if event has passed"""
        return self.get_datetime() < datetime.now()


class CalendarManager:
    """
    Manages calendar events and reminders.

    Uses SQLite database for storage.
    """

    def __init__(self, daemon_id: str = None):
        self._daemon_id = daemon_id
        if not self._daemon_id:
            self._load_default_daemon()

    def _load_default_daemon(self):
        """Load default daemon ID from database"""
        with get_db() as conn:
            cursor = conn.execute("SELECT id FROM daemons LIMIT 1")
            row = cursor.fetchone()
            if row:
                self._daemon_id = row[0]

    def _row_to_event(self, row) -> Event:
        """Convert database row to Event object"""
        return Event(
            id=row[0],
            title=row[1],
            start_time=row[2],
            end_time=row[3],
            description=row[4],
            location=row[5],
            is_reminder=bool(row[6]),
            reminder_minutes=row[7] or 15,
            recurrence=RecurrenceType(row[8]) if row[8] else RecurrenceType.NONE,
            recurrence_end=row[9],
            created_at=row[10],
            updated_at=row[11],
            completed=bool(row[12]),
            user_id=row[13],
            conversation_id=row[14],
            tags=json_deserialize(row[15]) or []
        )

    def _load_events(self, user_id: str) -> List[Event]:
        """Load all events for a user"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, title, start_time, end_time, description, location,
                       is_reminder, reminder_minutes, recurrence, recurrence_end,
                       created_at, updated_at, completed, user_id, conversation_id, tags_json
                FROM calendar_events
                WHERE daemon_id = ? AND user_id = ?
                ORDER BY start_time
            """, (self._daemon_id, user_id))
            return [self._row_to_event(row) for row in cursor.fetchall()]

    def create_event(
        self,
        user_id: str,
        title: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        is_reminder: bool = False,
        reminder_minutes: int = 15,
        recurrence: RecurrenceType = RecurrenceType.NONE,
        recurrence_end: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        conversation_id: Optional[str] = None
    ) -> Event:
        """Create a new event or reminder"""
        now = datetime.now().isoformat()
        event_id = str(uuid.uuid4())

        event = Event(
            id=event_id,
            title=title,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat() if end_time else None,
            description=description,
            location=location,
            is_reminder=is_reminder,
            reminder_minutes=reminder_minutes,
            recurrence=recurrence,
            recurrence_end=recurrence_end.isoformat() if recurrence_end else None,
            created_at=now,
            updated_at=now,
            user_id=user_id,
            conversation_id=conversation_id,
            tags=tags or []
        )

        with get_db() as conn:
            conn.execute("""
                INSERT INTO calendar_events (
                    id, daemon_id, user_id, title, description, location,
                    start_time, end_time, is_reminder, reminder_minutes,
                    recurrence, recurrence_end, completed, conversation_id,
                    tags_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id, self._daemon_id, user_id, title, description, location,
                event.start_time, event.end_time, int(is_reminder), reminder_minutes,
                recurrence.value, event.recurrence_end, 0, conversation_id,
                json_serialize(tags or []), now, now
            ))
            conn.commit()

        return event

    def create_reminder(
        self,
        user_id: str,
        title: str,
        remind_at: datetime,
        description: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Event:
        """Convenience method to create a simple reminder"""
        return self.create_event(
            user_id=user_id,
            title=title,
            start_time=remind_at,
            is_reminder=True,
            description=description,
            conversation_id=conversation_id
        )

    def get_event(self, user_id: str, event_id: str) -> Optional[Event]:
        """Get a specific event by ID"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, title, start_time, end_time, description, location,
                       is_reminder, reminder_minutes, recurrence, recurrence_end,
                       created_at, updated_at, completed, user_id, conversation_id, tags_json
                FROM calendar_events
                WHERE daemon_id = ? AND user_id = ? AND id = ?
            """, (self._daemon_id, user_id, event_id))
            row = cursor.fetchone()
            if row:
                return self._row_to_event(row)
        return None

    def update_event(
        self,
        user_id: str,
        event_id: str,
        title: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        completed: Optional[bool] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[Event]:
        """Update an existing event"""
        # Build dynamic update query
        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if start_time is not None:
            updates.append("start_time = ?")
            params.append(start_time.isoformat())
        if end_time is not None:
            updates.append("end_time = ?")
            params.append(end_time.isoformat())
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if location is not None:
            updates.append("location = ?")
            params.append(location)
        if completed is not None:
            updates.append("completed = ?")
            params.append(int(completed))
        if tags is not None:
            updates.append("tags_json = ?")
            params.append(json_serialize(tags))

        if not updates:
            return self.get_event(user_id, event_id)

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())

        params.extend([self._daemon_id, user_id, event_id])

        with get_db() as conn:
            conn.execute(f"""
                UPDATE calendar_events
                SET {', '.join(updates)}
                WHERE daemon_id = ? AND user_id = ? AND id = ?
            """, params)
            conn.commit()

        return self.get_event(user_id, event_id)

    def delete_event(self, user_id: str, event_id: str) -> bool:
        """Delete an event"""
        with get_db() as conn:
            cursor = conn.execute("""
                DELETE FROM calendar_events
                WHERE daemon_id = ? AND user_id = ? AND id = ?
            """, (self._daemon_id, user_id, event_id))
            conn.commit()
            return cursor.rowcount > 0

    def complete_reminder(self, user_id: str, event_id: str) -> Optional[Event]:
        """Mark a reminder as completed/acknowledged"""
        return self.update_event(user_id, event_id, completed=True)

    def get_events_for_date(self, user_id: str, date: datetime) -> List[Event]:
        """Get all events for a specific date"""
        target_date = date.strftime("%Y-%m-%d")
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, title, start_time, end_time, description, location,
                       is_reminder, reminder_minutes, recurrence, recurrence_end,
                       created_at, updated_at, completed, user_id, conversation_id, tags_json
                FROM calendar_events
                WHERE daemon_id = ? AND user_id = ?
                  AND date(start_time) = ?
                  AND completed = 0
                ORDER BY start_time
            """, (self._daemon_id, user_id, target_date))
            return [self._row_to_event(row) for row in cursor.fetchall()]

    def get_events_in_range(
        self,
        user_id: str,
        start: datetime,
        end: datetime,
        include_completed: bool = False
    ) -> List[Event]:
        """Get all events within a date range"""
        query = """
            SELECT id, title, start_time, end_time, description, location,
                   is_reminder, reminder_minutes, recurrence, recurrence_end,
                   created_at, updated_at, completed, user_id, conversation_id, tags_json
            FROM calendar_events
            WHERE daemon_id = ? AND user_id = ?
              AND start_time >= ? AND start_time <= ?
        """
        params = [self._daemon_id, user_id, start.isoformat(), end.isoformat()]

        if not include_completed:
            query += " AND completed = 0"

        query += " ORDER BY start_time"

        with get_db() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_event(row) for row in cursor.fetchall()]

    def get_upcoming_events(
        self,
        user_id: str,
        days: int = 7,
        limit: int = 10
    ) -> List[Event]:
        """Get upcoming events for the next N days"""
        now = datetime.now()
        end = now + timedelta(days=days)
        events = self.get_events_in_range(user_id, now, end)
        return events[:limit]

    def get_upcoming_reminders(
        self,
        user_id: str,
        within_minutes: int = 60
    ) -> List[Event]:
        """Get reminders that are coming up soon (for notifications)"""
        now = datetime.now()
        cutoff = now + timedelta(minutes=within_minutes)

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, title, start_time, end_time, description, location,
                       is_reminder, reminder_minutes, recurrence, recurrence_end,
                       created_at, updated_at, completed, user_id, conversation_id, tags_json
                FROM calendar_events
                WHERE daemon_id = ? AND user_id = ?
                  AND is_reminder = 1
                  AND completed = 0
                  AND start_time >= ? AND start_time <= ?
                ORDER BY start_time
            """, (self._daemon_id, user_id, now.isoformat(), cutoff.isoformat()))
            return [self._row_to_event(row) for row in cursor.fetchall()]

    def get_today_agenda(self, user_id: str) -> Dict:
        """Get a summary of today's events"""
        today = datetime.now()
        events = self.get_events_for_date(user_id, today)

        reminders = [e for e in events if e.is_reminder]
        calendar_events = [e for e in events if not e.is_reminder]

        return {
            "date": today.strftime("%Y-%m-%d"),
            "day_name": today.strftime("%A"),
            "events": [e.to_dict() for e in calendar_events],
            "reminders": [e.to_dict() for e in reminders],
            "total_count": len(events)
        }

    def search_events(
        self,
        user_id: str,
        query: str,
        limit: int = 10
    ) -> List[Event]:
        """Search events by title, description, or date"""
        events = self._load_events(user_id)
        query_lower = query.lower()

        results = []
        for event in events:
            # Search in title
            if query_lower in event.title.lower():
                results.append(event)
                continue
            # Search in description
            if event.description and query_lower in event.description.lower():
                results.append(event)
                continue
            # Search in date - try various date formats
            try:
                event_dt = datetime.fromisoformat(event.start_time)
                date_formats = [
                    event_dt.strftime("%Y-%m-%d"),           # 2025-12-15
                    event_dt.strftime("%B %d").lower(),      # december 15
                    event_dt.strftime("%b %d").lower(),      # dec 15
                    event_dt.strftime("%d %B").lower(),      # 15 december
                    event_dt.strftime("%d %b").lower(),      # 15 dec
                    event_dt.strftime("%A").lower(),         # sunday
                    event_dt.strftime("%a").lower(),         # sun
                    str(event_dt.day),                       # 15
                    f"{event_dt.day}th",                     # 15th
                    f"{event_dt.day}st",                     # 1st
                    f"{event_dt.day}nd",                     # 2nd
                    f"{event_dt.day}rd",                     # 3rd
                ]
                if any(query_lower in fmt for fmt in date_formats):
                    results.append(event)
                    continue
            except Exception:
                pass

        # Sort by start time (most recent first for past, soonest first for future)
        results.sort(key=lambda e: e.start_time, reverse=True)
        return results[:limit]

    def list_all_events(
        self,
        user_id: str,
        include_completed: bool = False,
        include_past: bool = False
    ) -> List[Event]:
        """List all events for a user"""
        query = """
            SELECT id, title, start_time, end_time, description, location,
                   is_reminder, reminder_minutes, recurrence, recurrence_end,
                   created_at, updated_at, completed, user_id, conversation_id, tags_json
            FROM calendar_events
            WHERE daemon_id = ? AND user_id = ?
        """
        params = [self._daemon_id, user_id]

        if not include_completed:
            query += " AND completed = 0"

        if not include_past:
            query += " AND start_time >= ?"
            params.append(datetime.now().isoformat())

        query += " ORDER BY start_time"

        with get_db() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_event(row) for row in cursor.fetchall()]


if __name__ == "__main__":
    # Test the calendar manager
    manager = CalendarManager()
    test_user = "test-user-123"

    # Create a reminder
    reminder = manager.create_reminder(
        user_id=test_user,
        title="Test reminder",
        remind_at=datetime.now() + timedelta(hours=1),
        description="This is a test"
    )
    print(f"Created reminder: {reminder.title} at {reminder.start_time}")

    # Create an event
    event = manager.create_event(
        user_id=test_user,
        title="Team meeting",
        start_time=datetime.now() + timedelta(days=1, hours=2),
        end_time=datetime.now() + timedelta(days=1, hours=3),
        description="Weekly sync",
        location="Conference Room A",
        recurrence=RecurrenceType.WEEKLY
    )
    print(f"Created event: {event.title}")

    # Get today's agenda
    agenda = manager.get_today_agenda(test_user)
    print(f"\nToday's agenda ({agenda['day_name']}):")
    print(f"  Events: {len(agenda['events'])}")
    print(f"  Reminders: {len(agenda['reminders'])}")

    # Get upcoming events
    upcoming = manager.get_upcoming_events(test_user, days=7)
    print(f"\nUpcoming events (next 7 days): {len(upcoming)}")
    for e in upcoming:
        print(f"  - {e.title} @ {e.start_time}")
