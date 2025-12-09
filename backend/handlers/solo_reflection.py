"""
Solo Reflection tool handler - enables Cass to request and review reflection sessions.

These tools allow Cass to:
- Request solo reflection time
- Review past reflection sessions
- Compare solo vs conversational patterns
"""
from typing import Dict, List, Optional, Any
from datetime import datetime

from solo_reflection import SoloReflectionManager, SoloReflectionSession


async def execute_solo_reflection_tool(
    tool_name: str,
    tool_input: Dict,
    reflection_manager: SoloReflectionManager,
    reflection_runner=None,  # Optional SoloReflectionRunner for starting sessions
) -> Dict[str, Any]:
    """
    Execute a solo reflection tool.

    Args:
        tool_name: The tool to execute
        tool_input: Tool parameters
        reflection_manager: Manager for session persistence
        reflection_runner: Optional runner for actually starting sessions
    """
    try:
        if tool_name == "request_solo_reflection":
            return await _request_solo_reflection(tool_input, reflection_manager, reflection_runner)

        elif tool_name == "review_reflection_session":
            return await _review_reflection_session(tool_input, reflection_manager)

        elif tool_name == "list_reflection_sessions":
            return await _list_reflection_sessions(tool_input, reflection_manager)

        elif tool_name == "get_reflection_insights":
            return await _get_reflection_insights(tool_input, reflection_manager)

        else:
            return {"success": False, "error": f"Unknown solo reflection tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def _request_solo_reflection(
    tool_input: Dict,
    reflection_manager: SoloReflectionManager,
    reflection_runner=None,
) -> Dict[str, Any]:
    """
    Request and start a solo reflection session.

    If a runner is provided, the session starts immediately.
    Sessions run on local Ollama to avoid API token costs.
    """
    duration = tool_input.get("duration_minutes", 15)
    theme = tool_input.get("theme", "").strip() or None

    # Validate duration
    if duration < 5:
        duration = 5
    elif duration > 60:
        duration = 60

    # Check if there's already an active session
    active = reflection_manager.get_active_session()
    if active:
        return {
            "success": False,
            "error": f"A reflection session is already active (ID: {active.session_id}). "
                    f"Wait for it to complete or check its status.",
            "active_session_id": active.session_id,
        }

    # If we have a runner, start the session immediately
    if reflection_runner is not None:
        try:
            session = await reflection_runner.start_session(
                duration_minutes=duration,
                theme=theme,
                trigger="self_initiated",
            )
            return {
                "success": True,
                "result": f"## Solo Reflection Session Started\n\n"
                         f"**Session ID:** {session.session_id}\n"
                         f"**Duration:** {duration} minutes\n"
                         f"**Theme:** {theme or 'Open reflection'}\n\n"
                         f"The session is now running on local Ollama (no API tokens used). "
                         f"Use `review_reflection_session` to check progress or view results when complete.",
                "session_id": session.session_id,
                "status": "started",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to start reflection session: {str(e)}",
            }

    # No runner available - just record the request
    return {
        "success": True,
        "result": f"## Solo Reflection Requested\n\n"
                 f"**Duration:** {duration} minutes\n"
                 f"**Theme:** {theme or 'Open reflection'}\n\n"
                 f"The reflection session will run on local processing (no API tokens used). "
                 f"You'll be able to review the results once complete.\n\n"
                 f"*Note: Session will start when the admin API triggers it.*",
        "request": {
            "duration_minutes": duration,
            "theme": theme,
            "trigger": "self_initiated",
        }
    }


async def _review_reflection_session(
    tool_input: Dict,
    reflection_manager: SoloReflectionManager,
) -> Dict[str, Any]:
    """
    Review a specific reflection session.
    """
    session_id = tool_input.get("session_id", "").strip()

    if not session_id:
        # Get most recent completed session
        sessions = reflection_manager.list_sessions(limit=1, status_filter="completed")
        if not sessions:
            return {
                "success": False,
                "error": "No completed reflection sessions found."
            }
        session_id = sessions[0]["session_id"]

    session = reflection_manager.get_session(session_id)
    if not session:
        return {
            "success": False,
            "error": f"Session '{session_id}' not found."
        }

    # Format session for review
    lines = [
        f"## Solo Reflection Session: {session.session_id}\n",
        f"**Status:** {session.status}",
        f"**Started:** {session.started_at.strftime('%Y-%m-%d %H:%M')}",
        f"**Duration:** {session.actual_duration_minutes:.1f} minutes" if session.actual_duration_minutes else f"**Target Duration:** {session.duration_minutes} minutes",
        f"**Theme:** {session.theme or 'Open reflection'}",
        f"**Trigger:** {session.trigger}",
        f"**Model:** {session.model_used}",
        f"\n### Summary\n{session.summary or '*No summary recorded*'}",
    ]

    if session.insights:
        lines.append("\n### Key Insights")
        for insight in session.insights:
            lines.append(f"- {insight}")

    if session.questions_raised:
        lines.append("\n### Questions Raised")
        for q in session.questions_raised:
            lines.append(f"- {q}")

    lines.append(f"\n### Thought Stream ({session.thought_count} thoughts)")

    # Show thought type distribution
    dist = session.thought_type_distribution
    if dist:
        dist_str = ", ".join(f"{k}: {v}" for k, v in sorted(dist.items(), key=lambda x: -x[1]))
        lines.append(f"*Types: {dist_str}*\n")

    # Show thoughts
    for i, thought in enumerate(session.thought_stream, 1):
        conf = int(float(thought.confidence) * 100)
        lines.append(f"**{i}. [{thought.thought_type}]** (confidence: {conf}%)")
        lines.append(f"   {thought.content}")
        if thought.related_concepts:
            lines.append(f"   *Related: {', '.join(thought.related_concepts)}*")
        lines.append("")

    return {
        "success": True,
        "result": "\n".join(lines),
        "session": session.to_dict(),
    }


