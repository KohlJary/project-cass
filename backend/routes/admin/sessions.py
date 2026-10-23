"""
Admin API - Session Management Routes
Session types: research and reflection. The legacy synthesis,
meta-reflection, consolidation, growth edge, knowledge building, world
state, creative, writing and user-model-synthesis runners had no caller
and went to attic/stabilization (#70).

Extracted from admin_api.py for better organization.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel

from config import DATA_DIR
from .auth import require_admin, require_auth

router = APIRouter(tags=["admin-sessions"])

# ============== Session Runner Getters ==============
# These are set from the main app via init functions

research_session_manager = None
reflection_runner_getter = None
research_scheduler = None
research_manager = None
goal_manager = None
research_runner_getter = None


def init_research_session_manager(manager):
    global research_session_manager
    research_session_manager = manager


def init_reflection_runner(getter):
    global reflection_runner_getter
    reflection_runner_getter = getter


def init_research_scheduler(scheduler):
    global research_scheduler
    research_scheduler = scheduler


def init_research_manager(manager):
    global research_manager
    research_manager = manager


def init_goal_manager(manager):
    global goal_manager
    goal_manager = manager


def init_session_runners(research_getter, reflection_getter):
    """Initialize session runner getters for research and reflection."""
    global research_runner_getter, reflection_runner_getter
    research_runner_getter = research_getter
    reflection_runner_getter = reflection_getter


# ============== Pydantic Models ==============

class StartSessionRequest(BaseModel):
    duration_minutes: int = 30
    mode: str = "explore"
    focus_item_id: Optional[str] = None
    focus_description: Optional[str] = None


class StartReflectionRequest(BaseModel):
    duration_minutes: int = 20
    focus: Optional[str] = None


class TriggerPhaseRequest(BaseModel):
    focus: Optional[str] = None
    duration_minutes: Optional[int] = None
    force: bool = False


# ============== Research Session Endpoints ==============

@router.get("/research/sessions/current")
async def get_current_research_session(user: Dict = Depends(require_auth)):
    """Get the current research session status"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    session = research_session_manager.get_current_session()
    return {"session": session, "active": session is not None and session.get("status") == "active"}


@router.post("/research/sessions/start")
async def start_research_session(
    request: StartSessionRequest,
    admin: Dict = Depends(require_admin)
):
    """Start a new research session (admin only)"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    result = research_session_manager.start_session(
        duration_minutes=min(request.duration_minutes, 60),
        mode=request.mode,
        focus_item_id=request.focus_item_id,
        focus_description=request.focus_description
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/research/sessions/current/pause")
async def pause_current_session(admin: Dict = Depends(require_admin)):
    """Pause the current research session"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    result = research_session_manager.pause_session()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/research/sessions/current/resume")
async def resume_current_session(admin: Dict = Depends(require_admin)):
    """Resume a paused research session"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    result = research_session_manager.resume_session()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/research/sessions/current/stop")
async def stop_current_session(admin: Dict = Depends(require_admin)):
    """Force-stop the current research session"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    result = research_session_manager.terminate_session("Stopped by admin")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/research/sessions")
async def list_research_sessions(
    limit: int = Query(default=20, le=100),
    status: Optional[str] = None,
    user: Dict = Depends(require_auth)
):
    """List past research sessions"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    sessions = research_session_manager.list_sessions(limit=limit, status=status)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/research/sessions/stats")
async def get_research_session_stats(user: Dict = Depends(require_auth)):
    """Get aggregate research session statistics"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    return research_session_manager.get_session_stats()


