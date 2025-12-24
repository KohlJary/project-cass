"""
Solo Reflection API Routes

Extracted from main_sdk.py as part of Phase 1 refactoring.
Handles solo reflection sessions - Cass reflecting autonomously.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Callable

router = APIRouter(prefix="/solo-reflection", tags=["solo-reflection"])


# === Request Models ===

class SoloReflectionStartRequest(BaseModel):
    duration_minutes: int = 15
    theme: Optional[str] = None


# === Dependencies (injected at startup) ===

_reflection_manager = None
_get_reflection_runner = None


def init_solo_reflection_routes(reflection_manager, get_reflection_runner: Callable):
    """Initialize route dependencies. Called from main_sdk.py startup."""
    global _reflection_manager, _get_reflection_runner
    _reflection_manager = reflection_manager
    _get_reflection_runner = get_reflection_runner


# === Solo Reflection Endpoints ===

@router.post("/sessions")
async def start_solo_reflection(request: SoloReflectionStartRequest, background_tasks: BackgroundTasks):
    """
    Start a solo reflection session.

    This runs on local Ollama to avoid API token costs.
    The session runs in the background and can be monitored.
    """
    runner = _get_reflection_runner()

    if runner.is_running:
        raise HTTPException(
            status_code=409,
            detail="A reflection session is already running"
        )

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            theme=request.theme,
            trigger="admin",
        )

        return {
            "status": "started",
            "session_id": session.session_id,
            "duration_minutes": session.duration_minutes,
            "theme": session.theme,
            "message": f"Solo reflection session started. Running on local Ollama for {session.duration_minutes} minutes."
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/sessions")
async def list_solo_reflection_sessions(
    limit: int = 20,
    status: Optional[str] = None
):
    """List solo reflection sessions."""
    sessions = _reflection_manager.list_sessions(limit=limit, status_filter=status)
    stats = _reflection_manager.get_stats()

    return {
        "sessions": sessions,
        "stats": stats,
        "active_session": stats.get("active_session"),
    }


@router.get("/sessions/{session_id}")
async def get_solo_reflection_session(session_id: str):
    """Get details of a specific solo reflection session."""
    session = _reflection_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.to_dict()


@router.get("/sessions/{session_id}/stream")
async def get_solo_reflection_thought_stream(session_id: str):
    """Get just the thought stream from a session."""
    session = _reflection_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "thought_count": session.thought_count,
        "thought_stream": [t.to_dict() for t in session.thought_stream],
        "thought_types": session.thought_type_distribution,
    }


@router.delete("/sessions/{session_id}")
async def delete_solo_reflection_session(session_id: str):
    """Delete a solo reflection session."""
    success = _reflection_manager.delete_session(session_id)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete session (may be active or not found)"
        )

    return {"status": "deleted", "session_id": session_id}


@router.post("/stop")
async def stop_solo_reflection():
    """Stop the currently running solo reflection session."""
    runner = _get_reflection_runner()

    if not runner.is_running:
        raise HTTPException(status_code=400, detail="No reflection session is running")

    runner.stop()
    session = _reflection_manager.interrupt_session("Stopped by admin")

    return {
        "status": "stopped",
        "session_id": session.session_id if session else None,
    }


@router.get("/stats")
async def get_solo_reflection_stats():
    """Get overall solo reflection statistics."""
    return _reflection_manager.get_stats()


@router.post("/sessions/{session_id}/integrate")
async def integrate_reflection_session(session_id: str):
    """Manually trigger self-model integration for a completed reflection session."""
    session = _reflection_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    if session.status != "completed":
        raise HTTPException(status_code=400, detail=f"Session not completed (status: {session.status})")

    runner = _get_reflection_runner()
    result = await runner.integrate_session_into_self_model(session)

    return {
        "status": "integrated",
        "session_id": session_id,
        "observations_created": len(result.get("observations_created", [])),
        "growth_edge_updates": len(result.get("growth_edge_updates", [])),
        "questions_added": len(result.get("questions_added", [])),
        "details": result,
    }
