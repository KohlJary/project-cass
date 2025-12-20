"""
Admin API - Unified Goals Routes
Provides endpoints for viewing, approving, and managing Cass's goals.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Dict, List
from pydantic import BaseModel

from .auth import require_admin
from unified_goals import (
    UnifiedGoalManager,
    GoalType,
    GoalStatus,
    AutonomyTier,
    GapType,
)

router = APIRouter(prefix="/goals", tags=["admin-goals"])

# Module-level manager reference
_goal_manager: Optional[UnifiedGoalManager] = None


def init_goal_manager(manager: UnifiedGoalManager = None):
    """Initialize the goal manager."""
    global _goal_manager
    if manager:
        _goal_manager = manager
    else:
        _goal_manager = UnifiedGoalManager()


def get_goal_manager() -> UnifiedGoalManager:
    """Get or create goal manager."""
    global _goal_manager
    if _goal_manager is None:
        _goal_manager = UnifiedGoalManager()
    return _goal_manager


# ============== Pydantic Models ==============

class CreateGoalRequest(BaseModel):
    title: str
    goal_type: str = GoalType.WORK.value
    description: Optional[str] = None
    parent_id: Optional[str] = None
    project_id: Optional[str] = None
    priority: str = "P2"
    urgency: str = "when_convenient"
    assigned_to: Optional[str] = None
    completion_criteria: Optional[List[str]] = None
    created_by: str = "user"


class UpdateGoalRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    urgency: Optional[str] = None
    assigned_to: Optional[str] = None
    completion_criteria: Optional[List[str]] = None


class ApproveGoalRequest(BaseModel):
    approved_by: str = "admin"


class RejectGoalRequest(BaseModel):
    reason: str


class AddCapabilityGapRequest(BaseModel):
    capability: str
    gap_type: str
    goal_id: Optional[str] = None
    description: Optional[str] = None
    urgency: str = "low"


class ResolveGapRequest(BaseModel):
    resolution: str


class AddProgressRequest(BaseModel):
    note: str
    details: Optional[Dict] = None


class CompleteGoalRequest(BaseModel):
    outcome_summary: Optional[str] = None


class AbandonGoalRequest(BaseModel):
    reason: Optional[str] = None


class AddGoalLinkRequest(BaseModel):
    target_id: str
    link_type: str


# ============== Goal Endpoints ==============

@router.get("")
async def list_goals(
    status: Optional[str] = Query(None, description="Filter by status"),
    goal_type: Optional[str] = Query(None, description="Filter by goal type"),
    created_by: Optional[str] = Query(None, description="Filter by creator"),
    assigned_to: Optional[str] = Query(None, description="Filter by assignee"),
    autonomy_tier: Optional[str] = Query(None, description="Filter by autonomy tier"),
    project_id: Optional[str] = Query(None, description="Filter by project"),
    limit: int = Query(100, le=500),
    admin: Dict = Depends(require_admin)
):
    """List goals with optional filters."""
    manager = get_goal_manager()
    goals = manager.list_goals(
        status=status,
        goal_type=goal_type,
        created_by=created_by,
        assigned_to=assigned_to,
        autonomy_tier=autonomy_tier,
        project_id=project_id,
        limit=limit,
    )
    return {
        "goals": [g.to_dict() for g in goals],
        "count": len(goals),
    }


@router.get("/pending")
async def get_pending_approval(admin: Dict = Depends(require_admin)):
    """Get goals waiting for approval."""
    manager = get_goal_manager()
    goals = manager.get_pending_approval()
    return {
        "goals": [g.to_dict() for g in goals],
        "count": len(goals),
    }


@router.get("/active")
async def get_active_goals(admin: Dict = Depends(require_admin)):
    """Get currently active goals."""
    manager = get_goal_manager()
    goals = manager.get_active_goals()
    return {
        "goals": [g.to_dict() for g in goals],
        "count": len(goals),
    }


@router.get("/blocked")
async def get_blocked_goals(admin: Dict = Depends(require_admin)):
    """Get blocked goals."""
    manager = get_goal_manager()
    goals = manager.get_blocked_goals()
    return {
        "goals": [g.to_dict() for g in goals],
        "count": len(goals),
    }


@router.get("/stats")
async def get_goal_stats(admin: Dict = Depends(require_admin)):
    """Get goal statistics."""
    manager = get_goal_manager()
    return manager.get_stats()


@router.get("/enums")
async def get_goal_enums(admin: Dict = Depends(require_admin)):
    """Get available enum values for goal fields."""
    return {
        "goal_types": [e.value for e in GoalType],
        "goal_statuses": [e.value for e in GoalStatus],
        "autonomy_tiers": [e.value for e in AutonomyTier],
        "gap_types": [e.value for e in GapType],
    }


# ============== Capability Gaps Endpoints ==============
# (Must come before /{goal_id} to avoid route conflicts)

@router.get("/gaps")
async def list_capability_gaps(
    goal_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    gap_type: Optional[str] = Query(None),
    admin: Dict = Depends(require_admin)
):
    """List capability gaps."""
    manager = get_goal_manager()
    gaps = manager.list_capability_gaps(
        goal_id=goal_id,
        status=status,
        gap_type=gap_type,
    )
    return {
        "gaps": [g.to_dict() for g in gaps],
        "count": len(gaps),
    }


@router.get("/gaps/blocking")
async def get_blocking_gaps(admin: Dict = Depends(require_admin)):
    """Get capability gaps that are blocking progress."""
    manager = get_goal_manager()
    gaps = manager.get_blocking_gaps()
    return {
        "gaps": [g.to_dict() for g in gaps],
        "count": len(gaps),
    }


@router.post("/gaps")
async def add_capability_gap(
    request: AddCapabilityGapRequest,
    admin: Dict = Depends(require_admin)
):
    """Add a capability gap."""
    manager = get_goal_manager()
    gap = manager.add_capability_gap(
        capability=request.capability,
        gap_type=request.gap_type,
        goal_id=request.goal_id,
        description=request.description,
        urgency=request.urgency,
    )
    return {
        "success": True,
        "gap": gap.to_dict(),
        "message": f"Capability gap '{request.capability}' recorded",
    }


@router.post("/gaps/{gap_id}/resolve")
async def resolve_gap(
    gap_id: str,
    request: ResolveGapRequest,
    admin: Dict = Depends(require_admin)
):
    """Resolve a capability gap."""
    manager = get_goal_manager()
    gap = manager.resolve_capability_gap(gap_id, request.resolution)
    if not gap:
        raise HTTPException(status_code=404, detail="Gap not found")
    return {
        "success": True,
        "gap": gap.to_dict(),
        "message": "Gap resolved",
    }


# ============== Goal CRUD Endpoints ==============

@router.get("/{goal_id}")
async def get_goal(goal_id: str, admin: Dict = Depends(require_admin)):
    """Get a specific goal by ID."""
    manager = get_goal_manager()
    goal = manager.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal.to_dict()


@router.get("/{goal_id}/hierarchy")
async def get_goal_hierarchy(goal_id: str, admin: Dict = Depends(require_admin)):
    """Get a goal and all its children in tree structure."""
    manager = get_goal_manager()
    hierarchy = manager.get_goal_hierarchy(goal_id)
    if not hierarchy:
        raise HTTPException(status_code=404, detail="Goal not found")
    return hierarchy


@router.post("")
async def create_goal(
    request: CreateGoalRequest,
    admin: Dict = Depends(require_admin)
):
    """Create a new goal."""
    manager = get_goal_manager()
    goal = manager.create_goal(
        title=request.title,
        goal_type=request.goal_type,
        created_by=request.created_by,
        description=request.description,
        parent_id=request.parent_id,
        project_id=request.project_id,
        priority=request.priority,
        urgency=request.urgency,
        assigned_to=request.assigned_to,
        completion_criteria=request.completion_criteria,
    )
    return {
        "success": True,
        "goal": goal.to_dict(),
        "message": f"Goal '{goal.title}' created",
    }


@router.put("/{goal_id}")
async def update_goal(
    goal_id: str,
    request: UpdateGoalRequest,
    admin: Dict = Depends(require_admin)
):
    """Update a goal's fields."""
    manager = get_goal_manager()
    goal = manager.update_goal(
        goal_id,
        title=request.title,
        description=request.description,
        priority=request.priority,
        urgency=request.urgency,
        assigned_to=request.assigned_to,
        completion_criteria=request.completion_criteria,
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {
        "success": True,
        "goal": goal.to_dict(),
    }


@router.delete("/{goal_id}")
async def delete_goal(goal_id: str, admin: Dict = Depends(require_admin)):
    """Delete a goal."""
    manager = get_goal_manager()
    if not manager.delete_goal(goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"success": True, "message": "Goal deleted"}


# ============== Status Transition Endpoints ==============

@router.post("/{goal_id}/approve")
async def approve_goal(
    goal_id: str,
    request: ApproveGoalRequest,
    admin: Dict = Depends(require_admin)
):
    """Approve a proposed goal."""
    manager = get_goal_manager()
    goal = manager.approve_goal(goal_id, request.approved_by)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found or not in proposed status")
    return {
        "success": True,
        "goal": goal.to_dict(),
        "message": f"Goal '{goal.title}' approved by {request.approved_by}",
    }


@router.post("/{goal_id}/reject")
async def reject_goal(
    goal_id: str,
    request: RejectGoalRequest,
    admin: Dict = Depends(require_admin)
):
    """Reject a proposed goal."""
    manager = get_goal_manager()
    goal = manager.reject_goal(goal_id, request.reason)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found or not in proposed status")
    return {
        "success": True,
        "goal": goal.to_dict(),
        "message": f"Goal rejected: {request.reason}",
    }


@router.post("/{goal_id}/start")
async def start_goal(goal_id: str, admin: Dict = Depends(require_admin)):
    """Start working on a goal (transitions to active)."""
    manager = get_goal_manager()
    goal = manager.start_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=400, detail="Goal not found or cannot be started (may need approval)")
    return {
        "success": True,
        "goal": goal.to_dict(),
        "message": f"Goal '{goal.title}' is now active",
    }


