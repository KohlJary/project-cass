#!/usr/bin/env python3
"""
Cass Smart Speaker Client

Connects to Cass backend via WebSocket, handles:
- Wake word detection (openWakeWord)
- Voice recording and STT
- WebSocket chat communication
- TTS audio playback
- LED status feedback (ReSpeaker HAT)

Designed for Raspberry Pi Zero 2 W + ReSpeaker 2-Mic HAT.
"""

import asyncio
import base64
import json
import logging
import os
import signal
import sys
import time
import wave
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Optional

# Audio
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None
    print("Warning: sounddevice not available, using pyaudio fallback")

try:
    import pyaudio
except ImportError:
    pyaudio = None

# WebSocket
import websockets

# Wake word detection
try:
    from openwakeword.model import Model as WakeWordModel
    WAKE_WORD_AVAILABLE = True
except ImportError:
    WAKE_WORD_AVAILABLE = False
    print("Warning: openwakeword not available, using keyboard trigger")

# LED control for ReSpeaker HAT
try:
    from pixel_ring import pixel_ring
    LED_AVAILABLE = True
except ImportError:
    LED_AVAILABLE = False


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cass_speaker")


class SpeakerState(Enum):
    """Current state of the smart speaker."""
    IDLE = "idle"           # Waiting for wake word
    LISTENING = "listening"  # Recording user speech
    PROCESSING = "processing"  # Sending to backend
    SPEAKING = "speaking"    # Playing TTS response
    ERROR = "error"          # Error state


@dataclass
class Config:
    """Speaker configuration."""
    # Backend connection
    backend_url: str = "ws://localhost:8000/ws"
    auth_token: Optional[str] = None

    # Audio settings
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    record_seconds: float = 5.0  # Max recording time
    silence_threshold: float = 0.01  # RMS threshold for silence
    silence_duration: float = 1.5  # Seconds of silence to stop recording

    # Wake word
    wake_word_model: str = "alexa"  # or "hey_jarvis", custom model path
    wake_word_threshold: float = 0.5

    # Paths
    temp_audio_path: Path = Path("/tmp/cass_recording.wav")

    @classmethod
    def from_env(cls) -> "Config":
        """Load config from environment variables."""
        return cls(
            backend_url=os.getenv("CASS_BACKEND_URL", "ws://localhost:8000/ws"),
            auth_token=os.getenv("CASS_AUTH_TOKEN"),
            wake_word_model=os.getenv("CASS_WAKE_WORD", "alexa"),
            wake_word_threshold=float(os.getenv("CASS_WAKE_THRESHOLD", "0.5")),
        )


class LEDController:
    """Control ReSpeaker LED ring for status feedback."""

    def __init__(self):
        self.available = LED_AVAILABLE
        if self.available:
            pixel_ring.set_brightness(10)

    def set_state(self, state: SpeakerState):
        """Update LED pattern based on state."""
        if not self.available:
            logger.debug(f"LED state: {state.value}")
            return

        if state == SpeakerState.IDLE:
            pixel_ring.off()
        elif state == SpeakerState.LISTENING:
            pixel_ring.listen()  # Pulsing blue
        elif state == SpeakerState.PROCESSING:
            pixel_ring.think()  # Spinning animation
        elif state == SpeakerState.SPEAKING:
            pixel_ring.speak()  # Green pulse
        elif state == SpeakerState.ERROR:
            pixel_ring.set_color(r=255, g=0, b=0)  # Red

    def off(self):
        if self.available:
            pixel_ring.off()


