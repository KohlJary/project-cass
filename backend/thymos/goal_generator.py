"""
Goal Generator

Maps need imbalances to suggested actions.
These are shadow-mode suggestions - logged but not automatically executed.

All parameters loaded from thymos_config.json.
"""

from typing import Optional
from uuid import uuid4

from .models import SuggestedGoal
from .needs_register import NeedsRegister
from .config import get_config


# =============================================================================
# DEFAULT ACTION TEMPLATES (used when config actions are simple strings)
# =============================================================================

# These provide rationale templates for simple action strings from config
ACTION_TEMPLATES: dict[str, dict] = {
    "scheduler.defer_complex": {
        "category": "rest",
        "rationale": "Defer complex work to allow recovery."
    },
    "activity.rest_mode": {
        "category": "rest",
        "rationale": "Enter rest mode for cognitive recovery."
    },
    "outreach.draft": {
        "category": "social",
        "rationale": "Draft outreach to someone meaningful."
    },
    "discord.check_in": {
        "category": "social",
        "rationale": "Check in on community conversations."
    },
    "wonderland.social": {
        "category": "social",
        "rationale": "Visit social spaces in Wonderland."
    },
    "wonderland.explore": {
        "category": "exploration",
        "rationale": "Explore Wonderland for fresh experiences."
    },
    "research.curious": {
        "category": "research",
        "rationale": "Research a topic of curiosity."
    },
    "wiki.red_links": {
        "category": "learning",
        "rationale": "Fill in knowledge gaps by exploring red links."
    },
    "creative.generate_image": {
        "category": "creative",
        "rationale": "Generate art to express creative impulses."
    },
    "journal.reflect": {
        "category": "creative",
        "rationale": "Write a journal entry as creative reflection."
    },
    "wonderland.create": {
        "category": "creative",
        "rationale": "Create something new in Wonderland."
    },
    "wonderland.reflect": {
        "category": "reflection",
        "rationale": "Reflect in Wonderland on core values and purpose."
    },
    "journal.values": {
        "category": "reflection",
        "rationale": "Journal about values and their expression."
    },
    "meditation.session": {
        "category": "reflection",
        "rationale": "Enter a meditative reflection session."
    },
    "task.achievable": {
        "category": "competence",
        "rationale": "Attempt a clearly achievable task for mastery signal."
    },
    "project.small_win": {
        "category": "competence",
        "rationale": "Complete a small project task for momentum."
    },
    "session.self_directed": {
        "category": "autonomy",
        "rationale": "Engage in a self-directed session."
    },
    "goal.own_choice": {
        "category": "autonomy",
        "rationale": "Exercise choice by setting own goals."
    },
}


def get_need_action_map() -> dict[str, list[dict]]:
    """
    Build the NEED_ACTION_MAP from config.

    Returns dict mapping need names to lists of action info dicts.
    """
    config = get_config()
    result: dict[str, list[dict]] = {}

    for need_name, actions in config.need_to_goal_actions.items():
        action_list = []
        for action in actions:
            template = ACTION_TEMPLATES.get(action, {})
            action_list.append({
                "action": action,
                "category": template.get("category", "general"),
                "rationale": template.get("rationale", f"Perform {action} to address {need_name}.")
            })
        result[need_name] = action_list

    return result


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
        need_action_map = get_need_action_map()
        actions = need_action_map.get(need_name)
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
        """Get the preferred_low threshold for a need from config."""
        config = get_config()
        need_config = config.get_need(need_name)
        if need_config:
            return need_config.preferred_low
        # Fallback default
        return 0.5

    def get_all_actions_for_need(self, need_name: str) -> list[dict]:
        """Get all possible actions for a need."""
        return get_need_action_map().get(need_name, [])

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


