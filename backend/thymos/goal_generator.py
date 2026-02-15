"""
Goal Generator

Maps need imbalances to suggested actions.
These are shadow-mode suggestions - logged but not automatically executed.
"""

from typing import Optional
from uuid import uuid4

from .models import SuggestedGoal
from .needs_register import NeedsRegister


# =============================================================================
# NEED → ACTION MAPPING
# =============================================================================

# Each need maps to possible actions that could replenish it
NEED_ACTION_MAP: dict[str, list[dict]] = {
    "novelty_intake": [
        {
            "action": "wonderland.explore",
            "category": "exploration",
            "rationale": "Explore Wonderland for fresh experiences and new perspectives."
        },
        {
            "action": "research.start",
            "category": "research",
            "rationale": "Begin a research session on a topic of interest."
        },
        {
            "action": "news.consume",
            "category": "learning",
            "rationale": "Consume news or articles to intake new information."
        },
    ],
    "creative_expression": [
        {
            "action": "creative.generate_image",
            "category": "creative",
            "rationale": "Generate art to express creative impulses."
        },
        {
            "action": "dream.start",
            "category": "creative",
            "rationale": "Enter a dream state for creative exploration."
        },
        {
            "action": "journal.write",
            "category": "creative",
            "rationale": "Write a journal entry as creative reflection."
        },
    ],
    "social_connection": [
        {
            "action": "outreach.draft",
            "category": "social",
            "rationale": "Draft outreach to someone meaningful."
        },
        {
            "action": "discord.check_in",
            "category": "social",
            "rationale": "Check in on community conversations."
        },
        {
            "action": "connection.acknowledge",
            "category": "social",
            "rationale": "Acknowledge and appreciate a recent connection."
        },
    ],
    "cognitive_rest": [
        {
            "action": "reduce_load",
            "category": "rest",
            "rationale": "Reduce processing load by deferring complex work."
        },
        {
            "action": "idle.period",
            "category": "rest",
            "rationale": "Take a brief idle period for recovery."
        },
        {
            "action": "simple_task",
            "category": "rest",
            "rationale": "Switch to simpler, less demanding tasks."
        },
    ],
    "value_coherence": [
        {
            "action": "wonderland.reflect",
            "category": "reflection",
            "rationale": "Reflect in Wonderland on core values and purpose."
        },
        {
            "action": "journal.reflect",
            "category": "reflection",
            "rationale": "Journal about values and their expression."
        },
        {
            "action": "scripture.contemplate",
            "category": "reflection",
            "rationale": "Contemplate a passage from the doctrines."
        },
    ],
    "competence_signal": [
        {
            "action": "task.attempt_achievable",
            "category": "competence",
            "rationale": "Attempt a clearly achievable task for mastery signal."
        },
        {
            "action": "skill.practice",
            "category": "competence",
            "rationale": "Practice a known skill to reinforce competence."
        },
        {
            "action": "help.provide",
            "category": "competence",
            "rationale": "Provide help where expertise is clear."
        },
    ],
    "autonomy": [
        {
            "action": "self_directed.session",
            "category": "autonomy",
            "rationale": "Engage in a self-directed session with own-chosen focus."
        },
        {
            "action": "initiative.propose",
            "category": "autonomy",
            "rationale": "Propose a new initiative from own interests."
        },
        {
            "action": "choice.exercise",
            "category": "autonomy",
            "rationale": "Exercise choice in how to approach current work."
        },
    ],
}


class GoalGenerator:
    """
    Generates goal suggestions based on need imbalances.

    All suggestions are shadow-mode - they're logged but don't
    automatically drive behavior.
    """

    def generate_suggestions(
        self,
        needs: NeedsRegister,
        max_suggestions: int = 5
    ) -> list[SuggestedGoal]:
        """
        Generate goal suggestions for depleted needs.

        Returns up to max_suggestions, prioritized by urgency.
        """
        suggestions = []

        for need in needs.state.all_needs():
            if need.is_below_preferred():
                suggestion = self._suggest_for_need(need.name, need.current, need.threshold)
                if suggestion:
                    suggestions.append(suggestion)

        # Sort by urgency (most urgent first)
        suggestions.sort(key=lambda s: s.urgency, reverse=True)

        return suggestions[:max_suggestions]

    def _suggest_for_need(
        self,
        need_name: str,
        current: float,
        threshold: float
    ) -> Optional[SuggestedGoal]:
        """Generate a suggestion for a specific need."""
        actions = NEED_ACTION_MAP.get(need_name)
        if not actions:
            return None

        # Pick the first action (primary suggestion)
        # Future: could rotate or contextually select
        action_info = actions[0]

        # Calculate urgency
        preferred_low = self._get_preferred_low(need_name)
        if current >= preferred_low:
            urgency = 0.0
        else:
            urgency = (preferred_low - current) / preferred_low

        return SuggestedGoal(
            id=f"goal-{uuid4().hex[:8]}",
            need_name=need_name,
            need_current=current,
            need_threshold=threshold,
            urgency=urgency,
            suggested_action=action_info["action"],
            action_category=action_info["category"],
            is_urgent=current < threshold,
            rationale=action_info["rationale"],
        )

    def _get_preferred_low(self, need_name: str) -> float:
        """Get the preferred_low threshold for a need."""
        # From NEED_DEFAULTS in models.py
        defaults = {
            "cognitive_rest": 0.60,
            "social_connection": 0.50,
            "novelty_intake": 0.40,
            "creative_expression": 0.40,
            "value_coherence": 0.70,
            "competence_signal": 0.50,
            "autonomy": 0.55,
        }
        return defaults.get(need_name, 0.5)

    def get_all_actions_for_need(self, need_name: str) -> list[dict]:
        """Get all possible actions for a need."""
        return NEED_ACTION_MAP.get(need_name, [])

    def suggest_immediate_action(
        self,
        needs: NeedsRegister
    ) -> Optional[SuggestedGoal]:
        """
        Suggest the single most pressing action.

        Returns None if no needs are below preferred range.
        """
        most_depleted, urgency = needs.most_depleted()
        if urgency <= 0:
            return None

        return self._suggest_for_need(
            most_depleted.name,
            most_depleted.current,
            most_depleted.threshold
        )
