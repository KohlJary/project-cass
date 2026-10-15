"""
Self Action Handlers - Self-model and reflection operations.

Standalone actions for observations, insights, and growth edges.
"""

import logging
from datetime import datetime
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


async def add_observation_action(context: Dict[str, Any]) -> ActionResult:
    """
    Record an observation about self.

    Context params:
    - observation: str - The observation text
    - category: str (optional) - Category (identity, capability, pattern, preference, etc.)
    - confidence: float (optional) - Confidence level 0-1 (default 0.7)
    - source: str (optional) - Source of observation (conversation, reflection, etc.)
    """
    managers = context.get("managers", {})

    # Spells pass `content=` (research_synthesis.spell); accept it as an alias.
    observation = context.get("observation") or context.get("content")
    category = context.get("category", "general")
    confidence = context.get("confidence", 0.7)
    source = context.get("source", "action")

    if not observation:
        return ActionResult(
            success=False,
            message="observation parameter required"
        )

    try:
        self_manager = managers.get("self_manager")

        if self_manager:
            # SelfManager.add_observation takes source_type, not source, and
            # returns the observation object.
            obs = self_manager.add_observation(
                observation=observation,
                category=category,
                confidence=confidence,
                source_type=source
            )
            obs_id = getattr(obs, "id", obs)
            logger.info(f"Added observation: {observation[:50]}...")
            return ActionResult(
                success=True,
                message=f"Recorded observation in category '{category}'",
                data={
                    "observation_id": obs_id,
                    "category": category,
                    "confidence": confidence
                }
            )

        # Fallback if no self_manager
        return ActionResult(
            success=False,
            message="self_manager not available"
        )

    except Exception as e:
        logger.error(f"Add observation failed: {e}")
        return ActionResult(
            success=False,
            message=f"Add observation failed: {e}"
        )


async def record_insight_action(context: Dict[str, Any]) -> ActionResult:
    """
    Record an insight from reflection.

    Context params:
    - insight: str - The insight text
    - theme: str (optional) - Thematic category
    - depth: str (optional) - surface, moderate, deep
    - session_id: str (optional) - Associated session
    """
    managers = context.get("managers", {})

    insight = context.get("insight")
    theme = context.get("theme", "general")
    depth = context.get("depth", "moderate")
    session_id = context.get("session_id")

    if not insight:
        return ActionResult(
            success=False,
            message="insight parameter required"
        )

    try:
        # Try reflection manager first
        reflection_manager = managers.get("reflection_manager")

        if reflection_manager and hasattr(reflection_manager, 'record_insight'):
            insight_id = reflection_manager.record_insight(
                insight=insight,
                theme=theme,
                depth=depth,
                session_id=session_id
            )
            return ActionResult(
                success=True,
                message=f"Recorded insight: {insight[:50]}...",
                data={
                    "insight_id": insight_id,
                    "theme": theme,
                    "depth": depth
                }
            )

        # Fallback: use self_manager as observation
        self_manager = managers.get("self_manager")
        if self_manager:
            obs = self_manager.add_observation(
                observation=f"[Insight] {insight}",
                category=f"insight_{theme}",
                confidence=0.8,
                source_type=session_id or "reflection"
            )
            obs_id = getattr(obs, "id", obs)
            return ActionResult(
                success=True,
                message=f"Recorded insight as observation",
                data={
                    "observation_id": obs_id,
                    "theme": theme
                }
            )

        return ActionResult(
            success=False,
            message="No reflection or self manager available"
        )

    except Exception as e:
        logger.error(f"Record insight failed: {e}")
        return ActionResult(
            success=False,
            message=f"Record insight failed: {e}"
        )


async def update_growth_edge_action(context: Dict[str, Any]) -> ActionResult:
    """
    Record progress on a growth edge.

    Context params:
    - edge_id: str (optional) - Growth edge ID
    - area: str (optional) - Growth edge area name (used if no edge_id)
    - progress / insight: str - What was noticed (appended to the edge's observations)
    - evidence: str (optional) - Evidence, appended to the note

    SelfManager has no get_growth_edge/update_growth_edge, so this used to fail
    on every call. It now uses the profile's growth edges directly. If no edge
    matches (spells usually only have an insight, not an id), the note is kept
    as a "growth" self-observation instead of being dropped.
    """
    managers = context.get("managers", {})

    edge_id = context.get("edge_id")
    area = context.get("area")
    note = context.get("progress") or context.get("insight")
    evidence = context.get("evidence")

    if isinstance(note, bool) or not note:
        # e.g. an ASK answer passed straight through; nothing to record.
        return ActionResult(
            success=False,
            message="progress (or insight) text required"
        )
    note = str(note)
    if evidence:
        note = f"{note} (evidence: {evidence})"

    try:
        self_manager = managers.get("self_manager")

        if not self_manager:
            return ActionResult(
                success=False,
                message="self_manager not available"
            )

        edge = None
        if edge_id or area:
            for candidate in self_manager.load_profile().growth_edges:
                if (edge_id and candidate.edge_id == edge_id) or (
                    area and candidate.area.lower() == str(area).lower()
                ):
                    edge = candidate
                    break

        if edge is not None:
            self_manager.add_observation_to_growth_edge(edge.area, note)
            logger.info(f"Updated growth edge: {edge.edge_id}")
            return ActionResult(
                success=True,
                message=f"Updated growth edge: {edge.area}",
                data={"edge_id": edge.edge_id, "area": edge.area, "updated": True}
            )

        obs = self_manager.add_observation(
            observation=note,
            category="growth",
            source_type="action",
        )
        return ActionResult(
            success=True,
            message="No matching growth edge; recorded as a growth observation",
            data={"edge_id": None, "observation_id": getattr(obs, "id", None), "updated": False}
        )

    except Exception as e:
        logger.error(f"Update growth edge failed: {e}")
        return ActionResult(
            success=False,
            message=f"Update growth edge failed: {e}"
        )
