"""
LoRA Manager

Discovers, loads, and manages LoRA adapters for image generation.
Supports house style LoRAs, artist-specific LoRAs, and custom LoRAs.
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime

from .generation_params import LoRAConfig

logger = logging.getLogger(__name__)


@dataclass
class LoRAInfo:
    """Information about an available LoRA."""
    name: str  # Filename without extension
    path: str  # Full path to file
    category: str  # house_style, artist, custom
    display_name: Optional[str] = None  # Human-readable name
    description: Optional[str] = None
    trained_on: Optional[str] = None  # e.g., "SDXL 1.0"
    recommended_strength: float = 0.8
    trigger_words: Optional[list[str]] = None  # Words that activate the style
    created_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LoRAInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class LoRAManager:
    """
    Manages LoRA adapter discovery and configuration.

    Directory structure:
        data/loras/
          ├── house_style/
          │   └── cass_house_style_v1.safetensors
          │   └── cass_house_style_v1.json  (metadata)
          ├── artists/
          │   ├── monet_style.safetensors
          │   └── turner_atmosphere.safetensors
          └── custom/
              └── ...
    """

    VALID_EXTENSIONS = {".safetensors", ".ckpt", ".pt"}

    def __init__(self, lora_dir: Path | str):
        self.lora_dir = Path(lora_dir)
        self._ensure_directories()
        self._cache: dict[str, LoRAInfo] = {}
        self._last_scan: Optional[datetime] = None

    def _ensure_directories(self):
        """Create LoRA directory structure if it doesn't exist."""
        for subdir in ["house_style", "artists", "custom"]:
            (self.lora_dir / subdir).mkdir(parents=True, exist_ok=True)

    def scan(self, force: bool = False) -> list[LoRAInfo]:
        """
        Scan for available LoRAs.

        Args:
            force: Force rescan even if recently scanned

        Returns:
            List of all available LoRAs
        """
        # Cache for 60 seconds unless forced
        if (
            not force
            and self._last_scan
            and (datetime.now() - self._last_scan).seconds < 60
        ):
            return list(self._cache.values())

        self._cache.clear()

        for category in ["house_style", "artists", "custom"]:
            category_dir = self.lora_dir / category
            if not category_dir.exists():
                continue

            for file in category_dir.iterdir():
                if file.suffix.lower() not in self.VALID_EXTENSIONS:
                    continue

                name = file.stem
                info = self._load_lora_info(file, category)
                self._cache[name] = info

        self._last_scan = datetime.now()
        logger.info(f"Scanned {len(self._cache)} LoRAs")
        return list(self._cache.values())

    def _load_lora_info(self, lora_path: Path, category: str) -> LoRAInfo:
        """Load LoRA info, checking for companion metadata file."""
        name = lora_path.stem

        # Check for companion metadata file
        metadata_path = lora_path.with_suffix(".json")
        if metadata_path.exists():
            try:
                with open(metadata_path) as f:
                    metadata = json.load(f)
                return LoRAInfo(
                    name=name,
                    path=str(lora_path),
                    category=category,
                    display_name=metadata.get("display_name", name.replace("_", " ").title()),
                    description=metadata.get("description"),
                    trained_on=metadata.get("trained_on"),
                    recommended_strength=metadata.get("recommended_strength", 0.8),
                    trigger_words=metadata.get("trigger_words"),
                    created_at=metadata.get("created_at"),
                )
            except Exception as e:
                logger.warning(f"Failed to load LoRA metadata {metadata_path}: {e}")

        # Default info without metadata
        return LoRAInfo(
            name=name,
            path=str(lora_path),
            category=category,
            display_name=name.replace("_", " ").title(),
        )

    def list_available(self) -> list[LoRAInfo]:
        """List all available LoRAs."""
        return self.scan()

    def list_by_category(self, category: str) -> list[LoRAInfo]:
        """List LoRAs in a specific category."""
        all_loras = self.scan()
        return [l for l in all_loras if l.category == category]

    def get(self, name: str) -> Optional[LoRAInfo]:
        """Get a specific LoRA by name."""
        self.scan()
        return self._cache.get(name)

    def get_config(
        self,
        name: str,
        strength: Optional[float] = None,
        clip_strength: Optional[float] = None,
    ) -> Optional[LoRAConfig]:
        """
        Get a LoRAConfig for use in generation.

        Args:
            name: LoRA name
            strength: Override model strength (uses recommended if None)
            clip_strength: Override CLIP strength (matches model strength if None)

        Returns:
            LoRAConfig ready for use, or None if not found
        """
        info = self.get(name)
        if not info:
            logger.warning(f"LoRA not found: {name}")
            return None

        actual_strength = strength if strength is not None else info.recommended_strength
        actual_clip = clip_strength if clip_strength is not None else actual_strength

        return LoRAConfig(
            name=info.name,
            strength=actual_strength,
            clip_strength=actual_clip,
        )

    def get_house_style_lora(self, daemon_id: str = "cass") -> Optional[LoRAConfig]:
        """
        Get the house style LoRA for a daemon.

        Args:
            daemon_id: ID of the daemon (for multi-daemon support)

        Returns:
            LoRAConfig for house style, or None if not trained
        """
        house_loras = self.list_by_category("house_style")

        # Look for daemon-specific house style
        for lora in house_loras:
            if daemon_id in lora.name.lower():
                return self.get_config(lora.name)

        # Fall back to generic house style
        for lora in house_loras:
            if "house_style" in lora.name.lower():
                return self.get_config(lora.name)

        return None

    def get_artist_lora(self, artist_name: str) -> Optional[LoRAConfig]:
        """
        Get an artist-specific LoRA.

        Args:
            artist_name: Name of the artist (partial match supported)

        Returns:
            LoRAConfig for artist style, or None if not found
        """
        artist_loras = self.list_by_category("artists")
        artist_lower = artist_name.lower()

        # Exact match first
        for lora in artist_loras:
            if lora.name.lower() == artist_lower or lora.name.lower() == f"{artist_lower}_style":
                return self.get_config(lora.name)

        # Partial match
        for lora in artist_loras:
            if artist_lower in lora.name.lower():
                return self.get_config(lora.name)

        return None

    def save_metadata(
        self,
        lora_name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        trained_on: Optional[str] = None,
        recommended_strength: Optional[float] = None,
        trigger_words: Optional[list[str]] = None,
    ) -> bool:
        """
        Save or update metadata for a LoRA.

        Returns:
            True if successful, False if LoRA not found
        """
        info = self.get(lora_name)
        if not info:
            return False

        lora_path = Path(info.path)
        metadata_path = lora_path.with_suffix(".json")

        # Load existing metadata or start fresh
        metadata = {}
        if metadata_path.exists():
            try:
                with open(metadata_path) as f:
                    metadata = json.load(f)
            except Exception:
                pass

        # Update fields
        if display_name is not None:
            metadata["display_name"] = display_name
        if description is not None:
            metadata["description"] = description
        if trained_on is not None:
            metadata["trained_on"] = trained_on
        if recommended_strength is not None:
            metadata["recommended_strength"] = recommended_strength
        if trigger_words is not None:
            metadata["trigger_words"] = trigger_words

        metadata["updated_at"] = datetime.now().isoformat()

        try:
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)
            # Invalidate cache
            self._last_scan = None
            return True
        except Exception as e:
            logger.error(f"Failed to save LoRA metadata: {e}")
            return False


# Singleton instance (initialized lazily)
_manager: Optional[LoRAManager] = None


def get_lora_manager(lora_dir: Optional[Path | str] = None) -> LoRAManager:
    """Get the singleton LoRA manager instance."""
    global _manager

    if _manager is None:
        if lora_dir is None:
            # Default to data/loras relative to backend
            backend_dir = Path(__file__).parent.parent.parent
            lora_dir = backend_dir / "data" / "loras"
        _manager = LoRAManager(lora_dir)

    return _manager
