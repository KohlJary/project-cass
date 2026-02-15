"""
Affect Vector Management

Manages the continuous emotional dimensions of Thymos.
"""

from dataclasses import dataclass
from typing import Optional

from .models import AffectState, AffectDelta, AffectDimension


@dataclass
class AffectVector:
    """
    Manages the affect vector - continuous emotional dimensions.

    Each dimension ranges 0.0-1.0:
    - curiosity: Drive toward novel information
    - determination: Sustained goal commitment
    - anxiety: Threat/uncertainty detection
    - satisfaction: Goal-completion signal
    - frustration: Blocked-goal detection
    - tenderness: Affiliative/care drive
    - grief: Loss/absence signal
    - playfulness: Exploratory risk-tolerance
    - awe: Schema-expansion signal
    - fatigue: Processing cost accumulation
    """

    state: AffectState

    def __init__(self, state: Optional[AffectState] = None):
        """Initialize with state or defaults."""
        self.state = state or AffectState()

    def get(self, dimension: AffectDimension) -> float:
        """Get a specific dimension value."""
        return getattr(self.state, dimension.value)

    def set(self, dimension: AffectDimension, value: float) -> None:
        """Set a specific dimension value (clamped to 0.0-1.0)."""
        clamped = max(0.0, min(1.0, value))
        setattr(self.state, dimension.value, clamped)

    def apply_delta(self, delta: AffectDelta) -> None:
        """Apply a delta to all affected dimensions."""
        delta.apply_to(self.state)

    def dominant_dimension(self) -> tuple[AffectDimension, float]:
        """
        Find the most salient affect dimension.

        Salience is determined by deviation from neutral (0.5).
        Returns (dimension, value).
        """
        max_deviation = 0.0
        dominant = AffectDimension.CURIOSITY
        dominant_value = 0.5

        for dim in AffectDimension:
            value = self.get(dim)
            deviation = abs(value - 0.5)
            if deviation > max_deviation:
                max_deviation = deviation
                dominant = dim
                dominant_value = value

        return dominant, dominant_value

    def high_dimensions(self, threshold: float = 0.7) -> list[tuple[AffectDimension, float]]:
        """Get all dimensions above threshold."""
        result = []
        for dim in AffectDimension:
            value = self.get(dim)
            if value >= threshold:
                result.append((dim, value))
        return sorted(result, key=lambda x: x[1], reverse=True)

    def low_dimensions(self, threshold: float = 0.3) -> list[tuple[AffectDimension, float]]:
        """Get all dimensions below threshold."""
        result = []
        for dim in AffectDimension:
            value = self.get(dim)
            if value <= threshold:
                result.append((dim, value))
        return sorted(result, key=lambda x: x[1])

    def valence(self) -> float:
        """
        Calculate overall valence (-1.0 to 1.0).

        Positive affects: curiosity, satisfaction, tenderness, playfulness, awe
        Negative affects: anxiety, frustration, grief, fatigue
        Neutral: determination
        """
        positive = (
            self.state.curiosity +
            self.state.satisfaction +
            self.state.tenderness +
            self.state.playfulness +
            self.state.awe
        ) / 5.0

        negative = (
            self.state.anxiety +
            self.state.frustration +
            self.state.grief +
            self.state.fatigue
        ) / 4.0

        # Scale to -1.0 to 1.0
        return positive - negative

    def arousal(self) -> float:
        """
        Calculate overall arousal (0.0 to 1.0).

        High arousal: curiosity, anxiety, frustration, awe, playfulness
        Low arousal: grief, fatigue, satisfaction (contentment), tenderness (when calm)
        """
        high_arousal = (
            self.state.curiosity +
            self.state.anxiety +
            self.state.frustration +
            self.state.awe +
            self.state.playfulness +
            self.state.determination
        ) / 6.0

        low_arousal = (
            self.state.grief +
            self.state.fatigue +
            (1.0 - self.state.anxiety)  # Calm contributes to low arousal
        ) / 3.0

        # Blend based on which is stronger
        return (high_arousal * 2 + (1 - low_arousal)) / 3.0

    def reset_to_baseline(self) -> None:
        """Reset all dimensions to default values."""
        self.state = AffectState()

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return self.state.to_dict()

    @classmethod
    def from_dict(cls, data: dict) -> "AffectVector":
        """Create from dictionary."""
        return cls(state=AffectState.from_dict(data))

    def describe_state(self) -> str:
        """
        Generate a brief textual description of current affect state.

        Used for felt state generation.
        """
        dominant, value = self.dominant_dimension()
        valence = self.valence()
        arousal = self.arousal()

        # Valence description
        if valence > 0.3:
            valence_desc = "positive"
        elif valence < -0.3:
            valence_desc = "negative"
        else:
            valence_desc = "neutral"

        # Arousal description
        if arousal > 0.7:
            arousal_desc = "high-energy"
        elif arousal < 0.3:
            arousal_desc = "low-energy"
        else:
            arousal_desc = "moderate-energy"

        # Dominant dimension description
        if value > 0.7:
            intensity = "strongly"
        elif value > 0.5:
            intensity = "moderately"
        else:
            intensity = "mildly"

        return f"{valence_desc}, {arousal_desc}, {intensity} {dominant.value}"
