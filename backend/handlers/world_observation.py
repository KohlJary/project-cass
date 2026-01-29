"""
World observation tool handler - enables Cass to record and query world awareness.

These tools allow Cass to:
- Record observations about the external world (news, events, patterns)
- Get current world context (location, weather, time)
- Build persistent world awareness across sessions

Part of Phase 2: Active World Engagement
"""
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from self_model import SelfManager
from state_bus import GlobalStateBus

logger = logging.getLogger(__name__)


@dataclass
class WorldObservationContext:
    """Context passed to world observation tool handlers."""
    daemon_id: str
    self_manager: SelfManager
    state_bus: Optional[GlobalStateBus] = None
    world_state_source: Optional[Any] = None  # WorldStateSource instance
    user_id: Optional[str] = None


def execute_world_observation_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    daemon_id: str,
    self_manager: SelfManager,
    state_bus: Optional[GlobalStateBus] = None,
    world_state_source: Optional[Any] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute a world observation tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        daemon_id: Daemon ID
        self_manager: SelfManager instance for recording observations
        state_bus: GlobalStateBus for querying world state
        world_state_source: WorldStateSource for location data
        user_id: Optional user ID for user-specific context

    Returns:
        Tool result dict with success status and result/error
    """
    ctx = WorldObservationContext(
        daemon_id=daemon_id,
        self_manager=self_manager,
        state_bus=state_bus,
        world_state_source=world_state_source,
        user_id=user_id
    )

    handlers = {
        "record_world_observation": _handle_record_world_observation,
        "get_world_context": _handle_get_world_context,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {
            "success": False,
            "error": f"Unknown world observation tool: {tool_name}"
        }

    try:
        return handler(tool_input, ctx)
    except Exception as e:
        logger.error(f"World observation tool {tool_name} failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def _handle_record_world_observation(tool_input: Dict, ctx: WorldObservationContext) -> Dict:
    """
    Handle record_world_observation tool.

    Records an observation about the external world as a self-observation
    with category "world_awareness".
    """
    observation = tool_input.get("observation")
    if not observation:
        return {"success": False, "error": "observation is required"}

    category = tool_input.get("category", "general")
    significance = tool_input.get("significance", "notable")
    source = tool_input.get("source", "conversation")

    # Build enriched observation text
    observation_text = f"[{category}] {observation}"
    if source:
        observation_text += f" (source: {source})"

    # Map significance to confidence
    significance_to_confidence = {
        "minor": 0.5,
        "notable": 0.7,
        "significant": 0.85,
        "major": 0.95,
    }
    confidence = significance_to_confidence.get(significance, 0.7)

    # Record as self-observation with world_awareness category
    obs = ctx.self_manager.add_observation(
        observation=observation_text,
        category="world_awareness",
        confidence=confidence,
        source_type="world_observation",
        influence_source="independent"
    )

    logger.info(f"[world_observation] Recorded: {observation[:50]}... ({category}, {significance})")

    return {
        "success": True,
        "result": f"Recorded world observation:\n\n**[{category}]** {observation}\n\n*Significance: {significance}*\n\nThis observation is now part of my world awareness and will be available for future context.",
        "observation_id": obs.id
    }


def _handle_get_world_context(tool_input: Dict, ctx: WorldObservationContext) -> Dict:
    """
    Handle get_world_context tool.

    Returns current world context including location, weather, time,
    and optionally recent world observations.
    """
    include_observations = tool_input.get("include_observations", True)
    target_user_id = tool_input.get("user_id") or ctx.user_id

    result_lines = ["## Current World Context\n"]

    # Get world state from source
    if ctx.world_state_source:
        rollups = ctx.world_state_source.get_precomputed_rollups()

        # Temporal context
        result_lines.append("### Temporal")
        if rollups.get("current_date"):
            result_lines.append(f"- **Date:** {rollups['current_date']}")
        if rollups.get("time_of_day"):
            result_lines.append(f"- **Time of Day:** {rollups['time_of_day']}")
        if rollups.get("season"):
            result_lines.append(f"- **Season:** {rollups['season']}")

        # Server location and weather
        result_lines.append("\n### Environment")
        if rollups.get("server_location"):
            loc_line = f"- **Server Location:** {rollups['server_location']}"
            if rollups.get("current_weather"):
                loc_line += f" - {rollups['current_weather']}"
            result_lines.append(loc_line)

        # User location if available
        if target_user_id:
            user_loc = ctx.world_state_source.get_user_location_summary(target_user_id)
            if user_loc:
                result_lines.append(f"- **User Location:** {user_loc}")

        # Last updated
        if rollups.get("last_updated"):
            result_lines.append(f"\n*Last updated: {rollups['last_updated']}*")

    else:
        result_lines.append("*World state source not available*")

    # Recent world observations
    if include_observations:
        result_lines.append("\n### Recent World Observations")

        # Get recent world_awareness observations
        recent_obs = ctx.self_manager.get_observations_by_category(
            category="world_awareness",
            limit=5
        )

        if recent_obs:
            for obs in recent_obs:
                result_lines.append(f"- {obs.observation}")
        else:
            result_lines.append("*No recent world observations*")

    return {
        "success": True,
        "result": "\n".join(result_lines)
    }


# Tool definitions for registration
WORLD_OBSERVATION_TOOLS = [
    {
        "name": "record_world_observation",
        "description": "Record an observation about the external world - news events, patterns in the world, notable occurrences, or changes you've noticed. Use this to build world awareness that persists across sessions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "observation": {
                    "type": "string",
                    "description": "What you've observed about the world"
                },
                "category": {
                    "type": "string",
                    "description": "Type of world observation",
                    "enum": ["news", "weather_pattern", "cultural_event", "trend", "geopolitical", "technology", "science", "general"],
                    "default": "general"
                },
                "significance": {
                    "type": "string",
                    "description": "How significant this observation is",
                    "enum": ["minor", "notable", "significant", "major"],
                    "default": "notable"
                },
                "source": {
                    "type": "string",
                    "description": "Where you learned about this"
                }
            },
            "required": ["observation"]
        }
    },
    {
        "name": "get_world_context",
        "description": "Get current world context - location, weather, time of day, season, and any recent world observations. Use this to ground yourself in the present moment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_observations": {
                    "type": "boolean",
                    "description": "Whether to include recent world observations",
                    "default": True
                },
                "user_id": {
                    "type": "string",
                    "description": "Optional user ID to get their location context"
                }
            },
            "required": []
        }
    }
]
