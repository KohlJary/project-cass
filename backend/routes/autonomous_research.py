"""
Autonomous Research API Routes

Extracted from main_sdk.py as part of Phase 1 refactoring.
Handles autonomous research sessions - Cass researching autonomously.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Callable

router = APIRouter(prefix="/autonomous-research", tags=["autonomous-research"])


# === Request Models ===

class AutonomousResearchStartRequest(BaseModel):
    duration_minutes: int = 30
    focus: str
    mode: str = "explore"  # explore or deep


# === Dependencies (injected at startup) ===

_get_research_runner = None


def init_autonomous_research_routes(get_research_runner: Callable):
    """Initialize route dependencies. Called from main_sdk.py startup."""
    global _get_research_runner
    _get_research_runner = get_research_runner


# === Autonomous Research Endpoints ===

@router.post("/sessions")
async def start_autonomous_research(request: AutonomousResearchStartRequest, background_tasks: BackgroundTasks):
    """
    Start an autonomous research session.

    This runs via LLM (Haiku or Ollama) with full Cass context injected.
    The session runs in the background and creates research notes.
    """
    runner = _get_research_runner()

    if runner.is_running:
        raise HTTPException(
            status_code=409,
            detail="A research session is already running"
        )

    try:
        session = await runner.start_session(
            duration_minutes=min(request.duration_minutes, 60),
            focus=request.focus,
            mode=request.mode,
            trigger="admin",
        )

        return {
            "status": "started",
            "session_id": session.session_id,
            "duration_minutes": session.duration_limit_minutes,
            "focus": session.focus_description,
            "mode": session.mode.value if hasattr(session.mode, 'value') else str(session.mode),
            "message": f"Autonomous research session started. Running for {session.duration_limit_minutes} minutes."
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/status")
async def get_autonomous_research_status():
    """Get status of the current autonomous research session."""
    runner = _get_research_runner()
    current_session = runner.session_manager.get_current_session()
    return {
        "is_running": runner.is_running,
        "current_session": current_session,
    }


@router.post("/stop")
async def stop_autonomous_research():
    """Stop the currently running autonomous research session."""
    runner = _get_research_runner()

    if not runner.is_running:
        raise HTTPException(
            status_code=409,
            detail="No research session is currently running"
        )

    await runner.stop()
    return {"status": "stopped", "message": "Research session stopped"}
