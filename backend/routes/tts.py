"""
TTS (Text-to-Speech) API Routes

Extracted from main_sdk.py as part of Phase 1 refactoring.
Handles TTS configuration and audio generation.
"""

import base64
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/tts", tags=["tts"])


# === Request Models ===

class TTSConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    voice: Optional[str] = None


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None


# === Dependencies (injected at startup) ===

_voices = None
_text_to_speech = None
_clean_text_for_tts = None
_set_tts_state = None
_get_tts_state = None  # Returns (enabled, voice) tuple


def init_tts_routes(
    voices: dict,
    text_to_speech_func,
    clean_text_for_tts_func,
    set_tts_state_func,
    get_tts_state_func
):
    """Initialize route dependencies. Called from main_sdk.py startup."""
    global _voices, _text_to_speech, _clean_text_for_tts, _set_tts_state, _get_tts_state
    _voices = voices
    _text_to_speech = text_to_speech_func
    _clean_text_for_tts = clean_text_for_tts_func
    _set_tts_state = set_tts_state_func
    _get_tts_state = get_tts_state_func


# === TTS Endpoints ===

@router.get("/config")
async def get_tts_config():
    """Get current TTS configuration"""
    enabled, voice = _get_tts_state()
    return {
        "enabled": enabled,
        "voice": voice,
        "available_voices": list(_voices.keys())
    }


@router.post("/config")
async def set_tts_config(request: TTSConfigRequest):
    """Update TTS configuration"""
    enabled, voice = _get_tts_state()

    if request.enabled is not None:
        enabled = request.enabled

    if request.voice is not None:
        # Resolve voice alias or use directly
        voice = _voices.get(request.voice, request.voice)

    # Update websocket handler state
    _set_tts_state(enabled, voice)

    return {
        "enabled": enabled,
        "voice": voice
    }


@router.post("/generate")
async def generate_tts(request: TTSRequest):
    """
    Generate TTS audio for arbitrary text.
    Returns base64-encoded MP3 audio.
    """
    _, current_voice = _get_tts_state()
    voice = _voices.get(request.voice, request.voice) if request.voice else current_voice

    try:
        audio_bytes = _text_to_speech(request.text, voice=voice)
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="No audio generated (text may be empty after cleaning)")

        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

        return {
            "audio": audio_base64,
            "format": "mp3",
            "voice": voice,
            "text_length": len(request.text),
            "cleaned_text": _clean_text_for_tts(request.text)[:100] + "..."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")
