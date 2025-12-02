"""
Text-to-Speech module for Cass Vessel
Uses Piper for high-quality, local neural TTS
"""
import io
import wave
import re
from pathlib import Path
from typing import Optional

# Piper TTS
from piper import PiperVoice
from piper.config import SynthesisConfig

# Audio conversion
from pydub import AudioSegment
import shutil

# Configure pydub to find ffmpeg
_ffmpeg_path = shutil.which("ffmpeg") or "/sbin/ffmpeg" or "/usr/bin/ffmpeg"
_ffprobe_path = shutil.which("ffprobe") or "/sbin/ffprobe" or "/usr/bin/ffprobe"
AudioSegment.converter = _ffmpeg_path
AudioSegment.ffmpeg = _ffmpeg_path
AudioSegment.ffprobe = _ffprobe_path

# Model configuration
MODELS_DIR = Path(__file__).parent / "models" / "piper"
DEFAULT_MODEL = "en_US-amy-medium"

# Available voices (model name -> description)
VOICES = {
    "amy": "en_US-amy-medium",      # Default - warm female voice
}

# Cache loaded voice to avoid reloading
_voice_cache: dict = {}

# Emote-based synthesis configurations
# These match the EmoteType values in gestures.py
# Parameters: length_scale (speed: <1 faster, >1 slower), noise_scale (variation), noise_w_scale (phoneme width)
EMOTE_CONFIGS = {
    "happy": SynthesisConfig(
        length_scale=0.95,    # Slightly faster, upbeat
        noise_scale=0.7,      # More expressive variation
        noise_w_scale=0.8,
    ),
    "excited": SynthesisConfig(
        length_scale=0.85,    # Faster, energetic
        noise_scale=0.8,      # More variation for enthusiasm
        noise_w_scale=0.9,
    ),
    "concern": SynthesisConfig(
        length_scale=1.1,     # Slower, more careful
        noise_scale=0.5,      # Less variation, more measured
        noise_w_scale=0.6,
    ),
    "thinking": SynthesisConfig(
        length_scale=1.15,    # Slower, contemplative
        noise_scale=0.4,      # Steady, thoughtful
        noise_w_scale=0.5,
    ),
    "love": SynthesisConfig(
        length_scale=1.05,    # Slightly slower, warm
        noise_scale=0.6,      # Gentle variation
        noise_w_scale=0.7,
    ),
    "surprised": SynthesisConfig(
        length_scale=0.9,     # Slightly faster
        noise_scale=0.9,      # High variation for expressiveness
        noise_w_scale=1.0,
    ),
}

# Default config for neutral speech
DEFAULT_SYNTH_CONFIG = SynthesisConfig(
    length_scale=1.0,
    noise_scale=0.667,
    noise_w_scale=0.8,
)


def extract_dominant_emote(text: str) -> Optional[str]:
    """
    Extract the first/dominant emote from text.
    Returns the emote name if found, None otherwise.
    """
    match = re.search(r'<emote:(\w+)(?::[^>]+)?>', text)
    if match:
        emote = match.group(1).lower()
        if emote in EMOTE_CONFIGS:
            return emote
    return None


def get_synth_config(emote: Optional[str] = None) -> SynthesisConfig:
    """Get synthesis config for an emote, or default if none."""
    if emote and emote in EMOTE_CONFIGS:
        return EMOTE_CONFIGS[emote]
    return DEFAULT_SYNTH_CONFIG


def _get_model_path(model_name: str) -> Path:
    """Get the path to a model file"""
    return MODELS_DIR / f"{model_name}.onnx"


def _load_voice(model_name: str = DEFAULT_MODEL) -> PiperVoice:
    """Load a Piper voice, with caching"""
    if model_name not in _voice_cache:
        model_path = _get_model_path(model_name)
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")
        _voice_cache[model_name] = PiperVoice.load(str(model_path))
    return _voice_cache[model_name]


def clean_text_for_tts(text: str) -> str:
    """
    Clean text for TTS by removing markup, gestures, and other non-spoken content.
    Also adds natural pauses for better cadence.
    """
    # Remove gesture/emote/memory tags
    text = re.sub(r'<(gesture|emote|memory):[^>]+>', '', text)

    # Remove markdown code blocks (don't read code aloud)
    text = re.sub(r'```[\s\S]*?```', ' [code block] ', text)

    # Remove inline code
    text = re.sub(r'`[^`]+`', '', text)

    # Remove markdown links, keep text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Remove markdown formatting
    text = re.sub(r'[*_]{1,2}([^*_]+)[*_]{1,2}', r'\1', text)

    # Remove headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove bullet points
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)

    # Convert ellipses to pause markers
    # Piper respects periods and commas for pauses, so we convert "..." to ". . ."
    # which creates a longer, more natural pause
    text = re.sub(r'…', '...', text)  # Unicode ellipsis to ASCII
    text = re.sub(r'\.{3,}', '. . .', text)  # "..." -> ". . ." for dramatic pause

    # Also handle em-dashes and spaced hyphens as slight pauses
    text = re.sub(r'\s*[—–-]{2,}\s*', ', ', text)  # em-dash, en-dash, or double hyphen
    text = re.sub(r'\s*—\s*', ', ', text)  # single em-dash
    text = re.sub(r' - ', ', ', text)  # spaced hyphen (like " - ")

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Clean up any double commas or comma-period combos we might have created
    text = re.sub(r',\s*,', ',', text)
    text = re.sub(r',\s*\.', '.', text)

    return text


