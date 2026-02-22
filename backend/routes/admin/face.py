"""
Face Identification API endpoints.

Provides face enrollment and identification for visual recognition.
Similar structure to voice.py for consistency.
"""

import base64
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from face_identification import (
    get_enrollment_manager,
    get_enrollment_status,
    delete_enrollment,
    identify_face,
    is_available,
    ENROLLMENT_INSTRUCTIONS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/face", tags=["face"])


# =============================================================================
# Request/Response Models
# =============================================================================

class StartEnrollmentResponse(BaseModel):
    """Response from starting a face enrollment session."""
    session_id: str
    required_samples: int
    instructions: list[str]
    expires_at: str


class AddSampleRequest(BaseModel):
    """Request to add a face sample to enrollment."""
    session_id: str
    image: str  # Base64-encoded image data (JPEG/PNG)


class AddSampleResponse(BaseModel):
    """Response from adding a face sample."""
    accepted: bool
    quality_score: float
    sample_count: int
    required_samples: int
    feedback: str


class CompleteEnrollmentRequest(BaseModel):
    """Request to complete enrollment."""
    session_id: str


class CompleteEnrollmentResponse(BaseModel):
    """Response from completing enrollment."""
    success: bool
    enrollment_id: str
    sample_count: int
    quality_score: float


class EnrollmentStatusResponse(BaseModel):
    """Face enrollment status for a user."""
    enrolled: bool
    enrollment_id: Optional[str] = None
    sample_count: Optional[int] = None
    quality_score: Optional[float] = None
    created_at: Optional[str] = None


class IdentifyRequest(BaseModel):
    """Request to identify a face."""
    image: str  # Base64-encoded image data


class IdentifyResponse(BaseModel):
    """Response from face identification."""
    identified: bool
    user_id: Optional[str] = None
    display_name: Optional[str] = None
    confidence: float
    confidence_level: str  # high, medium, low, none


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/status")
async def face_status():
    """Check if face identification is available."""
    available = is_available()
    return {
        "available": available,
        "model": "face_recognition (dlib)" if available else None,
        "error": None if available else "face_recognition library not installed",
    }


@router.get("/instructions")
async def get_instructions():
    """Get enrollment instructions/prompts."""
    return {
        "instructions": ENROLLMENT_INSTRUCTIONS,
        "count": len(ENROLLMENT_INSTRUCTIONS),
    }


@router.get("/enroll/status")
async def enrollment_status(user_id: str):
    """Check if a user has enrolled their face."""
    status = await get_enrollment_status(user_id)
    return EnrollmentStatusResponse(**status)


@router.post("/enroll/start", response_model=StartEnrollmentResponse)
async def start_enrollment(user_id: str):
    """Start a face enrollment session."""
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="Face identification not available"
        )

    manager = get_enrollment_manager()
    result = manager.start_session(user_id)

    return StartEnrollmentResponse(**result)


@router.post("/enroll/sample", response_model=AddSampleResponse)
async def add_enrollment_sample(request: AddSampleRequest):
    """Add a face sample to an enrollment session."""
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="Face identification not available"
        )

    # Decode image
    try:
        image_data = base64.b64decode(request.image)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}")

    manager = get_enrollment_manager()

    try:
        result = await manager.add_sample(request.session_id, image_data)
        return AddSampleResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/enroll/complete", response_model=CompleteEnrollmentResponse)
async def complete_enrollment(request: CompleteEnrollmentRequest):
    """Complete face enrollment and create faceprint."""
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="Face identification not available"
        )

    manager = get_enrollment_manager()

    try:
        result = await manager.complete_enrollment(request.session_id)
        return CompleteEnrollmentResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/enroll")
async def remove_enrollment(user_id: str):
    """Delete face enrollment for a user."""
    deleted = await delete_enrollment(user_id)

    if deleted:
        return {"success": True, "message": "Face enrollment deleted"}
    else:
        return {"success": False, "message": "No enrollment found"}


@router.post("/identify", response_model=IdentifyResponse)
async def identify(request: IdentifyRequest):
    """Identify a face from an image."""
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="Face identification not available"
        )

    # Decode image
    try:
        image_data = base64.b64decode(request.image)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}")

    match = await identify_face(image_data)

    if match is None:
        return IdentifyResponse(
            identified=False,
            confidence=0.0,
            confidence_level="none",
        )

    return IdentifyResponse(
        identified=match.user_id is not None,
        user_id=match.user_id,
        display_name=match.display_name,
        confidence=match.confidence,
        confidence_level=match.confidence_level.value,
    )
