"""
Admin API routes for Wonderland Session Viewer.

Provides endpoints for:
- Starting/ending exploration sessions
- Listing sessions
- Exporting session transcripts
- WebSocket streaming of live exploration events
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from wonderland.session_controller import SessionController, SessionStatus, GOAL_PRESETS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wonderland", tags=["wonderland"])

# Module-level session controller (initialized lazily)
_session_controller: Optional[SessionController] = None


def get_session_controller() -> SessionController:
    """Get or create the session controller."""
    global _session_controller
    if _session_controller is None:
        _session_controller = SessionController()
    return _session_controller


class StartSessionRequest(BaseModel):
    """Request to start a new exploration session."""
    daemon_name: str = "Cass"
    daemon_id: Optional[str] = None  # If provided, load real identity
    personality: Optional[str] = None
    goal_preset: Optional[str] = None  # e.g., "VISIT_ROOMS_3"


class GoalInfo(BaseModel):
    """Goal information in response."""
    goal_id: str
    title: str
    goal_type: str
    target_value: int
    current_value: int
    is_completed: bool


class StartSessionResponse(BaseModel):
    """Response from starting a session."""
    session_id: str
    daemon_name: str
    status: str
    current_room: str
    current_room_name: str
    goal: Optional[GoalInfo] = None


@router.post("/sessions", response_model=StartSessionResponse)
async def start_session(
    request: StartSessionRequest,
    user_id: str = Query(..., description="User ID of the spectator"),
):
    """
    Start a new Wonderland exploration session.

    The daemon will begin autonomous exploration, streaming events
    to connected spectators via WebSocket.
    """
    controller = get_session_controller()

    # Check for existing active session
    existing = [
        s for s in controller.list_sessions(user_id)
        if s.status == SessionStatus.ACTIVE
    ]
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Active session already exists: {existing[0].session_id}"
        )

    # Start new session
    kwargs = {"user_id": user_id, "daemon_name": request.daemon_name}

    # Load real identity if daemon_id provided
    if request.daemon_id and not request.personality:
        try:
            from identity_snippets import get_active_snippet
            snippet = get_active_snippet(request.daemon_id)
            if snippet and snippet.get("snippet_text"):
                kwargs["personality"] = snippet["snippet_text"]
                logger.info(f"Loaded real identity for daemon {request.daemon_id}")
        except Exception as e:
            logger.warning(f"Could not load identity for {request.daemon_id}: {e}")

    if request.personality:
        kwargs["personality"] = request.personality

    # Add goal preset if provided
    if request.goal_preset and request.goal_preset in GOAL_PRESETS:
        kwargs["goal_preset"] = request.goal_preset

    session = await controller.start_session(**kwargs)

    # Build response with optional goal info
    goal_info = None
    if session.exploration_goal:
        goal = session.exploration_goal
        goal_info = GoalInfo(
            goal_id=goal.goal_id,
            title=goal.title,
            goal_type=goal.goal_type,
            target_value=goal.target_value,
            current_value=goal.current_value,
            is_completed=goal.is_completed,
        )

    return StartSessionResponse(
        session_id=session.session_id,
        daemon_name=session.daemon_name,
        status=session.status.value,
        current_room=session.current_room,
        current_room_name=session.current_room_name,
        goal=goal_info,
    )


@router.get("/sessions")
async def list_sessions(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
):
    """List exploration sessions."""
    controller = get_session_controller()
    sessions = controller.list_sessions(user_id)

    if status:
        try:
            status_filter = SessionStatus(status)
            sessions = [s for s in sessions if s.status == status_filter]
        except ValueError:
            pass

    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "daemon_name": s.daemon_name,
                "user_id": s.user_id,
                "status": s.status.value,
                "started_at": s.started_at.isoformat(),
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "rooms_visited": len(s.rooms_visited),
                "event_count": len(s.events),
            }
            for s in sessions
        ]
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get details of a specific session."""
    controller = get_session_controller()
    session = controller.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.to_dict()


@router.post("/sessions/{session_id}/end")
async def end_session(
    session_id: str,
    reason: str = Query("user_request", description="Reason for ending"),
):
    """End an active exploration session."""
    controller = get_session_controller()
    session = await controller.end_session(session_id, reason)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.session_id,
        "status": session.status.value,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "end_reason": session.end_reason,
        "rooms_visited": len(session.rooms_visited),
        "event_count": len(session.events),
    }


@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    format: str = Query("md", description="Export format: md or json"),
):
    """Export a session transcript."""
    controller = get_session_controller()
    content = controller.export_session(session_id, format)

    if content is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "format": format,
        "content": content,
    }


@router.websocket("/sessions/{session_id}/stream")
async def stream_session(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for streaming session events.

    Connect to receive live updates as the daemon explores.
    Messages are JSON with format:
    - {"type": "session_state", "session": {...}, "current_room": "..."}
    - {"type": "session_event", "event": {...}}
    - {"type": "session_ended", "session_id": "...", "reason": "..."}
    """
    controller = get_session_controller()
    session = controller.get_session(session_id)

    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()
    logger.info(f"Spectator connected to session {session_id}")

    try:
        # Register as spectator
        await controller.add_spectator(session_id, websocket)

        # Keep connection open until session ends or client disconnects
        while True:
            # Wait for messages (ping/pong, or explicit close)
            try:
                data = await websocket.receive_text()
                # Handle ping
                if data == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break

    except Exception as e:
        logger.error(f"WebSocket error in session {session_id}: {e}")
    finally:
        controller.remove_spectator(session_id, websocket)
        logger.info(f"Spectator disconnected from session {session_id}")


# Goal presets endpoint
@router.get("/presets")
async def get_goal_presets():
    """
    Get available goal presets for exploration sessions.

    Returns a list of preset IDs with their titles and types.
    Use these IDs when starting a session with a goal.
    """
    return {
        "presets": [
            {
                "id": preset_id,
                "title": preset["title"],
                "type": preset["type"],
                "target": preset["target"],
            }
            for preset_id, preset in GOAL_PRESETS.items()
        ]
    }


# World info endpoints (for reference)
@router.get("/world/stats")
async def get_world_stats():
    """Get current world statistics."""
    controller = get_session_controller()
    world = controller.world

    return {
        "total_rooms": len(world.rooms),
        "active_daemons": len(world.daemons),
        "active_custodians": len(world.custodians),
        "recent_events": len(world.events),
        "active_sessions": len([
            s for s in controller.sessions.values()
            if s.status == SessionStatus.ACTIVE
        ]),
    }


@router.get("/world/realms")
async def get_realms():
    """Get list of available realms."""
    controller = get_session_controller()
    registry = controller.mythology

    return {
        "realms": [
            {
                "id": realm.realm_id,
                "name": realm.name,
                "tradition": realm.tradition,
                "themes": realm.themes,
                "room_count": len(realm.rooms),
                "npc_count": len(realm.npcs),
            }
            for realm in registry.realms.values()
        ]
    }


@router.get("/world/living")
async def get_living_world():
    """Get the Living World state - time, NPC locations, recent events."""
    controller = get_session_controller()

    return controller.world_simulation.get_world_state_summary()
