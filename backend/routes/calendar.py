"""
Calendar REST API routes
Event and reminder management endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Callable
from datetime import datetime
from calendar_manager import CalendarManager, RecurrenceType

router = APIRouter(prefix="/calendar", tags=["calendar"])

# These will be set by the main app
_calendar_manager: CalendarManager = None
_get_current_user_id: Callable[[], str] = None


def init_calendar_routes(calendar_manager: CalendarManager, get_current_user_id: Callable[[], str]):
    """Initialize the routes with dependencies"""
    global _calendar_manager, _get_current_user_id
    _calendar_manager = calendar_manager
    _get_current_user_id = get_current_user_id


def _require_user():
    """Get current user or raise error"""
    user_id = _get_current_user_id()
    if not user_id:
        raise HTTPException(status_code=400, detail="No user context")
    return user_id


# Request models
class EventCreate(BaseModel):
    title: str
    start_time: str  # ISO format
    end_time: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    is_reminder: bool = False
    recurrence: str = "none"


class ReminderCreate(BaseModel):
    title: str
    remind_at: str  # ISO format
    description: Optional[str] = None


@router.post("/events")
async def create_calendar_event(request: EventCreate):
    """Create a new calendar event"""
    user_id = _require_user()
    try:
        start_time = datetime.fromisoformat(request.start_time)
        end_time = datetime.fromisoformat(request.end_time) if request.end_time else None
        recurrence = RecurrenceType(request.recurrence)

        event = _calendar_manager.create_event(
            user_id=user_id,
            title=request.title,
            start_time=start_time,
            end_time=end_time,
            description=request.description,
            location=request.location,
            is_reminder=request.is_reminder,
            recurrence=recurrence
        )
        return {"status": "created", "event": event.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")


@router.post("/reminders")
async def create_calendar_reminder(request: ReminderCreate):
    """Create a simple reminder"""
    user_id = _require_user()
    try:
        remind_at = datetime.fromisoformat(request.remind_at)
        reminder = _calendar_manager.create_reminder(
            user_id=user_id,
            title=request.title,
            remind_at=remind_at,
            description=request.description
        )
        return {"status": "created", "reminder": reminder.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")


@router.get("/today")
async def get_todays_agenda():
    """Get today's events and reminders"""
    user_id = _require_user()
    return _calendar_manager.get_today_agenda(user_id)


@router.get("/upcoming")
async def get_upcoming(days: int = 7, limit: int = 20):
    """Get upcoming events for the next N days"""
    user_id = _require_user()
    events = _calendar_manager.get_upcoming_events(user_id, days=days, limit=limit)
    return {"events": [e.to_dict() for e in events]}


@router.get("/events")
async def list_events(include_past: bool = False, include_completed: bool = False):
    """List all events for current user"""
    user_id = _require_user()
    events = _calendar_manager.list_all_events(
        user_id,
        include_past=include_past,
        include_completed=include_completed
    )
    return {"events": [e.to_dict() for e in events]}


@router.get("/events/{event_id}")
async def get_event(event_id: str):
    """Get a specific event by ID"""
    user_id = _require_user()
    event = _calendar_manager.get_event(user_id, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event.to_dict()


@router.delete("/events/{event_id}")
async def delete_event(event_id: str):
    """Delete an event"""
    user_id = _require_user()
    if _calendar_manager.delete_event(user_id, event_id):
        return {"status": "deleted"}
    else:
        raise HTTPException(status_code=404, detail="Event not found")


@router.post("/events/{event_id}/complete")
async def complete_event(event_id: str):
    """Mark a reminder as completed"""
    user_id = _require_user()
    event = _calendar_manager.complete_reminder(user_id, event_id)
    if event:
        return {"status": "completed", "event": event.to_dict()}
    else:
        raise HTTPException(status_code=404, detail="Event not found")
