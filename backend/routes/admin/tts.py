"""
Text-to-Speech API endpoints for admin frontend.

Provides TTS synthesis and settings management.
"""

import base64
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tts import synthesize, get_available_providers, list_all_voices

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts", tags=["tts"])


class SynthesizeRequest(BaseModel):
    """Request body for TTS synthesis."""
    text: str
    provider: Optional[str] = None  # piper, xtts
    voice: Optional[str] = None
    format: str = "mp3"  # mp3, wav


class SynthesizeResponse(BaseModel):
    """Response from TTS synthesis."""
    audio: str  # Base64-encoded audio
    format: str
    provider: str


class TTSSettingsResponse(BaseModel):
    """TTS settings and available options."""
    current_provider: str
    available_providers: list[str]
    voices: dict  # provider -> {voice_name: description}


class SetTTSProviderRequest(BaseModel):
    """Request to change TTS provider."""
    provider: str


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_text(request: SynthesizeRequest):
    """
    Synthesize text to speech.

    Returns base64-encoded audio in the requested format.
    """
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    provider = request.provider or "piper"
    voice = request.voice or "amy"

    try:
        audio_bytes = synthesize(
            text=request.text,
            provider=provider,
            voice=voice,
            output_format=request.format,
        )

        if not audio_bytes:
            raise HTTPException(status_code=500, detail="No audio generated")

        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

        return SynthesizeResponse(
            audio=audio_base64,
            format=request.format,
            provider=provider,
        )

    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {e}")


@router.get("/settings", response_model=TTSSettingsResponse)
async def get_tts_settings():
    """Get current TTS settings and available options."""
    from websocket_handlers import _state

    return TTSSettingsResponse(
        current_provider=_state.get("tts_provider", "piper"),
        available_providers=get_available_providers(),
        voices=list_all_voices(),
    )


@router.post("/settings/provider")
async def set_tts_provider(request: SetTTSProviderRequest):
    """Set the active TTS provider."""
    from websocket_handlers import set_tts_state, _state

    available = get_available_providers()
    if request.provider not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{request.provider}' not available. Options: {available}"
        )

    # Update the TTS state (preserves enabled and voice settings)
    set_tts_state(
        enabled=_state.get("tts_enabled", False),
        voice=_state.get("tts_voice", "amy"),
        provider=request.provider,
    )

    logger.info(f"TTS provider set to: {request.provider}")

    return {
        "success": True,
        "provider": request.provider,
    }
