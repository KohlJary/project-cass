"""
Audio playback for TTS output.

Plays audio received from Cass backend (base64 WAV).
"""

import base64
import io
import logging
import threading
import queue
from typing import Optional

logger = logging.getLogger(__name__)

# Optional imports
try:
    import pygame
    import pygame.mixer
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logger.warning("pygame not available - audio playback disabled")


class AudioPlayer:
    """
    Audio playback handler.

    Plays WAV audio from base64-encoded data (as sent by Cass backend).
    Supports queueing multiple audio segments.
    """

    def __init__(self, sample_rate: int = 22050):
        """
        Args:
            sample_rate: Expected audio sample rate
        """
        self.sample_rate = sample_rate
        self._initialized = False
        self._playing = False
        self._queue: queue.Queue = queue.Queue()
        self._current_sound: Optional[pygame.mixer.Sound] = None
        self._play_thread: Optional[threading.Thread] = None
        self._running = False

        # Callbacks
        self.on_playback_start: Optional[callable] = None
        self.on_playback_end: Optional[callable] = None

    @property
    def available(self) -> bool:
        """Check if audio playback is available."""
        return PYGAME_AVAILABLE

    def initialize(self) -> bool:
        """Initialize the audio system."""
        if not PYGAME_AVAILABLE:
            logger.error("pygame not available")
            return False

        if self._initialized:
            return True

        try:
            pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=1)
            self._initialized = True
            logger.info("Audio player initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize audio: {e}")
            return False

    def start(self):
        """Start the playback handler."""
        if not self.initialize():
            return False

        self._running = True
        self._play_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._play_thread.start()
        return True

    def stop(self):
        """Stop the playback handler."""
        self._running = False
        self.clear_queue()

        if pygame.mixer.get_init():
            pygame.mixer.stop()

    def _playback_loop(self):
        """Background loop to play queued audio."""
        while self._running:
            try:
                audio_data = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            self._play_audio(audio_data)

    def _play_audio(self, wav_data: bytes):
        """Play WAV audio data."""
        try:
            # Load WAV from bytes
            wav_io = io.BytesIO(wav_data)
            sound = pygame.mixer.Sound(wav_io)

            self._playing = True
            self._current_sound = sound

            if self.on_playback_start:
                self.on_playback_start()

            # Play and wait for completion
            channel = sound.play()
            while channel.get_busy() and self._running:
                pygame.time.wait(50)

            self._playing = False
            self._current_sound = None

            if self.on_playback_end:
                self.on_playback_end()

        except Exception as e:
            logger.error(f"Playback error: {e}")
            self._playing = False

    def play_base64(self, audio_b64: str):
        """
        Queue base64-encoded WAV audio for playback.

        Args:
            audio_b64: Base64-encoded WAV data
        """
        try:
            wav_data = base64.b64decode(audio_b64)
            self._queue.put(wav_data)
        except Exception as e:
            logger.error(f"Failed to decode audio: {e}")

    def play_bytes(self, wav_data: bytes):
        """
        Queue WAV audio bytes for playback.

        Args:
            wav_data: Raw WAV data
        """
        self._queue.put(wav_data)

    def clear_queue(self):
        """Clear any pending audio."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def stop_current(self):
        """Stop currently playing audio."""
        if self._playing and pygame.mixer.get_init():
            pygame.mixer.stop()

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        return self._playing

    @property
    def queue_size(self) -> int:
        """Get number of queued audio segments."""
        return self._queue.qsize()
