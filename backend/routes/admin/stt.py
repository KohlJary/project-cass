"""
Speech-to-Text API endpoint for smart speaker integration.

Accepts audio data and returns transcription using Whisper.
Uses GPU coordinator to manage VRAM allocation.
"""

import asyncio
import base64
import logging
import os
import tempfile
from typing import Optional

# Ensure ffmpeg is in PATH (systemd services have minimal PATH)
_ffmpeg_paths = ["/sbin", "/usr/sbin", "/usr/local/bin"]
_current_path = os.environ.get("PATH", "")
for p in _ffmpeg_paths:
    if p not in _current_path:
        os.environ["PATH"] = f"{p}:{_current_path}"
        _current_path = os.environ["PATH"]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gpu_coordinator import get_gpu_coordinator, GPUService
from voice_identification import identify_speaker as identify_speaker_from_audio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stt", tags=["stt"])

# Lazy-load whisper to avoid startup cost if not used
_whisper_model = None
_whisper_model_device = None
_whisper_model_name = os.getenv("WHISPER_MODEL", "base")


async def ensure_whisper_model(use_gpu: bool = True):
    """
    Ensure Whisper model is loaded, using GPU coordinator if needed.

    Args:
        use_gpu: Whether to try loading on GPU (will use coordinator)
    """
    global _whisper_model, _whisper_model_device

    if _whisper_model is not None:
        return _whisper_model

    try:
        import whisper

        device = "cpu"

        if use_gpu:
            try:
                coordinator = get_gpu_coordinator()
                # Request GPU memory through coordinator
                async with coordinator.request_gpu(GPUService.WHISPER, max_wait=60.0):
                    device = "cuda"
                    logger.info(f"Loading Whisper model: {_whisper_model_name} on GPU")
                    _whisper_model = whisper.load_model(_whisper_model_name, device=device)
                    _whisper_model_device = device
                    logger.info("Whisper model loaded on GPU")
                    return _whisper_model
            except Exception as e:
                logger.warning(f"Could not get GPU for Whisper: {e}, falling back to CPU")
                device = "cpu"

        # CPU fallback
        logger.info(f"Loading Whisper model: {_whisper_model_name} on CPU")
        _whisper_model = whisper.load_model(_whisper_model_name, device=device)
        _whisper_model_device = device
        logger.info("Whisper model loaded on CPU")
        return _whisper_model

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


def get_whisper_model_sync():
    """Synchronous wrapper for getting the model (for status check)."""
    return _whisper_model


class TranscribeRequest(BaseModel):
    """Request body for transcription."""
    audio: str  # Base64-encoded audio data
    format: str = "wav"  # Audio format: wav, mp3, webm, etc.
    language: Optional[str] = None  # Optional language hint (e.g., "en")
    identify_speaker: bool = False  # Whether to identify the speaker


class SpeakerInfo(BaseModel):
    """Speaker identification result."""
    user_id: Optional[str] = None
    display_name: Optional[str] = None
    confidence: float
    confidence_level: str  # high, medium, low, none


class TranscribeResponse(BaseModel):
    """Response from transcription."""
    text: str
    language: str
    duration: float  # Audio duration in seconds
    speaker: Optional[SpeakerInfo] = None  # Speaker identification (if requested)


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(request: TranscribeRequest):
    """
    Transcribe audio to text using Whisper.

    Accepts base64-encoded audio data in various formats (wav, mp3, webm, etc.).
    Returns the transcribed text along with detected language and duration.
    Uses GPU coordinator to manage VRAM allocation.
    """
    model = await ensure_whisper_model(use_gpu=True)

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

        # Optional speaker identification
        speaker_info = None
        if request.identify_speaker:
            try:
                match = await identify_speaker_from_audio(audio_bytes)
                if match:
                    speaker_info = SpeakerInfo(
                        user_id=match.user_id,
                        display_name=match.display_name,
                        confidence=match.confidence,
                        confidence_level=match.confidence_level.value,
                    )
                    logger.info(f"Identified speaker: {match.display_name} ({match.confidence_level.value})")
                else:
                    speaker_info = SpeakerInfo(
                        user_id=None,
                        display_name=None,
                        confidence=0.0,
                        confidence_level="none",
                    )
                    logger.info("Speaker not identified")
            except Exception as e:
                logger.warning(f"Speaker identification failed: {e}")
                # Continue without speaker info rather than failing the request

        return TranscribeResponse(
            text=text,
            language=language,
            duration=duration,
            speaker=speaker_info
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
        import whisper  # noqa: F401
        return {
            "available": True,
            "model": _whisper_model_name,
            "loaded": _whisper_model is not None,
            "device": _whisper_model_device,
        }
    except ImportError:
        return {
            "available": False,
            "model": None,
            "loaded": False,
            "device": None,
            "error": "whisper not installed"
        }
