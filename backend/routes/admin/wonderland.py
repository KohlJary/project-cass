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
from wonderland.npc_conversation import NPCConversationHandler, ConversationStatus
import uuid

logger = logging.getLogger(__name__)

# NPC Conversation handler (initialized lazily)
_conversation_handler: Optional[NPCConversationHandler] = None


def get_conversation_handler() -> NPCConversationHandler:
    """Get or create the NPC conversation handler."""
    global _conversation_handler
    if _conversation_handler is None:
        _conversation_handler = NPCConversationHandler()
    return _conversation_handler

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

    # Pass source_daemon_id for dynamic identity context building
    # The session controller will use GlobalState to build identity
    # including growth edges, interests, open questions, emotional state
    if request.daemon_id:
        kwargs["source_daemon_id"] = request.daemon_id
        logger.info(f"Will build dynamic identity context for daemon {request.daemon_id}")

    # Allow explicit personality override if provided
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


# =============================================================================
# NPC CONVERSATION ENDPOINTS
# =============================================================================

class StartConversationRequest(BaseModel):
    """Request to start an NPC conversation."""
    daemon_id: str
    daemon_name: str
    npc_id: str
    room_id: str
    session_id: Optional[str] = None


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    message: str


@router.post("/npc/conversations")
async def start_npc_conversation(request: StartConversationRequest):
    """
    Start a conversation with an NPC.

    Returns the NPC's initial greeting based on their semantic pointer-set.
    The greeting warmth is affected by the NPC's disposition toward this daemon.
    """
    controller = get_session_controller()
    handler = get_conversation_handler()

    # Find the NPC in mythology registry
    npc = controller.mythology.get_npc(request.npc_id)
    if not npc:
        raise HTTPException(status_code=404, detail=f"NPC not found: {request.npc_id}")

    # Start the conversation
    conversation_id = str(uuid.uuid4())[:8]
    conversation = handler.start_conversation(
        conversation_id=conversation_id,
        session_id=request.session_id or "direct",
        daemon_id=request.daemon_id,
        daemon_name=request.daemon_name,
        npc=npc,
        room_id=request.room_id,
    )

    if not conversation:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start conversation - NPC {request.npc_id} has no pointer-set"
        )

    # Generate initial greeting
    greeting = await handler.generate_initial_greeting(conversation_id)

    return {
        "conversation_id": conversation_id,
        "npc_id": npc.npc_id,
        "npc_name": npc.name,
        "npc_title": npc.title,
        "status": conversation.status.value,
        "greeting": greeting,
        "messages": [m.to_dict() for m in conversation.messages],
    }


@router.get("/npc/conversations/{conversation_id}")
async def get_npc_conversation(conversation_id: str):
    """Get the current state of an NPC conversation."""
    handler = get_conversation_handler()
    conversation = handler.get_conversation(conversation_id)

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation.to_dict()


@router.post("/npc/conversations/{conversation_id}/message")
async def send_npc_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message to the NPC and receive their response.

    The NPC's response is generated via LLM using their semantic pointer-set,
    conversation history, memory of past interactions, and disposition.
    """
    handler = get_conversation_handler()
    conversation = handler.get_conversation(conversation_id)

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.status != ConversationStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Conversation is not active")

    # Generate NPC response
    response = await handler.generate_npc_response(conversation_id, request.message)

    if response is None:
        raise HTTPException(status_code=500, detail="Failed to generate NPC response")

    return {
        "conversation_id": conversation_id,
        "npc_response": response,
        "messages": [m.to_dict() for m in conversation.messages],
        "message_count": len(conversation.messages),
    }


@router.post("/npc/conversations/{conversation_id}/end")
async def end_npc_conversation(conversation_id: str):
    """
    End an NPC conversation.

    This triggers conversation summarization and memory storage.
    The NPC will remember this conversation in future interactions.
    """
    handler = get_conversation_handler()
    conversation = handler.get_conversation(conversation_id)

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Summarize and store in NPC memory
    memory = await handler.summarize_and_remember(conversation_id)

    # End the conversation
    handler.end_conversation(conversation_id)

    return {
        "conversation_id": conversation_id,
        "status": "ended",
        "message_count": len(conversation.messages),
        "memory_stored": memory is not None,
        "memory": {
            "topics": memory.topics if memory else [],
            "sentiment": memory.sentiment if memory else None,
            "memorable_quote": memory.memorable_quote if memory else None,
        } if memory else None,
    }


@router.get("/npc/{npc_id}")
async def get_npc_info(npc_id: str):
    """Get information about an NPC including their current state."""
    controller = get_session_controller()

    # Get NPC from mythology
    npc = controller.mythology.get_npc(npc_id)
    if not npc:
        raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")

    # Get NPC state
    from wonderland.npc_state import get_npc_state_manager
    state_manager = get_npc_state_manager()
    state = state_manager.get_state(npc_id)

    return {
        "npc_id": npc.npc_id,
        "name": npc.name,
        "title": npc.title,
        "archetype": npc.archetype.value if npc.archetype else None,
        "tradition": npc.tradition,
        "description": npc.description,
        "current_room": state.current_room if state else npc.current_room,
        "activity": state.activity.value if state else "idle",
        "behavior_type": state.behavior_type.value if state else None,
        "memory_count": len(state.memories) if state else 0,
    }
