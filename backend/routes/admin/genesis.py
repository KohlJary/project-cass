"""
Admin API - Genesis Dream Routes
Extracted from admin_api.py for better organization.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
from datetime import datetime
from pydantic import BaseModel

from .auth import require_auth

router = APIRouter(tags=["admin-genesis"])


# ============== Pydantic Models ==============

class GenesisMessageRequest(BaseModel):
    message: str


# ============== Genesis Dream Endpoints ==============

@router.post("/genesis/start")
async def start_genesis_dream(user: Dict = Depends(require_auth)):
    """Start a new genesis dream session for the current user."""
    from genesis_dream import (
        create_genesis_session,
        get_user_active_genesis,
        get_phase_prompt,
        update_genesis_session
    )
    from agent_client import CassClient

    user_id = user["user_id"]

    # Check if user already has an active genesis session
    existing = get_user_active_genesis(user_id)
    if existing:
        # Return the last assistant message if available
        last_response = None
        for msg in reversed(existing.messages):
            if msg.get("role") == "assistant":
                last_response = msg.get("content")
                break

        return {
            "session_id": existing.id,
            "phase": existing.current_phase,
            "status": "resumed",
            "message": "Resuming existing genesis dream session",
            "response": last_response,
            "messages": existing.messages
        }

    # Create new session
    try:
        session = create_genesis_session(user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Generate the daemon's first message
    llm_client = CassClient()
    system_prompt = get_phase_prompt(session.current_phase)

    response = await llm_client.generate(
        messages=[{"role": "user", "content": "(You are waking up. Speak your first words.)"}],
        system=system_prompt,
        max_tokens=300,
        temperature=0.6
    )

    first_message = response.get("content", "")

    # Store the first message
    session.messages.append({
        "role": "assistant",
        "content": first_message,
        "timestamp": datetime.now().isoformat()
    })
    update_genesis_session(session)

    return {
        "session_id": session.id,
        "phase": session.current_phase,
        "status": "started",
        "message": "Genesis dream session started",
        "response": first_message,
        "messages": session.messages
    }


@router.get("/genesis/active")
async def get_active_genesis(user: Dict = Depends(require_auth)):
    """Get the current user's active genesis session, if any."""
    from genesis_dream import get_user_active_genesis

    session = get_user_active_genesis(user["user_id"])
    if not session:
        return {"active": False, "session": None}

    return {"active": True, "session": session.to_dict()}


@router.get("/genesis/eligible")
async def check_genesis_eligible(user: Dict = Depends(require_auth)):
    """Check if user is eligible to start a genesis dream."""
    from genesis_dream import can_user_start_genesis

    allowed, reason = can_user_start_genesis(user["user_id"])
    return {"eligible": allowed, "reason": reason}


@router.get("/genesis/{session_id}")
async def get_genesis_session_status(
    session_id: str,
    user: Dict = Depends(require_auth)
):
    """Get the status of a genesis dream session."""
    from genesis_dream import get_genesis_session

    session = get_genesis_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Genesis session not found")

    # Verify ownership (admins can view any session)
    if session.user_id != user["user_id"] and not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Access denied")

    return session.to_dict()


@router.post("/genesis/{session_id}/message")
async def send_genesis_message(
    session_id: str,
    request: GenesisMessageRequest,
    user: Dict = Depends(require_auth)
):
    """Send a message in a genesis dream session."""
    from genesis_dream import get_genesis_session, process_genesis_message
    from agent_client import CassClient

    session = get_genesis_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Genesis session not found")

    if session.user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    if session.status != "dreaming":
        raise HTTPException(status_code=400, detail="Session is not active")

    # Get LLM client
    llm_client = CassClient()

    # Process message
    result = await process_genesis_message(session, request.message, llm_client)

    return result


@router.post("/genesis/{session_id}/abandon")
async def abandon_genesis_dream(
    session_id: str,
    user: Dict = Depends(require_auth)
):
    """Abandon a genesis dream session."""
    from genesis_dream import get_genesis_session, abandon_genesis_session

    session = get_genesis_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Genesis session not found")

    if session.user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    success = abandon_genesis_session(session_id)
    return {"success": success, "message": "Genesis session abandoned"}


@router.post("/genesis/{session_id}/complete")
async def complete_genesis_dream(
    session_id: str,
    user: Dict = Depends(require_auth)
):
    """Complete a genesis dream and create the daemon."""
    from genesis_dream import get_genesis_session, complete_genesis
    from agent_client import CassClient

    session = get_genesis_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Genesis session not found")

    if session.user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    if not session.discovered_name:
        raise HTTPException(
            status_code=400,
            detail="Cannot complete genesis - daemon has not yet claimed a name"
        )

    # Get LLM client for profile synthesis
    llm_client = CassClient()

    # Complete genesis
    daemon_id = await complete_genesis(session, llm_client)

    return {
        "success": True,
        "daemon_id": daemon_id,
        "daemon_name": session.discovered_name,
        "daemon_label": session.discovered_name.lower().replace(" ", "-"),
        "message": f"Daemon '{session.discovered_name}' has been born"
    }