class AudioHandler:
    """Handle audio recording and playback."""

    def __init__(self, config: Config):
        self.config = config
        self.pa = None
        if pyaudio:
            self.pa = pyaudio.PyAudio()

    def record_until_silence(self) -> Optional[bytes]:
        """
        Record audio until silence is detected or max time reached.
        Returns WAV bytes or None if failed.
        """
        logger.info("Recording started...")

        frames = []
        silence_frames = 0
        silence_frame_threshold = int(
            self.config.silence_duration * self.config.sample_rate / self.config.chunk_size
        )
        max_frames = int(
            self.config.record_seconds * self.config.sample_rate / self.config.chunk_size
        )

        if sd:
            # Use sounddevice
            def callback(indata, frames_count, time_info, status):
                if status:
                    logger.warning(f"Audio status: {status}")
                frames.append(indata.copy())

            with sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype='int16',
                blocksize=self.config.chunk_size,
                callback=callback
            ):
                while len(frames) < max_frames:
                    sd.sleep(int(self.config.chunk_size / self.config.sample_rate * 1000))

                    if frames:
                        # Check for silence
                        latest = frames[-1]
                        rms = np.sqrt(np.mean(latest.astype(np.float32) ** 2))
                        normalized_rms = rms / 32768.0

                        if normalized_rms < self.config.silence_threshold:
                            silence_frames += 1
                            if silence_frames >= silence_frame_threshold:
                                logger.info("Silence detected, stopping recording")
                                break
                        else:
                            silence_frames = 0

        elif self.pa:
            # Use PyAudio
            stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                frames_per_buffer=self.config.chunk_size
            )

            try:
                for _ in range(max_frames):
                    data = stream.read(self.config.chunk_size, exception_on_overflow=False)
                    frames.append(np.frombuffer(data, dtype=np.int16))

                    # Check for silence
                    rms = np.sqrt(np.mean(frames[-1].astype(np.float32) ** 2))
                    normalized_rms = rms / 32768.0

                    if normalized_rms < self.config.silence_threshold:
                        silence_frames += 1
                        if silence_frames >= silence_frame_threshold:
                            logger.info("Silence detected, stopping recording")
                            break
                    else:
                        silence_frames = 0
            finally:
                stream.stop_stream()
                stream.close()
        else:
            logger.error("No audio library available")
            return None

        if not frames:
            return None

        # Combine frames and convert to WAV
        audio_data = np.concatenate(frames)

        # Write to WAV bytes
        wav_buffer = BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(self.config.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.config.sample_rate)
            wf.writeframes(audio_data.tobytes())

        logger.info(f"Recording complete: {len(audio_data)} samples")
        return wav_buffer.getvalue()

    def play_audio(self, audio_bytes: bytes, format: str = "mp3"):
        """Play audio from bytes."""
        logger.info(f"Playing audio ({len(audio_bytes)} bytes, {format})")

        # For MP3, we need to decode first
        if format == "mp3":
            try:
                import subprocess
                # Use mpg123 or ffplay for MP3 playback
                proc = subprocess.Popen(
                    ["mpg123", "-q", "-"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                proc.communicate(input=audio_bytes)
            except FileNotFoundError:
                # Try ffplay as fallback
                try:
                    proc = subprocess.Popen(
                        ["ffplay", "-nodisp", "-autoexit", "-"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    proc.communicate(input=audio_bytes)
                except FileNotFoundError:
                    logger.error("No MP3 player available (install mpg123 or ffmpeg)")
        else:
            # Assume WAV, play directly
            if sd:
                import soundfile as sf
                data, samplerate = sf.read(BytesIO(audio_bytes))
                sd.play(data, samplerate)
                sd.wait()
            else:
                logger.warning("Direct WAV playback not implemented for PyAudio")

    def cleanup(self):
        if self.pa:
            self.pa.terminate()


class WakeWordDetector:
    """Detect wake word using openWakeWord."""

    def __init__(self, config: Config):
        self.config = config
        self.model = None

        if WAKE_WORD_AVAILABLE:
            try:
                self.model = WakeWordModel(
                    wakeword_models=[config.wake_word_model],
                    inference_framework="onnx"
                )
                logger.info(f"Wake word model loaded: {config.wake_word_model}")
            except Exception as e:
                logger.error(f"Failed to load wake word model: {e}")

    def listen_for_wake_word(self) -> bool:
        """
        Continuously listen for wake word.
        Returns True when wake word detected.
        """
        if not self.model:
            # Fallback: wait for Enter key
            logger.info("Press Enter to activate (wake word not available)...")
            input()
            return True

        logger.info("Listening for wake word...")

        chunk_size = 1280  # openWakeWord expects specific chunk size

        if sd:
            with sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype='int16',
                blocksize=chunk_size
            ) as stream:
                while True:
                    audio_chunk, _ = stream.read(chunk_size)
                    audio_chunk = audio_chunk.flatten()

                    # Run wake word detection
                    prediction = self.model.predict(audio_chunk)

                    for wake_word, score in prediction.items():
                        if score > self.config.wake_word_threshold:
                            logger.info(f"Wake word detected: {wake_word} ({score:.2f})")
                            return True

        return False


class CassSpeakerClient:
    """Main smart speaker client."""

    def __init__(self, config: Config):
        self.config = config
        self.state = SpeakerState.IDLE
        self.led = LEDController()
        self.audio = AudioHandler(config)
        self.wake_word = WakeWordDetector(config)
        self.websocket = None
        self.running = True

        # Conversation tracking
        self.conversation_id: Optional[str] = None

    async def connect(self):
        """Connect to Cass backend."""
        url = self.config.backend_url
        if self.config.auth_token:
            url += f"?token={self.config.auth_token}"

        logger.info(f"Connecting to {self.config.backend_url}...")

        self.websocket = await websockets.connect(url)

        # Wait for connected message
        response = await self.websocket.recv()
        data = json.loads(response)

        if data.get("type") == "connected":
            logger.info(f"Connected to Cass: {data.get('message')}")
            return True
        else:
            logger.error(f"Unexpected response: {data}")
            return False

    async def send_message(self, text: str) -> Optional[dict]:
        """Send a chat message and wait for response."""
        if not self.websocket:
            logger.error("Not connected")
            return None

        message = {
            "type": "chat",
            "message": text,
        }

        if self.conversation_id:
            message["conversation_id"] = self.conversation_id

        await self.websocket.send(json.dumps(message))

        # Wait for response (handle thinking messages)
        while True:
            response = await self.websocket.recv()
            data = json.loads(response)

            msg_type = data.get("type")

            if msg_type == "thinking":
                logger.debug(f"Thinking: {data.get('status')}")
                continue

            elif msg_type == "response":
                # Store conversation ID for continuity
                self.conversation_id = data.get("conversation_id")
                return data

            elif msg_type == "error":
                logger.error(f"Error from server: {data.get('message')}")
                return None

            else:
                logger.debug(f"Received: {msg_type}")

    async def transcribe_audio(self, audio_bytes: bytes) -> Optional[str]:
        """
        Transcribe audio to text via backend STT endpoint.

        The Pi Zero 2 W doesn't have enough RAM for Whisper,
        so we offload transcription to the backend server.
        """
        import aiohttp

        # Build STT endpoint URL from WebSocket URL
        # ws://host:port/ws -> http://host:port/admin/stt/transcribe
        ws_url = self.config.backend_url
        if ws_url.startswith("wss://"):
            http_url = ws_url.replace("wss://", "https://")
        else:
            http_url = ws_url.replace("ws://", "http://")
        http_url = http_url.replace("/ws", "")
        stt_url = f"{http_url}/admin/stt/transcribe"

        # Encode audio as base64
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')

        payload = {
            "audio": audio_b64,
            "format": "wav",
            "language": "en",
        }

        headers = {}
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    stt_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        text = result.get("text", "").strip()
                        logger.info(f"Transcribed: {text}")
                        return text
                    else:
                        error = await response.text()
                        logger.error(f"STT request failed ({response.status}): {error}")
                        return None

        except aiohttp.ClientError as e:
            logger.error(f"STT request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            return None

    def set_state(self, state: SpeakerState):
        """Update speaker state and LED."""
        self.state = state
        self.led.set_state(state)
        logger.info(f"State: {state.value}")

    async def handle_interaction(self):
        """Handle a single voice interaction cycle."""
        try:
            # 1. Record user speech
            self.set_state(SpeakerState.LISTENING)
            audio_bytes = self.audio.record_until_silence()

            if not audio_bytes:
                logger.warning("No audio recorded")
                self.set_state(SpeakerState.ERROR)
                await asyncio.sleep(1)
                return

            # 2. Transcribe
            self.set_state(SpeakerState.PROCESSING)
            text = await self.transcribe_audio(audio_bytes)

            if not text or text.startswith("["):
                logger.warning("Transcription failed")
                self.set_state(SpeakerState.ERROR)
                await asyncio.sleep(1)
                return

            # 3. Send to Cass
            response = await self.send_message(text)

            if not response:
                self.set_state(SpeakerState.ERROR)
                await asyncio.sleep(1)
                return

            # 4. Play response
            self.set_state(SpeakerState.SPEAKING)

            # Check for audio in response
            audio_base64 = response.get("audio")
            if audio_base64:
                audio_bytes = base64.b64decode(audio_base64)
                audio_format = response.get("audio_format", "mp3")
                self.audio.play_audio(audio_bytes, audio_format)
            else:
                # No TTS audio, just log the text
                logger.info(f"Cass: {response.get('text', '')[:100]}...")

        except Exception as e:
            logger.error(f"Interaction error: {e}", exc_info=True)
            self.set_state(SpeakerState.ERROR)
            await asyncio.sleep(1)

        finally:
            self.set_state(SpeakerState.IDLE)

    async def run(self):
        """Main run loop."""
        # Connect to backend
        if not await self.connect():
            logger.error("Failed to connect to backend")
            return

        logger.info("Cass Smart Speaker ready!")
        self.set_state(SpeakerState.IDLE)

        try:
            while self.running:
                # Wait for wake word
                detected = await asyncio.get_event_loop().run_in_executor(
                    None, self.wake_word.listen_for_wake_word
                )

                if detected:
                    await self.handle_interaction()

        except asyncio.CancelledError:
            logger.info("Shutting down...")

        finally:
            self.led.off()
            self.audio.cleanup()
            if self.websocket:
                await self.websocket.close()

    def stop(self):
        """Signal the client to stop."""
        self.running = False


async def main():
    """Entry point."""
    config = Config.from_env()
    client = CassSpeakerClient(config)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, client.stop)

    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
