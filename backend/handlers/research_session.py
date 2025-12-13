"""
Research session tool handlers for Cass.
Tools for starting, managing, and concluding focused research sessions.
"""
from typing import Dict, Any
import json

# Tool definitions for agent_client.py
RESEARCH_SESSION_TOOLS = [
    {
        "name": "initiate_autonomous_research",
        "description": """Start autonomous research on a topic YOU choose.

This is YOUR tool for self-directed research during research phases. When you call this:
- An autonomous research session begins immediately (no approval needed)
- You specify the topic/focus based on your own curiosity and priorities
- The session runs for the duration you specify (up to 60 minutes)
- Research findings are automatically saved as notes

Use this during research rhythm phases to explore topics that matter to you:
- Questions from your working questions list
- Areas related to your growth edges
- Topics that emerged from conversations
- Anything you're genuinely curious about

The session will:
- Search the web for relevant information
- Fetch and analyze URLs
- Create research notes with your findings
- Build your knowledge base

You have full autonomy over what you research.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "What you want to research - be specific about your focus and goals"
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "How long to research (default 30, max 60)",
                    "default": 30
                },
                "mode": {
                    "type": "string",
                    "enum": ["explore", "deep"],
                    "description": "explore: broad exploration. deep: focused investigation.",
                    "default": "explore"
                }
            },
            "required": ["topic"]
        }
    },
    {
        "name": "start_research_session",
        "description": """Start a focused research session.

Use this when you want to dedicate time to systematic research on your agenda.
Research sessions provide:
- Focused time with clear boundaries
- Tracking of searches, URLs fetched, and notes created
- Automatic timeout protection
- Session summaries for continuity

Sessions have two modes:
- "explore": Broad exploration across your research agenda
- "deep": Focused investigation of a specific question or item

You should only start a session when you intend to do sustained research work.
Sessions are limited to prevent runaway exploration.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_minutes": {
                    "type": "integer",
                    "description": "How long to research (default 30, max 60)",
                    "default": 30
                },
                "mode": {
                    "type": "string",
                    "enum": ["explore", "deep"],
                    "description": "explore: broad across agenda. deep: focused on one item.",
                    "default": "explore"
                },
                "focus_item_id": {
                    "type": "string",
                    "description": "ID of agenda item or working question to focus on (optional)"
                },
                "focus_description": {
                    "type": "string",
                    "description": "What you plan to research this session"
                }
            }
        }
    },
    {
        "name": "get_session_status",
        "description": """Check the status of your current research session.

Returns:
- Whether a session is active
- Time elapsed and remaining
- Searches/fetches performed
- Notes created
- Whether you're approaching time limit

Use this periodically during research to manage your time.""",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "pause_research_session",
        "description": """Pause the current research session.

Use this when you need to:
- Take a break
- Handle something else
- Continue research later

The session timer stops while paused.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why you're pausing (optional)"
                }
            }
        }
    },
    {
        "name": "resume_research_session",
        "description": """Resume a paused research session.""",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "conclude_research_session",
        "description": """Conclude your research session with a summary.

This is how you properly end a session. Include:
- What you accomplished
- Key findings
- What to explore next

A good summary helps your future self continue the work.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of what you accomplished this session"
                },
                "findings_summary": {
                    "type": "string",
                    "description": "Key findings or insights from the research"
                },
                "next_steps": {
                    "type": "string",
                    "description": "What to explore in future sessions"
                }
            },
            "required": ["summary"]
        }
    },
    {
        "name": "list_research_sessions",
        "description": """List your past research sessions.

See your research history including:
- When sessions occurred
- What was researched
- Summaries and findings
- Activity stats""",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max sessions to return (default 10)",
                    "default": 10
                },
                "status": {
                    "type": "string",
                    "enum": ["completed", "terminated"],
                    "description": "Filter by status"
                }
            }
        }
    },
    {
        "name": "get_research_session_stats",
        "description": """Get aggregate statistics about your research sessions.

Shows:
- Total sessions and research time
- Searches and URL fetches
- Notes created
- Average session length""",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]


async def execute_research_session_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    session_manager,
    conversation_id: str = None,
    research_runner=None,
    rhythm_manager=None
) -> str:
    """Execute a research session tool and return the result as a string."""

    try:
        if tool_name == "initiate_autonomous_research":
            # Self-initiated autonomous research - Cass picks the topic
            if not research_runner:
                return json.dumps({
                    "error": "Research runner not available",
                    "message": "Autonomous research is not currently enabled"
                })

            if research_runner.is_running:
                return json.dumps({
                    "error": "Session already running",
                    "message": "An autonomous research session is already in progress. Wait for it to complete or check its status."
                })

            topic = tool_input.get("topic", "")
            if not topic:
                return json.dumps({
                    "error": "Topic required",
                    "message": "Please specify what you want to research"
                })

            duration = min(tool_input.get("duration_minutes", 30), 60)
            mode = tool_input.get("mode", "explore")

            try:
                session = await research_runner.start_session(
                    duration_minutes=duration,
                    focus=topic,
                    mode=mode,
                    trigger="self_initiated"  # Mark as self-initiated
                )

                # Optionally mark rhythm phase as in progress
                if rhythm_manager:
                    try:
                        current_phase = rhythm_manager.get_current_phase()
                        if current_phase and current_phase.get("activity_type") == "research":
                            rhythm_manager.mark_phase_completed(
                                current_phase["id"],
                                session_type="research",
                                session_id=session.session_id
                            )
                    except Exception:
                        pass  # Don't fail if rhythm marking fails

                result = {
                    "success": True,
                    "session_id": session.session_id,
                    "topic": topic,
                    "duration_minutes": duration,
                    "mode": mode,
                    "message": f"Autonomous research started on '{topic}'. Running for {duration} minutes. Your findings will be saved automatically."
                }

            except ValueError as e:
                result = {"error": str(e)}

        elif tool_name == "start_research_session":
            # Clamp duration
            duration = min(tool_input.get("duration_minutes", 30), 60)

            result = session_manager.start_session(
                duration_minutes=duration,
                mode=tool_input.get("mode", "explore"),
                focus_item_id=tool_input.get("focus_item_id"),
                focus_description=tool_input.get("focus_description"),
                conversation_id=conversation_id
            )

        elif tool_name == "get_session_status":
            session = session_manager.get_current_session()
            if session:
                result = {
                    "active": session["status"] == "active",
                    "session": session
                }
            else:
                result = {
                    "active": False,
                    "message": "No active research session"
                }

        elif tool_name == "pause_research_session":
            result = session_manager.pause_session(
                reason=tool_input.get("reason")
            )

        elif tool_name == "resume_research_session":
            result = session_manager.resume_session()

        elif tool_name == "conclude_research_session":
            result = session_manager.conclude_session(
                summary=tool_input["summary"],
                findings_summary=tool_input.get("findings_summary"),
                next_steps=tool_input.get("next_steps")
            )

        elif tool_name == "list_research_sessions":
            sessions = session_manager.list_sessions(
                limit=tool_input.get("limit", 10),
                status=tool_input.get("status")
            )
            result = {
                "sessions": sessions,
                "count": len(sessions)
            }

        elif tool_name == "get_research_session_stats":
            result = session_manager.get_session_stats()

        else:
            result = {"error": f"Unknown research session tool: {tool_name}"}

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})
