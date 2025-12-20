"""
System Action Handlers - Low-level system maintenance actions.
"""

import logging
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


def _get_active_daemon_activity_mode() -> str:
    """Get the activity_mode of the active daemon."""
    try:
        from database import get_db
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT activity_mode FROM daemons WHERE status = 'active' LIMIT 1"
            )
            row = cursor.fetchone()
            return row["activity_mode"] if row and row["activity_mode"] else "active"
    except Exception:
        return "active"


async def github_metrics_action(context: Dict[str, Any]) -> ActionResult:
    """
    Fetch GitHub metrics.

    Expects managers to contain:
    - github_metrics_manager
    """
    managers = context.get("managers", {})
    github_manager = managers.get("github_metrics_manager")

    if not github_manager:
        return ActionResult(
            success=False,
            message="github_metrics_manager not available"
        )

    try:
        await github_manager.refresh_metrics()
        logger.info("GitHub metrics refreshed")

        return ActionResult(
            success=True,
            message="GitHub metrics refreshed",
            cost_usd=0.0,
            data={"refreshed": True}
        )

    except Exception as e:
        logger.error(f"GitHub metrics failed: {e}")
        return ActionResult(
            success=False,
            message=f"GitHub metrics failed: {e}"
        )


async def rhythm_phase_action(context: Dict[str, Any]) -> ActionResult:
    """
    Check current rhythm phase and dispatch appropriate session action.

    This is a meta-action that checks rhythm state and may trigger
    other actions. Returns info about what phase was found and what
    action (if any) should be dispatched.

    Expects managers to contain:
    - rhythm_manager
    """
    managers = context.get("managers", {})
    rhythm_manager = managers.get("rhythm_manager")

    if not rhythm_manager:
        return ActionResult(
            success=False,
            message="rhythm_manager not available"
        )

    # Check dormancy
    if _get_active_daemon_activity_mode() == "dormant":
        return ActionResult(
            success=True,
            message="Daemon is dormant",
            data={"skipped": True, "reason": "dormant"}
        )

    try:
        status = rhythm_manager.get_rhythm_status()
        current_phase = status.get("current_phase")

        if not current_phase:
            return ActionResult(
                success=True,
                message="No active rhythm phase",
                data={"current_phase": None, "dispatch_action": None}
            )

        # Find phase config
        phase_config = None
        for phase in status.get("phases", []):
            if phase.get("name") == current_phase:
                phase_config = phase
                break

        if not phase_config:
            return ActionResult(
                success=True,
                message=f"No config for phase: {current_phase}",
                data={"current_phase": current_phase, "dispatch_action": None}
            )

        phase_status = phase_config.get("status")
        activity_type = phase_config.get("activity_type")

        if phase_status != "pending":
            return ActionResult(
                success=True,
                message=f"Phase {current_phase} is {phase_status}",
                data={
                    "current_phase": current_phase,
                    "phase_status": phase_status,
                    "dispatch_action": None
                }
            )

        # Map activity type to action ID
        effective_type = "research" if activity_type == "any" else activity_type
        if effective_type == "creative_output":
            effective_type = "creative"

        action_id = f"session.{effective_type}"

        return ActionResult(
            success=True,
            message=f"Phase {current_phase} ready, dispatch {action_id}",
            data={
                "current_phase": current_phase,
                "activity_type": activity_type,
                "effective_type": effective_type,
                "dispatch_action": action_id,
                "phase_id": phase_config.get("id"),
                "window": phase_config.get("window")
            }
        )

    except Exception as e:
        logger.error(f"Rhythm phase check failed: {e}")
        return ActionResult(
            success=False,
            message=f"Rhythm phase check failed: {e}"
        )


async def queue_maintenance_action(context: Dict[str, Any]) -> ActionResult:
    """
    Refresh research queue and prune stale items.

    Expects managers to contain:
    - research_scheduler
    """
    managers = context.get("managers", {})
    scheduler = managers.get("research_scheduler")

    if not scheduler:
        return ActionResult(
            success=True,
            message="Research scheduler not available",
            data={"skipped": True}
        )

    try:
        scheduler.refresh_tasks()
        stats = scheduler.queue.get_stats() if hasattr(scheduler, 'queue') else {}

        return ActionResult(
            success=True,
            message="Queue refreshed",
            cost_usd=0.0,
            data={
                "queued": stats.get("queued", 0),
                "completed": stats.get("completed", 0)
            }
        )

    except Exception as e:
        logger.error(f"Queue maintenance failed: {e}")
        return ActionResult(
            success=False,
            message=f"Queue maintenance failed: {e}"
        )
