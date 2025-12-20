"""
State Query Tool Handler

Handles the query_state tool which allows Cass to query metrics
from registered subsystems through the unified state query interface.

Supports two modes:
1. Natural language: Cass provides an "intent" and a local LLM constructs the query
2. Structured: Cass provides explicit source/metric/time_preset parameters
"""

import logging
from typing import Any, Dict, Optional

from query_models import StateQuery, TimeRange, Aggregation
from state_bus import GlobalStateBus
from query_constructor import get_query_constructor


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
        tool_input: Tool input with intent OR source/metric/time_preset, etc.
        state_bus: The GlobalStateBus instance for executing queries

    Returns:
        Dict with success, result, and optional error
    """
    if tool_name != "query_state":
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    try:
        # Check if this is a natural language query
        if "intent" in tool_input and tool_input["intent"]:
            intent = tool_input["intent"]

            # Get relevant capabilities via semantic search
            capabilities = await state_bus.find_capabilities(intent, limit=5)
            available_sources = state_bus.list_sources()

            # Use QueryConstructor to build the query
            constructor = get_query_constructor()
            construction_result = await constructor.construct_query(
                intent=intent,
                capabilities=capabilities,
                available_sources=available_sources,
            )

            if not construction_result.success:
                return {
                    "success": False,
                    "error": f"Could not construct query: {construction_result.error}",
                    "result": f"Failed to understand query: {construction_result.error}",
                }

            query = construction_result.query
            logger.info(
                f"Constructed query from intent: source={query.source}, "
                f"metric={query.metric}, fallback={construction_result.fallback_used}"
            )
        else:
            # Structured path - build query directly from parameters
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

    # Build query - default to 'all' metric for comprehensive data
    query = StateQuery(
        source=source,
        metric=tool_input.get("metric") or "all",
        time_range=time_range,
        aggregation=aggregation,
        group_by=tool_input.get("group_by"),
        filters=tool_input.get("filters"),
    )

    return query


async def execute_discover_capabilities(
    tool_name: str,
    tool_input: Dict[str, Any],
    state_bus: GlobalStateBus
) -> Dict[str, Any]:
    """
    Execute a discover_capabilities tool call.

    Args:
        tool_name: Should be "discover_capabilities"
        tool_input: Tool input with query, limit, source_filter, tag_filter
        state_bus: The GlobalStateBus instance with capability registry

    Returns:
        Dict with success, result, and optional error
    """
    if tool_name != "discover_capabilities":
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    try:
        query = tool_input.get("query", "")
        if not query:
            return {
                "success": False,
                "error": "query is required",
                "result": "Please provide a query describing what data you're looking for.",
            }

        limit = tool_input.get("limit", 5)
        source_filter = tool_input.get("source")
        tag_filter = tool_input.get("tags")

        # Find matching capabilities
        matches = await state_bus.find_capabilities(
            query=query,
            limit=limit,
            source_filter=source_filter,
            tag_filter=tag_filter,
        )

        # Format for LLM consumption
        formatted = state_bus.format_capabilities_for_llm(matches)

        return {
            "success": True,
            "result": formatted,
            "matches": [m.to_dict() for m in matches],
        }

    except Exception as e:
        logger.error(f"Capability discovery failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "result": f"Discovery failed: {str(e)}",
        }


# Tool definition for agent_client.py
DISCOVER_CAPABILITIES_TOOL_DEFINITION = {
    "name": "discover_capabilities",
    "description": """Find what data is available to query by describing what you're looking for.

Use this tool when you want to know what metrics or data sources are available before querying.
The system will semantically match your description to registered capabilities.

Examples:
- "What data do we have about user engagement?" → Returns github:views, github:clones, github:stars
- "How much are we spending?" → Returns tokens:cost_usd
- "Repository activity metrics" → Returns github:clones, github:forks, github:views
- "Emotional state data" → Returns emotional dimensions like curiosity, contentment

After discovering capabilities, use query_state to actually retrieve the data.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language description of what data you want to find"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 5)",
                "default": 5
            },
            "source": {
                "type": "string",
                "description": "Optional: filter results to a specific source (github, tokens, emotional)"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional: filter by tags (e.g., engagement, cost, activity)"
            }
        },
        "required": ["query"]
    }
}


def get_query_state_tool_definition(state_bus: Optional[GlobalStateBus] = None) -> Dict[str, Any]:
    """
    Build query_state tool definition with dynamic source list from State Bus.

    Args:
        state_bus: Optional State Bus instance. If None, uses default sources.

    Returns:
        Tool definition dict with current available sources.
    """
    # Get available sources dynamically
    if state_bus:
        available_sources = sorted(state_bus.list_sources())
    else:
        # Fallback if no bus provided
        available_sources = ["github", "tokens", "conversations", "memory", "self", "goals"]

    # Build source descriptions
    source_descriptions = {
        "github": "Repository stars, forks, clones, views",
        "tokens": "LLM token usage and costs",
        "conversations": "Chat conversations and messages",
        "memory": "Journals, threads, questions, embeddings",
        "self": "Self-model graph nodes and edges",
        "goals": "Unified goals and capability gaps",
    }

    source_list = "\n".join([
        f"- {s}: {source_descriptions.get(s, 'Metrics and data')}"
        for s in available_sources
    ])

    return {
        "name": "query_state",
        "description": f"""Query metrics from the global state system using natural language OR structured parameters.

**Natural Language (recommended)**: Use the 'intent' field with a question:
- "how much have we spent on tokens this month?"
- "what are our GitHub star counts?"
- "show me conversation stats for today"

**Structured**: Specify source, metric, time_preset directly.

Available sources:
{source_list}

Time presets: today, yesterday, last_24h, last_7d, last_30d, this_week, this_month, all_time""",
        "input_schema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "Natural language query (recommended). Examples: 'how much spent this month?', 'GitHub repo stats'"
                },
                "source": {
                    "type": "string",
                    "enum": available_sources,
                    "description": "Which data source to query (for structured mode)"
                },
                "metric": {
                    "type": "string",
                    "description": "Specific metric to retrieve, or 'all' for comprehensive summary"
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
            "required": []
        }
    }


# Static fallback for imports that don't have state_bus context
QUERY_STATE_TOOL_DEFINITION = get_query_state_tool_definition()


async def execute_state_query_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    state_bus: GlobalStateBus
) -> Dict[str, Any]:
    """
    Unified executor for state query tools.

    Routes to the appropriate handler based on tool_name.
    """
    if tool_name == "query_state":
        return await execute_state_query(tool_name, tool_input, state_bus)
    elif tool_name == "discover_capabilities":
        return await execute_discover_capabilities(tool_name, tool_input, state_bus)
    else:
        return {"success": False, "error": f"Unknown state query tool: {tool_name}"}
