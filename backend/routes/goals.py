"""
Goals REST API routes
Expose Cass's goal generation and tracking system to admin frontend
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter(prefix="/goals", tags=["goals"])

# Set by main app
_goal_manager = None


def init_goal_routes(goal_manager):
    """Initialize the routes with dependencies"""
    global _goal_manager
    _goal_manager = goal_manager


# === Response Models ===

class InitiativeResponse(BaseModel):
    initiative_id: str
    status: str
    response: str


# === Working Questions ===

@router.get("/questions")
async def list_questions(status: Optional[str] = None):
    """List all working questions, optionally filtered by status."""
    if not _goal_manager:
        raise HTTPException(status_code=500, detail="Goal manager not initialized")

    questions = _goal_manager.list_working_questions(status=status)
    return {"questions": questions}


@router.get("/questions/{question_id}")
async def get_question(question_id: str):
    """Get a specific working question."""
    if not _goal_manager:
        raise HTTPException(status_code=500, detail="Goal manager not initialized")

    question = _goal_manager.get_working_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail=f"Question not found: {question_id}")

    return {"question": question}


# === Research Agenda ===

@router.get("/agenda")
async def list_agenda(
    status: Optional[str] = None,
    priority: Optional[str] = None
):
    """List research agenda items."""
    if not _goal_manager:
        raise HTTPException(status_code=500, detail="Goal manager not initialized")

    items = _goal_manager.list_research_agenda(status=status, priority=priority)
    return {"items": items}


@router.get("/agenda/{item_id}")
async def get_agenda_item(item_id: str):
    """Get a specific research agenda item."""
    if not _goal_manager:
        raise HTTPException(status_code=500, detail="Goal manager not initialized")

    item = _goal_manager.get_research_agenda_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Agenda item not found: {item_id}")

    return {"item": item}


# === Synthesis Artifacts ===

@router.get("/artifacts")
async def list_artifacts():
    """List all synthesis artifacts."""
    if not _goal_manager:
        raise HTTPException(status_code=500, detail="Goal manager not initialized")

    artifacts = _goal_manager.list_synthesis_artifacts()
    return {"artifacts": artifacts}


@router.get("/artifacts/{slug}")
async def get_artifact(slug: str):
    """Get a specific synthesis artifact with full content."""
    if not _goal_manager:
        raise HTTPException(status_code=500, detail="Goal manager not initialized")

    artifact = _goal_manager.get_synthesis_artifact(slug)
    if not artifact:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {slug}")

    return {"artifact": artifact}


# === Initiatives ===

@router.get("/initiatives")
async def list_initiatives(status: Optional[str] = None):
    """List initiatives (requests from Cass needing attention)."""
    if not _goal_manager:
        raise HTTPException(status_code=500, detail="Goal manager not initialized")

    initiatives = _goal_manager.list_initiatives(status=status)
    return {"initiatives": initiatives}


@router.post("/initiatives/{initiative_id}/respond")
async def respond_to_initiative(
    initiative_id: str,
    status: str,
    response: str
):
    """Respond to an initiative from Cass."""
    if not _goal_manager:
        raise HTTPException(status_code=500, detail="Goal manager not initialized")

    if status not in ["acknowledged", "completed", "declined"]:
        raise HTTPException(
            status_code=400,
            detail="Status must be: acknowledged, completed, or declined"
        )

    result = _goal_manager.respond_to_initiative(initiative_id, status, response)
    if not result:
        raise HTTPException(status_code=404, detail=f"Initiative not found: {initiative_id}")

    return {"initiative": result}


# === Progress & Review ===

@router.get("/progress")
async def get_progress(limit: int = 20, entry_type: Optional[str] = None):
    """Get recent progress entries."""
    if not _goal_manager:
        raise HTTPException(status_code=500, detail="Goal manager not initialized")

    entries = _goal_manager.get_recent_progress(limit=limit, entry_type=entry_type)
    return {"entries": entries}


@router.get("/review")
async def review_goals(include_progress: bool = True):
    """Get full goal review - overview of all goal state."""
    if not _goal_manager:
        raise HTTPException(status_code=500, detail="Goal manager not initialized")

    review = _goal_manager.review_goals(include_progress=include_progress)
    return {"review": review}


@router.get("/next-actions")
async def get_next_actions():
    """Get prioritized next actions across all goals."""
    if not _goal_manager:
        raise HTTPException(status_code=500, detail="Goal manager not initialized")

    actions = _goal_manager.get_next_actions()
    return {"actions": actions}