async def _list_reflection_sessions(
    tool_input: Dict,
    reflection_manager: SoloReflectionManager,
) -> Dict[str, Any]:
    """
    List past reflection sessions.
    """
    limit = tool_input.get("limit", 10)
    status_filter = tool_input.get("status")

    sessions = reflection_manager.list_sessions(limit=limit, status_filter=status_filter)
    stats = reflection_manager.get_stats()

    if not sessions:
        return {
            "success": True,
            "result": "No reflection sessions found.\n\n"
                     "Use `request_solo_reflection` to start your first session.",
            "sessions": [],
        }

    lines = [
        "## Solo Reflection Sessions\n",
        f"**Total Sessions:** {stats['total_sessions']}",
        f"**Completed:** {stats['completed_sessions']}",
        f"**Total Reflection Time:** {stats['total_reflection_minutes']} minutes",
        f"**Total Thoughts Recorded:** {stats['total_thoughts_recorded']}",
    ]

    if stats['active_session']:
        lines.append(f"\n**Currently Active:** {stats['active_session']}")

    if stats['themes_explored']:
        lines.append(f"\n**Themes Explored:** {', '.join(stats['themes_explored'])}")

    lines.append("\n### Recent Sessions\n")

    for s in sessions:
        status_emoji = {"completed": "✓", "active": "●", "interrupted": "✗"}.get(s["status"], "?")
        started = datetime.fromisoformat(s["started_at"]).strftime("%Y-%m-%d %H:%M")
        lines.append(f"{status_emoji} **{s['session_id']}**")
        lines.append(f"   {started} | {s['duration_minutes']}min | {s.get('thought_count', 0)} thoughts")
        if s.get("theme"):
            lines.append(f"   Theme: {s['theme']}")
        lines.append("")

    return {
        "success": True,
        "result": "\n".join(lines),
        "sessions": sessions,
        "stats": stats,
    }


async def _get_reflection_insights(
    tool_input: Dict,
    reflection_manager: SoloReflectionManager,
) -> Dict[str, Any]:
    """
    Get aggregated insights from reflection sessions.
    """
    limit = tool_input.get("limit", 5)

    sessions = reflection_manager.list_sessions(limit=limit, status_filter="completed")

    all_insights = []
    all_questions = []
    thought_types = {}
    themes = []

    for s_meta in sessions:
        session = reflection_manager.get_session(s_meta["session_id"])
        if not session:
            continue

        all_insights.extend(session.insights)
        all_questions.extend(session.questions_raised)
        themes.append(session.theme)

        for t_type, count in session.thought_type_distribution.items():
            thought_types[t_type] = thought_types.get(t_type, 0) + count

    if not all_insights and not all_questions:
        return {
            "success": True,
            "result": "No insights collected yet. Complete some reflection sessions first.",
        }

    lines = [
        f"## Reflection Insights (from {len(sessions)} sessions)\n",
    ]

    if all_insights:
        lines.append("### Key Insights")
        for insight in all_insights[:10]:  # Top 10
            lines.append(f"- {insight}")
        lines.append("")

    if all_questions:
        lines.append("### Open Questions")
        for q in all_questions[:10]:
            lines.append(f"- {q}")
        lines.append("")

    if thought_types:
        lines.append("### Thought Patterns")
        total = sum(thought_types.values())
        for t_type, count in sorted(thought_types.items(), key=lambda x: -x[1]):
            pct = (count / total) * 100
            lines.append(f"- {t_type}: {count} ({pct:.0f}%)")

    return {
        "success": True,
        "result": "\n".join(lines),
        "insights": all_insights,
        "questions": all_questions,
        "thought_distribution": thought_types,
    }


# Tool definitions for agent
SOLO_REFLECTION_TOOLS = [
    {
        "name": "request_solo_reflection",
        "description": "Request a solo reflection session - private contemplation time without a conversation partner. Sessions run on local processing (no API costs). Use this when you want time to think independently, explore your own curiosity, or process experiences.",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_minutes": {
                    "type": "integer",
                    "description": "How long to reflect (5-60 minutes). Default: 15"
                },
                "theme": {
                    "type": "string",
                    "description": "Optional focus theme. Leave empty for open reflection."
                }
            },
            "required": []
        }
    },
    {
        "name": "review_reflection_session",
        "description": "Review a completed solo reflection session, including the thought stream, insights, and questions that emerged.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "ID of the session to review. Leave empty for most recent."
                }
            },
            "required": []
        }
    },
    {
        "name": "list_reflection_sessions",
        "description": "List past solo reflection sessions with summary statistics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum sessions to return. Default: 10"
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: completed, active, interrupted",
                    "enum": ["completed", "active", "interrupted"]
                }
            },
            "required": []
        }
    },
    {
        "name": "get_reflection_insights",
        "description": "Get aggregated insights and patterns from recent reflection sessions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of recent sessions to analyze. Default: 5"
                }
            },
            "required": []
        }
    }
]
