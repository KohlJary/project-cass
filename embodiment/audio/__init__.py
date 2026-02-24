"""Audio subsystem for sensor module."""

from .microphone import MicrophoneInput
from .playback import AudioPlayer

__all__ = ["MicrophoneInput", "AudioPlayer"]
