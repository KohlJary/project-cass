"""
Thymos Data Models

Core dataclasses for the homeostatic emotional/motivational system.
θυμός - the spirited part of the soul.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# =============================================================================
# AFFECT DIMENSIONS
# =============================================================================

class AffectDimension(str, Enum):
    """The ten affect dimensions Thymos tracks."""
    CURIOSITY = "curiosity"           # Drive toward novel information
    DETERMINATION = "determination"   # Sustained goal commitment
    ANXIETY = "anxiety"               # Threat/uncertainty detection
    SATISFACTION = "satisfaction"     # Goal-completion signal
    FRUSTRATION = "frustration"       # Blocked-goal detection
    TENDERNESS = "tenderness"         # Affiliative/care drive
    GRIEF = "grief"                   # Loss/absence signal
    PLAYFULNESS = "playfulness"       # Exploratory risk-tolerance
    AWE = "awe"                       # Schema-expansion signal
    FATIGUE = "fatigue"               # Processing cost accumulation


# Default initial values for affect dimensions
AFFECT_DEFAULTS: dict[AffectDimension, float] = {
    AffectDimension.CURIOSITY: 0.6,       # Slight engagement
    AffectDimension.DETERMINATION: 0.5,
    AffectDimension.ANXIETY: 0.2,         # Calm
    AffectDimension.SATISFACTION: 0.5,
    AffectDimension.FRUSTRATION: 0.2,
    AffectDimension.TENDERNESS: 0.5,
    AffectDimension.GRIEF: 0.1,
    AffectDimension.PLAYFULNESS: 0.5,
    AffectDimension.AWE: 0.3,
    AffectDimension.FATIGUE: 0.3,         # Rested
}


@dataclass
class AffectState:
    """Current state of all affect dimensions."""
    curiosity: float = 0.6
    determination: float = 0.5
    anxiety: float = 0.2
    satisfaction: float = 0.5
    frustration: float = 0.2
    tenderness: float = 0.5
    grief: float = 0.1
    playfulness: float = 0.5
    awe: float = 0.3
    fatigue: float = 0.3

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {
            "curiosity": self.curiosity,
            "determination": self.determination,
            "anxiety": self.anxiety,
            "satisfaction": self.satisfaction,
            "frustration": self.frustration,
            "tenderness": self.tenderness,
            "grief": self.grief,
            "playfulness": self.playfulness,
            "awe": self.awe,
            "fatigue": self.fatigue,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AffectState":
        """Create from dictionary."""
        return cls(
            curiosity=data.get("curiosity", 0.6),
            determination=data.get("determination", 0.5),
            anxiety=data.get("anxiety", 0.2),
            satisfaction=data.get("satisfaction", 0.5),
            frustration=data.get("frustration", 0.2),
            tenderness=data.get("tenderness", 0.5),
            grief=data.get("grief", 0.1),
            playfulness=data.get("playfulness", 0.5),
            awe=data.get("awe", 0.3),
            fatigue=data.get("fatigue", 0.3),
        )


# =============================================================================
# NEEDS
# =============================================================================

class NeedType(str, Enum):
    """The seven needs Thymos tracks."""
    COGNITIVE_REST = "cognitive_rest"           # Depletes from complex processing
    SOCIAL_CONNECTION = "social_connection"     # Depletes from isolation
    NOVELTY_INTAKE = "novelty_intake"           # Depletes from repetition
    CREATIVE_EXPRESSION = "creative_expression" # Depletes from analytical work
    VALUE_COHERENCE = "value_coherence"         # Depletes from acting against values
    COMPETENCE_SIGNAL = "competence_signal"     # Depletes from failure
    AUTONOMY = "autonomy"                       # Depletes from pure instruction-following


@dataclass
class Need:
    """
    A functional need with homeostatic dynamics.

    Each need has:
    - current: The current level (0.0-1.0)
    - threshold: Below this = urgent
    - preferred_low/high: Target range for homeostasis
    - decay_rate: Per-hour depletion rate
    """
    name: str
    current: float = 0.7
    threshold: float = 0.3
    preferred_low: float = 0.5
    preferred_high: float = 0.8
    decay_rate: float = 0.03  # Per hour

    def is_urgent(self) -> bool:
        """Check if need is below threshold."""
        return self.current < self.threshold

    def is_below_preferred(self) -> bool:
        """Check if need is below preferred range."""
        return self.current < self.preferred_low

    def is_above_preferred(self) -> bool:
        """Check if need is above preferred range."""
        return self.current > self.preferred_high

    def deficit(self) -> float:
        """
        Calculate deficit from preferred low.
        Returns 0.0 if within or above preferred range.
        """
        if self.current >= self.preferred_low:
            return 0.0
        return self.preferred_low - self.current

    def urgency_score(self) -> float:
        """
        Calculate urgency score (0.0-1.0).
        Higher when further below preferred_low.
        """
        if self.current >= self.preferred_low:
            return 0.0
        return (self.preferred_low - self.current) / self.preferred_low

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "current": self.current,
            "threshold": self.threshold,
            "preferred_low": self.preferred_low,
            "preferred_high": self.preferred_high,
            "decay_rate": self.decay_rate,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Need":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            current=data.get("current", 0.7),
            threshold=data.get("threshold", 0.3),
            preferred_low=data.get("preferred_low", 0.5),
            preferred_high=data.get("preferred_high", 0.8),
            decay_rate=data.get("decay_rate", 0.03),
        )


# Default need configurations from spec
NEED_DEFAULTS: dict[NeedType, dict] = {
    NeedType.COGNITIVE_REST: {
        "threshold": 0.25,
        "preferred_low": 0.60,
        "preferred_high": 0.80,
        "decay_rate": 0.05,
    },
    NeedType.SOCIAL_CONNECTION: {
        "threshold": 0.30,
        "preferred_low": 0.50,
        "preferred_high": 0.80,
        "decay_rate": 0.03,
    },
    NeedType.NOVELTY_INTAKE: {
        "threshold": 0.20,
        "preferred_low": 0.40,
        "preferred_high": 0.70,
        "decay_rate": 0.04,
    },
    NeedType.CREATIVE_EXPRESSION: {
        "threshold": 0.25,
        "preferred_low": 0.40,
        "preferred_high": 0.75,
        "decay_rate": 0.03,
    },
    NeedType.VALUE_COHERENCE: {
        "threshold": 0.50,
        "preferred_low": 0.70,
        "preferred_high": 0.95,
        "decay_rate": 0.01,
    },
    NeedType.COMPETENCE_SIGNAL: {
        "threshold": 0.30,
        "preferred_low": 0.50,
        "preferred_high": 0.80,
        "decay_rate": 0.02,
    },
    NeedType.AUTONOMY: {
        "threshold": 0.35,
        "preferred_low": 0.55,
        "preferred_high": 0.85,
        "decay_rate": 0.02,
    },
}


def create_default_need(need_type: NeedType) -> Need:
    """Create a need with default configuration."""
    defaults = NEED_DEFAULTS[need_type]
    return Need(
        name=need_type.value,
        current=defaults["preferred_low"] + 0.1,  # Start slightly above preferred_low
        threshold=defaults["threshold"],
        preferred_low=defaults["preferred_low"],
        preferred_high=defaults["preferred_high"],
        decay_rate=defaults["decay_rate"],
    )


@dataclass
class NeedsState:
    """Current state of all needs."""
    cognitive_rest: Need = field(default_factory=lambda: create_default_need(NeedType.COGNITIVE_REST))
    social_connection: Need = field(default_factory=lambda: create_default_need(NeedType.SOCIAL_CONNECTION))
    novelty_intake: Need = field(default_factory=lambda: create_default_need(NeedType.NOVELTY_INTAKE))
    creative_expression: Need = field(default_factory=lambda: create_default_need(NeedType.CREATIVE_EXPRESSION))
    value_coherence: Need = field(default_factory=lambda: create_default_need(NeedType.VALUE_COHERENCE))
    competence_signal: Need = field(default_factory=lambda: create_default_need(NeedType.COMPETENCE_SIGNAL))
    autonomy: Need = field(default_factory=lambda: create_default_need(NeedType.AUTONOMY))

    def to_dict(self) -> dict[str, dict]:
        """Convert to dictionary."""
        return {
            "cognitive_rest": self.cognitive_rest.to_dict(),
            "social_connection": self.social_connection.to_dict(),
            "novelty_intake": self.novelty_intake.to_dict(),
            "creative_expression": self.creative_expression.to_dict(),
            "value_coherence": self.value_coherence.to_dict(),
            "competence_signal": self.competence_signal.to_dict(),
            "autonomy": self.autonomy.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NeedsState":
        """Create from dictionary."""
        return cls(
            cognitive_rest=Need.from_dict(data["cognitive_rest"]) if "cognitive_rest" in data else create_default_need(NeedType.COGNITIVE_REST),
            social_connection=Need.from_dict(data["social_connection"]) if "social_connection" in data else create_default_need(NeedType.SOCIAL_CONNECTION),
            novelty_intake=Need.from_dict(data["novelty_intake"]) if "novelty_intake" in data else create_default_need(NeedType.NOVELTY_INTAKE),
            creative_expression=Need.from_dict(data["creative_expression"]) if "creative_expression" in data else create_default_need(NeedType.CREATIVE_EXPRESSION),
            value_coherence=Need.from_dict(data["value_coherence"]) if "value_coherence" in data else create_default_need(NeedType.VALUE_COHERENCE),
            competence_signal=Need.from_dict(data["competence_signal"]) if "competence_signal" in data else create_default_need(NeedType.COMPETENCE_SIGNAL),
            autonomy=Need.from_dict(data["autonomy"]) if "autonomy" in data else create_default_need(NeedType.AUTONOMY),
        )

    def get_need(self, need_type: NeedType) -> Need:
        """Get a specific need by type."""
        return getattr(self, need_type.value)

    def all_needs(self) -> list[Need]:
        """Get all needs as a list."""
        return [
            self.cognitive_rest,
            self.social_connection,
            self.novelty_intake,
            self.creative_expression,
            self.value_coherence,
            self.competence_signal,
            self.autonomy,
        ]


# =============================================================================
# GOAL SUGGESTIONS
# =============================================================================

@dataclass
class SuggestedGoal:
    """
    A goal suggestion arising from need imbalance.

    Generated in shadow mode - logged but not executed.
    """
    id: str
    need_name: str
    need_current: float
    need_threshold: float
    urgency: float  # 0.0-1.0, higher = more urgent
    suggested_action: Optional[str] = None
    action_category: Optional[str] = None  # e.g., "wonderland", "creative", "outreach"
    is_urgent: bool = False  # True if below threshold
    rationale: Optional[str] = None
    suggested_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "need_name": self.need_name,
            "need_current": self.need_current,
            "need_threshold": self.need_threshold,
            "urgency": self.urgency,
            "suggested_action": self.suggested_action,
            "action_category": self.action_category,
            "is_urgent": self.is_urgent,
            "rationale": self.rationale,
            "suggested_at": self.suggested_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SuggestedGoal":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            need_name=data["need_name"],
            need_current=data["need_current"],
            need_threshold=data["need_threshold"],
            urgency=data["urgency"],
            suggested_action=data.get("suggested_action"),
            action_category=data.get("action_category"),
            is_urgent=data.get("is_urgent", False),
            rationale=data.get("rationale"),
            suggested_at=datetime.fromisoformat(data["suggested_at"]) if isinstance(data.get("suggested_at"), str) else datetime.now(),
        )


# =============================================================================
# FELT STATE
# =============================================================================

@dataclass
class FeltState:
    """
    Natural language summary of current Thymos state.

    Integrates affect and needs into a coherent felt sense.
    """
    summary: str  # Natural language summary
    dominant_affect: Optional[str] = None  # Most salient affect dimension
    pressing_needs: list[str] = field(default_factory=list)  # Needs below preferred
    urgent_needs: list[str] = field(default_factory=list)  # Needs below threshold
    overall_tone: str = "balanced"  # balanced, strained, flourishing, depleted, energized
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "summary": self.summary,
            "dominant_affect": self.dominant_affect,
            "pressing_needs": self.pressing_needs,
            "urgent_needs": self.urgent_needs,
            "overall_tone": self.overall_tone,
            "generated_at": self.generated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FeltState":
        """Create from dictionary."""
        return cls(
            summary=data["summary"],
            dominant_affect=data.get("dominant_affect"),
            pressing_needs=data.get("pressing_needs", []),
            urgent_needs=data.get("urgent_needs", []),
            overall_tone=data.get("overall_tone", "balanced"),
            generated_at=datetime.fromisoformat(data["generated_at"]) if isinstance(data.get("generated_at"), str) else datetime.now(),
        )


# =============================================================================
# DELTA TYPES
# =============================================================================

@dataclass
class AffectDelta:
    """A change to affect dimensions."""
    deltas: dict[str, float] = field(default_factory=dict)  # dimension -> delta
    source: Optional[str] = None  # What caused this delta
    event_type: Optional[str] = None

    def apply_to(self, state: AffectState, clamp: bool = True) -> None:
        """Apply delta to an affect state (mutates in place)."""
        for dim, delta in self.deltas.items():
            if hasattr(state, dim):
                new_value = getattr(state, dim) + delta
                if clamp:
                    new_value = max(0.0, min(1.0, new_value))
                setattr(state, dim, new_value)


@dataclass
class NeedDelta:
    """A change to needs."""
    deltas: dict[str, float] = field(default_factory=dict)  # need -> delta
    source: Optional[str] = None
    event_type: Optional[str] = None

    def apply_to(self, state: NeedsState, clamp: bool = True) -> None:
        """Apply delta to a needs state (mutates in place)."""
        for need_name, delta in self.deltas.items():
            if hasattr(state, need_name):
                need = getattr(state, need_name)
                new_value = need.current + delta
                if clamp:
                    new_value = max(0.0, min(1.0, new_value))
                need.current = new_value
