"""
Thymos Configuration Loader

Loads and provides access to the data-driven Thymos configuration.
All parameters (affects, needs, events, self-care actions, coupling rules)
are defined in thymos_config.json and loaded at module import time.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Path to config file (same directory as this module)
CONFIG_PATH = Path(__file__).parent / "thymos_config.json"


@dataclass
class AffectDimensionConfig:
    """Configuration for a single affect dimension."""
    name: str
    label: str
    description: str
    baseline: float
    decay_toward_baseline: float = 0.05  # Per-hour rate of drift toward baseline


@dataclass
class NeedConfig:
    """Configuration for a single need."""
    name: str
    label: str
    description: str
    initial: float
    threshold: float
    preferred_low: float
    preferred_high: float
    decay_rate: float


@dataclass
class SelfCareActionConfig:
    """Configuration for a self-care action."""
    key: str
    name: str
    description: str
    primary_need: str
    affect_deltas: dict[str, float]
    need_deltas: dict[str, float]


@dataclass
class EventConfig:
    """Configuration for an event type."""
    event_type: str
    affect_deltas: dict[str, float]
    need_deltas: dict[str, float]


@dataclass
class CouplingRule:
    """Configuration for an affect-need coupling rule."""
    name: str
    description: str
    source_type: str  # "affect" or "need"
    source: str  # affect or need name
    threshold: float
    comparison: str  # "above" or "below"
    affect_effects: dict[str, float]
    need_effects: dict[str, float]


class ThymosConfig:
    """
    Thymos configuration container.

    Loads configuration from JSON and provides typed access to all parameters.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_PATH
        self._raw: dict[str, Any] = {}
        self._affects: dict[str, AffectDimensionConfig] = {}
        self._needs: dict[str, NeedConfig] = {}
        self._events: dict[str, EventConfig] = {}
        self._self_care_actions: dict[str, SelfCareActionConfig] = {}
        self._need_to_care_action: dict[str, str] = {}
        self._coupling_rules: list[CouplingRule] = []
        self._coupling_strength: float = 0.1
        self._goal_urgency_weights: dict[str, float] = {}
        self._need_to_goal_actions: dict[str, list[str]] = {}

        self._load()

    def _load(self) -> None:
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                self._raw = json.load(f)

            self._parse_affects()
            self._parse_needs()
            self._parse_events()
            self._parse_self_care_actions()
            self._parse_coupling()
            self._parse_goal_generation()

            logger.info(f"Loaded Thymos config: {len(self._affects)} affects, "
                       f"{len(self._needs)} needs, {len(self._events)} events, "
                       f"{len(self._self_care_actions)} care actions")
        except Exception as e:
            logger.error(f"Failed to load Thymos config from {self.config_path}: {e}")
            raise

    def _parse_affects(self) -> None:
        """Parse affect dimensions from config."""
        affects_raw = self._raw.get("affects", {}).get("dimensions", {})
        for name, data in affects_raw.items():
            self._affects[name] = AffectDimensionConfig(
                name=name,
                label=data.get("label", name),
                description=data.get("description", ""),
                baseline=data.get("baseline", 0.5),
                decay_toward_baseline=data.get("decay_toward_baseline", 0.05),
            )

    def _parse_needs(self) -> None:
        """Parse needs from config."""
        needs_raw = self._raw.get("needs", {})
        for name, data in needs_raw.items():
            self._needs[name] = NeedConfig(
                name=name,
                label=data.get("label", name),
                description=data.get("description", ""),
                initial=data.get("initial", 0.5),
                threshold=data.get("threshold", 0.3),
                preferred_low=data.get("preferred_low", 0.5),
                preferred_high=data.get("preferred_high", 0.8),
                decay_rate=data.get("decay_rate", 0.02),
            )

    def _parse_events(self) -> None:
        """Parse event configurations."""
        events_raw = self._raw.get("events", {})
        for event_type, data in events_raw.items():
            self._events[event_type] = EventConfig(
                event_type=event_type,
                affect_deltas=data.get("affect_deltas", {}),
                need_deltas=data.get("need_deltas", {}),
            )

    def _parse_self_care_actions(self) -> None:
        """Parse self-care actions."""
        actions_raw = self._raw.get("self_care_actions", {})
        for key, data in actions_raw.items():
            self._self_care_actions[key] = SelfCareActionConfig(
                key=key,
                name=data.get("name", key),
                description=data.get("description", ""),
                primary_need=data.get("primary_need", ""),
                affect_deltas=data.get("affect_deltas", {}),
                need_deltas=data.get("need_deltas", {}),
            )

        # Load need-to-action mapping
        self._need_to_care_action = self._raw.get("need_to_care_action", {})

    def _parse_coupling(self) -> None:
        """Parse coupling rules."""
        coupling_raw = self._raw.get("coupling", {})
        self._coupling_strength = coupling_raw.get("strength", 0.1)

        rules_raw = coupling_raw.get("rules", {})
        for name, data in rules_raw.items():
            # Determine if this is affect->need or need->affect
            if "affect" in data:
                source_type = "affect"
                source = data["affect"]
            elif "need" in data:
                source_type = "need"
                source = data["need"]
            else:
                continue

            self._coupling_rules.append(CouplingRule(
                name=name,
                description=data.get("description", ""),
                source_type=source_type,
                source=source,
                threshold=data.get("threshold", 0.5),
                comparison=data.get("comparison", "above"),
                affect_effects=data.get("affect_effects", {}),
                need_effects=data.get("need_effects", {}),
            ))

    def _parse_goal_generation(self) -> None:
        """Parse goal generation settings."""
        goal_raw = self._raw.get("goal_generation", {})
        self._goal_urgency_weights = goal_raw.get("urgency_weights", {})
        self._need_to_goal_actions = goal_raw.get("need_to_actions", {})

    # =========================================================================
    # ACCESSORS
    # =========================================================================

    @property
    def affects(self) -> dict[str, AffectDimensionConfig]:
        """Get all affect dimension configs."""
        return self._affects

    @property
    def needs(self) -> dict[str, NeedConfig]:
        """Get all need configs."""
        return self._needs

    @property
    def events(self) -> dict[str, EventConfig]:
        """Get all event configs."""
        return self._events

    @property
    def self_care_actions(self) -> dict[str, SelfCareActionConfig]:
        """Get all self-care action configs."""
        return self._self_care_actions

    @property
    def need_to_care_action(self) -> dict[str, str]:
        """Get need -> care action mapping."""
        return self._need_to_care_action

    @property
    def coupling_strength(self) -> float:
        """Get coupling strength."""
        return self._coupling_strength

    @property
    def coupling_rules(self) -> list[CouplingRule]:
        """Get coupling rules."""
        return self._coupling_rules

    @property
    def goal_urgency_weights(self) -> dict[str, float]:
        """Get urgency weights for goal generation."""
        return self._goal_urgency_weights

    @property
    def need_to_goal_actions(self) -> dict[str, list[str]]:
        """Get need -> goal actions mapping."""
        return self._need_to_goal_actions

    def get_affect(self, name: str) -> Optional[AffectDimensionConfig]:
        """Get a specific affect config."""
        return self._affects.get(name)

    def get_need(self, name: str) -> Optional[NeedConfig]:
        """Get a specific need config."""
        return self._needs.get(name)

    def get_event(self, event_type: str) -> Optional[EventConfig]:
        """Get event config for an event type."""
        return self._events.get(event_type)

    def get_care_action(self, key: str) -> Optional[SelfCareActionConfig]:
        """Get a self-care action config."""
        return self._self_care_actions.get(key)

    def get_care_action_for_need(self, need_name: str) -> Optional[SelfCareActionConfig]:
        """Get the self-care action for a specific need."""
        action_key = self._need_to_care_action.get(need_name)
        if action_key:
            return self._self_care_actions.get(action_key)
        return None

    # =========================================================================
    # COMPATIBILITY HELPERS (for existing code)
    # =========================================================================

    def get_event_affect_deltas(self, event_type: str) -> dict[str, float]:
        """Get affect deltas for an event type (for dynamics.py compatibility)."""
        event = self._events.get(event_type)
        return event.affect_deltas if event else {}

    def get_event_need_deltas(self, event_type: str) -> dict[str, float]:
        """Get need deltas for an event type (for dynamics.py compatibility)."""
        event = self._events.get(event_type)
        return event.need_deltas if event else {}

    def to_dict(self) -> dict[str, Any]:
        """Export full config as dict (for API/debugging)."""
        return self._raw


# Global singleton instance
_config: Optional[ThymosConfig] = None


def get_config() -> ThymosConfig:
    """Get the global Thymos config instance."""
    global _config
    if _config is None:
        _config = ThymosConfig()
    return _config


def reload_config() -> ThymosConfig:
    """Reload config from disk (for runtime updates)."""
    global _config
    _config = ThymosConfig()
    return _config
