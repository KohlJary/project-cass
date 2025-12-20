"""
Research Action Handlers - Wiki research queue management.

These handlers wrap the research scheduler functionality.
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


async def run_batch_action(context: Dict[str, Any]) -> ActionResult:
    """
    Run a batch of wiki research tasks.

    Expects managers to contain:
    - research_scheduler
    """
    managers = context.get("managers", {})
    scheduler = managers.get("research_scheduler")
    max_tasks = context.get("max_tasks", 5)

    if not scheduler:
        return ActionResult(
            success=False,
            message="research_scheduler not available"
        )

    # Check dormancy
    if _get_active_daemon_activity_mode() == "dormant":
        return ActionResult(
            success=True,
            message="Daemon is dormant, skipping research",
            data={"skipped": True, "reason": "dormant"}
        )

    try:
        scheduler.refresh_tasks()
        report = await scheduler.run_batch(max_tasks=max_tasks)

        if report:
            logger.info(f"Research batch complete: {report.tasks_completed} tasks")
            return ActionResult(
                success=True,
                message=f"Completed {report.tasks_completed} tasks, created {len(report.pages_created)} pages",
                cost_usd=0.10 * report.tasks_completed,
                data={
                    "tasks_completed": report.tasks_completed,
                    "pages_created": report.pages_created,
                    "key_insights": report.key_insights[:3] if report.key_insights else []
                }
            )
        else:
            return ActionResult(
                success=True,
                message="No tasks to run",
                data={"tasks_completed": 0}
            )

    except Exception as e:
        logger.error(f"Research batch failed: {e}")
        return ActionResult(
            success=False,
            message=f"Research batch failed: {e}"
        )


async def run_single_action(context: Dict[str, Any]) -> ActionResult:
    """
    Run a single wiki research task from queue.

    Expects managers to contain:
    - research_scheduler
    """
    managers = context.get("managers", {})
    scheduler = managers.get("research_scheduler")

    if not scheduler:
        return ActionResult(
            success=False,
            message="research_scheduler not available"
        )

    # Check dormancy
    if _get_active_daemon_activity_mode() == "dormant":
        return ActionResult(
            success=True,
            message="Daemon is dormant, skipping research",
            data={"skipped": True, "reason": "dormant"}
        )

    try:
        stats = scheduler.queue.get_stats() if hasattr(scheduler, 'queue') else {}
        queued = stats.get("queued", 0)

        if queued == 0:
            scheduler.refresh_tasks()
            return ActionResult(
                success=True,
                message="Queue empty",
                data={"tasks_completed": 0, "queue_refreshed": True}
            )

        report = await scheduler.run_single_task()

        if report and report.tasks_completed > 0:
            page = report.pages_created[0] if report.pages_created else "task"
            logger.info(f"Research task complete: {page}")
            return ActionResult(
                success=True,
                message=f"Completed: {page}",
                cost_usd=0.10,
                data={
                    "tasks_completed": 1,
                    "page_created": page
                }
            )
        else:
            return ActionResult(
                success=True,
                message="Task skipped or failed",
                data={"tasks_completed": 0}
            )

    except Exception as e:
        logger.error(f"Research single task failed: {e}")
        return ActionResult(
            success=False,
            message=f"Research single task failed: {e}"
        )


async def refresh_queue_action(context: Dict[str, Any]) -> ActionResult:
    """
    Refresh the research task queue.

    Expects managers to contain:
    - research_scheduler
    """
    managers = context.get("managers", {})
    scheduler = managers.get("research_scheduler")

    if not scheduler:
        return ActionResult(
            success=True,
            message="research_scheduler not available",
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
                "completed": stats.get("completed", 0),
                "failed": stats.get("failed", 0)
            }
        )

    except Exception as e:
        logger.error(f"Queue refresh failed: {e}")
        return ActionResult(
            success=False,
            message=f"Queue refresh failed: {e}"
        )
