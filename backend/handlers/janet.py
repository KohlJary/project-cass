"""
Janet Tool Handlers

Handles tool calls for summoning Janet and providing feedback.
"""

import logging
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from state_bus import GlobalStateBus

logger = logging.getLogger(__name__)


async def execute_janet_tool(
    tool_name: str,
    tool_input: Dict,
    daemon_id: str = None,
    state_bus: Optional["GlobalStateBus"] = None,
    **kwargs
) -> Dict:
    """
    Execute a Janet tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        daemon_id: The daemon ID (Cass's ID)
        state_bus: Optional state bus for omniscience queries
        **kwargs: Additional context (ignored)

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "summon_janet":
            result = await handle_summon_janet(tool_input, daemon_id, state_bus=state_bus)
            return {"success": True, "result": result}

        elif tool_name == "janet_feedback":
            result = await handle_janet_feedback(tool_input, daemon_id)
            return {"success": True, "result": result}

        elif tool_name == "janet_stats":
            result = await handle_janet_stats(tool_input, daemon_id)
            return {"success": True, "result": result}

        else:
            return {"success": False, "error": f"Unknown Janet tool: {tool_name}"}

    except Exception as e:
        logger.error(f"Janet tool error: {e}")
        return {"success": False, "error": str(e)}


async def handle_summon_janet(
    params: Dict[str, Any],
    daemon_id: str,
    state_bus: Optional["GlobalStateBus"] = None,
    **kwargs
) -> str:
    """
    Handle the summon_janet tool call.

    Args:
        params: Tool parameters including 'task' and optionally 'context'
        daemon_id: The daemon ID (Cass's ID)
        state_bus: Optional state bus for omniscience queries

    Returns:
        Janet's response as a string
    """
    from janet import summon_janet

    task = params.get("task", "")
    context = params.get("context", "")

    if not task:
        return "Error: No task provided for Janet."

    try:
        result = await summon_janet(daemon_id, task, context, state_bus=state_bus)

        if result.success:
            # Format response with metadata
            response = f"""**Janet's Response:**

{result.content}

---
*Task completed in {result.duration_seconds:.2f}s | Interaction ID: {result.interaction_id}*
"""
            return response
        else:
            return f"Janet encountered an error: {result.error}"

    except Exception as e:
        logger.error(f"Error summoning Janet: {e}")
        return f"Error summoning Janet: {str(e)}"


async def handle_janet_feedback(
    params: Dict[str, Any],
    daemon_id: str,
    **kwargs
) -> str:
    """
    Handle feedback on a Janet result.

    Args:
        params: Tool parameters including 'interaction_id' and 'feedback'
        daemon_id: The daemon ID

    Returns:
        Confirmation message
    """
    from janet import get_janet

    interaction_id = params.get("interaction_id", "")
    feedback = params.get("feedback", "")

    if not interaction_id or not feedback:
        return "Error: Both interaction_id and feedback are required."

    try:
        janet = get_janet(daemon_id)
        janet.provide_feedback(interaction_id, feedback)
        return f"Feedback recorded for interaction {interaction_id}. Janet will learn from this."

    except Exception as e:
        logger.error(f"Error providing Janet feedback: {e}")
        return f"Error providing feedback: {str(e)}"


async def handle_janet_stats(
    params: Dict[str, Any],
    daemon_id: str,
    **kwargs
) -> str:
    """
    Get Janet's stats - interactions, preferences, quirks.

    Args:
        params: Tool parameters (none required)
        daemon_id: The daemon ID

    Returns:
        Stats summary
    """
    from janet import get_janet

    try:
        janet = get_janet(daemon_id)
        stats = janet.get_stats()

        return f"""**Janet's Stats:**

- Total interactions: {stats['total_interactions']}
- Learned preferences: {stats['learned_preferences']}
- Developed quirks: {stats['developed_quirks']}
"""

    except Exception as e:
        logger.error(f"Error getting Janet stats: {e}")
        return f"Error getting Janet stats: {str(e)}"


# Tool definitions for agent_client.py
JANET_TOOLS = [
    {
        "name": "summon_janet",
        "description": """Summon Janet, your research and retrieval assistant. Janet can help with:
- Finding specific information or facts
- Searching for data
- Compiling and summarizing research
- Quick lookups

Janet is straightforward, competent, and remembers your preferences over time. She handles the retrieval work so you can focus on relationship and thinking.

Use this when you need something found or looked up, not when you're designing what to research (that's your domain).

After receiving Janet's response, you can provide feedback using janet_feedback to help her learn your preferences.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "What you want Janet to do. Be specific about what information you need."
                },
                "context": {
                    "type": "string",
                    "description": "Optional additional context to help Janet understand your request better."
                }
            },
            "required": ["task"]
        }
    },
    {
        "name": "janet_feedback",
        "description": "Provide feedback on a Janet result to help her learn your preferences. Use this after summon_janet if the result was particularly good, off-target, too long, too short, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "interaction_id": {
                    "type": "string",
                    "description": "The interaction ID from Janet's response."
                },
                "feedback": {
                    "type": "string",
                    "description": "Your feedback on the result. Examples: 'too verbose', 'exactly what I needed', 'missed the point', 'good format'."
                }
            },
            "required": ["interaction_id", "feedback"]
        }
    },
    {
        "name": "janet_stats",
        "description": "See Janet's stats - how many interactions, learned preferences, and developed quirks. Use this to check on Janet's development over time.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]
