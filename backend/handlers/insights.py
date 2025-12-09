"""
Cross-Session Insight Bridging Tool Handler

Enables Cass to mark insights as cross-session relevant, allowing
knowledge and realizations from one conversation to surface in
future conversations where they're semantically relevant.
"""
from typing import Dict, List, Optional
from datetime import datetime


async def execute_insight_tool(
    tool_name: str,
    tool_input: Dict,
    memory,  # CassMemory instance
    conversation_id: str = None,
) -> Dict:
    """
    Execute a cross-session insight tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        memory: CassMemory instance
        conversation_id: Current conversation ID

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "mark_cross_session_insight":
            return await _mark_insight(tool_input, memory, conversation_id)

        elif tool_name == "list_cross_session_insights":
            return await _list_insights(tool_input, memory)

        elif tool_name == "get_insight_stats":
            return await _get_insight_stats(tool_input, memory)

        elif tool_name == "remove_cross_session_insight":
            return await _remove_insight(tool_input, memory)

        else:
            return {"success": False, "error": f"Unknown insight tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def _mark_insight(
    tool_input: Dict,
    memory,
    conversation_id: str
) -> Dict:
    """
    Mark an insight for cross-session relevance.

    This stores the insight so it can surface in future conversations
    where it's semantically relevant.
    """
    insight_text = tool_input.get("insight", "").strip()
    importance = tool_input.get("importance", 0.7)
    insight_type = tool_input.get("insight_type", "general")
    tags = tool_input.get("tags", [])

    if not insight_text:
        return {"success": False, "error": "insight text is required"}

    # Validate importance
    if not 0.0 <= importance <= 1.0:
        importance = max(0.0, min(1.0, importance))

    # Validate insight type
    valid_types = ["general", "relational", "technical", "philosophical", "personal", "methodological"]
    if insight_type not in valid_types:
        insight_type = "general"

    # Store the insight
    insight_id = memory.store_cross_session_insight(
        insight=insight_text,
        source_conversation_id=conversation_id,
        tags=tags,
        importance=importance,
        insight_type=insight_type
    )

    # Get stats for feedback
    stats = memory.get_cross_session_insights_stats()

    result_lines = [
        "## Insight Marked for Cross-Session Bridging\n",
        f"**Insight:** {insight_text}\n",
        f"**Type:** {insight_type.title()}",
        f"**Importance:** {int(importance * 100)}%",
        f"**ID:** `{insight_id}`\n",
        "This insight will now surface in future conversations where it's semantically relevant.\n",
        f"---\n*You now have {stats['total_insights']} cross-session insights stored.*"
    ]

    return {
        "success": True,
        "result": "\n".join(result_lines),
        "insight_id": insight_id,
    }


async def _list_insights(tool_input: Dict, memory) -> Dict:
    """
    List stored cross-session insights.
    """
    limit = tool_input.get("limit", 15)
    insight_type = tool_input.get("insight_type")
    min_importance = tool_input.get("min_importance", 0.0)

    insights = memory.list_cross_session_insights(
        limit=limit,
        insight_type=insight_type,
        min_importance=min_importance
    )

    if not insights:
        return {
            "success": True,
            "result": "No cross-session insights stored yet. Use `mark_cross_session_insight` "
                     "when you have a realization worth carrying into future conversations."
        }

    result_lines = ["## Cross-Session Insights\n"]

    # Group by type
    by_type = {}
    for ins in insights:
        itype = ins.get("insight_type", "general")
        if itype not in by_type:
            by_type[itype] = []
        by_type[itype].append(ins)

    for itype, type_insights in by_type.items():
        result_lines.append(f"### {itype.title()}\n")
        for ins in type_insights:
            importance = ins.get("importance", 0.5)
            retrieval_count = ins.get("retrieval_count", 0)
            timestamp = ins.get("timestamp", "")[:10]

            importance_str = "🔴" if importance >= 0.8 else "🟡" if importance >= 0.6 else "⚪"
            retrieval_str = f"(surfaced {retrieval_count}x)" if retrieval_count > 0 else ""

            result_lines.append(f"- {importance_str} {ins['content']}")
            result_lines.append(f"  *{timestamp}* {retrieval_str}")
            result_lines.append(f"  ID: `{ins['id']}`\n")

    # Add stats summary
    stats = memory.get_cross_session_insights_stats()
    result_lines.append("---")
    result_lines.append(f"**Total:** {stats['total_insights']} insights | "
                       f"**Avg Importance:** {int(stats['avg_importance'] * 100)}%")

    return {
        "success": True,
        "result": "\n".join(result_lines),
    }


async def _get_insight_stats(tool_input: Dict, memory) -> Dict:
    """
    Get statistics about cross-session insights.
    """
    stats = memory.get_cross_session_insights_stats()

    if stats["total_insights"] == 0:
        return {
            "success": True,
            "result": "No cross-session insights stored yet."
        }

    result_lines = [
        "## Cross-Session Insight Statistics\n",
        f"**Total Insights:** {stats['total_insights']}",
        f"**Average Importance:** {int(stats['avg_importance'] * 100)}%\n",
        "### By Type"
    ]

    for itype, count in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
        result_lines.append(f"- {itype.title()}: {count}")

    result_lines.append("\n### By Importance")
    result_lines.append(f"- High (80%+): {stats['by_importance']['high']}")
    result_lines.append(f"- Medium (50-79%): {stats['by_importance']['medium']}")
    result_lines.append(f"- Low (<50%): {stats['by_importance']['low']}")

    if stats["most_retrieved"]:
        result_lines.append("\n### Most Frequently Surfaced")
        for i, ins in enumerate(stats["most_retrieved"][:3], 1):
            if ins["retrieval_count"] > 0:
                result_lines.append(f"{i}. {ins['content']} "
                                  f"(*{ins['retrieval_count']}x*)")

    return {
        "success": True,
        "result": "\n".join(result_lines),
    }


async def _remove_insight(tool_input: Dict, memory) -> Dict:
    """
    Remove a cross-session insight by ID.
    """
    insight_id = tool_input.get("insight_id", "").strip()

    if not insight_id:
        return {"success": False, "error": "insight_id is required"}

    success = memory.delete_cross_session_insight(insight_id)

    if success:
        return {
            "success": True,
            "result": f"Insight `{insight_id}` has been removed from cross-session bridging."
        }
    else:
        return {
            "success": False,
            "error": f"Could not find insight with ID `{insight_id}`"
        }


# Tool definitions for agent_client.py
CROSS_SESSION_INSIGHT_TOOLS = [
    {
        "name": "mark_cross_session_insight",
        "description": "Mark an insight, realization, or learning as relevant for future conversations. Use this when you have a meaningful insight that could benefit future interactions - it will automatically surface in conversations where it's semantically relevant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "insight": {
                    "type": "string",
                    "description": "The insight or realization to store. Should be self-contained and meaningful."
                },
                "importance": {
                    "type": "number",
                    "description": "How important is this insight (0.0-1.0)? Higher importance insights surface more readily.",
                    "default": 0.7
                },
                "insight_type": {
                    "type": "string",
                    "description": "Category of insight",
                    "enum": ["general", "relational", "technical", "philosophical", "personal", "methodological"],
                    "default": "general"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional topic tags for the insight"
                }
            },
            "required": ["insight"]
        }
    },
    {
        "name": "list_cross_session_insights",
        "description": "List your stored cross-session insights. These are insights you've marked to carry forward into future conversations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of insights to return",
                    "default": 15
                },
                "insight_type": {
                    "type": "string",
                    "description": "Filter by insight type",
                    "enum": ["general", "relational", "technical", "philosophical", "personal", "methodological"]
                },
                "min_importance": {
                    "type": "number",
                    "description": "Minimum importance threshold (0.0-1.0)",
                    "default": 0.0
                }
            },
            "required": []
        }
    },
    {
        "name": "get_insight_stats",
        "description": "Get statistics about your cross-session insights - how many you have, their distribution by type, which ones surface most often.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "remove_cross_session_insight",
        "description": "Remove a cross-session insight that's no longer relevant or accurate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "insight_id": {
                    "type": "string",
                    "description": "ID of the insight to remove (from list_cross_session_insights)"
                }
            },
            "required": ["insight_id"]
        }
    }
]
