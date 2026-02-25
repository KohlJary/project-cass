"""
Speech-to-Text using faster-whisper.

Transcribes audio data to text locally using Whisper models.
"""

import logging
import threading
import queue
from dataclasses import dataclass
from typing import Callable, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Optional imports
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    logger.warning("faster-whisper not available - STT disabled")


@dataclass
class TranscriptionResult:
    """Result of speech-to-text transcription."""
    text: str
    language: str
    confidence: float
    duration: float


class SpeechToText:
    """
    Speech-to-text transcription using faster-whisper.

    Runs Whisper models locally for privacy and low latency.
    """

    # Model sizes: tiny, base, small, medium, large-v2, large-v3
    # Smaller = faster but less accurate
    # For Pi 5: "tiny" or "base" recommended
    # For desktop: "small" or "medium" work well

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: Optional[str] = "en",
        on_transcription: Optional[Callable[[TranscriptionResult], None]] = None,
    ):
        """
        Args:
            model_size: Whisper model size (tiny, base, small, medium, large-v2, large-v3)
            device: "cpu" or "cuda"
            compute_type: "int8" (fastest on CPU), "float16" (GPU), "float32"
            language: Language code (e.g., "en") or None for auto-detect
            on_transcription: Callback when transcription completes
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.on_transcription = on_transcription

        self._model: Optional[WhisperModel] = None
        self._running = False
        self._audio_queue: queue.Queue = queue.Queue()
        self._process_thread: Optional[threading.Thread] = None

    @property
    def available(self) -> bool:
        """Check if STT is available."""
        return FASTER_WHISPER_AVAILABLE and NUMPY_AVAILABLE

    def _load_model(self) -> bool:
        """Load the Whisper model."""
        if not self.available:
            return False

        try:
            logger.info(f"Loading Whisper model: {self.model_size} ({self.compute_type})")
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info("Whisper model loaded")
            return True
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            import traceback
            traceback.print_exc()
            return False

    def start(self) -> bool:
        """Start the STT processor."""
        if not self.available:
            logger.error("STT not available")
            return False

        if self._running:
            return True

        if not self._load_model():
            return False

        self._running = True
        self._process_thread = threading.Thread(
            target=self._process_loop,
            daemon=True,
        )
        self._process_thread.start()

        logger.info("STT processor started")
        return True

    def stop(self):
        """Stop the STT processor."""
        self._running = False
        if self._process_thread:
            self._process_thread.join(timeout=2.0)
            self._process_thread = None
        logger.info("STT processor stopped")

    def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> Optional[TranscriptionResult]:
        """
        Transcribe audio data synchronously.

        Args:
            audio_data: Raw audio bytes (int16)
            sample_rate: Audio sample rate

        Returns:
            TranscriptionResult or None on failure
        """
        if not self._model:
            logger.error("Model not loaded")
            return None

        try:
            # Convert bytes to float32 numpy array
            audio = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            audio = audio / 32768.0  # Normalize to [-1, 1]

            # Resample to 16kHz if needed (Whisper expects 16kHz)
            if sample_rate != 16000:
                # Simple resampling - for production use librosa or scipy
                ratio = 16000 / sample_rate
                new_length = int(len(audio) * ratio)
                indices = np.linspace(0, len(audio) - 1, new_length).astype(int)
                audio = audio[indices]

            # Calculate duration
            duration = len(audio) / 16000.0

            # Transcribe
            segments, info = self._model.transcribe(
                audio,
                language=self.language,
                beam_size=5,
                vad_filter=True,  # Filter out non-speech
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=200,
                ),
            )

            # Collect all segments
            text_parts = []
            total_confidence = 0.0
            segment_count = 0

            for segment in segments:
                text_parts.append(segment.text.strip())
                # avg_logprob is log probability, convert to rough confidence
                confidence = min(1.0, max(0.0, 1.0 + segment.avg_logprob / 2.0))
                total_confidence += confidence
                segment_count += 1

            text = " ".join(text_parts).strip()
            avg_confidence = total_confidence / segment_count if segment_count > 0 else 0.0

            if not text:
                logger.debug("No speech detected in audio")
                return None

            return TranscriptionResult(
                text=text,
                language=info.language,
                confidence=avg_confidence,
                duration=duration,
            )

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def transcribe_async(self, audio_data: bytes, sample_rate: int = 16000):
        """
        Queue audio for async transcription.

        Results are delivered via on_transcription callback.
        """
        if not self._running:
            logger.warning("STT not running - call start() first")
            return

        self._audio_queue.put((audio_data, sample_rate))

    def _process_loop(self):
        """Background thread for processing audio."""
        while self._running:
            try:
                audio_data, sample_rate = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            result = self.transcribe(audio_data, sample_rate)

            if result and self.on_transcription:
                self.on_transcription(result)


def get_recommended_model(device: str = "cpu") -> tuple[str, str]:
    """
    Get recommended model size and compute type for device.

    Returns:
        (model_size, compute_type)
    """
    if device == "cuda":
        # GPU: can handle larger models
        return ("small", "float16")
    else:
        # CPU: use smaller model with int8 quantization
        # For Raspberry Pi 5: "tiny" is recommended
        # For desktop CPU: "base" works well
        return ("base", "int8")
