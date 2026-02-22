"""
Voice Identification API endpoints.

Handles voice enrollment and speaker identification.
"""

import base64
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from voice_identification import (
    get_voice_manager,
    identify_speaker,
    is_voice_enrolled,
    ENROLLMENT_PHRASES,
    THRESHOLD_HIGH,
    THRESHOLD_MEDIUM,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


# =============================================================================
# Request/Response Models
# =============================================================================

class StartEnrollmentResponse(BaseModel):
    """Response when starting enrollment."""
    session_id: str
    required_samples: int
    phrases: list[str]
    expires_at: str


class AddSampleRequest(BaseModel):
    """Request to add a voice sample."""
    session_id: str
    phrase_index: int
    audio: str  # Base64-encoded audio


class AddSampleResponse(BaseModel):
    """Response after adding a sample."""
    accepted: bool
    quality_score: float
    sample_count: int
    required_samples: int
    feedback: str


class CompleteEnrollmentRequest(BaseModel):
    """Request to complete enrollment."""
    session_id: str


class CompleteEnrollmentResponse(BaseModel):
    """Response after completing enrollment."""
    success: bool
    enrollment_id: str
    sample_count: int
    quality_score: float


class EnrollmentStatusResponse(BaseModel):
    """Current enrollment status for a user."""
    enrolled: bool
    sample_count: Optional[int] = None
    quality_score: Optional[float] = None
    created_at: Optional[str] = None


class IdentifyRequest(BaseModel):
    """Request to identify a speaker."""
    audio: str  # Base64-encoded audio


class IdentifyResponse(BaseModel):
    """Speaker identification result."""
    identified: bool
    user_id: Optional[str] = None
    display_name: Optional[str] = None
    confidence: float
    confidence_level: str  # "high", "medium", "low", "none"


# =============================================================================
# Enrollment Endpoints
# =============================================================================

@router.post("/enroll/start", response_model=StartEnrollmentResponse)
async def start_enrollment(user_id: str):
    """
    Start a voice enrollment session.

    Returns the required phrases to record.
    """
    try:
        manager = get_voice_manager()
        result = manager.start_enrollment_session(user_id)

        return StartEnrollmentResponse(
            session_id=result["session_id"],
            required_samples=result["required_samples"],
            phrases=result["phrases"],
            expires_at=result["expires_at"],
        )

    except Exception as e:
        logger.error(f"Failed to start enrollment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enroll/sample", response_model=AddSampleResponse)
async def add_enrollment_sample(request: AddSampleRequest):
    """
    Add a voice sample to an enrollment session.

    Returns quality feedback.
    """
    try:
        # Decode audio
        audio_bytes = base64.b64decode(request.audio)

        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty audio data")

        manager = get_voice_manager()
        result = manager.add_enrollment_sample(
            session_id=request.session_id,
            phrase_index=request.phrase_index,
            audio_bytes=audio_bytes,
        )

        return AddSampleResponse(
            accepted=result["accepted"],
            quality_score=result["quality_score"],
            sample_count=result.get("sample_count", 0),
            required_samples=result.get("required_samples", len(ENROLLMENT_PHRASES)),
            feedback=result["feedback"],
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to add sample: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enroll/complete", response_model=CompleteEnrollmentResponse)
async def complete_enrollment(request: CompleteEnrollmentRequest):
    """
    Complete enrollment and generate voiceprint.

    Requires all phrases to be recorded.
    """
    try:
        manager = get_voice_manager()
        result = manager.complete_enrollment(request.session_id)

        return CompleteEnrollmentResponse(
            success=result["success"],
            enrollment_id=result["enrollment_id"],
            sample_count=result["sample_count"],
            quality_score=result["quality_score"],
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to complete enrollment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/enroll")
async def delete_enrollment(user_id: str):
    """Delete a user's voice enrollment."""
    try:
        manager = get_voice_manager()
        deleted = manager.delete_enrollment(user_id)

        return {
            "success": deleted,
            "message": "Enrollment deleted" if deleted else "No enrollment found",
        }

    except Exception as e:
        logger.error(f"Failed to delete enrollment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enroll/status", response_model=EnrollmentStatusResponse)
async def get_enrollment_status(user_id: str):
    """Check enrollment status for a user."""
    try:
        manager = get_voice_manager()
        enrollment = manager.get_enrollment(user_id)

        if enrollment:
            return EnrollmentStatusResponse(
                enrolled=True,
                sample_count=enrollment["sample_count"],
                quality_score=enrollment["quality_score"],
                created_at=enrollment["created_at"],
            )
        else:
            return EnrollmentStatusResponse(enrolled=False)

    except Exception as e:
        logger.error(f"Failed to get enrollment status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Identification Endpoints
# =============================================================================

@router.post("/identify", response_model=IdentifyResponse)
async def identify_speaker_endpoint(request: IdentifyRequest):
    """
    Identify who is speaking from audio.

    Returns the matched user if confidence is above threshold.
    """
    try:
        # Decode audio
        audio_bytes = base64.b64decode(request.audio)

        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty audio data")

        # Identify speaker
        result = identify_speaker(audio_bytes)

        # Determine confidence level
        if result.confidence >= THRESHOLD_HIGH:
            confidence_level = "high"
        elif result.confidence >= THRESHOLD_MEDIUM:
            confidence_level = "medium"
        elif result.confidence >= 0.5:
            confidence_level = "low"
        else:
            confidence_level = "none"

        return IdentifyResponse(
            identified=result.user_id is not None,
            user_id=result.user_id,
            display_name=result.display_name,
            confidence=result.confidence,
            confidence_level=confidence_level,
        )

    except Exception as e:
        logger.error(f"Speaker identification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/phrases")
async def get_enrollment_phrases():
    """Get the list of enrollment phrases."""
    return {
        "phrases": ENROLLMENT_PHRASES,
        "count": len(ENROLLMENT_PHRASES),
    }
