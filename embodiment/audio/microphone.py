"""
Microphone input with voice activity detection.

Captures audio from microphone, detects speech, and provides
audio chunks for speech-to-text processing.
"""

import asyncio
import logging
import queue
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Optional imports - graceful degradation
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    logger.warning("sounddevice not available - microphone disabled")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import webrtcvad
    WEBRTCVAD_AVAILABLE = True
except ImportError:
    WEBRTCVAD_AVAILABLE = False
    logger.warning("webrtcvad not available - using simple energy VAD")


class VADState(Enum):
    """Voice activity detection state."""
    SILENCE = "silence"
    SPEECH = "speech"
    TRAILING = "trailing"  # Brief silence after speech


@dataclass
class AudioChunk:
    """A chunk of audio data."""
    data: bytes
    sample_rate: int
    channels: int
    is_speech: bool


class SimpleEnergyVAD:
    """Simple energy-based voice activity detection."""

    def __init__(self, threshold: float = 0.02, sample_rate: int = 16000):
        self.threshold = threshold
        self.sample_rate = sample_rate

    def is_speech(self, audio_data: bytes) -> bool:
        """Check if audio chunk contains speech based on energy."""
        if not NUMPY_AVAILABLE:
            return True  # Can't detect, assume speech

        # Convert bytes to numpy array
        audio = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        audio = audio / 32768.0  # Normalize to [-1, 1]

        # Calculate RMS energy
        energy = np.sqrt(np.mean(audio ** 2))
        return energy > self.threshold


class WebRTCVAD:
    """WebRTC-based voice activity detection."""

    def __init__(self, aggressiveness: int = 2, sample_rate: int = 16000):
        """
        Args:
            aggressiveness: 0-3, higher = more aggressive filtering
            sample_rate: Must be 8000, 16000, 32000, or 48000
        """
        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate

    def is_speech(self, audio_data: bytes) -> bool:
        """Check if audio chunk contains speech."""
        # WebRTC VAD expects specific frame sizes
        # 16000 Hz: 160, 320, or 480 samples (10, 20, or 30 ms)
        try:
            return self.vad.is_speech(audio_data, self.sample_rate)
        except Exception:
            return True  # On error, assume speech


