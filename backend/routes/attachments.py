"""
Attachment API Routes

Extracted from main_sdk.py as part of Phase 1 refactoring.
Handles file/image uploads, retrieval, and deletion.
"""

import re

from fastapi import APIRouter, HTTPException, File, UploadFile, Request, Depends
from fastapi.responses import Response
from typing import Optional

from auth import get_current_user

router = APIRouter(prefix="/attachments", tags=["attachments"])


# === Dependencies (injected at startup) ===

_attachment_manager = None
_get_current_user_func = None


def init_attachment_routes(attachment_manager, get_current_user_func):
    """Initialize route dependencies. Called from main_sdk.py startup."""
    global _attachment_manager, _get_current_user_func
    _attachment_manager = attachment_manager
    _get_current_user_func = get_current_user_func


# Conversation ids are uuid4 strings. conversation_id becomes a directory name
# under data/attachments/, so anything else (e.g. "../../x") is rejected.
_CONVERSATION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _validate_conversation_id(conversation_id: Optional[str]) -> Optional[str]:
    if conversation_id is None or conversation_id == "":
        return None
    if not _CONVERSATION_ID_RE.match(conversation_id):
        raise HTTPException(status_code=400, detail="Invalid conversation_id")
    return conversation_id


def _user_may_touch_conversation(conversation_id: Optional[str], user_id: str) -> bool:
    """True if the conversation has no owner, is owned by user_id, or user is admin."""
    if not conversation_id:
        return True
    from database import get_db
    with get_db() as conn:
        row = conn.execute(
            "SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if row is None or row[0] in (None, user_id):
            return True
        admin = conn.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
    return bool(admin and admin[0])


# === Attachment Endpoints ===

@router.post("/upload")
async def upload_attachment(
    request: Request,
    file: UploadFile = File(...),
    conversation_id: Optional[str] = None,
    current_user: str = Depends(get_current_user),
):
    """
    Upload a file/image attachment.

    Returns attachment metadata including ID for later retrieval.
    In session-only mode, attachments are cleaned up when session disconnects.
    """
    # Auth used to call get_current_user(request) directly, which returned its
    # own Depends() default as the "user" - i.e. no auth at all.
    conversation_id = _validate_conversation_id(conversation_id)
    if not _user_may_touch_conversation(conversation_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized for this conversation")

    # Read file data
    file_data = await file.read()

    # Validate size (max 10MB)
    if len(file_data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10MB.")

    # Get media type
    media_type = file.content_type or "application/octet-stream"

    # Save attachment
    metadata = _attachment_manager.save(
        file_data=file_data,
        filename=file.filename or "upload",
        media_type=media_type,
        conversation_id=conversation_id,
        session_id=current_user  # Use user ID as session ID for cleanup
    )

    return {
        "id": metadata.id,
        "filename": metadata.filename,
        "media_type": metadata.media_type,
        "size": metadata.size,
        "is_image": metadata.is_image,
        "url": f"/attachments/{metadata.id}"
    }


@router.get("/{attachment_id}")
async def get_attachment(attachment_id: str):
    """
    Serve an attachment file.

    Returns the file with appropriate Content-Type header.
    """
    result = _attachment_manager.get(attachment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_data, metadata = result

    return Response(
        content=file_data,
        media_type=metadata.media_type,
        headers={
            "Content-Disposition": f'inline; filename="{metadata.filename}"',
            "Cache-Control": "public, max-age=31536000"  # Cache for 1 year
        }
    )


@router.delete("/{attachment_id}")
async def delete_attachment(
    request: Request,
    attachment_id: str,
    current_user: str = Depends(get_current_user),
):
    """Delete an attachment (owner of its conversation, or an admin)."""
    metadata = _attachment_manager.get_metadata(attachment_id)
    if metadata and not _user_may_touch_conversation(metadata.conversation_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to delete this attachment")

    if _attachment_manager.delete(attachment_id):
        return {"status": "success", "message": "Attachment deleted"}
    else:
        raise HTTPException(status_code=404, detail="Attachment not found")
