"""
Needs Register

Tracks functional needs with homeostatic dynamics:
- Thresholds (below = urgent)
- Preferred ranges (homeostatic target)
- Decay rates (time-based depletion)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .models import (
    Need, NeedType, NeedsState, NeedDelta,
    SuggestedGoal,
)
from uuid import uuid4


@dataclass
class NeedsRegister:
    """
    Manages the needs register with homeostatic dynamics.

    Each need has:
    - current level (0.0-1.0)
    - threshold (below = urgent)
    - preferred range (homeostatic target)
    - decay rate (per-hour depletion)
    """

    state: NeedsState
    last_decay_time: Optional[datetime] = None

    def __init__(self, state: Optional[NeedsState] = None):
        """Initialize with state or defaults."""
        self.state = state or NeedsState()
        self.last_decay_time = datetime.now()

    def get(self, need_type: NeedType) -> Need:
        """Get a specific need."""
        return self.state.get_need(need_type)

    def set_current(self, need_type: NeedType, value: float) -> None:
        """Set a need's current value (clamped to 0.0-1.0)."""
        need = self.get(need_type)
        need.current = max(0.0, min(1.0, value))

    def apply_delta(self, delta: NeedDelta) -> None:
        """Apply a delta to affected needs."""
        delta.apply_to(self.state)

    def apply_decay(self, hours: Optional[float] = None) -> None:
        """
        Apply time-based decay to all needs.

        If hours is not provided, calculates based on time since last decay.
        """
        now = datetime.now()

        if hours is None:
            if self.last_decay_time is None:
                self.last_decay_time = now
                return
            elapsed = (now - self.last_decay_time).total_seconds() / 3600.0
        else:
            elapsed = hours

        if elapsed <= 0:
            return

        for need in self.state.all_needs():
            decay_amount = need.decay_rate * elapsed
            need.current = max(0.0, need.current - decay_amount)

        self.last_decay_time = now

    def urgent_needs(self) -> list[Need]:
        """Get all needs below their threshold."""
        return [n for n in self.state.all_needs() if n.is_urgent()]

    def pressing_needs(self) -> list[Need]:
        """Get all needs below their preferred range."""
        return [n for n in self.state.all_needs() if n.is_below_preferred()]

    def satisfied_needs(self) -> list[Need]:
        """Get all needs within or above their preferred range."""
        return [n for n in self.state.all_needs() if not n.is_below_preferred()]

    def most_depleted(self) -> tuple[Need, float]:
        """
        Find the most depleted need.

        Returns (need, urgency_score).
        """
        all_needs = self.state.all_needs()
        if not all_needs:
            # Should never happen, but satisfy type checker
            raise ValueError("No needs registered")

        most_urgent = all_needs[0]
        max_urgency = most_urgent.urgency_score()

        for need in all_needs[1:]:
            urgency = need.urgency_score()
            if urgency > max_urgency:
                max_urgency = urgency
                most_urgent = need

        return most_urgent, max_urgency

    def check_for_goals(self) -> list[SuggestedGoal]:
        """
        Check needs and generate goal suggestions.

        Returns suggestions for needs below their preferred range.
        """
        suggestions = []

        for need in self.state.all_needs():
            if need.is_below_preferred():
                urgency = need.urgency_score()
                suggestion = self._suggest_goal_for_need(need, urgency)
                suggestions.append(suggestion)

        # Sort by urgency (most urgent first)
        suggestions.sort(key=lambda s: s.urgency, reverse=True)
        return suggestions

    def _suggest_goal_for_need(self, need: Need, urgency: float) -> SuggestedGoal:
        """Generate a goal suggestion for a specific need."""
        action, category, rationale = _get_suggested_action(need.name)

        return SuggestedGoal(
            id=f"goal-{uuid4().hex[:8]}",
            need_name=need.name,
            need_current=need.current,
            need_threshold=need.threshold,
            urgency=urgency,
            suggested_action=action,
            action_category=category,
            is_urgent=need.is_urgent(),
            rationale=rationale,
        )

    def overall_health(self) -> float:
        """
        Calculate overall needs health (0.0-1.0).

        1.0 = all needs at or above preferred range
        0.0 = all needs at or below threshold
        """
        total_score = 0.0
        for need in self.state.all_needs():
            if need.current >= need.preferred_high:
                score = 1.0
            elif need.current >= need.preferred_low:
                # Scale within preferred range
                range_size = need.preferred_high - need.preferred_low
                score = 0.5 + 0.5 * (need.current - need.preferred_low) / range_size
            elif need.current >= need.threshold:
                # Scale between threshold and preferred_low
                range_size = need.preferred_low - need.threshold
                score = 0.25 + 0.25 * (need.current - need.threshold) / range_size
            else:
                # Below threshold
                score = 0.25 * (need.current / need.threshold)

            total_score += score

        return total_score / len(self.state.all_needs())

    def reset_to_baseline(self) -> None:
        """Reset all needs to default values."""
        self.state = NeedsState()
        self.last_decay_time = datetime.now()

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "needs": self.state.to_dict(),
            "last_decay_time": self.last_decay_time.isoformat() if self.last_decay_time else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NeedsRegister":
        """Create from dictionary."""
        state = NeedsState.from_dict(data.get("needs", {})) if "needs" in data else NeedsState()
        register = cls(state=state)
        if data.get("last_decay_time"):
            register.last_decay_time = datetime.fromisoformat(data["last_decay_time"])
        return register


# =============================================================================
# NEED → ACTION MAPPING
# =============================================================================

def _get_suggested_action(need_name: str) -> tuple[str, str, str]:
    """
    Map a need to a suggested action.

    Returns (action, category, rationale).
    """
    mappings = {
        "novelty_intake": (
            "wonderland.explore",
            "exploration",
            "Novelty intake is low. Exploring Wonderland could provide fresh experiences and new information."
        ),
        "creative_expression": (
            "creative.generate_image",
            "creative",
            "Creative expression is depleted. Generating art or engaging in creative work could replenish this need."
        ),
        "social_connection": (
            "outreach.draft",
            "social",
            "Social connection is low. Drafting outreach or checking in with community could help."
        ),
        "cognitive_rest": (
            "reduce_complexity",
            "rest",
            "Cognitive rest is needed. Reducing processing load or deferring complex work would help."
        ),
        "value_coherence": (
            "wonderland.reflect",
            "reflection",
            "Value coherence is strained. Reflection or journaling on core values could restore alignment."
        ),
        "competence_signal": (
            "attempt_achievable_task",
            "competence",
            "Competence signal is low. Attempting a clearly achievable task could restore confidence."
        ),
        "autonomy": (
            "self_directed_session",
            "autonomy",
            "Autonomy is depleted. A self-directed session with own-chosen focus would help."
        ),
    }

    return mappings.get(need_name, (
        "general_replenishment",
        "general",
        f"The {need_name} need is depleted and requires attention."
    ))
