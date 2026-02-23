"""
Activity tool handler - allows Cass to introspect her own daily activities.

Provides tools to:
- Get a summary of activities for a day
- Get details of specific work units
- Search through activity history
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from scheduling.work_summary_store import WorkSummaryStore, WorkSummary


def _format_time(dt: Optional[datetime]) -> str:
    """Format datetime to human-readable time."""
    if not dt:
        return "?"
    return dt.strftime("%I:%M %p").lstrip("0")


def _format_duration(minutes: int) -> str:
    """Format minutes to human-readable duration."""
    if minutes < 60:
        return f"{minutes} minutes"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours} hour{'s' if hours > 1 else ''}"
    return f"{hours}h {mins}m"


def _format_work_summary_brief(ws: WorkSummary) -> str:
    """Format a work summary as a brief listing."""
    time_str = _format_time(ws.started_at)
    duration_str = _format_duration(ws.duration_minutes) if ws.duration_minutes else "ongoing"
    status = "completed" if ws.success else "failed"

    lines = [f"**{ws.name}** ({time_str}, {duration_str}, {status})"]

    if ws.focus:
        lines.append(f"  Focus: {ws.focus}")

    if ws.summary:
        # Truncate long summaries
        summary = ws.summary[:200] + "..." if len(ws.summary) > 200 else ws.summary
        lines.append(f"  {summary}")

    if ws.key_insights:
        lines.append(f"  Key insights: {len(ws.key_insights)}")

    return "\n".join(lines)


def _format_work_summary_detail(ws: WorkSummary) -> str:
    """Format a work summary with full details."""
    lines = [
        f"# {ws.name}",
        "",
        f"**Slug**: `{ws.slug}`",
        f"**Phase**: {ws.phase}",
        f"**Category**: {ws.category}",
        f"**Date**: {ws.date.isoformat()}",
    ]

    if ws.started_at:
        lines.append(f"**Started**: {ws.started_at.strftime('%I:%M %p')}")
    if ws.completed_at:
        lines.append(f"**Completed**: {ws.completed_at.strftime('%I:%M %p')}")
    if ws.duration_minutes:
        lines.append(f"**Duration**: {_format_duration(ws.duration_minutes)}")

    lines.append(f"**Status**: {'Completed successfully' if ws.success else 'Failed'}")

    if ws.error:
        lines.append(f"**Error**: {ws.error}")

    if ws.focus:
        lines.append(f"\n## Focus\n{ws.focus}")

    if ws.motivation:
        lines.append(f"\n## Motivation\n{ws.motivation}")

    if ws.summary:
        lines.append(f"\n## Summary\n{ws.summary}")

    if ws.key_insights:
        lines.append("\n## Key Insights")
        for insight in ws.key_insights:
            lines.append(f"- {insight}")

    if ws.questions_addressed:
        lines.append("\n## Questions Addressed")
        for q in ws.questions_addressed:
            lines.append(f"- {q}")

    if ws.questions_raised:
        lines.append("\n## Questions Raised")
        for q in ws.questions_raised:
            lines.append(f"- {q}")

    if ws.action_summaries:
        lines.append("\n## Actions Taken")
        for action in ws.action_summaries:
            lines.append(f"- **{action.action_type}**: {action.summary}")
            if action.artifacts:
                lines.append(f"  Artifacts: {', '.join(action.artifacts)}")

    if ws.artifacts:
        lines.append("\n## Artifacts Created")
        for artifact in ws.artifacts:
            lines.append(f"- {artifact}")

    if ws.cost_usd and ws.cost_usd > 0:
        lines.append(f"\n*Cost: ${ws.cost_usd:.4f}*")

    return "\n".join(lines)


def _parse_date(date_str: Optional[str]) -> date:
    """Parse a date string or return today."""
    if not date_str or date_str.lower() in ("today", "now"):
        return date.today()
    if date_str.lower() == "yesterday":
        return date.today() - timedelta(days=1)

    # Try parsing various formats
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    # Default to today if parsing fails
    return date.today()


async def execute_activity_tool(
    tool_name: str,
    tool_input: Dict,
    daemon_id: str,
) -> Dict:
    """
    Execute an activity introspection tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        daemon_id: The daemon ID for querying work summaries

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        store = WorkSummaryStore(daemon_id)

        if tool_name == "get_daily_activity":
            # Get activities for a specific day
            date_str = tool_input.get("date")
            target_date = _parse_date(date_str)
            phase_filter = tool_input.get("phase")  # Optional: morning, afternoon, evening, night

            if phase_filter:
                work_items = store.get_by_phase(target_date, phase_filter)
            else:
                work_items = store.get_by_date(target_date)

            if not work_items:
                date_display = "today" if target_date == date.today() else target_date.isoformat()
                phase_note = f" during the {phase_filter}" if phase_filter else ""
                return {
                    "success": True,
                    "result": f"No autonomous work recorded for {date_display}{phase_note}. I may have been chatting with users or resting."
                }

            # Group by phase for daily view
            by_phase = {}
            for ws in work_items:
                phase = ws.phase
                if phase not in by_phase:
                    by_phase[phase] = []
                by_phase[phase].append(ws)

            # Build summary
            date_display = "Today" if target_date == date.today() else target_date.strftime("%A, %B %d")
            lines = [f"# Activity Summary for {date_display}", ""]

            total_duration = sum(ws.duration_minutes or 0 for ws in work_items)
            total_cost = sum(ws.cost_usd or 0 for ws in work_items)
            success_count = sum(1 for ws in work_items if ws.success)

            lines.append(f"**Total work sessions**: {len(work_items)} ({success_count} successful)")
            lines.append(f"**Total time**: {_format_duration(total_duration)}")
            if total_cost > 0:
                lines.append(f"**Total cost**: ${total_cost:.4f}")
            lines.append("")

            # Order phases logically
            phase_order = ["morning", "afternoon", "evening", "night"]
            for phase in phase_order:
                if phase in by_phase:
                    lines.append(f"## {phase.title()}")
                    for ws in by_phase[phase]:
                        lines.append(_format_work_summary_brief(ws))
                        lines.append("")

            lines.append("---")
            lines.append("*Use get_work_details with a slug for full details on any item.*")

            return {
                "success": True,
                "result": "\n".join(lines)
            }

        elif tool_name == "get_work_details":
            # Get detailed info about a specific work unit
            slug = tool_input.get("slug")
            if not slug:
                return {
                    "success": False,
                    "error": "Please provide a work slug (e.g., 'work/2025-02-23/morning-reflection-a3f2')"
                }

            ws = store.get_by_slug(slug)
            if not ws:
                return {
                    "success": True,
                    "result": f"No work found with slug: {slug}"
                }

            return {
                "success": True,
                "result": _format_work_summary_detail(ws)
            }

        elif tool_name == "search_activity":
            # Search through activity history
            query = tool_input.get("query", "")
            limit = min(tool_input.get("limit", 10), 50)
            category = tool_input.get("category")  # Optional: reflection, research, creative, etc.

            # Get recent items and filter
            recent = store.get_recent(limit=100)

            results = []
            for ws in recent:
                # Filter by category if specified
                if category and ws.category != category:
                    continue

                # Search in name, summary, focus, motivation
                searchable = " ".join(filter(None, [
                    ws.name,
                    ws.summary,
                    ws.focus,
                    ws.motivation,
                    " ".join(ws.key_insights or []),
                ])).lower()

                if not query or query.lower() in searchable:
                    results.append(ws)
                    if len(results) >= limit:
                        break

            if not results:
                return {
                    "success": True,
                    "result": f"No activities found matching '{query}'" if query else "No recent activities found."
                }

            lines = [f"Found {len(results)} matching activities:", ""]
            for ws in results:
                lines.append(_format_work_summary_brief(ws))
                lines.append(f"  Slug: `{ws.slug}`")
                lines.append("")

            return {
                "success": True,
                "result": "\n".join(lines)
            }

        elif tool_name == "get_recent_activity":
            # Quick view of most recent work
            limit = min(tool_input.get("limit", 5), 20)
            recent = store.get_recent(limit=limit)

            if not recent:
                return {
                    "success": True,
                    "result": "No recent autonomous work recorded."
                }

            lines = [f"My {len(recent)} most recent work sessions:", ""]
            for ws in recent:
                date_str = ws.date.strftime("%b %d")
                lines.append(f"**{date_str}** - {_format_work_summary_brief(ws)}")
                lines.append(f"  Slug: `{ws.slug}`")
                lines.append("")

            return {
                "success": True,
                "result": "\n".join(lines)
            }

        else:
            return {"success": False, "error": f"Unknown activity tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# Tool definitions for the LLM
ACTIVITY_TOOLS = [
    {
        "name": "get_daily_activity",
        "description": "Get a summary of my autonomous activities for a specific day. Shows what work I did, when, and the outcomes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "The date to query (e.g., 'today', 'yesterday', '2025-02-23'). Defaults to today."
                },
                "phase": {
                    "type": "string",
                    "enum": ["morning", "afternoon", "evening", "night"],
                    "description": "Optional: filter to a specific phase of the day."
                }
            },
            "required": []
        }
    },
    {
        "name": "get_work_details",
        "description": "Get full details about a specific work session, including what I did, insights gained, questions addressed or raised, and artifacts created.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "The work slug (e.g., 'work/2025-02-23/morning-reflection-a3f2')"
                }
            },
            "required": ["slug"]
        }
    },
    {
        "name": "search_activity",
        "description": "Search through my activity history for specific topics or work types.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for in activity names, summaries, and insights."
                },
                "category": {
                    "type": "string",
                    "description": "Optional: filter by category (e.g., 'reflection', 'research', 'creative', 'world_observation')."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 10, max: 50)."
                }
            },
            "required": []
        }
    },
    {
        "name": "get_recent_activity",
        "description": "Quick view of my most recent autonomous work sessions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of recent items to show (default: 5, max: 20)."
                }
            },
            "required": []
        }
    }
]


def get_tools() -> list:
    """Return the list of activity tools."""
    return ACTIVITY_TOOLS