@router.post("/{goal_id}/complete")
async def complete_goal(
    goal_id: str,
    request: CompleteGoalRequest,
    admin: Dict = Depends(require_admin)
):
    """Mark a goal as completed."""
    manager = get_goal_manager()
    goal = manager.complete_goal(goal_id, request.outcome_summary)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {
        "success": True,
        "goal": goal.to_dict(),
        "message": f"Goal '{goal.title}' completed",
    }


@router.post("/{goal_id}/abandon")
async def abandon_goal(
    goal_id: str,
    request: AbandonGoalRequest,
    admin: Dict = Depends(require_admin)
):
    """Abandon a goal."""
    manager = get_goal_manager()
    goal = manager.abandon_goal(goal_id, request.reason)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {
        "success": True,
        "goal": goal.to_dict(),
        "message": f"Goal '{goal.title}' abandoned",
    }


@router.post("/{goal_id}/unblock")
async def unblock_goal(goal_id: str, admin: Dict = Depends(require_admin)):
    """Unblock a blocked goal."""
    manager = get_goal_manager()
    goal = manager.unblock_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {
        "success": True,
        "goal": goal.to_dict(),
        "message": f"Goal '{goal.title}' unblocked",
    }


# ============== Progress Endpoints ==============

@router.post("/{goal_id}/progress")
async def add_progress(
    goal_id: str,
    request: AddProgressRequest,
    admin: Dict = Depends(require_admin)
):
    """Add a progress entry to a goal."""
    manager = get_goal_manager()
    goal = manager.add_progress(goal_id, {
        "note": request.note,
        **(request.details or {}),
    })
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {
        "success": True,
        "progress_count": len(goal.progress),
        "message": "Progress added",
    }


