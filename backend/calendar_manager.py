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

    Stores events in a JSON file per user, with an index for quick lookups.
    """

    def __init__(self, storage_dir: str = "./data/calendar"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_user_file(self, user_id: str) -> Path:
        """Get the calendar file for a user"""
        return self.storage_dir / f"{user_id}.json"

    def _load_events(self, user_id: str) -> List[Event]:
        """Load all events for a user"""
        filepath = self._get_user_file(user_id)
        if not filepath.exists():
            return []

        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            return [Event.from_dict(e) for e in data.get("events", [])]
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_events(self, user_id: str, events: List[Event]):
        """Save all events for a user"""
        filepath = self._get_user_file(user_id)
        with open(filepath, 'w') as f:
            json.dump({
                "events": [e.to_dict() for e in events],
                "updated_at": datetime.now().isoformat()
            }, f, indent=2)

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

        event = Event(
            id=str(uuid.uuid4()),
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

        events = self._load_events(user_id)
        events.append(event)
        self._save_events(user_id, events)

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
        events = self._load_events(user_id)
        for event in events:
            if event.id == event_id:
                return event
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
        events = self._load_events(user_id)

        for i, event in enumerate(events):
            if event.id == event_id:
                if title is not None:
                    event.title = title
                if start_time is not None:
                    event.start_time = start_time.isoformat()
                if end_time is not None:
                    event.end_time = end_time.isoformat()
                if description is not None:
                    event.description = description
                if location is not None:
                    event.location = location
                if completed is not None:
                    event.completed = completed
                if tags is not None:
                    event.tags = tags

                event.updated_at = datetime.now().isoformat()
                events[i] = event
                self._save_events(user_id, events)
                return event

        return None

    def delete_event(self, user_id: str, event_id: str) -> bool:
        """Delete an event"""
        events = self._load_events(user_id)
        original_count = len(events)
        events = [e for e in events if e.id != event_id]

        if len(events) < original_count:
            self._save_events(user_id, events)
            return True
        return False

    def complete_reminder(self, user_id: str, event_id: str) -> Optional[Event]:
        """Mark a reminder as completed/acknowledged"""
        return self.update_event(user_id, event_id, completed=True)

    def get_events_for_date(self, user_id: str, date: datetime) -> List[Event]:
        """Get all events for a specific date"""
        events = self._load_events(user_id)
        target_date = date.date()

        return [
            e for e in events
            if datetime.fromisoformat(e.start_time).date() == target_date
            and not e.completed
        ]

    def get_events_in_range(
        self,
        user_id: str,
        start: datetime,
        end: datetime,
        include_completed: bool = False
    ) -> List[Event]:
        """Get all events within a date range"""
        events = self._load_events(user_id)

        results = []
        for event in events:
            event_time = datetime.fromisoformat(event.start_time)
            if start <= event_time <= end:
                if include_completed or not event.completed:
                    results.append(event)

        # Sort by start time
        results.sort(key=lambda e: e.start_time)
        return results

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
        events = self._load_events(user_id)
        now = datetime.now()
        cutoff = now + timedelta(minutes=within_minutes)

        return [
            e for e in events
            if e.is_reminder
            and not e.completed
            and now <= datetime.fromisoformat(e.start_time) <= cutoff
        ]

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
        events = self._load_events(user_id)
        now = datetime.now()

        results = []
        for event in events:
            if not include_completed and event.completed:
                continue
            if not include_past and datetime.fromisoformat(event.start_time) < now:
                continue
            results.append(event)

        results.sort(key=lambda e: e.start_time)
        return results


if __name__ == "__main__":
    # Test the calendar manager
    manager = CalendarManager("./data/calendar_test")
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
