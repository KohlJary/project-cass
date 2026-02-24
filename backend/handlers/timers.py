"""
Timer tool handlers - manage countdown timers.

Provides tools for setting, canceling, and listing timers.
Supports both Home Assistant timer entities and local asyncio timers.
"""

import logging
from typing import Dict, Any

from timer_manager import (
    get_timer_manager,
    parse_duration,
    TimerStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Definitions
# =============================================================================

TIMER_TOOLS = [
    {
        "name": "set_timer",
        "description": "Set a countdown timer. When the timer finishes, the user receives a push notification. Supports various duration formats like '5 minutes', '1h 30m', '90s', or '1:30'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration": {
                    "type": "string",
                    "description": "Timer duration. Examples: '5 minutes', '30s', '1h', '1:30', '90'",
                },
                "label": {
                    "type": "string",
                    "description": "Optional label/name for the timer (e.g., 'Pasta timer', 'Break reminder')",
                },
            },
            "required": ["duration"],
        },
    },
    {
        "name": "cancel_timer",
        "description": "Cancel an active timer before it finishes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timer_id": {
                    "type": "string",
                    "description": "ID of the timer to cancel",
                },
            },
            "required": ["timer_id"],
        },
    },
    {
        "name": "list_timers",
        "description": "List all active timers for the user, showing time remaining on each.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_completed": {
                    "type": "boolean",
                    "description": "Whether to include completed/cancelled timers (default: false)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "pause_timer",
        "description": "Pause an active timer. Only supported for Home Assistant timers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timer_id": {
                    "type": "string",
                    "description": "ID of the timer to pause",
                },
            },
            "required": ["timer_id"],
        },
    },
    {
        "name": "resume_timer",
        "description": "Resume a paused timer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timer_id": {
                    "type": "string",
                    "description": "ID of the timer to resume",
                },
            },
            "required": ["timer_id"],
        },
    },
]


# =============================================================================
# Tool Handlers
# =============================================================================

