"""
Audio playback for TTS output.

Plays audio received from Cass backend (base64 WAV/MP3).
Supports bitcrusher effect for lo-fi character.
"""

import base64
import io
import logging
import struct
import threading
import queue
import wave
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

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.info("numpy not available - bitcrusher disabled")


def apply_bitcrusher(audio_data: bytes, amount: float, sample_rate: int = 22050) -> bytes:
    """
    Apply bitcrusher effect to WAV audio data.

    Args:
        audio_data: Raw WAV data (with header)
        amount: Effect strength 0.0 (off) to 1.0 (maximum)
        sample_rate: Original sample rate

    Returns:
        Processed WAV data
    """
    if not NUMPY_AVAILABLE or amount <= 0:
        return audio_data

    try:
        # Parse WAV
        wav_io = io.BytesIO(audio_data)
        with wave.open(wav_io, 'rb') as wav:
            n_channels = wav.getnchannels()
            sampwidth = wav.getsampwidth()
            framerate = wav.getframerate()
            n_frames = wav.getnframes()
            raw_data = wav.readframes(n_frames)

        # Convert to numpy array
        if sampwidth == 2:
            samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
        else:
            return audio_data  # Only support 16-bit

        # Bitcrusher parameters based on amount
        # At amount=1.0: reduce to ~4 bits and 1/8 sample rate
        # At amount=0.5: reduce to ~8 bits and 1/4 sample rate
        bit_reduction = int(1 + amount * 11)  # 1-12 bits to remove
        rate_divisor = max(1, int(1 + amount * 7))  # 1-8x downsampling
        logger.info(f"Bitcrusher params: bit_reduction={bit_reduction}, rate_divisor={rate_divisor}")

        # Reduce bit depth
        bit_mask = ~((1 << bit_reduction) - 1)
        samples = (samples.astype(np.int32) & bit_mask).astype(np.float32)

        # Downsample then upsample (sample-and-hold)
        if rate_divisor > 1:
            # Take every Nth sample
            downsampled = samples[::rate_divisor]
            # Repeat each sample N times
            samples = np.repeat(downsampled, rate_divisor)[:len(samples)]

        # Add a tiny bit of noise for character (optional)
        if amount > 0.5:
            noise_level = (amount - 0.5) * 200
            noise = np.random.randint(-int(noise_level), int(noise_level) + 1, len(samples))
            samples = samples + noise

        # Clip and convert back to int16
        samples = np.clip(samples, -32768, 32767).astype(np.int16)

        # Write back to WAV
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav_out:
            wav_out.setnchannels(n_channels)
            wav_out.setsampwidth(sampwidth)
            wav_out.setframerate(framerate)
            wav_out.writeframes(samples.tobytes())

        return output.getvalue()

    except Exception as e:
        logger.warning(f"Bitcrusher failed: {e}")
        return audio_data


class AudioPlayer:
    """
    Audio playback handler.

    Plays WAV audio from base64-encoded data (as sent by Cass backend).
    Supports queueing multiple audio segments.
    Supports bitcrusher effect for lo-fi character.
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

        # Bitcrusher effect amount (0.0 = off, 1.0 = maximum)
        self.bitcrusher_amount: float = 0.0

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

    def _play_audio(self, audio_data: bytes):
        """Play audio data (WAV or MP3)."""
        try:
            logger.info(f"Playing audio: {len(audio_data)} bytes, header: {audio_data[:4]}")

            # Apply bitcrusher effect if enabled (only works on WAV)
            # Check if this is WAV data (starts with RIFF header)
            is_wav = audio_data[:4] == b'RIFF'
            logger.info(f"Bitcrusher: amount={self.bitcrusher_amount}, is_wav={is_wav}")
            if self.bitcrusher_amount > 0 and is_wav:
                logger.info(f"Applying bitcrusher at {self.bitcrusher_amount:.0%}")
                audio_data = apply_bitcrusher(audio_data, self.bitcrusher_amount, self.sample_rate)
                logger.info(f"After bitcrusher: {len(audio_data)} bytes")

            # Load audio from bytes (pygame can handle WAV and MP3)
            audio_io = io.BytesIO(audio_data)
            sound = pygame.mixer.Sound(audio_io)

            self._playing = True
            self._current_sound = sound

            if self.on_playback_start:
                self.on_playback_start()

            # Play and wait for completion
            channel = sound.play()
            if channel is None:
                logger.error("Failed to get audio channel")
                self._playing = False
                return

            logger.debug("Audio playing...")
            while channel.get_busy() and self._running:
                pygame.time.wait(50)

            logger.debug("Audio finished")
            self._playing = False
            self._current_sound = None

            if self.on_playback_end:
                self.on_playback_end()

        except Exception as e:
            logger.error(f"Playback error: {e}")
            import traceback
            traceback.print_exc()
            self._playing = False

    def play_base64(self, audio_b64: str):
        """
        Queue base64-encoded audio for playback.

        Args:
            audio_b64: Base64-encoded audio data (WAV or MP3)
        """
        try:
            audio_data = base64.b64decode(audio_b64)
            logger.debug(f"Decoded audio: {len(audio_data)} bytes, header: {audio_data[:4]}")
            self._queue.put(audio_data)
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
