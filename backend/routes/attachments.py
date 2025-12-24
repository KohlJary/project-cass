"""
Attachment API Routes

Extracted from main_sdk.py as part of Phase 1 refactoring.
Handles file/image uploads, retrieval, and deletion.
"""

from fastapi import APIRouter, HTTPException, File, UploadFile, Request
from fastapi.responses import Response
from typing import Optional

router = APIRouter(prefix="/attachments", tags=["attachments"])


# === Dependencies (injected at startup) ===

_attachment_manager = None
_get_current_user_func = None


def init_attachment_routes(attachment_manager, get_current_user_func):
    """Initialize route dependencies. Called from main_sdk.py startup."""
    global _attachment_manager, _get_current_user_func
    _attachment_manager = attachment_manager
    _get_current_user_func = get_current_user_func


async def _get_current_user(request: Request):
    """Wrapper to call the injected get_current_user function."""
    return await _get_current_user_func(request)


# === Attachment Endpoints ===

@router.post("/upload")
async def upload_attachment(
    request: Request,
    file: UploadFile = File(...),
    conversation_id: Optional[str] = None,
):
    """
    Upload a file/image attachment.

    Returns attachment metadata including ID for later retrieval.
    In session-only mode, attachments are cleaned up when session disconnects.
    """
    current_user = await _get_current_user(request)

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
):
    """Delete an attachment."""
    current_user = await _get_current_user(request)  # noqa: F841 - may be needed for auth

    if _attachment_manager.delete(attachment_id):
        return {"status": "success", "message": "Attachment deleted"}
    else:
        raise HTTPException(status_code=404, detail="Attachment not found")
