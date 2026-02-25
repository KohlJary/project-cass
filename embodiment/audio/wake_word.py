"""
Wake word detection for Cass.

Uses OpenWakeWord for local, privacy-preserving wake word detection.
Supports custom trained models (e.g., "Hey Cass") or pre-trained models.
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
    from openwakeword.model import Model
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False
    logger.warning("openwakeword not available - wake word detection disabled")


@dataclass
class WakeWordDetection:
    """A wake word detection event."""
    model_name: str
    confidence: float
    timestamp: float


class WakeWordDetector:
    """
    Wake word detector using OpenWakeWord.

    Processes audio chunks and detects wake words like "Hey Cass".
    """

    # Pre-trained models that ship with OpenWakeWord
    BUILTIN_MODELS = {
        "alexa": "alexa_v0.1.onnx",
        "hey_mycroft": "hey_mycroft_v0.1.onnx",
        "hey_jarvis": "hey_jarvis_v0.1.onnx",
    }

    def __init__(
        self,
        model_path: Optional[str] = None,
        model_name: str = "hey_jarvis",  # Default to hey_jarvis (similar to "hey cass")
        threshold: float = 0.5,
        on_wake_word: Optional[Callable[[WakeWordDetection], None]] = None,
    ):
        """
        Args:
            model_path: Path to custom .onnx model (e.g., trained "Hey Cass" model)
            model_name: Name of built-in model to use if no custom model
            threshold: Detection confidence threshold (0-1)
            on_wake_word: Callback when wake word detected
        """
        self.model_path = model_path
        self.model_name = model_name
        self.threshold = threshold
        self.on_wake_word = on_wake_word

        self._model: Optional[Model] = None
        self._running = False
        self._audio_queue: queue.Queue = queue.Queue()
        self._process_thread: Optional[threading.Thread] = None

        # Track detection state to avoid repeated triggers
        self._last_detection_time = 0.0
        self._cooldown_seconds = 2.0  # Minimum time between detections

    @property
    def available(self) -> bool:
        """Check if wake word detection is available."""
        return OPENWAKEWORD_AVAILABLE and NUMPY_AVAILABLE

    def _load_model(self) -> bool:
        """Load the wake word model."""
        if not self.available:
            return False

        try:
            import openwakeword
            if self.model_path and Path(self.model_path).exists():
                # Custom model
                logger.info(f"Loading custom wake word model: {self.model_path}")
                self._model = Model(
                    wakeword_model_paths=[self.model_path],
                )
            else:
                # Built-in model - get the path from openwakeword
                model_paths = openwakeword.get_pretrained_model_paths()
                selected = [p for p in model_paths if self.model_name in p]
                if selected:
                    logger.info(f"Loading built-in wake word model: {self.model_name}")
                    self._model = Model(wakeword_model_paths=selected)
                else:
                    # Load all available models
                    logger.info("Loading all available wake word models")
                    self._model = Model(wakeword_model_paths=model_paths[:3])  # Limit to 3
            return True
        except Exception as e:
            logger.error(f"Failed to load wake word model: {e}")
            import traceback
            traceback.print_exc()
            return False

    def start(self) -> bool:
        """Start wake word detection."""
        if not self.available:
            logger.error("Wake word detection not available")
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

        logger.info("Wake word detector started")
        return True

    def stop(self):
        """Stop wake word detection."""
        self._running = False
        if self._process_thread:
            self._process_thread.join(timeout=1.0)
            self._process_thread = None
        logger.info("Wake word detector stopped")

    def process_audio(self, audio_data: bytes, sample_rate: int = 16000):
        """
        Process an audio chunk for wake word detection.

        Args:
            audio_data: Raw audio bytes (int16)
            sample_rate: Audio sample rate (OpenWakeWord expects 16kHz)
        """
        if not self._running:
            return

        # OpenWakeWord expects 16kHz audio
        # If sample rate differs, we'd need to resample
        # For now, queue the audio for processing
        self._audio_queue.put((audio_data, sample_rate))

    def _process_loop(self):
        """Background thread for processing audio."""
        import time

        while self._running:
            try:
                audio_data, sample_rate = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                # Convert bytes to numpy array
                audio = np.frombuffer(audio_data, dtype=np.int16)

                # Resample if needed (OpenWakeWord expects 16kHz)
                if sample_rate != 16000:
                    # Simple decimation - for production, use proper resampling
                    ratio = sample_rate / 16000
                    indices = np.arange(0, len(audio), ratio).astype(int)
                    indices = indices[indices < len(audio)]
                    audio = audio[indices]

                # Run prediction
                prediction = self._model.predict(audio)

                # Check each model's prediction
                current_time = time.time()
                for model_name, confidence in prediction.items():
                    # confidence is a float (0-1)
                    if confidence >= self.threshold:
                        if current_time - self._last_detection_time >= self._cooldown_seconds:
                            self._last_detection_time = current_time

                            detection = WakeWordDetection(
                                model_name=model_name,
                                confidence=float(confidence),
                                timestamp=current_time,
                            )

                            logger.info(f"Wake word detected: {model_name} ({confidence:.2f})")

                            if self.on_wake_word:
                                self.on_wake_word(detection)

            except Exception as e:
                logger.error(f"Wake word processing error: {e}")

    def reset(self):
        """Reset detector state (e.g., after handling a wake word)."""
        self._last_detection_time = 0.0
        if self._model:
            self._model.reset()


def train_custom_model():
    """
    Instructions for training a custom "Hey Cass" wake word model.

    OpenWakeWord supports training custom models. Steps:

    1. Collect positive samples:
       - Record ~50-100 samples of "Hey Cass" from different speakers
       - Vary distance, background noise, speaking styles

    2. Collect negative samples:
       - General speech that shouldn't trigger
       - Similar-sounding phrases ("Hey Class", "Hay Cast", etc.)

    3. Use OpenWakeWord training tools:
       ```
       pip install openwakeword[training]
       python -m openwakeword.train --help
       ```

    4. Place trained model in embodiment/models/wake_word/hey_cass.onnx

    See: https://github.com/dscripka/openWakeWord#training-new-models
    """
    pass
