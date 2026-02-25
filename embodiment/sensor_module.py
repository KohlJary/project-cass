"""
Cass Sensor Module - Main Application

Integrates:
- Text face display (pygame)
- Microphone input with VAD
- Audio playback for TTS
- WebSocket connection to Cass backend

State machine:
  IDLE -> LISTENING (VAD detects speech)
  LISTENING -> PROCESSING (speech ends, sending to STT/Cass)
  PROCESSING -> SPEAKING (Cass responds with audio)
  SPEAKING -> IDLE (audio finishes)
"""

import asyncio
import logging
import sys
import os
from enum import Enum
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame

from text_face.text_face import TextFaceRenderer, TEXT_POOL
from audio import MicrophoneInput, AudioPlayer, WakeWordDetector, SpeechToText
from audio.microphone import VADState
from audio.wake_word import WakeWordDetection
from cass_client import CassClient, ConnectionState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


class ModuleState(Enum):
    """Sensor module state machine states."""
    IDLE = "idle"           # Waiting, face gently animated
    LISTENING = "listening"  # Detected speech, recording
    PROCESSING = "processing"  # Sending to Cass, waiting for response
    SPEAKING = "speaking"    # Playing Cass's audio response


class SensorModule:
    """
    Main sensor module application.

    Coordinates between display, audio I/O, and Cass backend.
    """

    def __init__(
        self,
        backend_url: str = "ws://localhost:8000/ws",
        width: int = 480,
        height: int = 800,
        user_id: str = "sensor-module",
        device_name: str = "Embodiment (Emulated)",
        enable_mic: bool = True,
        enable_tts: bool = True,
        enable_wake_word: bool = True,
        wake_word_model: Optional[str] = None,
        stt_model: str = "base",
    ):
        self.width = width
        self.height = height
        self.enable_mic = enable_mic
        self.enable_tts = enable_tts
        self.enable_wake_word = enable_wake_word
        self.wake_word_model = wake_word_model
        self.stt_model = stt_model

        # State
        self.state = ModuleState.IDLE
        self._running = False
        self._pending_text: Optional[str] = None
        self._pending_audio: Optional[tuple[bytes, int]] = None  # (audio_data, sample_rate)
        self._connection_state: str = "disconnected"
        self._last_message: str = ""
        self._wake_word_active = True  # Track if waiting for wake word

        # Components
        self.display: Optional[TextFaceRenderer] = None
        self.mic: Optional[MicrophoneInput] = None
        self.player: Optional[AudioPlayer] = None
        self.client: Optional[CassClient] = None
        self.wake_word: Optional[WakeWordDetector] = None
        self.stt: Optional[SpeechToText] = None

        # Backend config
        self.backend_url = backend_url
        self.user_id = user_id
        self.device_name = device_name

        # Async event loop reference
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _set_state(self, new_state: ModuleState):
        """Update module state and adjust display."""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            logger.info(f"State: {old_state.value} -> {new_state.value}")
            self._update_display_for_state()
            self._update_status()

    def _update_status(self):
        """Update the status line display."""
        if not self.display:
            return

        # Line 1: Connection + State + Wake word
        conn_icon = "●" if self._connection_state == "connected" else "○"
        wake_status = ""
        if self.enable_wake_word:
            wake_status = " | 👂" if self._wake_word_active else " | 🎤"
        line1 = f"{conn_icon} {self._connection_state} | {self.state.value}{wake_status}"

        # Line 2: Last message (truncated)
        line2 = self._last_message[:50] + "..." if len(self._last_message) > 50 else self._last_message

        # Line 3: Controls hint
        line3 = "T:test F1-F6:emote M:rain ESC:quit"

        self.display.set_status(line1, line2, line3)

    def _update_display_for_state(self):
        """Update display appearance based on state."""
        if not self.display:
            return

        if self.state == ModuleState.IDLE:
            # Calm, slow breathing
            self.display.breathing_rate = 0.3
            self.display.base_color = (160, 100, 180)  # Normal purple

        elif self.state == ModuleState.LISTENING:
            # Alert, faster animation
            self.display.breathing_rate = 0.8
            self.display.base_color = (100, 180, 200)  # Shift toward cyan

        elif self.state == ModuleState.PROCESSING:
            # Thinking, pulsing
            self.display.breathing_rate = 1.2
            self.display.base_color = (180, 140, 200)  # Brighter

        elif self.state == ModuleState.SPEAKING:
            # Speaking, animated
            self.display.breathing_rate = 0.6
            self.display.base_color = (200, 120, 180)  # Warm

    # -------------------------------------------------------------------------
    # Audio Callbacks
    # -------------------------------------------------------------------------

    def _on_wake_word(self, detection: WakeWordDetection):
        """Handle wake word detection."""
        if self.state == ModuleState.IDLE and self._wake_word_active:
            logger.info(f"Wake word detected: {detection.model_name} ({detection.confidence:.2f})")
            self._wake_word_active = False  # Disable until interaction complete
            self._last_message = "Listening..."
            self._update_status()

            # Show excited emote
            if self.display:
                self.display.show_emote("excited")

            # Transition to listening
            self._set_state(ModuleState.LISTENING)

    def _on_audio_chunk(self, audio_data: bytes, sample_rate: int):
        """Handle raw audio chunks - route to wake word detector."""
        if self.wake_word and self.state == ModuleState.IDLE and self._wake_word_active:
            self.wake_word.process_audio(audio_data, sample_rate)

    def _on_vad_state(self, vad_state: VADState):
        """Handle VAD state changes."""
        # Only respond to VAD when NOT waiting for wake word
        if self.enable_wake_word and self._wake_word_active:
            return  # Ignore VAD while waiting for wake word

        if vad_state == VADState.SPEECH and self.state == ModuleState.IDLE:
            self._set_state(ModuleState.LISTENING)
        elif vad_state == VADState.SILENCE and self.state == ModuleState.LISTENING:
            # Will transition to PROCESSING when utterance is complete
            pass

    def _on_utterance(self, audio_data: bytes):
        """Handle completed utterance from microphone."""
        logger.info(f"Utterance captured: {len(audio_data)} bytes")
        self._set_state(ModuleState.PROCESSING)

        if self.stt and self.mic:
            # Queue audio for STT processing
            self._pending_audio = (audio_data, self.mic.sample_rate)
            self._last_message = "Transcribing..."
            self._update_status()
        else:
            # No STT available
            logger.warning("STT not available - utterance discarded")
            self._set_state(ModuleState.IDLE)
            self._reset_wake_word()

    def _on_playback_start(self):
        """Handle audio playback starting."""
        self._set_state(ModuleState.SPEAKING)

    def _on_playback_end(self):
        """Handle audio playback ending."""
        if self.state == ModuleState.SPEAKING:
            self._set_state(ModuleState.IDLE)
            # Re-enable wake word detection after interaction complete
            if self.enable_wake_word:
                self._wake_word_active = True
                if self.wake_word:
                    self.wake_word.reset()

    # -------------------------------------------------------------------------
    # Cass Client Callbacks
    # -------------------------------------------------------------------------

    def _on_connection_state(self, state: ConnectionState):
        """Handle connection state changes."""
        logger.info(f"Connection: {state.value}")
        self._connection_state = state.value
        self._update_status()

    def _on_thinking(self):
        """Cass is thinking."""
        if self.state == ModuleState.PROCESSING:
            logger.debug("Cass thinking...")
        self._last_message = "Cass is thinking..."
        self._update_status()

    def _on_response(self, text: str):
        """Received text response from Cass."""
        logger.info(f"Cass: {text[:100]}...")
        self._last_message = f"Cass: {text}"
        self._update_status()
        # Note: Don't go to IDLE here - wait for audio or explicit transition

    def _on_audio(self, audio_b64: str):
        """Received audio response from Cass."""
        if self.player and self.enable_tts:
            self.player.play_base64(audio_b64)
        else:
            # No audio playback, go back to idle and reset wake word
            self._set_state(ModuleState.IDLE)
            self._reset_wake_word()

    def _reset_wake_word(self):
        """Reset wake word detection after interaction."""
        if self.enable_wake_word:
            self._wake_word_active = True
            if self.wake_word:
                self.wake_word.reset()

    def _on_error(self, error: str):
        """Handle error from backend."""
        logger.error(f"Backend error: {error}")
        self._last_message = f"Error: {error}"
        self._set_state(ModuleState.IDLE)
        self._reset_wake_word()

    # -------------------------------------------------------------------------
    # Main Loop
    # -------------------------------------------------------------------------

    async def _async_main(self):
        """Async portion of main loop - handles WebSocket."""
        # Connect to backend
        self.client = CassClient(
            url=self.backend_url,
            user_id=self.user_id,
            device_name=self.device_name,
        )
        self.client.on_state_change = self._on_connection_state
        self.client.on_thinking = self._on_thinking
        self.client.on_response = self._on_response
        self.client.on_audio = self._on_audio
        self.client.on_error = self._on_error

        await self.client.connect()

        # Process pending messages and audio
        while self._running:
            # Handle pending text (from keyboard test)
            if self._pending_text:
                text = self._pending_text
                self._pending_text = None
                self._set_state(ModuleState.PROCESSING)
                await self.client.send_message(text, request_audio=self.enable_tts)

            # Handle pending audio (from microphone)
            if self._pending_audio and self.stt:
                audio_data, sample_rate = self._pending_audio
                self._pending_audio = None

                # Run STT in thread pool to not block
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    self.stt.transcribe,
                    audio_data,
                    sample_rate,
                )

                if result and result.text:
                    logger.info(f"Transcribed: \"{result.text}\" ({result.confidence:.2f})")
                    self._last_message = f"You: {result.text}"
                    self._update_status()

                    # Send to Cass
                    await self.client.send_message(result.text, request_audio=self.enable_tts)
                else:
                    logger.warning("No speech detected in audio")
                    self._last_message = "No speech detected"
                    self._update_status()
                    self._set_state(ModuleState.IDLE)
                    self._reset_wake_word()

            await asyncio.sleep(0.05)

        await self.client.disconnect()

    def _handle_keyboard_input(self, event):
        """Handle keyboard events for testing."""
        if event.key == pygame.K_ESCAPE:
            self._running = False

        elif event.key == pygame.K_RETURN:
            # For testing: type a message with keyboard
            # In real use, this would come from STT
            pass

        elif event.key == pygame.K_t:
            # Test message
            self._pending_text = "Hello Cass, this is a test from the sensor module."
            self._last_message = "Sending: Hello Cass..."
            self._update_status()
            logger.info("Sending test message...")

        elif event.key == pygame.K_r:
            # Regenerate face
            if self.display:
                self.display._generate_particles()

        elif event.key == pygame.K_1:
            self._set_state(ModuleState.IDLE)
        elif event.key == pygame.K_2:
            self._set_state(ModuleState.LISTENING)
        elif event.key == pygame.K_3:
            self._set_state(ModuleState.PROCESSING)
        elif event.key == pygame.K_4:
            self._set_state(ModuleState.SPEAKING)

        # Emote test keys (F1-F6)
        elif event.key == pygame.K_F1:
            if self.display:
                self.display.show_emote("happy")
        elif event.key == pygame.K_F2:
            if self.display:
                self.display.show_emote("concern")
        elif event.key == pygame.K_F3:
            if self.display:
                self.display.show_emote("excited")
        elif event.key == pygame.K_F4:
            if self.display:
                self.display.show_emote("thinking")
        elif event.key == pygame.K_F5:
            if self.display:
                self.display.show_emote("love")
        elif event.key == pygame.K_F6:
            if self.display:
                self.display.show_emote("surprised")
        elif event.key == pygame.K_m:
            # Toggle rain
            if self.display:
                self.display.rain_enabled = not self.display.rain_enabled
                if not self.display.rain_enabled:
                    self.display.rain_drops.clear()

    def run(self):
        """Main entry point."""
        logger.info("Starting Cass Sensor Module...")

        # Initialize pygame
        pygame.init()

        # Create display
        self.display = TextFaceRenderer(
            width=self.width,
            height=self.height,
        )

        # Show initial status
        self._update_status()

        # Initialize audio
        if self.enable_mic:
            self.mic = MicrophoneInput(
                on_utterance=self._on_utterance,
                on_vad_state=self._on_vad_state,
                on_audio_chunk=self._on_audio_chunk if self.enable_wake_word else None,
            )
            if self.mic.available:
                self.mic.start()
            else:
                logger.warning("Microphone not available")

        # Initialize wake word detector
        if self.enable_wake_word and self.enable_mic:
            self.wake_word = WakeWordDetector(
                model_path=self.wake_word_model,
                on_wake_word=self._on_wake_word,
                threshold=0.5,
            )
            if self.wake_word.available:
                self.wake_word.start()
                logger.info("Wake word detection enabled (say 'Hey Jarvis' to activate)")
            else:
                logger.warning("Wake word detection not available")
                self.enable_wake_word = False
                self._wake_word_active = False

        # Initialize STT
        if self.enable_mic:
            self.stt = SpeechToText(
                model_size=self.stt_model,
                device="cpu",
                compute_type="int8",
                language="en",
            )
            if self.stt.available:
                # Load model (this may take a moment on first run)
                logger.info(f"Loading STT model ({self.stt_model})...")
                if self.stt.start():
                    logger.info("STT ready")
                else:
                    logger.warning("Failed to start STT")
                    self.stt = None
            else:
                logger.warning("STT not available")
                self.stt = None

        if self.enable_tts:
            self.player = AudioPlayer()
            self.player.on_playback_start = self._on_playback_start
            self.player.on_playback_end = self._on_playback_end
            if self.player.available:
                self.player.start()
            else:
                logger.warning("Audio playback not available")

        # Start async event loop in background thread
        self._loop = asyncio.new_event_loop()

        def run_async():
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._async_main())
            except Exception as e:
                logger.error(f"Async thread error: {e}")
                import traceback
                traceback.print_exc()

        import threading
        async_thread = threading.Thread(target=run_async, daemon=True)

        self._running = True
        async_thread.start()

        # Main pygame loop
        clock = pygame.time.Clock()

        while self._running:
            dt = clock.tick(30) / 1000.0

            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                elif event.type == pygame.KEYDOWN:
                    self._handle_keyboard_input(event)

            # Update and render
            self.display._update(dt)
            self.display._render()

        # Cleanup
        logger.info("Shutting down...")

        if self.wake_word:
            self.wake_word.stop()
        if self.stt:
            self.stt.stop()
        if self.mic:
            self.mic.stop()
        if self.player:
            self.player.stop()

        pygame.quit()
        logger.info("Goodbye!")