class MicrophoneInput:
    """
    Microphone input handler with VAD.

    Captures audio, detects speech boundaries, and emits complete
    utterances for speech-to-text processing.
    """

    def __init__(
        self,
        sample_rate: int = None,  # None = auto-detect from device
        channels: int = 1,
        device: int = None,  # None = default device
        chunk_duration_ms: int = 30,
        silence_threshold_ms: int = 800,
        min_speech_ms: int = 250,
        on_utterance: Optional[Callable[[bytes], None]] = None,
        on_vad_state: Optional[Callable[[VADState], None]] = None,
    ):
        """
        Args:
            sample_rate: Audio sample rate
            channels: Number of audio channels
            chunk_duration_ms: Duration of each audio chunk
            silence_threshold_ms: Silence duration to end utterance
            min_speech_ms: Minimum speech duration to emit
            on_utterance: Callback when complete utterance detected
            on_vad_state: Callback when VAD state changes
        """
        self.device = device
        self.channels = channels
        self.chunk_duration_ms = chunk_duration_ms
        self.silence_threshold_ms = silence_threshold_ms
        self.min_speech_ms = min_speech_ms

        self.on_utterance = on_utterance
        self.on_vad_state = on_vad_state

        # Auto-detect sample rate from device if not specified
        if sample_rate is None and SOUNDDEVICE_AVAILABLE:
            try:
                if device is not None:
                    dev_info = sd.query_devices(device)
                else:
                    dev_info = sd.query_devices(sd.default.device[0])
                self.sample_rate = int(dev_info['default_samplerate'])
                logger.info(f"Auto-detected sample rate: {self.sample_rate} Hz")
            except Exception as e:
                logger.warning(f"Could not auto-detect sample rate: {e}, using 44100")
                self.sample_rate = 44100
        else:
            self.sample_rate = sample_rate or 44100

        # Calculate chunk size in samples
        self.chunk_samples = int(self.sample_rate * chunk_duration_ms / 1000)

        # VAD setup - webrtcvad only supports specific sample rates
        if WEBRTCVAD_AVAILABLE and self.sample_rate in [8000, 16000, 32000, 48000]:
            self.vad = WebRTCVAD(aggressiveness=2, sample_rate=self.sample_rate)
        else:
            if WEBRTCVAD_AVAILABLE:
                logger.info(f"WebRTC VAD doesn't support {self.sample_rate} Hz, using energy VAD")
            self.vad = SimpleEnergyVAD(sample_rate=self.sample_rate)

        # State
        self.state = VADState.SILENCE
        self.audio_buffer: list[bytes] = []
        self.silence_chunks = 0
        self.speech_chunks = 0

        # Threading
        self._running = False
        self._stream = None
        self._audio_queue: queue.Queue = queue.Queue()

    @property
    def available(self) -> bool:
        """Check if microphone input is available."""
        return SOUNDDEVICE_AVAILABLE and NUMPY_AVAILABLE

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback for sounddevice stream."""
        if status:
            logger.warning(f"Audio status: {status}")
        # Convert to bytes and queue
        audio_bytes = indata.tobytes()
        self._audio_queue.put(audio_bytes)

    def _process_audio(self):
        """Process audio chunks from queue."""
        silence_chunks_threshold = int(self.silence_threshold_ms / self.chunk_duration_ms)
        min_speech_chunks = int(self.min_speech_ms / self.chunk_duration_ms)

        while self._running:
            try:
                audio_data = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            is_speech = self.vad.is_speech(audio_data)

            if self.state == VADState.SILENCE:
                if is_speech:
                    # Speech started
                    self.state = VADState.SPEECH
                    self.audio_buffer = [audio_data]
                    self.speech_chunks = 1
                    self.silence_chunks = 0
                    self._emit_state(VADState.SPEECH)

            elif self.state == VADState.SPEECH:
                self.audio_buffer.append(audio_data)
                if is_speech:
                    self.speech_chunks += 1
                    self.silence_chunks = 0
                else:
                    self.silence_chunks += 1
                    if self.silence_chunks >= silence_chunks_threshold:
                        # Utterance complete
                        self.state = VADState.SILENCE
                        self._emit_state(VADState.SILENCE)

                        if self.speech_chunks >= min_speech_chunks:
                            # Emit the utterance
                            full_audio = b"".join(self.audio_buffer)
                            if self.on_utterance:
                                self.on_utterance(full_audio)

                        self.audio_buffer = []
                        self.speech_chunks = 0
                        self.silence_chunks = 0

    def _emit_state(self, state: VADState):
        """Emit VAD state change."""
        if self.on_vad_state:
            self.on_vad_state(state)

    def start(self):
        """Start microphone capture."""
        if not self.available:
            logger.error("Microphone not available")
            return False

        if self._running:
            return True

        self._running = True

        # Start audio stream
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=np.int16,
            blocksize=self.chunk_samples,
            device=self.device,
            callback=self._audio_callback,
        )
        self._stream.start()

        # Start processing thread
        self._process_thread = threading.Thread(target=self._process_audio, daemon=True)
        self._process_thread.start()

        logger.info("Microphone started")
        return True

    def stop(self):
        """Stop microphone capture."""
        self._running = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        logger.info("Microphone stopped")

    def get_input_devices(self) -> list[dict]:
        """List available input devices."""
        if not SOUNDDEVICE_AVAILABLE:
            return []

        devices = []
        for i, dev in enumerate(sd.query_devices()):
            if dev['max_input_channels'] > 0:
                devices.append({
                    'index': i,
                    'name': dev['name'],
                    'channels': dev['max_input_channels'],
                    'sample_rate': dev['default_samplerate'],
                })
        return devices