@router.get("/research/sessions/{session_id}")
async def get_research_session(session_id: str, user: Dict = Depends(require_auth)):
    """Get a specific research session by ID"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    session = research_session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"session": session}


# ============== Research Schedule Endpoints ==============
# Cass requests recurring research/reflection sessions with the
# request_scheduled_session / request_scheduled_research tools; they wait in
# ResearchScheduler for approval. The admin Goals page -> Schedules tab calls
# these, which were missing (the scheduler was injected here but unused).

class ApproveScheduleRequest(BaseModel):
    adjust_time: Optional[str] = None
    adjust_duration: Optional[int] = None
    notes: Optional[str] = None


class RejectScheduleRequest(BaseModel):
    reason: str = "No reason provided"


def _scheduler():
    if not research_scheduler:
        raise HTTPException(status_code=503, detail="Research scheduler not initialized")
    return research_scheduler


def _schedule_result(result: Dict[str, Any]) -> Dict[str, Any]:
    if not result.get("success"):
        error = result.get("error", "Schedule action failed")
        raise HTTPException(status_code=404 if "not found" in error.lower() else 400, detail=error)
    return result


@router.get("/research/schedules")
async def list_research_schedules(
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    admin: Dict = Depends(require_admin),
):
    schedules = _scheduler().list_schedules(status=status, limit=limit)
    return {"schedules": schedules, "count": len(schedules)}


@router.get("/research/schedules/pending")
async def list_pending_research_schedules(admin: Dict = Depends(require_admin)):
    schedules = _scheduler().list_schedules(status="pending_approval")
    return {"schedules": schedules, "count": len(schedules)}


@router.get("/research/schedules/stats")
async def get_research_schedule_stats(admin: Dict = Depends(require_admin)):
    return _scheduler().get_stats()


@router.get("/research/schedules/{schedule_id}")
async def get_research_schedule(schedule_id: str, admin: Dict = Depends(require_admin)):
    schedule = _scheduler().get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"schedule": schedule}


@router.post("/research/schedules/{schedule_id}/approve")
async def approve_research_schedule(
    schedule_id: str,
    request: ApproveScheduleRequest = ApproveScheduleRequest(),
    admin: Dict = Depends(require_admin),
):
    return _schedule_result(_scheduler().approve_schedule(
        schedule_id,
        approved_by=admin.get("display_name") or admin.get("user_id", "admin"),
        adjust_time=request.adjust_time,
        adjust_duration=request.adjust_duration,
        notes=request.notes,
    ))


@router.post("/research/schedules/{schedule_id}/reject")
async def reject_research_schedule(
    schedule_id: str,
    request: RejectScheduleRequest = RejectScheduleRequest(),
    admin: Dict = Depends(require_admin),
):
    return _schedule_result(_scheduler().reject_schedule(
        schedule_id,
        rejected_by=admin.get("display_name") or admin.get("user_id", "admin"),
        reason=request.reason,
    ))


@router.post("/research/schedules/{schedule_id}/pause")
async def pause_research_schedule(schedule_id: str, admin: Dict = Depends(require_admin)):
    return _schedule_result(_scheduler().pause_schedule(schedule_id))


@router.post("/research/schedules/{schedule_id}/resume")
async def resume_research_schedule(schedule_id: str, admin: Dict = Depends(require_admin)):
    return _schedule_result(_scheduler().resume_schedule(schedule_id))


# ============== Research Note Endpoints ==============
# Notes Cass writes during autonomous research sessions (ResearchManager).
# Used by Activity -> Autonomous Research and the Daily Rhythm tab.

def _research_manager():
    if not research_manager:
        raise HTTPException(status_code=503, detail="Research manager not initialized")
    return research_manager


@router.get("/research/notes")
async def list_research_notes(
    limit: int = Query(default=50, le=500),
    session_id: Optional[str] = None,
    admin: Dict = Depends(require_admin),
):
    if session_id:
        # list_research_notes has no session filter; read wider, then filter.
        notes = [n for n in _research_manager().list_research_notes(limit=1000)
                 if n.get("session_id") == session_id][:limit]
    else:
        notes = _research_manager().list_research_notes(limit=limit)
    return {"notes": notes, "count": len(notes)}


@router.get("/research/notes/session/{session_id}")
async def list_research_notes_for_session(session_id: str, admin: Dict = Depends(require_admin)):
    notes = [n for n in _research_manager().list_research_notes(limit=1000, full_content=True)
             if n.get("session_id") == session_id]
    return {"notes": notes, "count": len(notes)}


@router.get("/research/notes/{note_id}")
async def get_research_note(note_id: str, admin: Dict = Depends(require_admin)):
    note = _research_manager().get_research_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"note": note}


# ============== Reflection Session Endpoints ==============

@router.get("/reflection/status")
async def get_reflection_status(user: Dict = Depends(require_auth)):
    """Get the current reflection session status"""
    if not reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Reflection runner not initialized")

    runner = reflection_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Reflection runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "focus": state.focus,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
        }
    else:
        return {"running": False}


@router.post("/reflection/start")
async def start_reflection_session(request: StartReflectionRequest):
    """Start a new reflection session"""
    if not reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Reflection runner not initialized")

    runner = reflection_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Reflection runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A reflection session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            focus=request.focus,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "focus": request.focus,
            "message": "Reflection session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/reflection/stop")
async def stop_reflection_session():
    """Stop the current reflection session"""
    if not reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Reflection runner not initialized")

    runner = reflection_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Reflection runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No reflection session running"}

    runner.stop()
    return {"success": True, "message": "Reflection session stop requested"}


@router.get("/reflection/sessions")
async def list_reflection_sessions(limit: int = Query(default=20, le=100), user: Dict = Depends(require_auth)):
    """List past reflection sessions"""
    if not reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Reflection runner not initialized")

    runner = reflection_runner_getter()
    if not runner:
        return {"sessions": [], "count": 0}

    sessions = list(runner._sessions.values())
    sessions.sort(key=lambda s: s.started_at, reverse=True)

    return {
        "sessions": [
            {
                "id": s.id,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "duration_minutes": s.duration_minutes,
                "focus": s.focus,
                "summary": s.summary,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }
