"""
Synkratos Admin Routes - Monitor and control the universal work orchestrator.

Provides unified access to:
- Task scheduling and budget monitoring
- Approval queue ("what needs my attention?")
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/scheduler", tags=["scheduler"])

# Global scheduler references (set during startup)
_scheduler = None
_autonomous_scheduler = None
_phase_queue_manager = None


def set_scheduler(scheduler):
    """Set the global Synkratos scheduler instance."""
    global _scheduler
    _scheduler = scheduler


def get_scheduler():
    """Get the global Synkratos scheduler instance."""
    return _scheduler


def set_autonomous_scheduler(scheduler):
    """Set the global autonomous scheduler instance."""
    global _autonomous_scheduler
    _autonomous_scheduler = scheduler


def get_autonomous_scheduler():
    """Get the global autonomous scheduler instance."""
    return _autonomous_scheduler


def set_phase_queue_manager(manager):
    """Set the global phase queue manager instance."""
    global _phase_queue_manager
    _phase_queue_manager = manager


def get_phase_queue_manager():
    """Get the global phase queue manager instance."""
    return _phase_queue_manager


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
            "message": "Synkratos not initialized"
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


# ============== Approval Queue Endpoints ==============


class ApproveRequest(BaseModel):
    approved_by: str = "admin"


class RejectRequest(BaseModel):
    rejected_by: str = "admin"
    reason: str = ""


@router.get("/approvals")
async def get_pending_approvals(type: Optional[str] = None):
    """
    Get all pending approvals across all subsystems.

    This is Synkratos's unified "what needs my attention?" view.

    Args:
        type: Optional filter by approval type (goal, research, action, user)

    Returns:
        List of pending approval items sorted by priority
    """
    from scheduler import ApprovalType

    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Synkratos not available")

    approval_type = None
    if type:
        try:
            approval_type = ApprovalType(type)
        except ValueError:
            valid_types = [t.value for t in ApprovalType]
            raise HTTPException(
                status_code=400,
                detail=f"Unknown approval type: {type}. Valid types: {valid_types}"
            )

    approvals = scheduler.get_pending_approvals(approval_type)

    return {
        "approvals": [
            {
                "approval_id": a.approval_id,
                "type": a.approval_type.value,
                "title": a.title,
                "description": a.description,
                "source_id": a.source_id,
                "created_at": a.created_at.isoformat() if hasattr(a.created_at, 'isoformat') else a.created_at,
                "created_by": a.created_by,
                "priority": a.priority.value,
                "source_data": a.source_data,
            }
            for a in approvals
        ],
        "count": len(approvals),
        "counts_by_type": scheduler.get_approval_counts(),
    }


@router.get("/approvals/counts")
async def get_approval_counts():
    """Get count of pending approvals by type."""
    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Synkratos not available")

    return scheduler.get_approval_counts()


@router.post("/approvals/{approval_type}/{source_id}/approve")
async def approve_item(
    approval_type: str,
    source_id: str,
    request: ApproveRequest,
):
    """
    Approve an item through the unified interface.

    Args:
        approval_type: Type of approval (goal, research, action, user)
        source_id: ID of the item in its source system
        request: Approval details
    """
    from scheduler import ApprovalType

    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Synkratos not available")

    try:
        atype = ApprovalType(approval_type)
    except ValueError:
        valid_types = [t.value for t in ApprovalType]
        raise HTTPException(
            status_code=400,
            detail=f"Unknown approval type: {approval_type}. Valid types: {valid_types}"
        )

    result = await scheduler.approve_item(atype, source_id, request.approved_by)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Approval failed"))

    return result


@router.post("/approvals/{approval_type}/{source_id}/reject")
async def reject_item(
    approval_type: str,
    source_id: str,
    request: RejectRequest,
):
    """
    Reject an item through the unified interface.

    Args:
        approval_type: Type of approval (goal, research, action, user)
        source_id: ID of the item in its source system
        request: Rejection details including reason
    """
    from scheduler import ApprovalType

    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Synkratos not available")

    try:
        atype = ApprovalType(approval_type)
    except ValueError:
        valid_types = [t.value for t in ApprovalType]
        raise HTTPException(
            status_code=400,
            detail=f"Unknown approval type: {approval_type}. Valid types: {valid_types}"
        )

    result = await scheduler.reject_item(atype, source_id, request.rejected_by, request.reason)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Rejection failed"))

    return result
