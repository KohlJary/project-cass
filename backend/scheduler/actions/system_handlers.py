"""
System Action Handlers - Low-level system maintenance actions.
"""

import logging
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


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
