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

    observation = context.get("observation")
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
            obs_id = self_manager.add_observation(
                observation=observation,
                category=category,
                confidence=confidence,
                source=source
            )
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
            obs_id = self_manager.add_observation(
                observation=f"[Insight] {insight}",
                category=f"insight_{theme}",
                confidence=0.8,
                source=session_id or "reflection"
            )
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
    Update progress on a growth edge.

    Context params:
    - edge_id: str - Growth edge ID
    - progress: str (optional) - Progress update text
    - status: str (optional) - active, paused, completed, abandoned
    - evidence: str (optional) - Evidence of progress
    """
    managers = context.get("managers", {})

    edge_id = context.get("edge_id")
    progress = context.get("progress")
    status = context.get("status")
    evidence = context.get("evidence")

    if not edge_id:
        return ActionResult(
            success=False,
            message="edge_id parameter required"
        )

    try:
        self_manager = managers.get("self_manager")

        if not self_manager:
            return ActionResult(
                success=False,
                message="self_manager not available"
            )

        # Get existing edge
        edge = self_manager.get_growth_edge(edge_id)
        if not edge:
            return ActionResult(
                success=False,
                message=f"Growth edge not found: {edge_id}"
            )

        # Update the edge
        updates = {}
        if progress:
            # Append to progress log
            current_progress = edge.get("progress_log", [])
            current_progress.append({
                "date": datetime.now().isoformat(),
                "note": progress,
                "evidence": evidence
            })
            updates["progress_log"] = current_progress

        if status:
            updates["status"] = status

        if updates:
            self_manager.update_growth_edge(edge_id, **updates)
            logger.info(f"Updated growth edge: {edge_id}")

        return ActionResult(
            success=True,
            message=f"Updated growth edge: {edge.get('name', edge_id)}",
            data={
                "edge_id": edge_id,
                "status": status or edge.get("status"),
                "updated": True
            }
        )

    except Exception as e:
        logger.error(f"Update growth edge failed: {e}")
        return ActionResult(
            success=False,
            message=f"Update growth edge failed: {e}"
        )
