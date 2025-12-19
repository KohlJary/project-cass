"""
State Query Tool Handler

Handles the query_state tool which allows Cass to query metrics
from registered subsystems through the unified state query interface.
"""

import logging
from typing import Any, Dict, Optional

from query_models import StateQuery, TimeRange, Aggregation
from state_bus import GlobalStateBus


logger = logging.getLogger(__name__)


async def execute_state_query(
    tool_name: str,
    tool_input: Dict[str, Any],
    state_bus: GlobalStateBus
) -> Dict[str, Any]:
    """
    Execute a state query tool call.

    Args:
        tool_name: Should be "query_state"
        tool_input: Tool input with source, metric, time_preset, etc.
        state_bus: The GlobalStateBus instance for executing queries

    Returns:
        Dict with success, result, and optional error
    """
    if tool_name != "query_state":
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    try:
        # Build the StateQuery from tool input
        query = _build_query_from_input(tool_input)

        # Execute the query
        result = await state_bus.query(query)

        # Format for LLM consumption
        formatted = result.format_for_llm()

        return {
            "success": True,
            "result": formatted,
            "data": result.to_dict() if result.data else None,
        }

    except Exception as e:
        logger.error(f"State query failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "result": f"Query failed: {str(e)}",
        }


def _build_query_from_input(tool_input: Dict[str, Any]) -> StateQuery:
    """
    Build a StateQuery from tool input parameters.

    Args:
        tool_input: Dict with source, metric, time_preset, aggregation, group_by, filters

    Returns:
        StateQuery instance
    """
    source = tool_input.get("source")
    if not source:
        raise ValueError("source is required")

    # Build TimeRange
    time_range = None
    if tool_input.get("time_preset"):
        time_range = TimeRange(preset=tool_input["time_preset"])

    # Build Aggregation
    aggregation = None
    if tool_input.get("aggregation"):
        aggregation = Aggregation(function=tool_input["aggregation"])

    # Build query
    query = StateQuery(
        source=source,
        metric=tool_input.get("metric"),
        time_range=time_range,
        aggregation=aggregation,
        group_by=tool_input.get("group_by"),
        filters=tool_input.get("filters"),
    )

    return query


# Tool definition for agent_client.py
QUERY_STATE_TOOL_DEFINITION = {
    "name": "query_state",
    "description": """Query metrics from the global state system.

Use this tool to get information about:
- github: Repository stars, forks, clones, views for tracked repos
- tokens: LLM token usage and costs (today, this week, etc.)
- emotional: Current emotional state dimensions

Time presets: today, yesterday, last_24h, last_7d, last_30d, this_week, this_month, all_time

Examples:
- Stars gained this week: source=github, metric=stars_gained, time_preset=last_7d
- Token cost today: source=tokens, metric=cost_usd, time_preset=today
- Daily clone trends: source=github, metric=clones, group_by=day
- Current curiosity level: source=emotional, metric=curiosity""",
    "input_schema": {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "enum": ["github", "tokens", "emotional"],
                "description": "Which data source to query"
            },
            "metric": {
                "type": "string",
                "description": "Specific metric to retrieve (e.g., stars, cost_usd, curiosity)"
            },
            "time_preset": {
                "type": "string",
                "enum": ["today", "yesterday", "last_24h", "last_7d", "last_30d", "this_week", "this_month", "all_time"],
                "description": "Time range preset"
            },
            "aggregation": {
                "type": "string",
                "enum": ["sum", "avg", "count", "max", "min", "latest"],
                "description": "How to aggregate values (default: latest)"
            },
            "group_by": {
                "type": "string",
                "enum": ["day", "hour", "week", "repo", "provider", "category"],
                "description": "Group results by this dimension for time series or breakdowns"
            },
            "filters": {
                "type": "object",
                "description": "Source-specific filters (e.g., {\"repo\": \"KohlJary/Temple-Codex\"})"
            }
        },
        "required": ["source"]
    }
}