def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Cass Sensor Module")
    parser.add_argument(
        "--backend", "-b",
        default="ws://localhost:8000/ws",
        help="Cass backend WebSocket URL"
    )
    parser.add_argument(
        "--width", "-W",
        type=int, default=480,
        help="Display width"
    )
    parser.add_argument(
        "--height", "-H",
        type=int, default=800,
        help="Display height"
    )
    parser.add_argument(
        "--no-mic",
        action="store_true",
        help="Disable microphone input"
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Disable TTS playback"
    )
    parser.add_argument(
        "--user", "-u",
        default="sensor-module",
        help="User ID for backend"
    )
    parser.add_argument(
        "--device", "-d",
        default="Embodiment (Emulated)",
        help="Device name shown to Cass (e.g., 'Sensor Module - Kitchen')"
    )
    parser.add_argument(
        "--no-wake-word",
        action="store_true",
        help="Disable wake word detection (always listening)"
    )
    parser.add_argument(
        "--wake-word-model",
        default=None,
        help="Path to custom wake word model (.onnx)"
    )
    parser.add_argument(
        "--stt-model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
        help="Whisper model size (tiny=fastest, large-v3=best quality)"
    )

    args = parser.parse_args()

    module = SensorModule(
        backend_url=args.backend,
        width=args.width,
        height=args.height,
        user_id=args.user,
        device_name=args.device,
        enable_mic=not args.no_mic,
        enable_tts=not args.no_tts,
        enable_wake_word=not args.no_wake_word,
        wake_word_model=args.wake_word_model,
        stt_model=args.stt_model,
    )
    module.run()


if __name__ == "__main__":
    main()