# ============== Goal Links Endpoints ==============

@router.post("/{goal_id}/links")
async def add_goal_link(
    goal_id: str,
    request: AddGoalLinkRequest,
    admin: Dict = Depends(require_admin)
):
    """Add a link between two goals."""
    manager = get_goal_manager()
    if not manager.add_goal_link(goal_id, request.target_id, request.link_type):
        raise HTTPException(status_code=400, detail="Failed to add link")
    return {
        "success": True,
        "message": f"Link added: {goal_id} --{request.link_type}--> {request.target_id}",
    }


@router.delete("/{goal_id}/links/{target_id}/{link_type}")
async def remove_goal_link(
    goal_id: str,
    target_id: str,
    link_type: str,
    admin: Dict = Depends(require_admin)
):
    """Remove a link between two goals."""
    manager = get_goal_manager()
    if not manager.remove_goal_link(goal_id, target_id, link_type):
        raise HTTPException(status_code=404, detail="Link not found")
    return {"success": True, "message": "Link removed"}


@router.get("/{goal_id}/dependencies")
async def get_dependencies(goal_id: str, admin: Dict = Depends(require_admin)):
    """Get goals this goal depends on."""
    manager = get_goal_manager()
    deps = manager.get_dependencies(goal_id)
    return {"dependencies": deps}


@router.get("/{goal_id}/dependents")
async def get_dependents(goal_id: str, admin: Dict = Depends(require_admin)):
    """Get goals that depend on this goal."""
    manager = get_goal_manager()
    deps = manager.get_dependents(goal_id)
    return {"dependents": deps}
