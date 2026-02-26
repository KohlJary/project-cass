"""
Sensor Module Configuration

Persistent configuration storage for sensor module settings.
Saves to JSON file and loads on startup.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default config location
CONFIG_PATH = Path(__file__).parent / "sensor_config.json"


@dataclass
class DisplayConfig:
    """Display-related settings."""
    rain_enabled: bool = True
    breathing_rate: float = 0.4  # Hz (0.2 = slow, 0.4 = normal, 0.8 = fast)
    attention_rain_enabled: bool = True  # Auto-enable when gaze detected


@dataclass
class AudioConfig:
    """Audio-related settings."""
    tts_enabled: bool = True
    mic_enabled: bool = True
    wake_word_enabled: bool = True
    stt_model: str = "base"  # tiny, base, small, medium, large-v2, large-v3
    bitcrusher_amount: float = 0.0  # 0.0 = off, 1.0 = maximum effect


@dataclass
class VisionConfig:
    """Vision-related settings."""
    face_recognition_enabled: bool = False
    gaze_detection_enabled: bool = False


@dataclass
class ConnectionConfig:
    """Connection-related settings."""
    backend_url: str = "ws://localhost:8000/ws"
    user_id: str = "sensor-module"
    device_name: str = "Embodiment (Emulated)"


@dataclass
class SensorConfig:
    """Complete sensor module configuration."""
    display: DisplayConfig = field(default_factory=DisplayConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    connection: ConnectionConfig = field(default_factory=ConnectionConfig)

    def to_dict(self) -> dict:
        """Convert config to dictionary for JSON serialization."""
        return {
            "display": asdict(self.display),
            "audio": asdict(self.audio),
            "vision": asdict(self.vision),
            "connection": asdict(self.connection),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SensorConfig":
        """Create config from dictionary."""
        config = cls()

        if "display" in data:
            for key, value in data["display"].items():
                if hasattr(config.display, key):
                    setattr(config.display, key, value)

        if "audio" in data:
            for key, value in data["audio"].items():
                if hasattr(config.audio, key):
                    setattr(config.audio, key, value)

        if "vision" in data:
            for key, value in data["vision"].items():
                if hasattr(config.vision, key):
                    setattr(config.vision, key, value)

        if "connection" in data:
            for key, value in data["connection"].items():
                if hasattr(config.connection, key):
                    setattr(config.connection, key, value)

        return config


def load_config(path: Optional[Path] = None) -> SensorConfig:
    """
    Load configuration from file.

    Returns default config if file doesn't exist or is invalid.
    """
    config_path = path or CONFIG_PATH

    if not config_path.exists():
        logger.info(f"No config file found at {config_path}, using defaults")
        return SensorConfig()

    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        config = SensorConfig.from_dict(data)
        logger.info(f"Loaded config from {config_path}")
        return config
    except Exception as e:
        logger.error(f"Failed to load config from {config_path}: {e}")
        return SensorConfig()


def save_config(config: SensorConfig, path: Optional[Path] = None) -> bool:
    """
    Save configuration to file.

    Returns True if successful, False otherwise.
    """
    config_path = path or CONFIG_PATH

    try:
        with open(config_path, "w") as f:
            json.dump(config.to_dict(), f, indent=2)
        logger.info(f"Saved config to {config_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save config to {config_path}: {e}")
        return False
