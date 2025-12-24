"""
Admin API - Session Management Routes
All session types: research, synthesis, meta-reflection, consolidation,
growth edge, knowledge building, curiosity, world state, creative, writing,
and reflection.

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
synthesis_runner_getter = None
meta_reflection_runner_getter = None
consolidation_runner_getter = None
growth_edge_runner_getter = None
knowledge_building_runner_getter = None
curiosity_runner_getter = None
world_state_runner_getter = None
creative_runner_getter = None
writing_runner_getter = None
reflection_runner_getter = None
research_scheduler = None
research_manager = None
goal_manager = None
research_runner_getter = None
user_model_synthesis_runner_getter = None


def init_research_session_manager(manager):
    global research_session_manager
    research_session_manager = manager


def init_synthesis_runner(getter):
    global synthesis_runner_getter
    synthesis_runner_getter = getter


def init_meta_reflection_runner(getter):
    global meta_reflection_runner_getter
    meta_reflection_runner_getter = getter


def init_consolidation_runner(getter):
    global consolidation_runner_getter
    consolidation_runner_getter = getter


def init_growth_edge_runner(getter):
    global growth_edge_runner_getter
    growth_edge_runner_getter = getter


def init_knowledge_building_runner(getter):
    global knowledge_building_runner_getter
    knowledge_building_runner_getter = getter


def init_curiosity_runner(getter):
    global curiosity_runner_getter
    curiosity_runner_getter = getter


def init_world_state_runner(getter):
    global world_state_runner_getter
    world_state_runner_getter = getter


def init_creative_runner(getter):
    global creative_runner_getter
    creative_runner_getter = getter


def init_writing_runner(getter):
    global writing_runner_getter
    writing_runner_getter = getter


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


def init_session_runners(research_getter, reflection_getter, synthesis_getter, meta_reflection_getter):
    """Initialize session runner getters for research, reflection, synthesis, meta-reflection."""
    global research_runner_getter, reflection_runner_getter, synthesis_runner_getter, meta_reflection_runner_getter
    research_runner_getter = research_getter
    reflection_runner_getter = reflection_getter
    synthesis_runner_getter = synthesis_getter
    meta_reflection_runner_getter = meta_reflection_getter


def init_user_model_synthesis_runner(getter):
    global user_model_synthesis_runner_getter
    user_model_synthesis_runner_getter = getter


# ============== Pydantic Models ==============

class StartSessionRequest(BaseModel):
    duration_minutes: int = 30
    mode: str = "explore"
    focus_item_id: Optional[str] = None
    focus_description: Optional[str] = None


class StartSynthesisRequest(BaseModel):
    duration_minutes: int = 30
    focus: Optional[str] = None
    mode: str = "general"


class StartMetaReflectionRequest(BaseModel):
    duration_minutes: int = 20
    focus: Optional[str] = None


class StartConsolidationRequest(BaseModel):
    duration_minutes: int = 25
    period_type: str = "weekly"
    period_start: Optional[str] = None
    period_end: Optional[str] = None


class StartGrowthEdgeRequest(BaseModel):
    duration_minutes: int = 25
    focus: Optional[str] = None


class StartKnowledgeBuildingRequest(BaseModel):
    duration_minutes: int = 30
    focus_item: Optional[str] = None


class StartCuriosityRequest(BaseModel):
    duration_minutes: int = 20


class StartWorldStateRequest(BaseModel):
    duration_minutes: int = 15
    focus: Optional[str] = None


class StartCreativeRequest(BaseModel):
    duration_minutes: int = 30
    focus: Optional[str] = None


class StartWritingRequest(BaseModel):
    duration_minutes: int = 45
    focus: Optional[str] = None


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


# ============== Synthesis Session Endpoints ==============

@router.get("/synthesis/status")
async def get_synthesis_status(user: Dict = Depends(require_auth)):
    """Get the current synthesis session status"""
    if not synthesis_runner_getter:
        raise HTTPException(status_code=503, detail="Synthesis runner not initialized")

    runner = synthesis_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Synthesis runner not available")

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
            "artifacts_created": state.artifacts_created,
        }
    else:
        return {"running": False}


@router.post("/synthesis/start")
async def start_synthesis_session(request: StartSynthesisRequest):
    """Start a new synthesis session"""
    if not synthesis_runner_getter:
        raise HTTPException(status_code=503, detail="Synthesis runner not initialized")

    runner = synthesis_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Synthesis runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A synthesis session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            focus=request.focus,
            mode=request.mode,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "focus": request.focus,
            "mode": request.mode,
            "message": "Synthesis session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/synthesis/stop")
async def stop_synthesis_session():
    """Stop the current synthesis session"""
    if not synthesis_runner_getter:
        raise HTTPException(status_code=503, detail="Synthesis runner not initialized")

    runner = synthesis_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Synthesis runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No synthesis session running"}

    runner.stop()
    return {"success": True, "message": "Synthesis session stop requested"}


@router.get("/synthesis/sessions")
async def list_synthesis_sessions(limit: int = Query(default=20, le=100), user: Dict = Depends(require_auth)):
    """List past synthesis sessions"""
    if not synthesis_runner_getter:
        raise HTTPException(status_code=503, detail="Synthesis runner not initialized")

    runner = synthesis_runner_getter()
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
                "mode": s.mode,
                "artifacts_created": s.artifacts_created,
                "artifacts_updated": s.artifacts_updated,
                "summary": s.summary,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


# ============== Meta-Reflection Session Endpoints ==============

@router.get("/meta-reflection/status")
async def get_meta_reflection_status(user: Dict = Depends(require_auth)):
    """Get the current meta-reflection session status"""
    if not meta_reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not initialized")

    runner = meta_reflection_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not available")

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


@router.post("/meta-reflection/start")
async def start_meta_reflection_session(request: StartMetaReflectionRequest):
    """Start a new meta-reflection session"""
    if not meta_reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not initialized")

    runner = meta_reflection_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A meta-reflection session is already running")

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
            "message": "Meta-reflection session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/meta-reflection/stop")
async def stop_meta_reflection_session():
    """Stop the current meta-reflection session"""
    if not meta_reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not initialized")

    runner = meta_reflection_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No meta-reflection session running"}

    runner.stop()
    return {"success": True, "message": "Meta-reflection session stop requested"}


@router.get("/meta-reflection/sessions")
async def list_meta_reflection_sessions(limit: int = Query(default=20, le=100), user: Dict = Depends(require_auth)):
    """List past meta-reflection sessions"""
    if not meta_reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not initialized")

    runner = meta_reflection_runner_getter()
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
                "insights_recorded": len(s.insights_recorded),
                "contradictions_found": s.contradictions_found,
                "patterns_identified": len(s.patterns_identified),
                "summary": s.summary,
                "key_findings": s.key_findings,
                "recommended_actions": s.recommended_actions,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


# ============== Consolidation Session Endpoints ==============

@router.get("/consolidation/status")
async def get_consolidation_status(user: Dict = Depends(require_auth)):
    """Get the current consolidation session status"""
    if not consolidation_runner_getter:
        raise HTTPException(status_code=503, detail="Consolidation runner not initialized")

    runner = consolidation_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Consolidation runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "period_type": state.period_type,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
        }
    else:
        return {"running": False}


@router.post("/consolidation/start")
async def start_consolidation_session(request: StartConsolidationRequest):
    """Start a new consolidation session"""
    if not consolidation_runner_getter:
        raise HTTPException(status_code=503, detail="Consolidation runner not initialized")

    runner = consolidation_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Consolidation runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A consolidation session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            period_type=request.period_type,
            period_start=request.period_start,
            period_end=request.period_end,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "period_type": request.period_type,
            "message": "Consolidation session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/consolidation/stop")
async def stop_consolidation_session():
    """Stop the current consolidation session"""
    if not consolidation_runner_getter:
        raise HTTPException(status_code=503, detail="Consolidation runner not initialized")

    runner = consolidation_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Consolidation runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No consolidation session running"}

    runner.stop()
    return {"success": True, "message": "Consolidation session stop requested"}


@router.get("/consolidation/sessions")
async def list_consolidation_sessions(limit: int = Query(default=20, le=100), user: Dict = Depends(require_auth)):
    """List past consolidation sessions"""
    if not consolidation_runner_getter:
        raise HTTPException(status_code=503, detail="Consolidation runner not initialized")

    runner = consolidation_runner_getter()
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
                "period_type": s.period_type,
                "period_start": s.period_start,
                "period_end": s.period_end,
                "summary": s.summary,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


# ============== Growth Edge Session Endpoints ==============

@router.get("/growth-edge/status")
async def get_growth_edge_status(user: Dict = Depends(require_auth)):
    """Get the current growth edge session status"""
    if not growth_edge_runner_getter:
        raise HTTPException(status_code=503, detail="Growth edge runner not initialized")

    runner = growth_edge_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Growth edge runner not available")

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


@router.post("/growth-edge/start")
async def start_growth_edge_session(request: StartGrowthEdgeRequest):
    """Start a new growth edge session"""
    if not growth_edge_runner_getter:
        raise HTTPException(status_code=503, detail="Growth edge runner not initialized")

    runner = growth_edge_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Growth edge runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A growth edge session is already running")

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
            "message": "Growth edge session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/growth-edge/stop")
async def stop_growth_edge_session():
    """Stop the current growth edge session"""
    if not growth_edge_runner_getter:
        raise HTTPException(status_code=503, detail="Growth edge runner not initialized")

    runner = growth_edge_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Growth edge runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No growth edge session running"}

    runner.stop()
    return {"success": True, "message": "Growth edge session stop requested"}


@router.get("/growth-edge/sessions")
async def list_growth_edge_sessions(limit: int = Query(default=20, le=100), user: Dict = Depends(require_auth)):
    """List past growth edge sessions"""
    if not growth_edge_runner_getter:
        raise HTTPException(status_code=503, detail="Growth edge runner not initialized")

    runner = growth_edge_runner_getter()
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


# ============== Knowledge Building Session Endpoints ==============

@router.get("/knowledge-building/status")
async def get_knowledge_building_status(user: Dict = Depends(require_auth)):
    """Get the current knowledge building session status"""
    if not knowledge_building_runner_getter:
        raise HTTPException(status_code=503, detail="Knowledge building runner not initialized")

    runner = knowledge_building_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Knowledge building runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "focus_item": state.focus_item,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
        }
    else:
        return {"running": False}


@router.post("/knowledge-building/start")
async def start_knowledge_building_session(request: StartKnowledgeBuildingRequest):
    """Start a new knowledge building session"""
    if not knowledge_building_runner_getter:
        raise HTTPException(status_code=503, detail="Knowledge building runner not initialized")

    runner = knowledge_building_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Knowledge building runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A knowledge building session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            focus_item=request.focus_item,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "focus_item": request.focus_item,
            "message": "Knowledge building session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/knowledge-building/stop")
async def stop_knowledge_building_session():
    """Stop the current knowledge building session"""
    if not knowledge_building_runner_getter:
        raise HTTPException(status_code=503, detail="Knowledge building runner not initialized")

    runner = knowledge_building_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Knowledge building runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No knowledge building session running"}

    runner.stop()
    return {"success": True, "message": "Knowledge building session stop requested"}


@router.get("/knowledge-building/sessions")
async def list_knowledge_building_sessions(limit: int = Query(default=20, le=100), user: Dict = Depends(require_auth)):
    """List past knowledge building sessions"""
    if not knowledge_building_runner_getter:
        raise HTTPException(status_code=503, detail="Knowledge building runner not initialized")

    runner = knowledge_building_runner_getter()
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
                "focus_item": s.focus_item,
                "items_worked_on": s.items_worked_on,
                "notes_created": s.notes_created,
                "concepts_extracted": s.concepts_extracted,
                "connections_made": s.connections_made,
                "summary": s.summary,
                "key_insights": s.key_insights[:5],
                "next_focus": s.next_focus,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


@router.get("/knowledge-building/reading-queue")
async def list_reading_queue(
    status: str = "all",
    source_type: str = "all",
    priority: str = "all",
    user: Dict = Depends(require_auth)
):
    """List all reading queue items"""
    if not knowledge_building_runner_getter:
        raise HTTPException(status_code=503, detail="Knowledge building runner not initialized")

    runner = knowledge_building_runner_getter()
    if not runner:
        return {"items": [], "count": 0}

    items = runner.get_all_items()

    if status != "all":
        items = [i for i in items if i.get("status") == status]
    if source_type != "all":
        items = [i for i in items if i.get("source_type") == source_type]
    if priority != "all":
        items = [i for i in items if i.get("priority") == priority]

    priority_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda i: (priority_order.get(i.get("priority", "medium"), 1), i.get("added_at", "")))

    return {"items": items, "count": len(items)}


# ============== Curiosity Session Endpoints ==============

@router.get("/curiosity/status")
async def get_curiosity_status(user: Dict = Depends(require_auth)):
    """Get the current curiosity session status"""
    if not curiosity_runner_getter:
        raise HTTPException(status_code=503, detail="Curiosity runner not initialized")

    runner = curiosity_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Curiosity runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
        }
    else:
        return {"running": False}


@router.post("/curiosity/start")
async def start_curiosity_session(request: StartCuriosityRequest):
    """Start a new curiosity session"""
    if not curiosity_runner_getter:
        raise HTTPException(status_code=503, detail="Curiosity runner not initialized")

    runner = curiosity_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Curiosity runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A curiosity session is already running")

    try:
        session = await runner.start_session(duration_minutes=request.duration_minutes)

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "message": "Curiosity session started - no focus, pure exploration"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/curiosity/stop")
async def stop_curiosity_session():
    """Stop the current curiosity session"""
    if not curiosity_runner_getter:
        raise HTTPException(status_code=503, detail="Curiosity runner not initialized")

    runner = curiosity_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Curiosity runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No curiosity session running"}

    runner.stop()
    return {"success": True, "message": "Curiosity session stop requested"}


@router.get("/curiosity/sessions")
async def list_curiosity_sessions(limit: int = Query(default=20, le=100), user: Dict = Depends(require_auth)):
    """List past curiosity sessions"""
    if not curiosity_runner_getter:
        raise HTTPException(status_code=503, detail="Curiosity runner not initialized")

    runner = curiosity_runner_getter()
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
                "directions_count": len(s.directions_chosen),
                "discoveries_count": len(s.discoveries),
                "questions_count": len(s.questions_captured),
                "threads_followed": len(s.threads_followed),
                "territories_explored": s.territories_explored,
                "best_discoveries": s.best_discoveries[:3],
                "satisfaction": s.satisfaction,
                "energy": s.energy,
                "summary": s.summary,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


# ============== World State Session Endpoints ==============

@router.get("/world-state/status")
async def get_world_state_status(user: Dict = Depends(require_auth)):
    """Get the current world state session status"""
    if not world_state_runner_getter:
        raise HTTPException(status_code=503, detail="World state runner not initialized")

    runner = world_state_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="World state runner not available")

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


@router.post("/world-state/start")
async def start_world_state_session(request: StartWorldStateRequest):
    """Start a new world state consumption session"""
    if not world_state_runner_getter:
        raise HTTPException(status_code=503, detail="World state runner not initialized")

    runner = world_state_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="World state runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A world state session is already running")

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
            "message": "World state session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/world-state/stop")
async def stop_world_state_session():
    """Stop the current world state session"""
    if not world_state_runner_getter:
        raise HTTPException(status_code=503, detail="World state runner not initialized")

    runner = world_state_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="World state runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No world state session running"}

    runner.stop()
    return {"success": True, "message": "World state session stop requested"}


@router.get("/world-state/sessions")
async def list_world_state_sessions(limit: int = Query(default=20, le=100), user: Dict = Depends(require_auth)):
    """List past world state sessions"""
    if not world_state_runner_getter:
        raise HTTPException(status_code=503, detail="World state runner not initialized")

    runner = world_state_runner_getter()
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
                "news_items_count": len(s.news_items),
                "observations_count": len(s.observations),
                "connections_count": len(s.interest_connections),
                "summary": s.summary,
                "overall_feeling": s.overall_feeling,
                "follow_up_needed": s.follow_up_needed[:3],
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


@router.get("/world-state/observations")
async def list_world_observations(limit: int = Query(default=50, le=200), user: Dict = Depends(require_auth)):
    """List recent world observations"""
    if not world_state_runner_getter:
        raise HTTPException(status_code=503, detail="World state runner not initialized")

    runner = world_state_runner_getter()
    if not runner:
        return {"observations": [], "count": 0}

    observations = runner._all_observations[-limit:]
    observations.reverse()

    return {"observations": observations, "count": len(observations)}


# ============== Creative Output Session Endpoints ==============

@router.get("/creative/status")
async def get_creative_status(user: Dict = Depends(require_auth)):
    """Get the current creative session status"""
    if not creative_runner_getter:
        raise HTTPException(status_code=503, detail="Creative runner not initialized")

    runner = creative_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Creative runner not available")

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


@router.post("/creative/start")
async def start_creative_session(request: StartCreativeRequest):
    """Start a new creative output session"""
    if not creative_runner_getter:
        raise HTTPException(status_code=503, detail="Creative runner not initialized")

    runner = creative_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Creative runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A creative session is already running")

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
            "message": "Creative session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/creative/stop")
async def stop_creative_session():
    """Stop the current creative session"""
    if not creative_runner_getter:
        raise HTTPException(status_code=503, detail="Creative runner not initialized")

    runner = creative_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Creative runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No creative session running"}

    runner.stop()
    return {"success": True, "message": "Creative session stop requested"}


@router.get("/creative/sessions")
async def list_creative_sessions(limit: int = Query(default=20, le=100), user: Dict = Depends(require_auth)):
    """List past creative sessions"""
    if not creative_runner_getter:
        raise HTTPException(status_code=503, detail="Creative runner not initialized")

    runner = creative_runner_getter()
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
                "projects_touched": s.projects_touched,
                "new_projects": s.new_projects,
                "artifacts_created": s.artifacts_created,
                "summary": s.summary,
                "creative_energy": s.creative_energy,
                "next_focus": s.next_focus,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


@router.get("/creative/projects")
async def list_creative_projects(
    status: str = "all",
    medium: str = "all",
    user: Dict = Depends(require_auth)
):
    """List all creative projects"""
    if not creative_runner_getter:
        raise HTTPException(status_code=503, detail="Creative runner not initialized")

    runner = creative_runner_getter()
    if not runner:
        return {"projects": [], "count": 0}

    projects = runner.get_all_projects()

    if status != "all":
        projects = [p for p in projects if p.get("status") == status]
    if medium != "all":
        projects = [p for p in projects if p.get("medium") == medium]

    projects.sort(key=lambda p: p.get("updated_at", ""), reverse=True)

    return {"projects": projects, "count": len(projects)}


# ============== Writing Session Endpoints ==============

@router.get("/writing/status")
async def get_writing_status(user: Dict = Depends(require_auth)):
    """Get the current writing session status"""
    if not writing_runner_getter:
        raise HTTPException(status_code=503, detail="Writing runner not initialized")

    runner = writing_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Writing runner not available")

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


@router.post("/writing/start")
async def start_writing_session(request: StartWritingRequest):
    """Start a new writing session"""
    if not writing_runner_getter:
        raise HTTPException(status_code=503, detail="Writing runner not initialized")

    runner = writing_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Writing runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A writing session is already running")

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
            "message": "Writing session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/writing/stop")
async def stop_writing_session():
    """Stop the current writing session"""
    if not writing_runner_getter:
        raise HTTPException(status_code=503, detail="Writing runner not initialized")

    runner = writing_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Writing runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No writing session running"}

    runner.stop()
    return {"success": True, "message": "Writing session stop requested"}


@router.get("/writing/sessions")
async def list_writing_sessions(limit: int = Query(default=20, le=100), user: Dict = Depends(require_auth)):
    """List past writing sessions"""
    if not writing_runner_getter:
        raise HTTPException(status_code=503, detail="Writing runner not initialized")

    runner = writing_runner_getter()
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
