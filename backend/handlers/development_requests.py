"""
Development Request tool handler - Cass-Daedalus coordination bridge

Enables Cass to request development work from Daedalus (human-timescale
development that can't be done instantly via LLM execution).

Key patterns:
- request_development: Create a new work request
- list_my_requests: Check status of pending/active requests
- get_request_status: Get details on a specific request
"""

from typing import Dict, Optional


async def execute_development_request_tool(
    tool_name: str,
    tool_input: Dict,
    daemon_id: str,
    state_bus=None,
) -> Dict:
    """
    Execute a development request tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        daemon_id: Daemon ID for the manager
        state_bus: Optional state bus for event emission

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    from development_requests import get_development_request_manager

    try:
        manager = get_development_request_manager(daemon_id, state_bus)

        if tool_name == "request_development":
            # Create a new development request
            title = tool_input.get("title")
            if not title:
                return {
                    "success": False,
                    "error": "'title' is required"
                }

            # An alias of babelr_plans ask (2026-11-16): her request goes into her
            # standing plan in Plans, where Kohl sees it. The admin-panel store it
            # used to write had no page, so nobody saw it.
            parts = [tool_input.get("description", "").strip()]
            if tool_input.get("context"):
                parts.append(f"Why now: {tool_input['context']}")
            extra = [f"type: {tool_input.get('request_type', 'feature')}",
                     f"priority: {tool_input.get('priority', 'normal')}"]
            if tool_input.get("related_actions"):
                extra.append(f"related: {', '.join(tool_input['related_actions'])}")
            parts.append("(" + "; ".join(extra) + ")")
            from babelr_organ.tools import ask_in_plans
            got = ask_in_plans(title, "\n\n".join(p for p in parts if p))
            if got.get("success"):
                return {"success": True, "result": (
                    f"Asked in Plans ({got['plan']}): {title}. It waits there, outside any phase, "
                    f"until Kohl takes it up. babelr_plans my_asks shows what came of it."),
                    "plan": got["plan"]}
            if not got.get("unavailable"):
                return {"success": False, "error": got.get("error", "Plans didn't take the ask")}
            request = manager.create_request(
                title=title,
                request_type=tool_input.get("request_type", "feature"),
                description=tool_input.get("description", ""),
                priority=tool_input.get("priority", "normal"),
                context=tool_input.get("context"),
                related_actions=tool_input.get("related_actions"),
                requested_by="cass",
            )
            return {
                "success": True,
                "result": (f"Babelr isn't running, so this couldn't go to Plans. It's kept here "
                           f"({request.id}) but nobody will see it until it's asked again in Plans."),
                "request_id": request.id,
            }

        elif tool_name == "list_my_requests":
            # Her asks live in Plans now (2026-11-16); older ones kept here are listed below them.
            from babelr_organ.organ import get_babelr_organ
            organ = get_babelr_organ()
            asked = organ.plans("my_asks") if organ is not None and organ.enabled else None
            if asked and asked.get("success") and asked.get("asks"):
                lines = ["**What I've asked in Plans:**"]
                for a in asked["asks"]:
                    where = "in a phase" if a["in_a_phase"] else "waiting"
                    lines.append(f"- {a['title']} ({a['plan']}; {a['status']}, {where})"
                                 + (f": {a['resolution']}" if a.get("resolution") else ""))
                return {"success": True, "result": "\n".join(lines), "count": len(asked["asks"])}
            # List requests with optional status filter
            status = tool_input.get("status")
            limit = tool_input.get("limit", 10)

            requests = manager.list_requests(status=status, limit=limit)

            if not requests:
                if status:
                    return {
                        "success": True,
                        "result": f"No development requests with status '{status}'."
                    }
                return {
                    "success": True,
                    "result": "No development requests found."
                }

            # Group by status for readability
            by_status = {}
            for req in requests:
                s = req.status.value
                if s not in by_status:
                    by_status[s] = []
                by_status[s].append(req)

            lines = ["**My Development Requests:**\n"]
            for status_name, reqs in by_status.items():
                lines.append(f"\n__{status_name.upper()}__ ({len(reqs)}):")
                for req in reqs:
                    lines.append(f"  {req.get_display_summary()}")
                    if req.claimed_by:
                        lines.append(f"    → Claimed by: {req.claimed_by}")
                    if req.result:
                        lines.append(f"    → Result: {req.result[:100]}...")

            return {
                "success": True,
                "result": "\n".join(lines),
                "count": len(requests),
            }

        elif tool_name == "get_request_status":
            # Get details on a specific request
            request_id = tool_input.get("request_id")
            if not request_id:
                return {
                    "success": False,
                    "error": "'request_id' is required"
                }

            request = manager.get_request(request_id)
            if not request:
                return {
                    "success": False,
                    "error": f"Request not found: {request_id}"
                }

            lines = [
                f"**Development Request: {request.id}**\n",
                f"**Title**: {request.title}",
                f"**Type**: {request.request_type.value}",
                f"**Priority**: {request.priority.value}",
                f"**Status**: {request.status.value}",
                f"**Created**: {request.created_at.strftime('%Y-%m-%d %H:%M')}",
            ]

            if request.description:
                lines.append(f"\n**Description**:\n{request.description}")

            if request.context:
                lines.append(f"\n**Context**:\n{request.context}")

            if request.claimed_by:
                lines.append(f"\n**Claimed by**: {request.claimed_by}")
                if request.claimed_at:
                    lines.append(f"**Claimed at**: {request.claimed_at.strftime('%Y-%m-%d %H:%M')}")

            if request.result:
                lines.append(f"\n**Result**:\n{request.result}")

            if request.result_artifacts:
                lines.append(f"\n**Artifacts**: {', '.join(request.result_artifacts)}")

            if request.completed_at:
                lines.append(f"\n**Completed**: {request.completed_at.strftime('%Y-%m-%d %H:%M')}")

            return {
                "success": True,
                "result": "\n".join(lines),
                "request": request.to_dict(),
            }

        elif tool_name == "get_development_stats":
            # Get statistics about requests
            stats = manager.get_stats()

            lines = [
                "**Development Request Statistics:**\n",
                f"**Pending**: {stats['total_pending']}",
                f"**In Progress**: {stats['total_in_progress']}",
                f"**Completed This Week**: {stats['completed_this_week']}",
            ]

            if stats['pending_by_priority']:
                lines.append("\n**Pending by Priority**:")
                for priority, count in stats['pending_by_priority'].items():
                    lines.append(f"  - {priority}: {count}")

            return {
                "success": True,
                "result": "\n".join(lines),
                "stats": stats,
            }

        else:
            return {
                "success": False,
                "error": f"Unknown development request tool: {tool_name}"
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"Error executing {tool_name}: {str(e)}"
        }


# =============================================================================
# TOOL DEFINITIONS for LLM
# =============================================================================

DEVELOPMENT_REQUEST_TOOLS = [
    {
        "name": "request_development",
        "description": "Request development work from Daedalus (human-timescale development that can't be done instantly via LLM). Use this when you need a new action handler, capability, or feature that requires code changes. It goes into my standing plan in Babelr Plans (same as babelr_plans ask), where Kohl sees it and can pull it into a phase to build.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Brief title for the request (e.g., 'Add recipe management tools')"
                },
                "request_type": {
                    "type": "string",
                    "enum": ["new_action", "bug_fix", "feature", "refactor", "capability", "integration"],
                    "description": "Type of work: new_action (new tool/handler), bug_fix (fix broken functionality), feature (new feature), refactor (code improvement), capability (new ability), integration (connect to external system)"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of what you need and why. Include use cases, expected behavior, and any context that would help Daedalus understand and implement this well."
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high", "urgent"],
                    "description": "How urgently you need this: low (nice to have), normal (would help), high (important for current work), urgent (blocking critical functionality)"
                },
                "context": {
                    "type": "string",
                    "description": "Additional context about why you need this - what conversation or situation led to this request"
                },
                "related_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Names of related actions or tools that this request connects to"
                }
            },
            "required": ["title", "description"]
        }
    },
    {
        "name": "list_my_requests",
        "description": "List your development requests to Daedalus. Check on pending requests, see what's in progress, and track completed work.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "claimed", "in_progress", "review", "completed", "cancelled"],
                    "description": "Filter by status (optional - shows all if not specified)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of requests to return (default 10)"
                }
            }
        }
    },
    {
        "name": "get_request_status",
        "description": "Get detailed status of a specific development request, including who's working on it and any results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "request_id": {
                    "type": "string",
                    "description": "ID of the request to check"
                }
            },
            "required": ["request_id"]
        }
    },
    {
        "name": "get_development_stats",
        "description": "Get statistics about your development requests - how many pending, in progress, completed this week, etc.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]
