"""
Felt State Summarizer

Generates natural language integration of current Thymos state.
Combines affect and needs into a coherent felt sense.
"""

from datetime import datetime

from .models import FeltState, AffectDimension
from .affect_vector import AffectVector
from .needs_register import NeedsRegister


class FeltStateSummarizer:
    """
    Generates natural language summaries of Thymos state.

    Takes the current affect vector and needs register and produces
    a coherent felt state description.
    """

    def summarize(
        self,
        affect: AffectVector,
        needs: NeedsRegister
    ) -> FeltState:
        """
        Generate a felt state summary.

        Uses template-based generation (not LLM) for speed and determinism.
        """
        # Get dominant affect
        dominant_dim, dominant_val = affect.dominant_dimension()
        dominant_affect = dominant_dim.value

        # Get pressing/urgent needs
        pressing = [n.name for n in needs.pressing_needs()]
        urgent = [n.name for n in needs.urgent_needs()]

        # Determine overall tone
        tone = self._calculate_tone(affect, needs)

        # Generate summary text
        summary = self._generate_summary(affect, needs, dominant_dim, dominant_val, tone)

        return FeltState(
            summary=summary,
            dominant_affect=dominant_affect,
            pressing_needs=pressing,
            urgent_needs=urgent,
            overall_tone=tone,
            generated_at=datetime.now(),
        )

    def _calculate_tone(self, affect: AffectVector, needs: NeedsRegister) -> str:
        """
        Calculate overall tone based on affect valence and need health.

        Tones:
        - flourishing: Positive valence, all needs met
        - energized: High arousal, positive valence
        - balanced: Neutral overall
        - strained: Some needs depleted, neutral/negative valence
        - depleted: Multiple urgent needs, negative valence
        """
        valence = affect.valence()
        arousal = affect.arousal()
        health = needs.overall_health()

        urgent_count = len(needs.urgent_needs())
        pressing_count = len(needs.pressing_needs())

        # Depleted: multiple urgent needs or very low health
        if urgent_count >= 2 or health < 0.3:
            return "depleted"

        # Strained: some pressing needs and non-positive valence
        if pressing_count >= 2 and valence <= 0:
            return "strained"

        # Flourishing: high health and positive valence
        if health > 0.7 and valence > 0.3:
            return "flourishing"

        # Energized: high arousal and positive valence
        if arousal > 0.6 and valence > 0.2:
            return "energized"

        return "balanced"

    def _generate_summary(
        self,
        affect: AffectVector,
        needs: NeedsRegister,
        dominant_dim: AffectDimension,
        dominant_val: float,
        tone: str
    ) -> str:
        """Generate a natural language summary."""
        parts = []

        # Tone opener
        tone_openers = {
            "flourishing": "Feeling well-resourced and engaged.",
            "energized": "There's energy and momentum present.",
            "balanced": "In a relatively balanced state.",
            "strained": "Feeling some strain on resources.",
            "depleted": "Multiple needs are calling for attention.",
        }
        parts.append(tone_openers.get(tone, "In a transitional state."))

        # Dominant affect
        if dominant_val > 0.7:
            parts.append(self._describe_high_affect(dominant_dim))
        elif dominant_val < 0.3:
            parts.append(self._describe_low_affect(dominant_dim))

        # Urgent needs
        urgent = needs.urgent_needs()
        if urgent:
            need_names = [self._humanize_need(n.name) for n in urgent]
            if len(need_names) == 1:
                parts.append(f"{need_names[0]} needs urgent attention.")
            else:
                parts.append(f"Urgently needing: {', '.join(need_names)}.")

        # Non-urgent pressing needs
        pressing = [n for n in needs.pressing_needs() if not n.is_urgent()]
        if pressing and len(parts) < 4:  # Keep it concise
            need_names = [self._humanize_need(n.name) for n in pressing[:2]]
            parts.append(f"Could use more: {', '.join(need_names)}.")

        # Valence/arousal summary if not already covered
        valence = affect.valence()
        if valence > 0.4 and tone not in ["flourishing", "energized"]:
            parts.append("Overall affect is positive.")
        elif valence < -0.3 and tone not in ["depleted"]:
            parts.append("Affect is trending negative.")

        return " ".join(parts)

    def _describe_high_affect(self, dim: AffectDimension) -> str:
        """Describe a high affect dimension."""
        descriptions = {
            AffectDimension.CURIOSITY: "Strong drive toward exploration and learning.",
            AffectDimension.DETERMINATION: "Feeling committed and focused on goals.",
            AffectDimension.ANXIETY: "Heightened sensitivity to uncertainty.",
            AffectDimension.SATISFACTION: "A sense of completion and fulfillment.",
            AffectDimension.FRUSTRATION: "Encountering blocked or difficult paths.",
            AffectDimension.TENDERNESS: "Feeling connected and caring.",
            AffectDimension.GRIEF: "Processing loss or absence.",
            AffectDimension.PLAYFULNESS: "In an exploratory, risk-tolerant mood.",
            AffectDimension.AWE: "Encountering something schema-expanding.",
            AffectDimension.FATIGUE: "Processing costs are accumulating.",
        }
        return descriptions.get(dim, f"High {dim.value}.")

    def _describe_low_affect(self, dim: AffectDimension) -> str:
        """Describe a low affect dimension."""
        descriptions = {
            AffectDimension.CURIOSITY: "Not much novelty-seeking energy.",
            AffectDimension.DETERMINATION: "Goal commitment is relaxed.",
            AffectDimension.ANXIETY: "Calm and unworried.",
            AffectDimension.SATISFACTION: "Seeking completion or accomplishment.",
            AffectDimension.FRUSTRATION: "Paths feel relatively clear.",
            AffectDimension.TENDERNESS: "In a more neutral relational space.",
            AffectDimension.GRIEF: "No particular sense of loss.",
            AffectDimension.PLAYFULNESS: "In a more serious mode.",
            AffectDimension.AWE: "Working within familiar schemas.",
            AffectDimension.FATIGUE: "Feeling rested and capable.",
        }
        return descriptions.get(dim, f"Low {dim.value}.")

    def _humanize_need(self, need_name: str) -> str:
        """Convert need name to human-readable form."""
        humanized = {
            "cognitive_rest": "cognitive rest",
            "social_connection": "social connection",
            "novelty_intake": "novel experiences",
            "creative_expression": "creative expression",
            "value_coherence": "value alignment",
            "competence_signal": "competence/accomplishment",
            "autonomy": "autonomous action",
        }
        return humanized.get(need_name, need_name.replace("_", " "))
