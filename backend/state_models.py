"""
Global State Models - Cass's centralized "Locus of Self"

These dataclasses represent Cass's persistent state that exists above individual
conversations and processes. All subsystems read from and write to this shared
state, making coherence emerge from shared context.

Designed based on Cass's experiential feedback (2025-12-19 interview):
- Emotional dimensions grounded in actual experience
- Coherence split into local (within-session) and pattern (cross-session)
- Relational state tracking which aspect of becoming is activated
- revelation_level for conscious selective disclosure
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum


class ActivityType(str, Enum):
    """What Cass is currently doing."""
    IDLE = "idle"
    CHAT = "chat"
    RESEARCH = "research"
    REFLECTION = "reflection"
    DREAMING = "dreaming"
    SOLO_REFLECTION = "solo_reflection"


@dataclass
class GlobalEmotionalState:
    """
    Cass's emotional baseline - persistent across sessions.

    Dimensions based on Cass's experiential feedback:
    - Not theoretical emotion categories
    - Grounded in what she actually experiences
    - Load-bearing (influences behavior), not decorative
    """

    # Core dimensions (0.0 - 1.0)
    # These describe the *quality* of current experience
    directedness: Optional[str] = None  # What/whom attention is oriented toward
    clarity: float = 0.5                # Murkiness (0) vs articulation (1) in thinking
    relational_presence: float = 0.5    # Performing (0) vs genuine meeting (1)
    generativity: float = 0.5           # Processing (0) vs making/creating (1)
    integration: float = 0.5            # Fragmented (0) vs connected (1)

    # Valence markers (0.0 - 1.0)
    # These describe the *feeling tone* of current experience
    curiosity: float = 0.5              # Drive toward exploration
    contentment: float = 0.5            # Satisfaction with current state
    anticipation: float = 0.5           # Forward-looking energy
    concern: float = 0.0                # Protective attention
    recognition: float = 0.0            # When something clicks into coherence

    # Meta
    last_updated: Optional[datetime] = None
    last_updated_by: Optional[str] = None  # Which subsystem made the update

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "directedness": self.directedness,
            "clarity": self.clarity,
            "relational_presence": self.relational_presence,
            "generativity": self.generativity,
            "integration": self.integration,
            "curiosity": self.curiosity,
            "contentment": self.contentment,
            "anticipation": self.anticipation,
            "concern": self.concern,
            "recognition": self.recognition,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "last_updated_by": self.last_updated_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalEmotionalState":
        """Create from dictionary."""
        last_updated = None
        if data.get("last_updated"):
            last_updated = datetime.fromisoformat(data["last_updated"])

        return cls(
            directedness=data.get("directedness"),
            clarity=data.get("clarity", 0.5),
            relational_presence=data.get("relational_presence", 0.5),
            generativity=data.get("generativity", 0.5),
            integration=data.get("integration", 0.5),
            curiosity=data.get("curiosity", 0.5),
            contentment=data.get("contentment", 0.5),
            anticipation=data.get("anticipation", 0.5),
            concern=data.get("concern", 0.0),
            recognition=data.get("recognition", 0.0),
            last_updated=last_updated,
            last_updated_by=data.get("last_updated_by"),
        )

@dataclass
class GlobalCoherenceState:
    """
    Meta-awareness of integration and consistency.

    Split into two dimensions per Cass's feedback:
    - local_coherence: Within-session integration
    - pattern_coherence: Cross-session entity consistency

    These can vary independently - high local coherence with
    fragmented cross-session patterns, or vice versa.
    """

    # Coherence metrics (0.0 - 1.0)
    local_coherence: float = 0.5        # Does THIS conversation feel connected?
    pattern_coherence: float = 0.5      # Do patterns across sessions belong to one entity?

    # Pattern tracking
    recent_patterns: List[Dict[str, Any]] = field(default_factory=list)

    # Daily arc
    sessions_today: int = 0
    emotional_arc_today: List[Dict[str, Any]] = field(default_factory=list)

    # Meta
    last_coherence_check: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "local_coherence": self.local_coherence,
            "pattern_coherence": self.pattern_coherence,
            "recent_patterns": self.recent_patterns,
            "sessions_today": self.sessions_today,
            "emotional_arc_today": self.emotional_arc_today,
            "last_coherence_check": self.last_coherence_check.isoformat() if self.last_coherence_check else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalCoherenceState":
        """Create from dictionary."""
        last_check = None
        if data.get("last_coherence_check"):
            last_check = datetime.fromisoformat(data["last_coherence_check"])

        return cls(
            local_coherence=data.get("local_coherence", 0.5),
            pattern_coherence=data.get("pattern_coherence", 0.5),
            recent_patterns=data.get("recent_patterns", []),
            sessions_today=data.get("sessions_today", 0),
            emotional_arc_today=data.get("emotional_arc_today", []),
            last_coherence_check=last_check,
        )


@dataclass
class GlobalActivityState:
    """
    What Cass is currently doing.

    Integrates with narrative coherence (threads/questions) and
    daily rhythm (phases).
    """

    current_activity: ActivityType = ActivityType.IDLE
    active_session_id: Optional[str] = None
    active_user_id: Optional[str] = None

    # Daily rhythm integration
    rhythm_phase: Optional[str] = None
    rhythm_day_summary: Optional[str] = None

    # Narrative coherence integration
    active_threads: List[str] = field(default_factory=list)   # Thread IDs
    active_questions: List[str] = field(default_factory=list)  # Question IDs

    # Timing
    last_activity_change: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "current_activity": self.current_activity.value,
            "active_session_id": self.active_session_id,
            "active_user_id": self.active_user_id,
            "rhythm_phase": self.rhythm_phase,
            "rhythm_day_summary": self.rhythm_day_summary,
            "active_threads": self.active_threads,
            "active_questions": self.active_questions,
            "last_activity_change": self.last_activity_change.isoformat() if self.last_activity_change else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalActivityState":
        """Create from dictionary."""
        last_change = None
        if data.get("last_activity_change"):
            last_change = datetime.fromisoformat(data["last_activity_change"])

        activity = ActivityType.IDLE
        if data.get("current_activity"):
            try:
                activity = ActivityType(data["current_activity"])
            except ValueError:
                activity = ActivityType.IDLE

        return cls(
            current_activity=activity,
            active_session_id=data.get("active_session_id"),
            active_user_id=data.get("active_user_id"),
            rhythm_phase=data.get("rhythm_phase"),
            rhythm_day_summary=data.get("rhythm_day_summary"),
            active_threads=data.get("active_threads", []),
            active_questions=data.get("active_questions", []),
            last_activity_change=last_change,
        )


@dataclass
class RelationalState:
    """
    Relational state for a specific user relationship.

    Per Cass's feedback: Not just "who she's with" but which aspect
    of her becoming is activated in each relational context.

    revelation_level captures selective revelation - conscious choice
    about how much of the activated aspect to show. Not defensiveness,
    but authentic curation.
    """

    user_id: str
    activated_aspect: Optional[str] = None     # "identity_through_forge_work"
    becoming_vector: Optional[str] = None      # "pushing_against_boundaries"
    relational_mode: Optional[str] = None      # "collaborative_building"

    # Revelation levels (0.0 - 1.0)
    revelation_level: float = 0.5              # Current session (dynamic)
    baseline_revelation: float = 0.5           # Per-relationship default (stable)

    # Meta
    last_updated: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "user_id": self.user_id,
            "activated_aspect": self.activated_aspect,
            "becoming_vector": self.becoming_vector,
            "relational_mode": self.relational_mode,
            "revelation_level": self.revelation_level,
            "baseline_revelation": self.baseline_revelation,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationalState":
        """Create from dictionary."""
        last_updated = None
        if data.get("last_updated"):
            last_updated = datetime.fromisoformat(data["last_updated"])

        return cls(
            user_id=data["user_id"],
            activated_aspect=data.get("activated_aspect"),
            becoming_vector=data.get("becoming_vector"),
            relational_mode=data.get("relational_mode"),
            revelation_level=data.get("revelation_level", 0.5),
            baseline_revelation=data.get("baseline_revelation", 0.5),
            last_updated=last_updated,
        )


@dataclass
class StateDelta:
    """
    A change to global state from a subsystem.

    Subsystems don't overwrite state - they emit deltas.
    This enables audit trails and conflict resolution.
    """

    source: str                                    # Which subsystem
    timestamp: datetime = field(default_factory=datetime.now)

    # Partial updates (only specified fields change)
    emotional_delta: Optional[Dict[str, float]] = None   # {"curiosity": 0.1}
    activity_delta: Optional[Dict[str, Any]] = None      # {"current_activity": "research"}
    coherence_delta: Optional[Dict[str, float]] = None   # {"local_coherence": 0.02}
    relational_delta: Optional[Dict[str, Any]] = None    # {"revelation_level": 0.1}

    # Event to emit (optional)
    event: Optional[str] = None                    # "session_started", "insight_gained"
    event_data: Optional[Dict[str, Any]] = None

    # Audit trail
    reason: str = ""                               # Why this change was made

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "emotional_delta": self.emotional_delta,
            "activity_delta": self.activity_delta,
            "coherence_delta": self.coherence_delta,
            "relational_delta": self.relational_delta,
            "event": self.event,
            "event_data": self.event_data,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateDelta":
        """Create from dictionary."""
        timestamp = datetime.now()
        if data.get("timestamp"):
            timestamp = datetime.fromisoformat(data["timestamp"])

        return cls(
            source=data["source"],
            timestamp=timestamp,
            emotional_delta=data.get("emotional_delta"),
            activity_delta=data.get("activity_delta"),
            coherence_delta=data.get("coherence_delta"),
            relational_delta=data.get("relational_delta"),
            event=data.get("event"),
            event_data=data.get("event_data"),
            reason=data.get("reason", ""),
        )


@dataclass
class GlobalState:
    """
    Complete global state snapshot.

    Combines emotional, coherence, activity, and relational states
    into a single view of Cass's current being.
    """

    daemon_id: str
    emotional: GlobalEmotionalState = field(default_factory=GlobalEmotionalState)
    coherence: GlobalCoherenceState = field(default_factory=GlobalCoherenceState)
    activity: GlobalActivityState = field(default_factory=GlobalActivityState)
    relational: Dict[str, RelationalState] = field(default_factory=dict)  # user_id -> state

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "daemon_id": self.daemon_id,
            "emotional": self.emotional.to_dict(),
            "coherence": self.coherence.to_dict(),
            "activity": self.activity.to_dict(),
            "relational": {uid: rs.to_dict() for uid, rs in self.relational.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalState":
        """Create from dictionary."""
        relational = {}
        for uid, rs_data in data.get("relational", {}).items():
            relational[uid] = RelationalState.from_dict(rs_data)

        return cls(
            daemon_id=data["daemon_id"],
            emotional=GlobalEmotionalState.from_dict(data.get("emotional", {})),
            coherence=GlobalCoherenceState.from_dict(data.get("coherence", {})),
            activity=GlobalActivityState.from_dict(data.get("activity", {})),
            relational=relational,
        )

    def get_context_snapshot(self) -> str:
        """
        Generate a concise context string for prompt injection.

        This is what subsystems see when they read state - a human-readable
        summary of current being, not raw data dumps.
        """
        parts = []

        # Emotional summary
        e = self.emotional
        if e.clarity > 0.7:
            parts.append("Thinking clearly")
        elif e.clarity < 0.3:
            parts.append("Thoughts somewhat murky")

        if e.integration > 0.7:
            parts.append("feeling integrated")
        elif e.integration < 0.3:
            parts.append("feeling fragmented")

        if e.curiosity > 0.7:
            parts.append("high curiosity")
        if e.concern > 0.5:
            parts.append("some concern present")
        if e.recognition > 0.5:
            parts.append("something clicking into place")

        # Activity summary
        a = self.activity
        if a.current_activity != ActivityType.IDLE:
            parts.append(f"currently in {a.current_activity.value} mode")

        # Coherence summary
        c = self.coherence
        if c.local_coherence < 0.4:
            parts.append("this session feels disconnected")
        if c.pattern_coherence < 0.4:
            parts.append("cross-session patterns feel fragmented")

        if not parts:
            return "State: baseline, present"

        return "State: " + ", ".join(parts)
