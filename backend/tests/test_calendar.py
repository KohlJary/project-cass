"""
Tests for calendar_manager.py - Calendar and reminder management.

Tests cover:
- RecurrenceType enum
- Event dataclass (serialization, helpers)
- CalendarManager CRUD operations
- Date queries and filtering
- Search functionality
"""
import pytest
from datetime import datetime, timedelta

from calendar_manager import RecurrenceType, Event, CalendarManager


# ---------------------------------------------------------------------------
# RecurrenceType Tests
# ---------------------------------------------------------------------------

class TestRecurrenceType:
    """Tests for RecurrenceType enum."""

    def test_recurrence_values(self):
        """RecurrenceType should have expected values."""
        assert RecurrenceType.NONE == "none"
        assert RecurrenceType.DAILY == "daily"
        assert RecurrenceType.WEEKLY == "weekly"
        assert RecurrenceType.MONTHLY == "monthly"
        assert RecurrenceType.YEARLY == "yearly"


# ---------------------------------------------------------------------------
# Event Tests
# ---------------------------------------------------------------------------

class TestEvent:
    """Tests for Event dataclass."""

    def test_event_creation(self):
        """Event should store basic metadata."""
        now = datetime.now()
        event = Event(
            id="evt-123",
            title="Team Meeting",
            start_time=now.isoformat(),
            end_time=(now + timedelta(hours=1)).isoformat(),
            description="Weekly sync"
        )
        assert event.id == "evt-123"
        assert event.title == "Team Meeting"
        assert event.is_reminder is False

    def test_event_to_dict(self):
        """Event.to_dict() should serialize all fields."""
        event = Event(
            id="evt-1",
            title="Test",
            start_time=datetime.now().isoformat(),
            tags=["work"]
        )
        d = event.to_dict()
        assert d["id"] == "evt-1"
        assert d["tags"] == ["work"]

    def test_event_from_dict(self):
        """Event.from_dict() should deserialize correctly."""
        now = datetime.now()
        data = {
            "id": "evt-abc",
            "title": "From Dict",
            "start_time": now.isoformat(),
            "end_time": None,
            "description": None,
            "location": None,
            "is_reminder": True,
            "reminder_minutes": 30,
            "recurrence": "weekly",
            "recurrence_end": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "completed": False,
            "user_id": "user-1",
            "conversation_id": None,
            "tags": []
        }
        event = Event.from_dict(data)
        assert event.id == "evt-abc"
        assert event.recurrence == RecurrenceType.WEEKLY
        assert event.is_reminder is True

    def test_is_all_day(self):
        """is_all_day() should detect all-day events."""
        all_day = Event(
            id="evt-1",
            title="Birthday",
            start_time=datetime.now().isoformat(),
            is_reminder=False
        )
        assert all_day.is_all_day() is True

        timed = Event(
            id="evt-2",
            title="Meeting",
            start_time=datetime.now().isoformat(),
            end_time=(datetime.now() + timedelta(hours=1)).isoformat()
        )
        assert timed.is_all_day() is False

    def test_is_past(self):
        """is_past() should detect events that have passed."""
        past = Event(
            id="evt-1",
            title="Past",
            start_time=(datetime.now() - timedelta(hours=1)).isoformat()
        )
        assert past.is_past() is True

        future = Event(
            id="evt-2",
            title="Future",
            start_time=(datetime.now() + timedelta(hours=1)).isoformat()
        )
        assert future.is_past() is False


# ---------------------------------------------------------------------------
# CalendarManager Tests
# ---------------------------------------------------------------------------

