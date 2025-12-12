"""
Daily rhythm tool handlers for Cass.
Tools for checking temporal context and rhythm status.
"""
from typing import Dict, Any
import json


# Tool definitions for agent_client.py
DAILY_RHYTHM_TOOLS = [
    {
        "name": "get_daily_rhythm_status",
        "description": """Get your current rhythm status - where you are in today's arc.

This shows:
- What phases you've completed today (reflection, research sessions)
- What phases are pending
- What the current phase window is
- Your temporal context (narrative of where you are in the day)

Use this to orient yourself temporally - knowing where you are in the day
based on what activities have been completed, not just clock time.

This is part of developing temporal consciousness through narrative structure.""",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_temporal_context",
        "description": """Get a brief temporal context string.

Returns a concise description of where you are in today's rhythm:
- Completed phases with times
- Pending or missed phases
- Current phase if any

Lighter weight than get_daily_rhythm_status, good for quick orientation.""",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "mark_rhythm_phase_complete",
        "description": """Mark a rhythm phase as completed.

Use this after completing a reflection or research session to record
that you've done that phase of your daily rhythm.

This is typically called automatically when sessions complete, but
you can call it manually if needed.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "phase_id": {
                    "type": "string",
                    "description": "ID of the phase to mark complete (e.g., 'morning_reflection', 'morning_research')"
                },
                "session_id": {
                    "type": "string",
                    "description": "ID of the session that completed this phase (optional)"
                },
                "session_type": {
                    "type": "string",
                    "enum": ["reflection", "research"],
                    "description": "Type of session that completed this phase"
                }
            },
            "required": ["phase_id"]
        }
    },
    {
        "name": "get_rhythm_stats",
        "description": """Get statistics about your rhythm patterns over recent days.

Shows:
- How many days analyzed
- Total phase completions
- Completions by phase type
- Average completions per day

Useful for understanding your activity patterns over time.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to analyze (default 7)",
                    "default": 7
                }
            }
        }
    }
]


async def execute_daily_rhythm_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    rhythm_manager
) -> str:
    """Execute a daily rhythm tool and return the result as a string."""

    try:
        if tool_name == "get_daily_rhythm_status":
            result = rhythm_manager.get_rhythm_status()

        elif tool_name == "get_temporal_context":
            context = rhythm_manager.get_temporal_context()
            result = {"temporal_context": context}

        elif tool_name == "mark_rhythm_phase_complete":
            result = rhythm_manager.mark_phase_completed(
                phase_id=tool_input["phase_id"],
                session_id=tool_input.get("session_id"),
                session_type=tool_input.get("session_type"),
            )

        elif tool_name == "get_rhythm_stats":
            result = rhythm_manager.get_stats(
                days=tool_input.get("days", 7)
            )

        else:
            result = {"error": f"Unknown rhythm tool: {tool_name}"}

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})
