"""
Scheduler Admin Routes - Monitor and control the unified scheduler.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional

router = APIRouter(prefix="/scheduler", tags=["scheduler"])

# Global scheduler reference (set during startup)
_scheduler = None


def set_scheduler(scheduler):
    """Set the global scheduler instance."""
    global _scheduler
    _scheduler = scheduler


def get_scheduler():
    """Get the global scheduler instance."""
    return _scheduler


@router.get("/status")
async def get_scheduler_status():
    """
    Get full scheduler status.

    Returns:
        - running state
        - idle detection state
        - system tasks with last/next run times
        - queue states (pending, running, paused)
        - budget status by category
    """
    scheduler = get_scheduler()
    if not scheduler:
        return {
            "enabled": False,
            "message": "Unified scheduler not initialized"
        }

    return {
        "enabled": True,
        **scheduler.get_status()
    }


@router.get("/budget")
async def get_budget_status():
    """
    Get detailed budget status.

    Returns spend by category, remaining amounts, daily totals.
    """
    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not available")

    return scheduler.budget.get_budget_status()


@router.get("/history")
async def get_task_history(limit: int = 50):
    """
    Get recent task execution history.

    Args:
        limit: Max entries to return (default 50)
    """
    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not available")

    return {
        "history": scheduler.get_history(limit=limit)
    }


@router.post("/pause/{category}")
async def pause_queue(category: str):
    """
    Pause a task queue.

    No new tasks will be started in this category until resumed.
    """
    from scheduler import TaskCategory

    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not available")

    try:
        cat = TaskCategory(category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category}")

    scheduler.pause_queue(cat)
    return {"status": "paused", "category": category}


@router.post("/resume/{category}")
async def resume_queue(category: str):
    """Resume a paused task queue."""
    from scheduler import TaskCategory

    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not available")

    try:
        cat = TaskCategory(category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category}")

    scheduler.resume_queue(cat)
    return {"status": "resumed", "category": category}


@router.post("/activity")
async def record_activity():
    """
    Record user activity (resets idle timer).

    Call this when user sends a message to prevent idle-only tasks
    from running during active conversations.
    """
    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not available")

    scheduler.record_activity()
    return {"status": "activity_recorded", "is_idle": scheduler.is_idle()}


@router.get("/tasks/system")
async def get_system_tasks():
    """Get all registered system tasks with their schedules."""
    from scheduler.system_tasks import get_system_task_config

    scheduler = get_scheduler()
    config = get_system_task_config()

    if not scheduler:
        return {
            "enabled": False,
            "tasks": config
        }

    # Enrich with runtime status
    tasks = {}
    for task_id, task_config in config.items():
        task_status = scheduler.system_tasks.get(task_id)
        tasks[task_id] = {
            **task_config,
            "registered": task_status is not None,
            "status": task_status.status.value if task_status else None,
            "last_run": task_status.last_run.isoformat() if task_status and task_status.last_run else None,
            "next_run": task_status.next_run.isoformat() if task_status and task_status.next_run else None,
            "run_count": task_status.run_count if task_status else 0,
        }

    return {
        "enabled": True,
        "tasks": tasks
    }


@router.post("/run/{task_id}")
async def trigger_task(task_id: str):
    """
    Manually trigger a system task.

    Bypasses scheduling - runs immediately if not already running.
    """
    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not available")

    task = scheduler.system_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    from scheduler import TaskStatus
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=409, detail=f"Task already running: {task_id}")

    # Trigger immediate execution
    import asyncio
    asyncio.create_task(scheduler._run_system_task(task))

    return {
        "status": "triggered",
        "task_id": task_id,
        "message": f"Task {task_id} triggered for immediate execution"
    }
