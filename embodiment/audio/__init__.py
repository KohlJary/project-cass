"""Audio subsystem for sensor module."""

from .microphone import MicrophoneInput
from .playback import AudioPlayer
from .wake_word import WakeWordDetector, WakeWordDetection
from .stt import SpeechToText, TranscriptionResult

__all__ = [
    "MicrophoneInput",
    "AudioPlayer",
    "WakeWordDetector",
    "WakeWordDetection",
    "SpeechToText",
    "TranscriptionResult",
]