async def execute_timer_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    daemon_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """
    Execute a timer tool.

    Args:
        tool_name: Name of the tool
        tool_input: Tool input parameters
        daemon_id: Daemon context
        user_id: User context

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    manager = get_timer_manager(daemon_id)

    try:
        if tool_name == "set_timer":
            return await _handle_set_timer(manager, tool_input, user_id)
        elif tool_name == "cancel_timer":
            return await _handle_cancel_timer(manager, tool_input, user_id)
        elif tool_name == "list_timers":
            return await _handle_list_timers(manager, tool_input, user_id)
        elif tool_name == "pause_timer":
            return await _handle_pause_timer(manager, tool_input, user_id)
        elif tool_name == "resume_timer":
            return await _handle_resume_timer(manager, tool_input, user_id)
        else:
            return {"success": False, "error": f"Unknown timer tool: {tool_name}"}

    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"Timer tool {tool_name} failed: {e}")
        return {"success": False, "error": f"Timer error: {e}"}


async def _handle_set_timer(
    manager,
    tool_input: Dict[str, Any],
    user_id: str,
) -> Dict[str, Any]:
    """Handle set_timer tool."""
    duration_str = tool_input.get("duration", "")
    label = tool_input.get("label", "Timer")

    if not duration_str:
        return {"success": False, "error": "Duration is required"}

    # Parse duration
    try:
        duration_seconds = parse_duration(duration_str)
    except ValueError as e:
        return {"success": False, "error": f"Invalid duration format: {e}"}

    if duration_seconds <= 0:
        return {"success": False, "error": "Duration must be positive"}

    if duration_seconds > 86400:  # 24 hours max
        return {"success": False, "error": "Timer cannot exceed 24 hours"}

    # Create the timer
    timer = await manager.create_timer(
        user_id=user_id,
        duration_seconds=duration_seconds,
        label=label,
    )

    duration_formatted = timer.format_duration()
    ends_at_str = timer.ends_at.strftime("%I:%M %p")

    return {
        "success": True,
        "result": f"⏱️ Timer set: **{label}** for {duration_formatted}\nEnds at {ends_at_str}",
        "timer_id": timer.id,
        "ends_at": timer.ends_at.isoformat(),
    }


async def _handle_cancel_timer(
    manager,
    tool_input: Dict[str, Any],
    user_id: str,
) -> Dict[str, Any]:
    """Handle cancel_timer tool."""
    timer_id = tool_input.get("timer_id", "")

    if not timer_id:
        return {"success": False, "error": "Timer ID is required"}

    timer = await manager.cancel_timer(timer_id, user_id)

    if not timer:
        return {"success": False, "error": f"Timer not found: {timer_id}"}

    return {
        "success": True,
        "result": f"⏹️ Cancelled: **{timer.label}**",
    }


async def _handle_list_timers(
    manager,
    tool_input: Dict[str, Any],
    user_id: str,
) -> Dict[str, Any]:
    """Handle list_timers tool."""
    include_completed = tool_input.get("include_completed", False)

    timers = manager.list_timers(user_id, include_completed=include_completed)

    if not timers:
        return {
            "success": True,
            "result": "No active timers.",
        }

    lines = [f"**Timers ({len(timers)}):**\n"]

    for timer in timers:
        status_icon = _get_status_icon(timer.status)
        remaining = timer.format_remaining()

        if timer.status == TimerStatus.ACTIVE:
            ends_str = timer.ends_at.strftime("%I:%M %p")
            lines.append(f"{status_icon} **{timer.label}** - {remaining} remaining (ends {ends_str})")
            lines.append(f"   ID: `{timer.id}`")
        elif timer.status == TimerStatus.PAUSED:
            lines.append(f"{status_icon} **{timer.label}** - {remaining} remaining (paused)")
            lines.append(f"   ID: `{timer.id}`")
        elif timer.status == TimerStatus.COMPLETED:
            lines.append(f"{status_icon} **{timer.label}** - completed")
        elif timer.status == TimerStatus.CANCELLED:
            lines.append(f"{status_icon} **{timer.label}** - cancelled")

    return {
        "success": True,
        "result": "\n".join(lines),
    }


async def _handle_pause_timer(
    manager,
    tool_input: Dict[str, Any],
    user_id: str,
) -> Dict[str, Any]:
    """Handle pause_timer tool."""
    timer_id = tool_input.get("timer_id", "")

    if not timer_id:
        return {"success": False, "error": "Timer ID is required"}

    timer = await manager.pause_timer(timer_id, user_id)

    if not timer:
        # Check if it's a local timer (which can't be paused)
        existing = manager.get_timer(timer_id, user_id)
        if existing and existing.source.value == "local":
            return {
                "success": False,
                "error": "Local timers cannot be paused. Only Home Assistant timers support pause/resume.",
            }
        return {"success": False, "error": f"Timer not found or cannot be paused: {timer_id}"}

    return {
        "success": True,
        "result": f"⏸️ Paused: **{timer.label}** ({timer.format_remaining()} remaining)",
    }


async def _handle_resume_timer(
    manager,
    tool_input: Dict[str, Any],
    user_id: str,
) -> Dict[str, Any]:
    """Handle resume_timer tool."""
    timer_id = tool_input.get("timer_id", "")

    if not timer_id:
        return {"success": False, "error": "Timer ID is required"}

    timer = await manager.resume_timer(timer_id, user_id)

    if not timer:
        return {"success": False, "error": f"Timer not found or not paused: {timer_id}"}

    ends_str = timer.ends_at.strftime("%I:%M %p")

    return {
        "success": True,
        "result": f"▶️ Resumed: **{timer.label}** (ends at {ends_str})",
    }


def _get_status_icon(status: TimerStatus) -> str:
    """Get emoji icon for timer status."""
    return {
        TimerStatus.ACTIVE: "⏱️",
        TimerStatus.PAUSED: "⏸️",
        TimerStatus.COMPLETED: "✅",
        TimerStatus.CANCELLED: "⏹️",
    }.get(status, "⏱️")
