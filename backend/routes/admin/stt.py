"""
Speech-to-Text API endpoint for smart speaker integration.

Accepts audio data and returns transcription using Whisper.
"""

import base64
import logging
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stt", tags=["stt"])

# Lazy-load whisper to avoid startup cost if not used
_whisper_model = None
_whisper_model_name = os.getenv("WHISPER_MODEL", "base")


def get_whisper_model():
    """Lazy-load Whisper model."""
    global _whisper_model

    if _whisper_model is None:
        try:
            import whisper
            logger.info(f"Loading Whisper model: {_whisper_model_name}")
            _whisper_model = whisper.load_model(_whisper_model_name)
            logger.info("Whisper model loaded")
        except ImportError:
            logger.error("Whisper not installed. Install with: pip install openai-whisper")
            raise HTTPException(
                status_code=503,
                detail="Speech-to-text not available (whisper not installed)"
            )
        except Exception as e:
            logger.error(f"Failed to load Whisper: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Speech-to-text not available: {e}"
            )

    return _whisper_model


class TranscribeRequest(BaseModel):
    """Request body for transcription."""
    audio: str  # Base64-encoded audio data
    format: str = "wav"  # Audio format: wav, mp3, webm, etc.
    language: Optional[str] = None  # Optional language hint (e.g., "en")


class TranscribeResponse(BaseModel):
    """Response from transcription."""
    text: str
    language: str
    duration: float  # Audio duration in seconds


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(request: TranscribeRequest):
    """
    Transcribe audio to text using Whisper.

    Accepts base64-encoded audio data in various formats (wav, mp3, webm, etc.).
    Returns the transcribed text along with detected language and duration.
    """
    model = get_whisper_model()

    # Decode audio
    try:
        audio_bytes = base64.b64decode(request.audio)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 audio: {e}")

    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty audio data")

    # Write to temp file (Whisper needs file path)
    suffix = f".{request.format}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name

    try:
        # Transcribe
        options = {"fp16": False}  # Disable FP16 for CPU compatibility
        if request.language:
            options["language"] = request.language

        result = model.transcribe(temp_path, **options)

        text = result["text"].strip()
        language = result.get("language", "unknown")

        # Get duration from segments
        segments = result.get("segments", [])
        duration = segments[-1]["end"] if segments else 0.0

        logger.info(f"Transcribed {len(audio_bytes)} bytes: '{text[:50]}...' ({language})")

        return TranscribeResponse(
            text=text,
            language=language,
            duration=duration
        )

    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    finally:
        # Clean up temp file
        try:
            os.unlink(temp_path)
        except Exception:
            pass


@router.get("/status")
async def stt_status():
    """Check if STT service is available."""
    try:
        import whisper
        return {
            "available": True,
            "model": _whisper_model_name,
            "loaded": _whisper_model is not None,
        }
    except ImportError:
        return {
            "available": False,
            "model": None,
            "loaded": False,
            "error": "whisper not installed"
        }
