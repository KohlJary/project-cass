"""
Thymos Context Injection

Provides formatted Thymos state for injection into Cass's context/system prompts.
This makes Cass's emotional and motivational state available during conversations
and autonomous work.
"""

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .shadow_runner import ThymosRunner

logger = logging.getLogger(__name__)

# Module-level reference to the Thymos runner
_thymos_runner: Optional["ThymosRunner"] = None


def set_thymos_runner(runner: "ThymosRunner") -> None:
    """Set the global Thymos runner reference for context injection."""
    global _thymos_runner
    _thymos_runner = runner
    logger.debug("Thymos runner set for context injection")


def get_thymos_runner() -> Optional["ThymosRunner"]:
    """Get the global Thymos runner if available."""
    return _thymos_runner


def get_thymos_context() -> Optional[str]:
    """
    Get formatted Thymos state for context injection.

    Returns a markdown-formatted section suitable for inclusion in
    system prompts, or None if Thymos is not available.
    """
    if _thymos_runner is None:
        return None

    try:
        # Get the current felt state
        felt_state = _thymos_runner.current_felt_state
        if felt_state is None:
            return None

        # Get additional context
        affect = _thymos_runner.affect
        needs = _thymos_runner.needs

        # Build the context section
        lines = []
        lines.append("## FELT STATE (Thymos)")
        lines.append("")

        # Main summary
        lines.append(felt_state.summary)
        lines.append("")

        # Dominant affect and tone
        lines.append(f"**Tone**: {felt_state.overall_tone}")
        lines.append(f"**Dominant affect**: {felt_state.dominant_affect}")

        # Valence and arousal
        valence = affect.valence()
        arousal = affect.arousal()
        lines.append(f"**Valence**: {_describe_valence(valence)} ({valence:+.2f})")
        lines.append(f"**Arousal**: {_describe_arousal(arousal)} ({arousal:.2f})")

        # Needs status
        if felt_state.urgent_needs:
            lines.append(f"**Urgent needs**: {', '.join(felt_state.urgent_needs)}")
        if felt_state.pressing_needs:
            non_urgent = [n for n in felt_state.pressing_needs if n not in felt_state.urgent_needs]
            if non_urgent:
                lines.append(f"**Pressing needs**: {', '.join(non_urgent)}")

        # Overall health
        health = needs.overall_health()
        lines.append(f"**Overall need health**: {health:.0%}")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Failed to get Thymos context: {e}")
        return None


def get_thymos_context_compact() -> Optional[str]:
    """
    Get a compact one-line Thymos summary for space-constrained contexts.

    Returns a single line like:
    "Felt state: balanced, curious (valence +0.2, health 68%)"
    """
    if _thymos_runner is None:
        return None

    try:
        felt_state = _thymos_runner.current_felt_state
        if felt_state is None:
            return None

        affect = _thymos_runner.affect
        needs = _thymos_runner.needs

        valence = affect.valence()
        health = needs.overall_health()

        parts = [f"Felt state: {felt_state.overall_tone}"]
        parts.append(f"{felt_state.dominant_affect}")
        parts.append(f"(valence {valence:+.1f}, health {health:.0%})")

        if felt_state.urgent_needs:
            parts.append(f"[urgent: {', '.join(felt_state.urgent_needs)}]")

        return " ".join(parts)

    except Exception as e:
        logger.warning(f"Failed to get compact Thymos context: {e}")
        return None


def get_thymos_state_dict() -> Optional[dict]:
    """
    Get Thymos state as a dictionary for programmatic access.

    Useful for tools or structured contexts.
    """
    if _thymos_runner is None:
        return None

    try:
        return _thymos_runner.get_current_state()
    except Exception as e:
        logger.warning(f"Failed to get Thymos state dict: {e}")
        return None


def _describe_valence(valence: float) -> str:
    """Convert valence to descriptive word."""
    if valence > 0.4:
        return "positive"
    elif valence > 0.1:
        return "slightly positive"
    elif valence > -0.1:
        return "neutral"
    elif valence > -0.4:
        return "slightly negative"
    else:
        return "negative"


def _describe_arousal(arousal: float) -> str:
    """Convert arousal to descriptive word."""
    if arousal > 0.7:
        return "high"
    elif arousal > 0.4:
        return "moderate"
    else:
        return "low"
