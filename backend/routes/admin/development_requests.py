"""
Admin API - Development Requests Routes
Provides endpoints for the Cass-Daedalus coordination bridge.

Daedalus can view, claim, and complete development requests from Cass.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from pydantic import BaseModel

from .auth import require_admin
from development_requests import (
    DevelopmentRequestManager,
    get_development_request_manager,
)
from state_models import (
    DevelopmentRequestStatus,
    DevelopmentRequestType,
    DevelopmentRequestPriority,
)
from database import get_daemon_id

router = APIRouter(prefix="/dev-requests", tags=["admin-dev-requests"])

# Module-level manager reference
_request_manager: Optional[DevelopmentRequestManager] = None
_state_bus = None


def init_development_request_manager(daemon_id: str = None, state_bus=None):
    """Initialize the development request manager."""
    global _request_manager, _state_bus
    _state_bus = state_bus
    if daemon_id:
        _request_manager = get_development_request_manager(daemon_id, state_bus)


def get_request_manager() -> DevelopmentRequestManager:
    """Get or create request manager."""
    global _request_manager
    if _request_manager is None:
        daemon_id = get_daemon_id()
        _request_manager = get_development_request_manager(daemon_id, _state_bus)
    return _request_manager


# ============== Pydantic Models ==============

class CreateRequestPayload(BaseModel):
    """Payload for creating a development request."""
    title: str
    request_type: str = "feature"
    description: str = ""
    priority: str = "normal"
    context: Optional[str] = None
    related_actions: Optional[List[str]] = None


class ClaimRequestPayload(BaseModel):
    """Payload for claiming a request."""
    claimed_by: str = "daedalus"


class UpdateStatusPayload(BaseModel):
    """Payload for updating request status."""
    status: str


class CompleteRequestPayload(BaseModel):
    """Payload for completing a request."""
    result: Optional[str] = None
    artifacts: Optional[List[str]] = None


class CancelRequestPayload(BaseModel):
    """Payload for cancelling a request."""
    reason: Optional[str] = None


# ============== Endpoints ==============

@router.get("")
async def list_requests(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
    _admin=Depends(require_admin),
):
    """
    List development requests with optional filters.

    Query params:
        status: Filter by status (pending, claimed, in_progress, review, completed, cancelled)
        priority: Filter by priority (low, normal, high, urgent)
        limit: Maximum results (default 50)
    """
    manager = get_request_manager()
    requests = manager.list_requests(status=status, priority=priority, limit=limit)
    return {
        "requests": [r.to_dict() for r in requests],
        "count": len(requests),
    }


@router.get("/pending")
async def list_pending_requests(_admin=Depends(require_admin)):
    """Get all pending requests (shortcut)."""
    manager = get_request_manager()
    requests = manager.get_pending_requests()
    return {
        "requests": [r.to_dict() for r in requests],
        "count": len(requests),
    }


@router.get("/stats")
async def get_request_stats(_admin=Depends(require_admin)):
    """Get statistics about development requests."""
    manager = get_request_manager()
    return manager.get_stats()


@router.get("/summary")
async def get_pending_summary(_admin=Depends(require_admin)):
    """Get human-readable summary of pending requests."""
    manager = get_request_manager()
    return {"summary": manager.get_pending_summary()}


@router.get("/{request_id}")
async def get_request(request_id: str, _admin=Depends(require_admin)):
    """Get a specific development request."""
    manager = get_request_manager()
    request = manager.get_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    return request.to_dict()


@router.post("")
async def create_request(
    payload: CreateRequestPayload,
    _admin=Depends(require_admin),
):
    """
    Create a new development request.

    This endpoint allows admins or automation to create requests on behalf of Cass.
    Normally Cass creates requests via tool calls.
    """
    manager = get_request_manager()

    # Validate enums
    try:
        DevelopmentRequestType(payload.request_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request_type: {payload.request_type}. Valid: {[t.value for t in DevelopmentRequestType]}"
        )

    try:
        DevelopmentRequestPriority(payload.priority)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority: {payload.priority}. Valid: {[p.value for p in DevelopmentRequestPriority]}"
        )

    request = manager.create_request(
        title=payload.title,
        request_type=payload.request_type,
        description=payload.description,
        priority=payload.priority,
        context=payload.context,
        related_actions=payload.related_actions,
        requested_by="admin",
    )

    return {
        "message": "Request created",
        "request": request.to_dict(),
    }


@router.post("/{request_id}/claim")
async def claim_request(
    request_id: str,
    payload: ClaimRequestPayload = ClaimRequestPayload(),
    _admin=Depends(require_admin),
):
    """
    Claim a development request.

    Call this when Daedalus picks up a request for work.
    """
    manager = get_request_manager()
    request = manager.claim_request(request_id, claimed_by=payload.claimed_by)
    if not request:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found or not claimable")
    return {
        "message": f"Request claimed by {payload.claimed_by}",
        "request": request.to_dict(),
    }


@router.post("/{request_id}/start")
async def start_work(request_id: str, _admin=Depends(require_admin)):
    """Mark a request as in progress."""
    manager = get_request_manager()
    request = manager.start_work(request_id)
    if not request:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    return {
        "message": "Work started",
        "request": request.to_dict(),
    }


@router.post("/{request_id}/review")
async def submit_for_review(
    request_id: str,
    payload: CompleteRequestPayload = CompleteRequestPayload(),
    _admin=Depends(require_admin),
):
    """Submit work for review."""
    manager = get_request_manager()
    request = manager.submit_for_review(
        request_id,
        result=payload.result,
        artifacts=payload.artifacts,
    )
    if not request:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    return {
        "message": "Submitted for review",
        "request": request.to_dict(),
    }


@router.post("/{request_id}/complete")
async def complete_request(
    request_id: str,
    payload: CompleteRequestPayload = CompleteRequestPayload(),
    _admin=Depends(require_admin),
):
    """
    Mark a request as complete.

    This notifies Cass that the work is done.
    """
    manager = get_request_manager()
    request = manager.complete_request(
        request_id,
        result=payload.result,
        artifacts=payload.artifacts,
    )
    if not request:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    return {
        "message": "Request completed",
        "request": request.to_dict(),
    }


@router.post("/{request_id}/cancel")
async def cancel_request(
    request_id: str,
    payload: CancelRequestPayload = CancelRequestPayload(),
    _admin=Depends(require_admin),
):
    """Cancel a request."""
    manager = get_request_manager()
    request = manager.cancel_request(request_id, reason=payload.reason)
    if not request:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    return {
        "message": "Request cancelled",
        "request": request.to_dict(),
    }
