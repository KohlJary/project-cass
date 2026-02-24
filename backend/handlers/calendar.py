"""
Calendar tool handler - manages events and reminders

Supports both the legacy SQLite-only CalendarManager and the new
UnifiedCalendarManager that integrates with Home Assistant calendars.
"""
from datetime import datetime
from typing import Dict, Optional, Any
from calendar_manager import CalendarManager, RecurrenceType
from unified_calendar import UnifiedCalendarManager, UnifiedEvent


async def execute_calendar_tool(
    tool_name: str,
    tool_input: Dict,
    user_id: str,
    calendar_manager: CalendarManager,
    conversation_id: Optional[str] = None,
    daemon_id: Optional[str] = None,
) -> Dict:
    """
    Handle calendar-related tool calls.

    Args:
        tool_name: Name of the tool being called
        tool_input: Input parameters for the tool
        user_id: Current user's ID
        calendar_manager: CalendarManager instance (legacy SQLite-only)
        conversation_id: Optional conversation ID for linking
        daemon_id: Optional daemon_id for UnifiedCalendarManager

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    # Use UnifiedCalendarManager if daemon_id is provided
    unified: Optional[UnifiedCalendarManager] = None
    if daemon_id:
        unified = UnifiedCalendarManager(daemon_id, user_id)

    try:
        # =====================================================================
        # Calendar Configuration Tools (Unified only)
        # =====================================================================
        if tool_name == "list_calendars":
            if not unified:
                return {
                    "success": False,
                    "error": "Calendar listing requires daemon context"
                }
            calendars = await unified.get_available_calendars()
            if not calendars:
                return {
                    "success": True,
                    "result": "No calendars available."
                }

            lines = [f"**Available Calendars ({len(calendars)}):**\n"]
            for cal in calendars:
                write_support = "✓ writable" if cal["supports_write"] else "read-only"
                lines.append(f"- **{cal['friendly_name']}** (`{cal['entity_id']}`)")
                lines.append(f"  Provider: {cal['provider']}, {write_support}")

            config = unified.get_config()
            lines.append(f"\n**Current Configuration:**")
            lines.append(f"- Primary: `{config['primary_calendar']}`")
            lines.append(f"- Write to: `{config['write_calendar']}`")
            if config['read_calendars']:
                lines.append(f"- Also reading: {', '.join(f'`{c}`' for c in config['read_calendars'])}")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "configure_calendar":
            if not unified:
                return {
                    "success": False,
                    "error": "Calendar configuration requires daemon context"
                }

            primary = tool_input.get("primary_calendar")
            write = tool_input.get("write_calendar")
            read = tool_input.get("read_calendars")

            changes = []
            if primary:
                unified.set_primary_calendar(primary)
                changes.append(f"primary calendar to `{primary}`")
            if write:
                unified.set_write_calendar(write)
                changes.append(f"write calendar to `{write}`")
            if read is not None:
                unified.set_read_calendars(read)
                changes.append(f"read calendars to {read}")

            if not changes:
                return {
                    "success": False,
                    "error": "No configuration changes specified"
                }

            return {
                "success": True,
                "result": f"✓ Updated calendar configuration: {', '.join(changes)}"
            }

        # =====================================================================
        # Event Creation
        # =====================================================================
        elif tool_name == "create_event":
            title = tool_input["title"]
            start_time = datetime.fromisoformat(tool_input["start_time"])
            end_time = datetime.fromisoformat(tool_input["end_time"]) if tool_input.get("end_time") else None
            description = tool_input.get("description")
            location = tool_input.get("location")
            recurrence_str = tool_input.get("recurrence", "none")
            recurrence = RecurrenceType(recurrence_str)

            if unified:
                event = await unified.create_event(
                    title=title,
                    start_time=start_time,
                    end_time=end_time,
                    description=description,
                    location=location,
                    is_reminder=False,
                    recurrence=recurrence,
                    conversation_id=conversation_id
                )
                event_id = event.id if event else None
            else:
                sqlite_event = calendar_manager.create_event(
                    user_id=user_id,
                    title=title,
                    start_time=start_time,
                    end_time=end_time,
                    description=description,
                    location=location,
                    recurrence=recurrence,
                    conversation_id=conversation_id
                )
                event_id = sqlite_event.id

            time_str = start_time.strftime("%A, %B %d at %I:%M %p")
            result = f"✓ Created event: **{title}** on {time_str}"
            if location:
                result += f" at {location}"
            if recurrence != RecurrenceType.NONE:
                result += f" (repeats {recurrence.value})"

            return {"success": True, "result": result, "event_id": event_id}

        elif tool_name == "create_reminder":
            title = tool_input["title"]
            remind_at = datetime.fromisoformat(tool_input["remind_at"])
            description = tool_input.get("description")

            if unified:
                event = await unified.create_event(
                    title=title,
                    start_time=remind_at,
                    description=description,
                    is_reminder=True,
                    conversation_id=conversation_id
                )
                event_id = event.id if event else None
            else:
                reminder = calendar_manager.create_reminder(
                    user_id=user_id,
                    title=title,
                    remind_at=remind_at,
                    description=description,
                    conversation_id=conversation_id
                )
                event_id = reminder.id

            time_str = remind_at.strftime("%A, %B %d at %I:%M %p")
            return {
                "success": True,
                "result": f"✓ Reminder set: **{title}** for {time_str}",
                "event_id": event_id
            }

        # =====================================================================
        # Event Queries
        # =====================================================================
        elif tool_name == "get_todays_agenda":
            if unified:
                events = await unified.get_agenda()
                if not events:
                    day_name = datetime.now().strftime("%A")
                    return {
                        "success": True,
                        "result": f"No events or reminders scheduled for today ({day_name})."
                    }
                return _format_agenda(events)
            else:
                agenda = calendar_manager.get_today_agenda(user_id)
                if agenda["total_count"] == 0:
                    return {
                        "success": True,
                        "result": f"No events or reminders scheduled for today ({agenda['day_name']})."
                    }
                return _format_legacy_agenda(agenda)

        elif tool_name == "get_upcoming_events":
            days = tool_input.get("days", 7)
            limit = tool_input.get("limit", 10)

            if unified:
                events = await unified.get_upcoming(days=days)
                events = events[:limit]
                if not events:
                    return {
                        "success": True,
                        "result": f"No events or reminders in the next {days} days."
                    }
                return _format_upcoming(events, days)
            else:
                events = calendar_manager.get_upcoming_events(user_id, days=days, limit=limit)
                if not events:
                    return {
                        "success": True,
                        "result": f"No events or reminders in the next {days} days."
                    }
                return _format_legacy_upcoming(events, days)

        elif tool_name == "search_events":
            query = tool_input["query"]
            limit = tool_input.get("limit", 10)

            if unified:
                events = await unified.search(query, limit=limit)
            else:
                events_raw = calendar_manager.search_events(user_id, query, limit=limit)
                events = [UnifiedEvent.from_sqlite_event(e) for e in events_raw]

            if not events:
                return {
                    "success": True,
                    "result": f"No events found matching '{query}'."
                }

            lines = [f"**Found {len(events)} event(s) matching '{query}':**\n"]
            for e in events:
                time_str = e.start_time.strftime("%a %b %d, %I:%M %p")
                status = " (completed)" if e.completed else ""
                source_tag = f" [{e.source}]" if e.source != "sqlite" else ""
                lines.append(f"- **{e.title}** - {time_str}{status}{source_tag}\n  ID: `{e.id}`")

            lines.append("\n⚠️ ACTION REQUIRED: You must now call update_event, delete_event, or complete_reminder with one of the event IDs above. Do not respond to the user until you have completed the action.")

            return {"success": True, "result": "\n".join(lines)}

        # =====================================================================
        # Event Modification (SQLite only for now)
        # =====================================================================
        elif tool_name == "complete_reminder":
            event_id = tool_input["event_id"]

            if unified:
                event = unified.complete_reminder(event_id)
            else:
                event_raw = calendar_manager.complete_reminder(user_id, event_id)
                event = UnifiedEvent.from_sqlite_event(event_raw) if event_raw else None

            if event:
                return {
                    "success": True,
                    "result": f"✓ Marked reminder as complete: **{event.title}**"
                }
            else:
                return {
                    "success": False,
                    "error": f"Reminder not found with ID: {event_id}"
                }

        elif tool_name == "delete_event":
            event_id = tool_input["event_id"]

            # Get the event first for the response message
            if unified:
                event = unified.get_event(event_id)
            else:
                event_raw = calendar_manager.get_event(user_id, event_id)
                event = UnifiedEvent.from_sqlite_event(event_raw) if event_raw else None

            if not event:
                return {
                    "success": False,
                    "error": f"Event not found with ID: {event_id}"
                }

            title = event.title
            if unified:
                success = unified.delete_event(event_id, event.source)
            else:
                success = calendar_manager.delete_event(user_id, event_id)

            if success:
                return {
                    "success": True,
                    "result": f"✓ Deleted: **{title}**"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to delete event"
                }

        elif tool_name == "update_event":
            event_id = tool_input["event_id"]

            # Get the event first to verify it exists
            if unified:
                event = unified.get_event(event_id)
            else:
                event_raw = calendar_manager.get_event(user_id, event_id)
                event = UnifiedEvent.from_sqlite_event(event_raw) if event_raw else None

            if not event:
                return {
                    "success": False,
                    "error": f"Event not found with ID: {event_id}"
                }

            # Parse optional update fields
            title = tool_input.get("title")
            start_time = datetime.fromisoformat(tool_input["start_time"]) if tool_input.get("start_time") else None
            end_time = datetime.fromisoformat(tool_input["end_time"]) if tool_input.get("end_time") else None
            description = tool_input.get("description")
            location = tool_input.get("location")

            if unified:
                updated_event = unified.update_event(
                    event_id=event_id,
                    title=title,
                    start_time=start_time,
                    end_time=end_time,
                    description=description,
                    location=location,
                    source=event.source
                )
            else:
                updated_raw = calendar_manager.update_event(
                    user_id=user_id,
                    event_id=event_id,
                    title=title,
                    start_time=start_time,
                    end_time=end_time,
                    description=description,
                    location=location
                )
                updated_event = UnifiedEvent.from_sqlite_event(updated_raw) if updated_raw else None

            if updated_event:
                changes = []
                if title:
                    changes.append(f"title to '{title}'")
                if start_time:
                    changes.append(f"time to {start_time.strftime('%A, %B %d at %I:%M %p')}")
                if location:
                    changes.append(f"location to '{location}'")
                if description:
                    changes.append("description")

                change_str = ", ".join(changes) if changes else "details"
                return {
                    "success": True,
                    "result": f"✓ Updated **{updated_event.title}**: changed {change_str}"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to update event"
                }

        elif tool_name == "clear_all_events":
            confirm = tool_input.get("confirm", False)

            if not confirm:
                return {
                    "success": False,
                    "error": "Must set confirm=true to delete all events"
                }

            # This only clears SQLite events (not HA calendars)
            events = calendar_manager.list_all_events(user_id, include_completed=True, include_past=True)

            if not events:
                return {
                    "success": True,
                    "result": "Calendar is already empty - no events to delete."
                }

            count = 0
            for event in events:
                calendar_manager.delete_event(user_id, event.id)
                count += 1

            return {
                "success": True,
                "result": f"✓ Cleared local calendar - deleted {count} event(s)."
            }

        elif tool_name == "delete_events_by_query":
            query = tool_input["query"]
            delete_all = tool_input.get("delete_all_matches", False)

            # Search for matching events
            events = calendar_manager.search_events(user_id, query, limit=20)

            if not events:
                return {
                    "success": True,
                    "result": f"No events found matching '{query}'. Nothing to delete."
                }

            deleted = []
            if delete_all:
                # Delete all matches
                for event in events:
                    calendar_manager.delete_event(user_id, event.id)
                    deleted.append(event.title)
            else:
                # Delete only the first (most relevant) match
                event = events[0]
                calendar_manager.delete_event(user_id, event.id)
                deleted.append(event.title)

            if len(deleted) == 1:
                return {
                    "success": True,
                    "result": f"✓ Deleted: **{deleted[0]}**"
                }
            else:
                return {
                    "success": True,
                    "result": f"✓ Deleted {len(deleted)} events:\n" + "\n".join(f"- {t}" for t in deleted)
                }

        elif tool_name == "reschedule_event_by_query":
            query = tool_input["query"]
            new_start_time = datetime.fromisoformat(tool_input["new_start_time"])
            new_end_time = datetime.fromisoformat(tool_input["new_end_time"]) if tool_input.get("new_end_time") else None

            # Search for matching event
            events = calendar_manager.search_events(user_id, query, limit=5)

            if not events:
                return {
                    "success": True,
                    "result": f"No events found matching '{query}'. Nothing to reschedule."
                }

            # Reschedule the first match
            event = events[0]
            old_time = datetime.fromisoformat(event.start_time)

            updated = calendar_manager.update_event(
                user_id=user_id,
                event_id=event.id,
                start_time=new_start_time,
                end_time=new_end_time
            )

            if updated:
                old_str = old_time.strftime("%A, %B %d at %I:%M %p")
                new_str = new_start_time.strftime("%A, %B %d at %I:%M %p")
                return {
                    "success": True,
                    "result": f"✓ Rescheduled **{event.title}**\n  From: {old_str}\n  To: {new_str}"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to reschedule event"
                }

        else:
            return {"success": False, "error": f"Unknown calendar tool: {tool_name}"}

    except ValueError as e:
        return {"success": False, "error": f"Invalid date/time format: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# Formatting Helpers
# =============================================================================

def _format_agenda(events: list[UnifiedEvent]) -> Dict[str, Any]:
    """Format unified events as agenda response."""
    day_name = datetime.now().strftime("%A")
    date_str = datetime.now().strftime("%Y-%m-%d")

    lines = [f"**{day_name}'s Agenda** ({date_str})\n"]

    regular_events = [e for e in events if not e.is_reminder]
    reminders = [e for e in events if e.is_reminder]

    if regular_events:
        lines.append("**Events:**")
        for e in regular_events:
            time_str = e.start_time.strftime("%I:%M %p")
            source_tag = f" [{e.source}]" if e.source != "sqlite" else ""
            lines.append(f"- {time_str}: {e.title}{source_tag}")

    if reminders:
        lines.append("\n**Reminders:**")
        for r in reminders:
            time_str = r.start_time.strftime("%I:%M %p")
            lines.append(f"- {time_str}: {r.title}")

    return {"success": True, "result": "\n".join(lines)}


def _format_legacy_agenda(agenda: Dict) -> Dict[str, Any]:
    """Format legacy CalendarManager agenda."""
    lines = [f"**{agenda['day_name']}'s Agenda** ({agenda['date']})\n"]

    if agenda["events"]:
        lines.append("**Events:**")
        for e in agenda["events"]:
            time_str = datetime.fromisoformat(e["start_time"]).strftime("%I:%M %p")
            lines.append(f"- {time_str}: {e['title']}")

    if agenda["reminders"]:
        lines.append("\n**Reminders:**")
        for r in agenda["reminders"]:
            time_str = datetime.fromisoformat(r["start_time"]).strftime("%I:%M %p")
            lines.append(f"- {time_str}: {r['title']}")

    return {"success": True, "result": "\n".join(lines)}


def _format_upcoming(events: list[UnifiedEvent], days: int) -> Dict[str, Any]:
    """Format unified events as upcoming response."""
    lines = [f"**Upcoming ({len(events)} items in next {days} days):**\n"]
    for e in events:
        time_str = e.start_time.strftime("%a %b %d, %I:%M %p")
        event_type = "🔔" if e.is_reminder else "📅"
        source_tag = f" [{e.source}]" if e.source != "sqlite" else ""
        lines.append(f"{event_type} **{time_str}**: {e.title}{source_tag}\n   ID: `{e.id}`")

    lines.append("\n⚠️ ACTION REQUIRED: You must now call update_event, delete_event, or complete_reminder with one of the event IDs above. Do not respond to the user until you have completed the action.")

    return {"success": True, "result": "\n".join(lines)}


def _format_legacy_upcoming(events: list, days: int) -> Dict[str, Any]:
    """Format legacy CalendarManager upcoming events."""
    lines = [f"**Upcoming ({len(events)} items in next {days} days):**\n"]
    for e in events:
        dt = datetime.fromisoformat(e.start_time)
        time_str = dt.strftime("%a %b %d, %I:%M %p")
        event_type = "🔔" if e.is_reminder else "📅"
        lines.append(f"{event_type} **{time_str}**: {e.title}\n   ID: `{e.id}`")

    lines.append("\n⚠️ ACTION REQUIRED: You must now call update_event, delete_event, or complete_reminder with one of the event IDs above. Do not respond to the user until you have completed the action.")

    return {"success": True, "result": "\n".join(lines)}


# =============================================================================
# New Calendar Tools Definitions
# =============================================================================

CALENDAR_CONFIG_TOOLS = [
    {
        "name": "list_calendars",
        "description": "List all available calendars including Home Assistant calendars (Google, CalDAV, Local) and the built-in SQLite calendar. Shows current calendar configuration.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "configure_calendar",
        "description": "Configure which calendars to use. Set primary calendar for main view, write calendar for creating new events, and additional read calendars to aggregate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "primary_calendar": {
                    "type": "string",
                    "description": "Entity ID of the primary calendar (e.g., 'sqlite', 'calendar.google_personal')",
                },
                "write_calendar": {
                    "type": "string",
                    "description": "Entity ID where new events should be created",
                },
                "read_calendars": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional calendar entity IDs to include in agenda views",
                },
            },
            "required": [],
        },
    },
]
