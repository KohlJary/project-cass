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
import os
import sys
import threading
from enum import Enum
from pathlib import Path
from typing import Optional

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame

from text_face.text_face import TextFaceRenderer, TEXT_POOL
from text_face.pages import create_test_page, create_menu_page, create_about_page, create_settings_page
from config import SensorConfig, load_config, save_config
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

# Optional face recognition (imported after logger configured)
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'vision'))
    from face_recognition_module import FaceRecognizer, RecognizedFace, FACE_RECOGNITION_AVAILABLE
except ImportError as e:
    FACE_RECOGNITION_AVAILABLE = False
    FaceRecognizer = None
    logger.warning(f"Face recognition not available: {e}")

# Optional gaze/attention detection
try:
    from attention_detector import AttentionDetector, AttentionState, MEDIAPIPE_AVAILABLE
except ImportError as e:
    MEDIAPIPE_AVAILABLE = False
    AttentionDetector = None
    logger.warning(f"Attention detection not available: {e}")


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
        enable_face_recognition: bool = False,
        face_recognition_backend: Optional[str] = None,
        enable_gaze_detection: bool = False,
    ):
        self.width = width
        self.height = height
        self.enable_mic = enable_mic
        self.enable_tts = enable_tts
        self.enable_wake_word = enable_wake_word
        self.wake_word_model = wake_word_model
        self.stt_model = stt_model
        self.enable_face_recognition = enable_face_recognition
        self.face_recognition_backend = face_recognition_backend
        self.enable_gaze_detection = enable_gaze_detection

        # State
        self.state = ModuleState.IDLE
        self._running = False
        self._pending_text: Optional[str] = None
        self._pending_audio: Optional[tuple[bytes, int]] = None  # (audio_data, sample_rate)
        self._pending_tts_test: Optional[str] = None  # Direct TTS test (text with emote tags)
        self._connection_state: str = "disconnected"
        self._last_message: str = ""
        self._wake_word_active = True  # Track if waiting for wake word
        self._current_face_user: Optional[str] = None  # Currently recognized user
        self._gaze_looking = False  # Is user looking at camera?

        # Vision thread state (updated by background thread)
        self._vision_thread = None
        self._vision_running = False
        self._vision_lock = threading.Lock()
        self._pending_status_update = False  # Flag to update status from main thread
        self._pending_emote: Optional[str] = None  # Emote to show from main thread

        # Components
        self.display: Optional[TextFaceRenderer] = None
        self.mic: Optional[MicrophoneInput] = None
        self.player: Optional[AudioPlayer] = None
        self.client: Optional[CassClient] = None
        self.wake_word: Optional[WakeWordDetector] = None
        self.stt: Optional[SpeechToText] = None
        self.face_recognizer: Optional["FaceRecognizer"] = None
        self.attention_detector: Optional["AttentionDetector"] = None
        self.camera = None  # cv2.VideoCapture

        # Backend config
        self.backend_url = backend_url
        self.user_id = user_id
        self.device_name = device_name

        # Configuration (loaded from file, can be modified via settings)
        self.config: Optional[SensorConfig] = None

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
        line3 = "T:test P:page M:menu N:rain ESC:quit"

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

    def _check_gaze(self, frame):
        """Check gaze direction and update gaze state (called from vision thread)."""
        if not self.attention_detector:
            return

        result = self.attention_detector.process_frame(frame)

        # Update shared gaze state
        looking = result.state in [AttentionState.LOOKING_AT_CAMERA, AttentionState.ENGAGED]
        with self._vision_lock:
            self._gaze_looking = looking

        # Log engagement events
        if result.state == AttentionState.ENGAGED:
            logger.debug(f"Engaged: {result.attention_duration:.1f}s")

    def _vision_thread_func(self):
        """Background thread for vision processing (face recognition + gaze)."""
        import time
        logger.info("Vision thread started")

        while self._vision_running and self.camera:
            try:
                ret, frame = self.camera.read()
                if not ret:
                    time.sleep(0.1)
                    continue

                # Face recognition
                if self.enable_face_recognition and self.face_recognizer:
                    faces = self.face_recognizer.recognize(frame)

                    # Update shared state
                    with self._vision_lock:
                        if faces:
                            for f in faces:
                                if f.is_known and f.user_id:
                                    if f.user_id != self._current_face_user:
                                        logger.info(f"Recognized: {f.user_name} ({f.confidence:.0%})")
                                        self._current_face_user = f.user_id
                                        self.user_id = f.user_id
                                        if self.client:
                                            self.client.user_id = f.user_id
                                        self._last_message = f"👋 Hi, {f.user_name}!"
                                        self._pending_status_update = True
                                        self._pending_emote = "happy"
                                    break
                            else:
                                # Only unknown faces
                                if self._current_face_user:
                                    logger.info("Face lost")
                                    self._current_face_user = None
                        else:
                            if self._current_face_user:
                                self._current_face_user = None

                # Gaze detection
                if self.enable_gaze_detection:
                    self._check_gaze(frame)

                # Throttle to ~1 FPS for vision processing (face recognition is CPU intensive)
                time.sleep(1.0)

            except Exception as e:
                logger.error(f"Vision thread error: {e}")
                time.sleep(1.0)

        logger.info("Vision thread stopped")

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

            # Handle pending TTS test (direct synthesis, no Cass response)
            if self._pending_tts_test:
                test_text = self._pending_tts_test
                self._pending_tts_test = None
                logger.info(f"Generating TTS test: {test_text[:50]}...")
                audio_b64 = await self.client.generate_tts(test_text)
                if audio_b64 and self.player:
                    logger.info(f"Got TTS audio: {len(audio_b64)} chars")
                    self.player.play_base64(audio_b64)
                else:
                    logger.warning("TTS test failed - no audio returned")
                    self._last_message = "TTS test failed"
                    self._update_status()

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
        # Route to display first for page handling
        if self.display and self.display.handle_event(event):
            return

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
            # Toggle menu page
            if self.display:
                if self.display.page_manager.has_page:
                    self.display.page_manager.clear()
                else:
                    page = create_menu_page(
                        on_close=lambda: self.display.page_manager.pop() if self.display else None,
                        on_settings=self._show_settings_page,
                        on_about=self._show_about_page,
                    )
                    self.display.page_manager.push(page)

        elif event.key == pygame.K_p:
            # Toggle test page
            if self.display:
                if self.display.page_manager.has_page:
                    self.display.page_manager.clear()
                else:
                    page = create_test_page(
                        on_close=lambda: self.display.page_manager.pop() if self.display else None
                    )
                    self.display.page_manager.push(page)

        elif event.key == pygame.K_n:
            # Toggle rain (moved from M)
            if self.display:
                self.display.rain_enabled = not self.display.rain_enabled
                if not self.display.rain_enabled:
                    self.display.rain_drops.clear()

    def _on_settings_icon_click(self):
        """Handle click on the settings gear icon."""
        if self.display and not self.display.page_manager.has_page:
            page = create_menu_page(
                on_close=lambda: self.display.page_manager.pop() if self.display else None,
                on_settings=self._show_settings_page,
                on_about=self._show_about_page,
            )
            self.display.page_manager.push(page)

    def _show_about_page(self):
        """Show the about page."""
        if self.display:
            page = create_about_page(
                on_close=lambda: self.display.page_manager.pop() if self.display else None
            )
            self.display.page_manager.push(page)

    def _show_settings_page(self):
        """Show the settings page."""
        if not self.display or not self.config:
            return

        page = create_settings_page(
            config=self.config,
            on_close=lambda: self.display.page_manager.pop() if self.display else None,
            on_save=self._on_settings_save,
            on_show_emote=self._on_demo_emote,
            on_test_voice=self._on_test_voice,
        )
        self.display.page_manager.push(page)

    def _on_demo_emote(self, emote: str):
        """Demo an emote on the face."""
        if self.display:
            self.display.show_emote(emote)
            logger.debug(f"Demo emote: {emote}")

    def _on_test_voice(self, emote: str):
        """Test voice with an emote tone using direct TTS (no Cass response)."""
        # Create a test phrase with the emote
        test_phrases = {
            "happy": "Hello! I'm so glad to see you!",
            "excited": "Oh wow, that's amazing news!",
            "thinking": "Hmm, let me consider that carefully...",
            "concern": "I understand, that sounds difficult.",
            "love": "You're wonderful, and I appreciate you.",
            "surprised": "Oh! I didn't expect that at all!",
        }
        phrase = test_phrases.get(emote, "Hello, this is a voice test.")
        test_text = f"<emote:{emote}> {phrase}"

        # Show the emote on the face too
        if self.display:
            self.display.show_emote(emote)

        # Queue direct TTS synthesis (doesn't go through Cass)
        self._pending_tts_test = test_text
        self._last_message = f"Testing voice: {emote}"
        self._update_status()
        logger.info(f"Testing voice with emote: {emote}")

    def _on_settings_save(self, config: SensorConfig):
        """Handle settings save - apply changes and persist to disk."""
        self.config = config
        self._apply_config()
        save_config(config)
        logger.info("Settings saved")

    def _apply_config(self):
        """Apply current config to running components."""
        if not self.config or not self.display:
            return

        # Apply display settings
        self.display.rain_enabled = self.config.display.rain_enabled
        self.display.breathing_rate = self.config.display.breathing_rate

        # Apply audio settings that can change at runtime
        if self.player:
            self.player.bitcrusher_amount = self.config.audio.bitcrusher_amount
            logger.info(f"Set player bitcrusher_amount to {self.player.bitcrusher_amount}")

        # Note: Other audio and vision settings require restart to take effect

    def run(self):
        """Main entry point."""
        logger.info("Starting Cass Sensor Module...")

        # Load configuration
        self.config = load_config()
        logger.info(f"Loaded config: rain={self.config.display.rain_enabled}, "
                    f"tts={self.config.audio.tts_enabled}")

        # Initialize pygame
        pygame.init()

        # Create display
        self.display = TextFaceRenderer(
            width=self.width,
            height=self.height,
        )

        # Set up settings icon callback
        self.display.on_settings_click = self._on_settings_icon_click

        # Apply initial config to display
        self._apply_config()

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

        # Initialize face recognition
        if self.enable_face_recognition:
            if not FACE_RECOGNITION_AVAILABLE:
                logger.warning("Face recognition not available - dependencies not installed")
                self.enable_face_recognition = False
            else:
                try:
                    import cv2
                    # Determine backend URL for remote database
                    if self.face_recognition_backend:
                        backend_http = self.face_recognition_backend
                    else:
                        # Derive HTTP URL from WebSocket URL
                        backend_http = self.backend_url.replace("ws://", "http://").replace("wss://", "https://")
                        backend_http = backend_http.replace("/ws", "")

                    self.face_recognizer = FaceRecognizer(
                        remote_backend=backend_http,
                        tolerance=0.6,  # face_recognition default
                        min_confidence=0.1,  # Low threshold - distance ~0.5 gives ~17% confidence
                    )

                    # Open camera
                    self.camera = cv2.VideoCapture(0)
                    if self.camera.isOpened():
                        logger.info(f"Face recognition enabled with remote database: {backend_http}")
                        # Initial sync and refresh cache
                        if hasattr(self.face_recognizer.db, 'sync'):
                            if self.face_recognizer.db.sync():
                                # Refresh the recognizer's cache after sync
                                self.face_recognizer._refresh_cache()
                                users = self.face_recognizer.db.list_users()
                                logger.info(f"Synced {len(users)} face(s) from backend")
                                for u in users:
                                    logger.info(f"  - {u.get('name', u.get('user_id'))}")
                                logger.info(f"Recognizer cache: {len(self.face_recognizer._known_encodings)} encodings")
                            else:
                                logger.warning("Failed to sync face database from backend")
                    else:
                        logger.warning("Could not open camera for face recognition")
                        self.camera = None
                        self.face_recognizer = None
                        self.enable_face_recognition = False
                except Exception as e:
                    logger.error(f"Failed to initialize face recognition: {e}")
                    self.enable_face_recognition = False

        # Initialize gaze/attention detection
        if self.enable_gaze_detection:
            if not MEDIAPIPE_AVAILABLE:
                logger.warning("Gaze detection not available - mediapipe not installed")
                self.enable_gaze_detection = False
            elif not self.camera:
                # Need camera for gaze detection - try to open if face recognition didn't
                try:
                    import cv2
                    self.camera = cv2.VideoCapture(0)
                    if not self.camera.isOpened():
                        logger.warning("Could not open camera for gaze detection")
                        self.enable_gaze_detection = False
                except Exception as e:
                    logger.error(f"Failed to open camera for gaze detection: {e}")
                    self.enable_gaze_detection = False

            if self.enable_gaze_detection:
                self.attention_detector = AttentionDetector(
                    engagement_threshold=1.5,
                    gaze_threshold=0.15,
                )
                logger.info("Gaze detection enabled")

        # Start vision thread if we have camera and vision features enabled
        if self.camera and (self.enable_face_recognition or self.enable_gaze_detection):
            if self._vision_thread is not None and self._vision_thread.is_alive():
                logger.warning("Vision thread already running - skipping")
            else:
                self._vision_running = True
                self._vision_thread = threading.Thread(target=self._vision_thread_func, daemon=True)
                self._vision_thread.start()
                logger.info("Vision processing thread started")

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
                elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
                    # Route mouse events to display for page interaction
                    if self.display:
                        self.display.handle_event(event)

            # Read shared vision state (updated by background thread)
            with self._vision_lock:
                if self.enable_gaze_detection and self.display:
                    self.display.attention_rain_enabled = self._gaze_looking
                # Handle pending UI updates from vision thread
                if self._pending_status_update:
                    self._pending_status_update = False
                    self._update_status()
                if self._pending_emote and self.display:
                    self.display.show_emote(self._pending_emote)
                    self._pending_emote = None

            # Update and render
            self.display._update(dt)
            self.display._render()

        # Cleanup
        logger.info("Shutting down...")

        # Stop vision thread
        if self._vision_thread:
            self._vision_running = False
            self._vision_thread.join(timeout=1.0)
            logger.info("Vision thread stopped")

        if self.wake_word:
            self.wake_word.stop()
        if self.stt:
            self.stt.stop()
        if self.mic:
            self.mic.stop()
        if self.player:
            self.player.stop()
        if self.camera:
            self.camera.release()

        pygame.quit()
        logger.info("Goodbye!")