def text_to_speech(
    text: str,
    voice: str = "amy",
    output_format: str = "mp3",
    emote: Optional[str] = None,
) -> bytes:
    """
    Convert text to speech and return audio bytes.

    Args:
        text: Text to convert to speech
        voice: Voice name (currently only "amy" available)
        output_format: Output format - "mp3" (default, smaller) or "wav" (larger)
        emote: Optional emote name to adjust synthesis tone (happy, excited, concern, thinking, love, surprised)

    Returns:
        Audio bytes in the specified format
    """
    # Extract emote from text if not explicitly provided
    if emote is None:
        emote = extract_dominant_emote(text)

    # Clean the text
    clean_text = clean_text_for_tts(text)

    if not clean_text:
        return b''

    # Get model name from voice alias
    model_name = VOICES.get(voice, DEFAULT_MODEL)

    # Load voice
    piper_voice = _load_voice(model_name)

    # Get synthesis config based on emote
    synth_config = get_synth_config(emote)

    # Synthesize audio with emote-adjusted config
    audio_chunks = list(piper_voice.synthesize(clean_text, synth_config))

    if not audio_chunks:
        return b''

    # Combine audio bytes from all chunks
    all_audio = b''.join(chunk.audio_int16_bytes for chunk in audio_chunks)

    # Get sample info from first chunk
    sample_rate = audio_chunks[0].sample_rate
    sample_width = audio_chunks[0].sample_width
    channels = audio_chunks[0].sample_channels

    # Create WAV file in memory
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(all_audio)

    if output_format == "wav":
        return wav_io.getvalue()

    # Convert to MP3 for smaller size (important for WebSocket transfer)
    # Using 32k bitrate for smaller files - still good quality for speech
    wav_io.seek(0)
    audio_segment = AudioSegment.from_wav(wav_io)
    mp3_io = io.BytesIO()
    audio_segment.export(mp3_io, format="mp3", bitrate="32k")
    return mp3_io.getvalue()


# Async wrapper for compatibility with existing code
async def text_to_speech_async(
    text: str,
    voice: str = "amy",
) -> bytes:
    """
    Async wrapper for text_to_speech.
    Piper is fast enough that we don't need true async, but this maintains API compatibility.
    """
    return text_to_speech(text, voice)


def save_to_file(
    text: str,
    output_path: str,
    voice: str = "amy",
) -> str:
    """
    Generate TTS and save to a file.

    Args:
        text: Text to convert
        output_path: Path to save the WAV file
        voice: Voice name to use

    Returns:
        Path to the saved file
    """
    audio_bytes = text_to_speech(text, voice)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'wb') as f:
        f.write(audio_bytes)

    return str(path)


def list_voices() -> dict:
    """
    List available voices.

    Returns:
        Dict of voice name -> model name
    """
    return VOICES.copy()


def preload_voice(voice: str = "amy"):
    """
    Preload a voice into cache for faster first synthesis.
    Call this at startup to avoid delay on first TTS request.
    """
    model_name = VOICES.get(voice, DEFAULT_MODEL)
    _load_voice(model_name)


# Quick test
if __name__ == "__main__":
    print("Testing Piper TTS with emote-based tone...")

    test_texts = [
        ("<emote:happy> Hello! I'm so glad to see you!", "happy"),
        ("<emote:excited> Oh wow, that's amazing news!", "excited"),
        ("<emote:thinking> Hmm... let me consider that carefully...", "thinking"),
        ("<emote:concern> I'm a bit worried about that approach.", "concern"),
        ("<emote:love> I really appreciate you sharing that with me.", "love"),
        ("<emote:surprised> Wait, really? I didn't expect that!", "surprised"),
    ]

    for text, expected_emote in test_texts:
        detected = extract_dominant_emote(text)
        print(f"\nText: {text}")
        print(f"Detected emote: {detected} (expected: {expected_emote})")
        print(f"Cleaned: {clean_text_for_tts(text)}")

    # Generate audio with emote
    test_text = "<emote:excited> <gesture:wave> Hello! I'm Cass! This is really exciting!"
    print(f"\n\nGenerating audio for: {test_text}")
    audio = text_to_speech(test_text)
    print(f"Generated {len(audio)} bytes of audio")

    # Save to file
    save_to_file(test_text, "/tmp/test_piper_emote.mp3")
    print("Saved to /tmp/test_piper_emote.mp3")
