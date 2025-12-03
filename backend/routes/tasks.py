"""
Tasks REST API routes
Taskwarrior-style task management endpoints
"""
from fastapi import APIRouter, HTTPException
from typing import Callable

router = APIRouter(prefix="/tasks", tags=["tasks"])

# These will be set by the main app
_task_manager = None
_get_current_user_id: Callable[[], str] = None


def init_tasks_routes(task_manager, get_current_user_id: Callable[[], str]):
    """Initialize the routes with dependencies"""
    global _task_manager, _get_current_user_id
    _task_manager = task_manager
    _get_current_user_id = get_current_user_id


def _require_user():
    """Get current user or raise error"""
    user_id = _get_current_user_id()
    if not user_id:
        raise HTTPException(status_code=400, detail="No user context")
    return user_id


@router.get("")
async def list_tasks(filter: str = None, include_completed: bool = False):
    """List tasks with optional Taskwarrior-style filter"""
    user_id = _require_user()
    tasks = _task_manager.list_tasks(
        user_id,
        filter_str=filter,
        include_completed=include_completed
    )
    return {"tasks": [t.to_dict() for t in tasks]}


@router.get("/stats/summary")
async def tasks_summary():
    """Get task statistics summary"""
    user_id = _require_user()
    pending_count = _task_manager.count_pending(user_id)
    projects = _task_manager.get_projects(user_id)
    tags = _task_manager.get_tags(user_id)
    return {
        "pending_count": pending_count,
        "projects": projects,
        "tags": tags
    }


@router.get("/{task_id}")
async def get_task(task_id: str):
    """Get a specific task by ID"""
    user_id = _require_user()
    task = _task_manager.get(user_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.post("/{task_id}/complete")
async def complete_task_endpoint(task_id: str):
    """Mark a task as completed"""
    user_id = _require_user()
    task = _task_manager.complete(user_id, task_id)
    if task:
        return {"status": "completed", "task": task.to_dict()}
    else:
        raise HTTPException(status_code=404, detail="Task not found")


@router.delete("/{task_id}")
async def delete_task_endpoint(task_id: str):
    """Delete a task"""
    user_id = _require_user()
    if _task_manager.delete(user_id, task_id):
        return {"status": "deleted"}
    else:
        raise HTTPException(status_code=404, detail="Task not found")
