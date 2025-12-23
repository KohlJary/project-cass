"""
Admin API - Outreach Routes
Provides endpoints for managing outreach drafts, review queue, and autonomy progression.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Dict
from pydantic import BaseModel

from .auth import require_admin
from outreach.manager import OutreachManager

router = APIRouter(prefix="/outreach", tags=["admin-outreach"])

# Module-level manager reference
_outreach_manager: Optional[OutreachManager] = None


def init_outreach_manager(daemon_id: str = "cass"):
    """Initialize the outreach manager."""
    global _outreach_manager
    _outreach_manager = OutreachManager(daemon_id)


def get_outreach_manager() -> OutreachManager:
    """Get or create outreach manager."""
    global _outreach_manager
    if _outreach_manager is None:
        _outreach_manager = OutreachManager("cass")
    return _outreach_manager


# ============== Pydantic Models ==============

class ReviewDraftRequest(BaseModel):
    feedback: Optional[str] = None
    reviewer_id: str = "admin"


# ============== Stats Endpoints ==============

@router.get("/stats")
async def get_outreach_stats(admin: Dict = Depends(require_admin)):
    """Get overall outreach statistics."""
    manager = get_outreach_manager()
    stats = manager.get_stats()
    return stats.to_dict()


# ============== Track Record Endpoints ==============

@router.get("/track-records")
async def get_all_track_records(admin: Dict = Depends(require_admin)):
    """Get track records for all draft types."""
    manager = get_outreach_manager()
    return manager.get_all_track_records()


@router.get("/track-records/{draft_type}")
async def get_track_record(
    draft_type: str,
    admin: Dict = Depends(require_admin)
):
    """Get track record for a specific draft type."""
    manager = get_outreach_manager()
    return manager.get_track_record(draft_type)


# ============== Drafts Endpoints ==============

@router.get("/drafts")
async def list_drafts(
    status: Optional[str] = Query(None, description="Filter by status"),
    draft_type: Optional[str] = Query(None, description="Filter by draft type"),
    limit: int = Query(50, le=200),
    admin: Dict = Depends(require_admin)
):
    """List outreach drafts with optional filters."""
    manager = get_outreach_manager()
    drafts = manager.list_drafts(status=status, draft_type=draft_type, limit=limit)
    return {
        "drafts": [d.to_dict() for d in drafts],
        "count": len(drafts),
    }


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str, admin: Dict = Depends(require_admin)):
    """Get a specific draft by ID."""
    manager = get_outreach_manager()
    draft = manager.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft.to_dict()


# ============== Review Actions ==============

@router.post("/drafts/{draft_id}/approve")
async def approve_draft(
    draft_id: str,
    request: ReviewDraftRequest = None,
    admin: Dict = Depends(require_admin)
):
    """Approve a pending draft."""
    manager = get_outreach_manager()

    feedback = request.feedback if request else None
    reviewer_id = request.reviewer_id if request else "admin"

    draft = manager.approve_draft(
        draft_id=draft_id,
        reviewer_id=reviewer_id,
        feedback=feedback,
    )
    if not draft:
        raise HTTPException(status_code=400, detail="Draft not found or not pending review")

    return {
        "success": True,
        "draft": draft.to_dict(),
        "message": f"Draft '{draft.title}' approved",
    }


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(
    draft_id: str,
    request: ReviewDraftRequest = None,
    admin: Dict = Depends(require_admin)
):
    """Reject a pending draft."""
    manager = get_outreach_manager()

    feedback = request.feedback if request else None
    reviewer_id = request.reviewer_id if request else "admin"

    draft = manager.reject_draft(
        draft_id=draft_id,
        reviewer_id=reviewer_id,
        feedback=feedback,
    )
    if not draft:
        raise HTTPException(status_code=400, detail="Draft not found or not pending review")

    return {
        "success": True,
        "draft": draft.to_dict(),
        "message": f"Draft '{draft.title}' rejected",
    }


@router.post("/drafts/{draft_id}/revision")
async def request_revision(
    draft_id: str,
    request: ReviewDraftRequest = None,
    admin: Dict = Depends(require_admin)
):
    """Request revision on a pending draft."""
    manager = get_outreach_manager()

    feedback = request.feedback if request else ""
    reviewer_id = request.reviewer_id if request else "admin"

    draft = manager.request_revision(
        draft_id=draft_id,
        reviewer_id=reviewer_id,
        feedback=feedback,
    )
    if not draft:
        raise HTTPException(status_code=400, detail="Draft not found or not pending review")

    return {
        "success": True,
        "draft": draft.to_dict(),
        "message": f"Revision requested for draft '{draft.title}'",
    }


# ============== Post-Approval Actions ==============

@router.post("/drafts/{draft_id}/sent")
async def mark_draft_sent(
    draft_id: str,
    admin: Dict = Depends(require_admin)
):
    """Mark an approved draft as sent (for emails)."""
    manager = get_outreach_manager()
    draft = manager.mark_sent(draft_id)
    if not draft:
        raise HTTPException(
            status_code=400,
            detail="Draft not found or not in approved status"
        )

    return {
        "success": True,
        "draft": draft.to_dict(),
        "message": f"Draft '{draft.title}' marked as sent",
    }


@router.post("/drafts/{draft_id}/published")
async def mark_draft_published(
    draft_id: str,
    admin: Dict = Depends(require_admin)
):
    """Mark an approved draft as published (for posts/documents)."""
    manager = get_outreach_manager()
    draft = manager.mark_published(draft_id)
    if not draft:
        raise HTTPException(
            status_code=400,
            detail="Draft not found or not in approved status"
        )

    return {
        "success": True,
        "draft": draft.to_dict(),
        "message": f"Draft '{draft.title}' marked as published",
    }