def _env_bool(key: str, default: bool = False) -> bool:
    """Get boolean from environment variable."""
    val = os.environ.get(key, "").lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off"):
        return False
    return default


def main():
    """Entry point."""
    import argparse

    # Defaults from environment
    env_backend = os.environ.get("CASS_BACKEND_URL", "ws://localhost:8000/ws")
    env_width = int(os.environ.get("DISPLAY_WIDTH", "480"))
    env_height = int(os.environ.get("DISPLAY_HEIGHT", "800"))
    env_user = os.environ.get("USER_ID", "sensor-module")
    env_device = os.environ.get("DEVICE_NAME", "Embodiment (Emulated)")
    env_mic = _env_bool("ENABLE_MIC", True)
    env_tts = _env_bool("ENABLE_TTS", True)
    env_wake_word = _env_bool("ENABLE_WAKE_WORD", True)
    env_wake_model = os.environ.get("WAKE_WORD_MODEL")
    env_stt_model = os.environ.get("STT_MODEL", "base")
    env_face_recognition = _env_bool("ENABLE_FACE_RECOGNITION", False)
    env_gaze_detection = _env_bool("ENABLE_GAZE_DETECTION", False)
    env_face_backend = os.environ.get("FACE_BACKEND_URL")

    parser = argparse.ArgumentParser(description="Cass Sensor Module")
    parser.add_argument(
        "--backend", "-b",
        default=env_backend,
        help="Cass backend WebSocket URL"
    )
    parser.add_argument(
        "--width", "-W",
        type=int, default=env_width,
        help="Display width"
    )
    parser.add_argument(
        "--height", "-H",
        type=int, default=env_height,
        help="Display height"
    )
    parser.add_argument(
        "--no-mic",
        action="store_true",
        default=not env_mic,
        help="Disable microphone input"
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        default=not env_tts,
        help="Disable TTS playback"
    )
    parser.add_argument(
        "--user", "-u",
        default=env_user,
        help="User ID for backend"
    )
    parser.add_argument(
        "--device", "-d",
        default=env_device,
        help="Device name shown to Cass (e.g., 'Sensor Module - Kitchen')"
    )
    parser.add_argument(
        "--no-wake-word",
        action="store_true",
        default=not env_wake_word,
        help="Disable wake word detection (always listening)"
    )
    parser.add_argument(
        "--wake-word-model",
        default=env_wake_model,
        help="Path to custom wake word model (.onnx)"
    )
    parser.add_argument(
        "--stt-model",
        default=env_stt_model,
        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
        help="Whisper model size (tiny=fastest, large-v3=best quality)"
    )
    parser.add_argument(
        "--face-recognition",
        action="store_true",
        default=env_face_recognition,
        help="Enable face recognition for user identification"
    )
    parser.add_argument(
        "--face-backend",
        default=env_face_backend,
        help="Backend URL for face database (defaults to HTTP version of WebSocket URL)"
    )
    parser.add_argument(
        "--gaze-detection",
        action="store_true",
        default=env_gaze_detection,
        help="Enable gaze/attention detection (shows blue rain when looking at camera)"
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
        enable_face_recognition=args.face_recognition,
        face_recognition_backend=args.face_backend,
        enable_gaze_detection=args.gaze_detection,
    )
    module.run()


if __name__ == "__main__":
    main()
