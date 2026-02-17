"""
Affect-Need Dynamics

Rules for how affects and needs interact:
- Event → affect deltas
- Event → need deltas
- Affect-need coupling (how affects influence needs and vice versa)

All parameters are loaded from thymos_config.json for easy tuning.
"""

import logging
from dataclasses import dataclass

from .models import AffectDelta, NeedDelta, NeedType
from .affect_vector import AffectVector
from .needs_register import NeedsRegister
from .config import get_config, SelfCareActionConfig

logger = logging.getLogger(__name__)


@dataclass
class EventMapping:
    """Defines how an event type affects Thymos state."""
    affect_deltas: dict[str, float]  # dimension -> delta
    need_deltas: dict[str, float]    # need -> delta


# Legacy aliases for backwards compatibility
SelfCareAction = SelfCareActionConfig


def get_event_mapping(event_type: str) -> EventMapping | None:
    """Get event mapping from config."""
    config = get_config()
    event = config.get_event(event_type)
    if event:
        return EventMapping(
            affect_deltas=event.affect_deltas,
            need_deltas=event.need_deltas,
        )
    return None


def get_self_care_action(action_key: str) -> SelfCareActionConfig | None:
    """Get self-care action from config."""
    config = get_config()
    return config.get_care_action(action_key)


def get_care_action_for_need(need_name: str) -> SelfCareActionConfig | None:
    """Get the self-care action for a specific need."""
    config = get_config()
    return config.get_care_action_for_need(need_name)


class AffectNeedDynamics:
    """
    Manages the dynamics between affects and needs.

    Includes:
    - Event → affect/need deltas
    - Affect-need coupling rules

    All parameters loaded from thymos_config.json.
    """

    def __init__(self, coupling_strength: float | None = None):
        """
        Initialize dynamics.

        Args:
            coupling_strength: Override for coupling strength.
                               If None, uses value from config.
        """
        config = get_config()
        self.coupling_strength = coupling_strength if coupling_strength is not None else config.coupling_strength

    def event_to_affect_delta(self, event_type: str, data: dict) -> AffectDelta:
        """
        Convert an event to affect changes.

        Args:
            event_type: The type of event (e.g., "message.received")
            data: Event payload (can modify base deltas)
        """
        config = get_config()
        event = config.get_event(event_type)
        if not event:
            return AffectDelta()

        # Start with base deltas from config
        deltas = dict(event.affect_deltas)

        # Allow event data to modify deltas
        if "affect_modifiers" in data:
            for dim, mod in data["affect_modifiers"].items():
                if dim in deltas:
                    deltas[dim] *= mod
                else:
                    deltas[dim] = mod

        return AffectDelta(
            deltas=deltas,
            source="event",
            event_type=event_type
        )

    def event_to_need_delta(self, event_type: str, data: dict) -> NeedDelta:
        """
        Convert an event to need changes.

        Args:
            event_type: The type of event
            data: Event payload (can modify base deltas)
        """
        config = get_config()
        event = config.get_event(event_type)
        if not event:
            return NeedDelta()

        # Start with base deltas from config
        deltas = dict(event.need_deltas)

        # Allow event data to modify deltas
        if "need_modifiers" in data:
            for need, mod in data["need_modifiers"].items():
                if need in deltas:
                    deltas[need] *= mod
                else:
                    deltas[need] = mod

        return NeedDelta(
            deltas=deltas,
            source="event",
            event_type=event_type
        )

    def apply_coupling(
        self,
        affect: AffectVector,
        needs: NeedsRegister
    ) -> tuple[AffectDelta, NeedDelta]:
        """
        Apply affect-need coupling rules from config.

        Returns (affect_delta, need_delta) from coupling.
        """
        affect_delta = AffectDelta(source="coupling")
        need_delta = NeedDelta(source="coupling")

        config = get_config()

        for rule in config.coupling_rules:
            triggered = False

            # Check if rule condition is met
            if rule.source_type == "affect":
                # Get affect value
                affect_value = getattr(affect.state, rule.source, None)
                if affect_value is not None:
                    if rule.comparison == "above" and affect_value > rule.threshold:
                        triggered = True
                    elif rule.comparison == "below" and affect_value < rule.threshold:
                        triggered = True
            elif rule.source_type == "need":
                # Get need value
                try:
                    need_type = NeedType(rule.source)
                    need = needs.get(need_type)
                    if rule.comparison == "above" and need.current > rule.threshold:
                        triggered = True
                    elif rule.comparison == "below" and need.current < rule.threshold:
                        triggered = True
                except ValueError:
                    logger.warning(f"Unknown need type in coupling rule: {rule.source}")

            # Apply effects if triggered
            if triggered:
                # Scale by coupling strength
                s = self.coupling_strength

                # Apply affect effects
                for affect_name, effect in rule.affect_effects.items():
                    current = affect_delta.deltas.get(affect_name, 0)
                    affect_delta.deltas[affect_name] = current + (effect * s)

                # Apply need effects
                for need_name, effect in rule.need_effects.items():
                    current = need_delta.deltas.get(need_name, 0)
                    need_delta.deltas[need_name] = current + (effect * s)

        return affect_delta, need_delta


# =============================================================================
# COMPATIBILITY LAYER
# =============================================================================
# These provide backwards compatibility for code that uses the old module-level
# constants. They dynamically load from config.

def _get_event_mappings() -> dict[str, EventMapping]:
    """Build EVENT_MAPPINGS dict from config (for backwards compatibility)."""
    config = get_config()
    mappings = {}
    for event_type, event_config in config.events.items():
        mappings[event_type] = EventMapping(
            affect_deltas=event_config.affect_deltas,
            need_deltas=event_config.need_deltas,
        )
    return mappings


def _get_self_care_actions() -> dict[str, SelfCareActionConfig]:
    """Build SELF_CARE_ACTIONS dict from config (for backwards compatibility)."""
    config = get_config()
    return config.self_care_actions


def _get_need_to_care_action() -> dict[str, str]:
    """Build NEED_TO_CARE_ACTION dict from config (for backwards compatibility)."""
    config = get_config()
    return config.need_to_care_action


# Re-export functions for clean API
get_event_mappings = _get_event_mappings
get_all_self_care_actions = _get_self_care_actions
get_need_to_action_mapping = _get_need_to_care_action
