"""
Research scheduler tool handlers for Cass.
Tools for requesting scheduled research sessions.
"""
from typing import Dict, Any
import json

# Tool definitions for agent_client.py
RESEARCH_SCHEDULER_TOOLS = [
    {
        "name": "request_scheduled_session",
        "description": """Request a scheduled REFLECTION session (solo contemplation).

Use this when you want dedicated private reflection time.
This is for introspection, processing experiences, and forming perspectives.

Your request will be reviewed by an admin who can:
- Approve it (session will run at scheduled time)
- Adjust the timing
- Reject it with a reason

For RESEARCH (web search, reading sources), use request_scheduled_research instead.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus_description": {
                    "type": "string",
                    "description": "Theme or topic for reflection. What do you want to contemplate?"
                },
                "preferred_time": {
                    "type": "string",
                    "description": "Preferred time in HH:MM format (24-hour). Optional."
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Requested duration (default 15, max 30)",
                    "default": 15
                },
                "recurrence": {
                    "type": "string",
                    "enum": ["once", "daily", "weekly"],
                    "description": "How often to run this session",
                    "default": "once"
                }
            },
            "required": ["focus_description"]
        }
    },
    {
        "name": "request_scheduled_research",
        "description": """Request a scheduled RESEARCH session (autonomous web research).

Use this when you want dedicated time for researching a topic.
In research sessions you can:
- Search the web
- Read URLs and pages
- Create research notes
- Build knowledge on a topic

Your request will be reviewed by an admin who can approve, adjust timing, or reject.

For REFLECTION (private contemplation), use request_scheduled_session instead.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus_description": {
                    "type": "string",
                    "description": "What you want to research. Be specific about your goals."
                },
                "focus_item_id": {
                    "type": "string",
                    "description": "ID of agenda item or working question to focus on (optional)"
                },
                "preferred_time": {
                    "type": "string",
                    "description": "Preferred time in HH:MM format (24-hour). Optional."
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Requested duration (default 30, max 60)",
                    "default": 30
                },
                "recurrence": {
                    "type": "string",
                    "enum": ["once", "daily", "weekly"],
                    "description": "How often to run this session",
                    "default": "once"
                },
                "mode": {
                    "type": "string",
                    "enum": ["explore", "deep"],
                    "description": "explore: broad exploration. deep: focused on one question.",
                    "default": "explore"
                }
            },
            "required": ["focus_description"]
        }
    },
    {
        "name": "list_my_schedule_requests",
        "description": """List your pending and active schedule requests.

See what research sessions you've requested and their status:
- pending_approval: Awaiting admin review
- approved: Will run at scheduled time
- paused: Temporarily stopped
- rejected: Admin declined (see reason)""",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_completed": {
                    "type": "boolean",
                    "description": "Include completed/rejected requests",
                    "default": False
                }
            }
        }
    },
    {
        "name": "cancel_schedule_request",
        "description": """Cancel a pending schedule request.

You can only cancel requests that are still pending approval.
Once approved, only an admin can pause or delete the schedule.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "schedule_id": {
                    "type": "string",
                    "description": "ID of the schedule to cancel"
                }
            },
            "required": ["schedule_id"]
        }
    },
    {
        "name": "get_scheduler_stats",
        "description": """Get statistics about research scheduling.

Shows counts of schedules by status, total runs completed, etc.""",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]


async def execute_research_scheduler_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    scheduler
) -> str:
    """Execute a research scheduler tool and return the result as a string."""

    try:
        if tool_name == "request_scheduled_session":
            # Request a REFLECTION session
            result = scheduler.request_session(
                focus_description=tool_input["focus_description"],
                focus_item_id=tool_input.get("focus_item_id"),
                preferred_time=tool_input.get("preferred_time"),
                duration_minutes=tool_input.get("duration_minutes", 15),
                recurrence=tool_input.get("recurrence", "once"),
                mode="explore",  # Reflection doesn't use mode
                session_type="reflection"
            )

        elif tool_name == "request_scheduled_research":
            # Request a RESEARCH session
            result = scheduler.request_session(
                focus_description=tool_input["focus_description"],
                focus_item_id=tool_input.get("focus_item_id"),
                preferred_time=tool_input.get("preferred_time"),
                duration_minutes=tool_input.get("duration_minutes", 30),
                recurrence=tool_input.get("recurrence", "once"),
                mode=tool_input.get("mode", "explore"),
                session_type="research"
            )

        elif tool_name == "list_my_schedule_requests":
            requests = scheduler.list_my_requests(
                include_completed=tool_input.get("include_completed", False)
            )
            result = {
                "requests": requests,
                "count": len(requests)
            }

        elif tool_name == "cancel_schedule_request":
            result = scheduler.cancel_request(tool_input["schedule_id"])

        elif tool_name == "get_scheduler_stats":
            result = scheduler.get_stats()

        else:
            result = {"error": f"Unknown scheduler tool: {tool_name}"}

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})
