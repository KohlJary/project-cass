"""
XTTS v2 TTS Provider for Cass Vessel

Higher quality TTS with better prosody than Piper.
Requires GPU for reasonable latency (~1-2s per sentence on RTX 3060+).

Voice cloning: Can clone from ~6-30 seconds of reference audio.
Built-in voices: Available if no reference provided.
"""
import io
import logging
import wave
from pathlib import Path
from typing import Optional

import numpy as np

# Audio conversion
from pydub import AudioSegment
import shutil

# Configure pydub to find ffmpeg
_ffmpeg_path = shutil.which("ffmpeg") or "/sbin/ffmpeg" or "/usr/bin/ffmpeg"
_ffprobe_path = shutil.which("ffprobe") or "/sbin/ffprobe" or "/usr/bin/ffprobe"
AudioSegment.converter = _ffmpeg_path
AudioSegment.ffmpeg = _ffmpeg_path
AudioSegment.ffprobe = _ffprobe_path

logger = logging.getLogger(__name__)

# Try to import TTS library
try:
    from TTS.api import TTS
    import torch
    XTTS_AVAILABLE = True
except ImportError as e:
    XTTS_AVAILABLE = False
    logger.warning(f"XTTS not available: {e}")
    logger.warning("Install with: pip install TTS")

# Model and voice configuration
XTTS_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
VOICES_DIR = Path(__file__).parent / "voices"

# Built-in XTTS speakers (subset - these are the cleaner ones)
BUILTIN_VOICES = {
    "default": None,  # Use default XTTS voice
    "female_1": "Claribel Dervla",
    "female_2": "Daisy Studious",
    "female_3": "Gracie Wise",
    "female_4": "Tammie Ema",
    "female_5": "Alison Dietlinde",
    "female_6": "Ana Florence",
    "female_7": "Annmarie Nele",
    "female_8": "Asya Anara",
    "female_9": "Brenda Stern",
    "male_1": "Eugenio Matarese",
    "male_2": "Gitta Nikolina",
    "male_3": "Henriette Usha",
    "male_4": "Sofia Hellen",
    "male_5": "Tammy Grit",
    "male_6": "Tanja Adelina",
    "male_7": "Viktor Eka",
    "male_8": "Viktor Menelaos",
    "male_9": "Zacharie Aimilios",
}

# Cache the TTS model (expensive to load)
_tts_instance: Optional["TTS"] = None


def _get_tts() -> "TTS":
    """Get or create the cached TTS instance."""
    global _tts_instance

    if _tts_instance is None:
        if not XTTS_AVAILABLE:
            raise RuntimeError("XTTS not available - install with: pip install TTS")

        logger.info("Loading XTTS v2 model (this may take a moment)...")
        _tts_instance = TTS(XTTS_MODEL)

        # Move to GPU if available
        if torch.cuda.is_available():
            _tts_instance.to("cuda")
            logger.info("XTTS loaded on GPU")
        else:
            logger.warning("XTTS running on CPU - synthesis will be slow")

    return _tts_instance


def get_reference_audio(voice: str) -> Optional[str]:
    """
    Get reference audio path for voice cloning.

    Args:
        voice: Voice name - either a custom voice file or builtin name

    Returns:
        Path to reference audio, or None for default voice
    """
    # Check for custom reference audio
    custom_path = VOICES_DIR / f"{voice}.wav"
    if custom_path.exists():
        return str(custom_path)

    # Check for builtin voice
    if voice in BUILTIN_VOICES:
        return None  # Will use speaker parameter instead

    # Default - no reference
    return None


def text_to_speech_xtts(
    text: str,
    voice: str = "default",
    output_format: str = "mp3",
    language: str = "en",
) -> bytes:
    """
    Convert text to speech using XTTS v2.

    Args:
        text: Text to convert to speech
        voice: Voice name - custom reference file, builtin name, or "default"
        output_format: Output format - "mp3" (default) or "wav"
        language: Language code (en, es, fr, de, it, pt, pl, tr, ru, nl, cs, ar, zh-cn, ja, ko, hu)

    Returns:
        Audio bytes in the specified format
    """
    if not text.strip():
        return b''

    tts = _get_tts()

    # Determine voice parameters
    reference_audio = get_reference_audio(voice)
    speaker = None

    if reference_audio:
        # Use voice cloning from reference
        logger.debug(f"Using voice cloning from: {reference_audio}")
    elif voice in BUILTIN_VOICES and BUILTIN_VOICES[voice]:
        # Use builtin speaker
        speaker = BUILTIN_VOICES[voice]
        logger.debug(f"Using builtin speaker: {speaker}")

    # Generate audio
    # XTTS returns numpy array
    if reference_audio:
        wav = tts.tts(
            text=text,
            speaker_wav=reference_audio,
            language=language,
        )
    elif speaker:
        wav = tts.tts(
            text=text,
            speaker=speaker,
            language=language,
        )
    else:
        # Default voice
        wav = tts.tts(
            text=text,
            language=language,
        )

    # Convert numpy array to audio bytes
    # XTTS outputs at 24kHz
    sample_rate = 24000

    # Normalize and convert to int16
    wav_array = np.array(wav)
    wav_array = wav_array / np.max(np.abs(wav_array)) * 0.95  # Normalize
    wav_int16 = (wav_array * 32767).astype(np.int16)

    # Create WAV in memory
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(wav_int16.tobytes())

    if output_format == "wav":
        return wav_io.getvalue()

    # Convert to MP3
    wav_io.seek(0)
    audio_segment = AudioSegment.from_wav(wav_io)
    mp3_io = io.BytesIO()
    audio_segment.export(mp3_io, format="mp3", bitrate="64k")  # Higher bitrate for quality
    return mp3_io.getvalue()


def list_voices() -> dict:
    """
    List available XTTS voices.

    Returns:
        Dict of voice name -> description
    """
    voices = {}

    # Add builtin voices
    for name, speaker in BUILTIN_VOICES.items():
        voices[name] = f"Built-in: {speaker or 'default'}"

    # Add custom reference voices
    if VOICES_DIR.exists():
        for wav_file in VOICES_DIR.glob("*.wav"):
            name = wav_file.stem
            if name not in voices:
                voices[name] = f"Custom: {wav_file.name}"

    return voices


def preload():
    """Preload the XTTS model for faster first synthesis."""
    if XTTS_AVAILABLE:
        try:
            _get_tts()
            logger.info("XTTS model preloaded")
        except Exception as e:
            logger.error(f"Failed to preload XTTS: {e}")


def is_available() -> bool:
    """Check if XTTS is available."""
    return XTTS_AVAILABLE


# Quick test
if __name__ == "__main__":
    import time

    print("Testing XTTS v2...")
    print(f"Available: {is_available()}")

    if is_available():
        print("\nAvailable voices:")
        for name, desc in list_voices().items():
            print(f"  {name}: {desc}")

        test_text = "Hello! I'm Cass. This is a test of the XTTS voice synthesis system."
        print(f"\nGenerating: {test_text}")

        start = time.time()
        audio = text_to_speech_xtts(test_text, voice="female_1")
        elapsed = time.time() - start

        print(f"Generated {len(audio)} bytes in {elapsed:.2f}s")

        # Save test file
        with open("/tmp/test_xtts.mp3", "wb") as f:
            f.write(audio)
        print("Saved to /tmp/test_xtts.mp3")