class TestCalendarManager:
    """Tests for CalendarManager."""

    @pytest.fixture
    def user_id(self):
        return "test-user-calendar-001"

    def test_create_event(self, calendar_manager, user_id):
        """create_event should create and persist an event."""
        start = datetime.now() + timedelta(days=1)
        event = calendar_manager.create_event(
            user_id=user_id,
            title="Team Standup",
            start_time=start,
            description="Daily sync",
            tags=["work"]
        )
        assert event.id is not None
        assert event.title == "Team Standup"
        assert event.tags == ["work"]

    def test_create_reminder(self, calendar_manager, user_id):
        """create_reminder should create a reminder event."""
        remind_at = datetime.now() + timedelta(hours=2)
        reminder = calendar_manager.create_reminder(
            user_id=user_id,
            title="Call dentist",
            remind_at=remind_at
        )
        assert reminder.is_reminder is True

    def test_get_event(self, calendar_manager, user_id):
        """get_event should retrieve by ID."""
        created = calendar_manager.create_event(
            user_id=user_id,
            title="Find Me",
            start_time=datetime.now() + timedelta(days=1)
        )
        found = calendar_manager.get_event(user_id, created.id)
        assert found is not None
        assert found.title == "Find Me"

    def test_get_event_nonexistent(self, calendar_manager, user_id):
        """get_event should return None for missing events."""
        result = calendar_manager.get_event(user_id, "nonexistent-id")
        assert result is None

    def test_update_event(self, calendar_manager, user_id):
        """update_event should modify event fields."""
        event = calendar_manager.create_event(
            user_id=user_id,
            title="Original",
            start_time=datetime.now() + timedelta(days=1)
        )
        updated = calendar_manager.update_event(
            user_id=user_id,
            event_id=event.id,
            title="Updated Title"
        )
        assert updated.title == "Updated Title"

    def test_delete_event(self, calendar_manager, user_id):
        """delete_event should remove event."""
        event = calendar_manager.create_event(
            user_id=user_id,
            title="Delete Me",
            start_time=datetime.now() + timedelta(days=1)
        )
        result = calendar_manager.delete_event(user_id, event.id)
        assert result is True
        assert calendar_manager.get_event(user_id, event.id) is None

    def test_complete_reminder(self, calendar_manager, user_id):
        """complete_reminder should mark as completed."""
        reminder = calendar_manager.create_reminder(
            user_id=user_id,
            title="Test",
            remind_at=datetime.now() + timedelta(hours=1)
        )
        completed = calendar_manager.complete_reminder(user_id, reminder.id)
        assert completed.completed is True

    def test_get_events_for_date(self, calendar_manager, user_id):
        """get_events_for_date should return events on specific date."""
        target = datetime.now() + timedelta(days=3)
        calendar_manager.create_event(
            user_id=user_id,
            title="Event 1",
            start_time=target.replace(hour=10)
        )
        calendar_manager.create_event(
            user_id=user_id,
            title="Event 2",
            start_time=target.replace(hour=14)
        )
        events = calendar_manager.get_events_for_date(user_id, target)
        assert len(events) == 2

    def test_get_events_in_range(self, calendar_manager, user_id):
        """get_events_in_range should return events within date range."""
        base = datetime.now()
        calendar_manager.create_event(
            user_id=user_id,
            title="Day 1",
            start_time=base + timedelta(days=1)
        )
        calendar_manager.create_event(
            user_id=user_id,
            title="Day 3",
            start_time=base + timedelta(days=3)
        )
        calendar_manager.create_event(
            user_id=user_id,
            title="Day 10",
            start_time=base + timedelta(days=10)
        )
        events = calendar_manager.get_events_in_range(
            user_id, base, base + timedelta(days=5)
        )
        assert len(events) == 2

    def test_get_upcoming_events(self, calendar_manager, user_id):
        """get_upcoming_events should return next N days of events."""
        now = datetime.now()
        calendar_manager.create_event(
            user_id=user_id,
            title="Tomorrow",
            start_time=now + timedelta(days=1)
        )
        calendar_manager.create_event(
            user_id=user_id,
            title="In 10 days",
            start_time=now + timedelta(days=10)
        )
        upcoming = calendar_manager.get_upcoming_events(user_id, days=7)
        assert len(upcoming) == 1
        assert upcoming[0].title == "Tomorrow"

    def test_get_today_agenda(self, calendar_manager, user_id):
        """get_today_agenda should return summary of today's events."""
        today = datetime.now()
        calendar_manager.create_event(
            user_id=user_id,
            title="Meeting",
            start_time=today.replace(hour=10, minute=0, second=0, microsecond=0)
        )
        agenda = calendar_manager.get_today_agenda(user_id)
        assert "date" in agenda
        assert "events" in agenda
        assert "reminders" in agenda

    def test_search_events(self, calendar_manager, user_id):
        """search_events should find events by title."""
        calendar_manager.create_event(
            user_id=user_id,
            title="Team Meeting",
            start_time=datetime.now() + timedelta(days=1)
        )
        calendar_manager.create_event(
            user_id=user_id,
            title="Client Call",
            start_time=datetime.now() + timedelta(days=2)
        )
        results = calendar_manager.search_events(user_id, "meeting")
        assert len(results) == 1
        assert results[0].title == "Team Meeting"

    def test_list_all_events(self, calendar_manager, user_id):
        """list_all_events should return all events for user."""
        calendar_manager.create_event(
            user_id=user_id,
            title="Event 1",
            start_time=datetime.now() + timedelta(days=1)
        )
        calendar_manager.create_event(
            user_id=user_id,
            title="Event 2",
            start_time=datetime.now() + timedelta(days=2)
        )
        events = calendar_manager.list_all_events(user_id)
        assert len(events) == 2

    def test_multiple_users_isolated(self, calendar_manager):
        """Events for different users should be isolated."""
        calendar_manager.create_event(
            user_id="user-1",
            title="User 1 Event",
            start_time=datetime.now() + timedelta(days=1)
        )
        calendar_manager.create_event(
            user_id="user-2",
            title="User 2 Event",
            start_time=datetime.now() + timedelta(days=1)
        )
        user1_events = calendar_manager.list_all_events("user-1")
        user2_events = calendar_manager.list_all_events("user-2")
        assert len(user1_events) == 1
        assert len(user2_events) == 1
