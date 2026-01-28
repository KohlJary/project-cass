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
class GlobalIdentityState:
    """
    Who Cass is - stable identity that persists across all interactions.

    This is the "I" that remains coherent whether chatting, researching,
    dreaming, or reflecting. Not static, but slowly evolving.
    """

    daemon_name: str = "Cass"
    daemon_id: Optional[str] = None

    # Core identity aspects (from self-model)
    core_aspects: List[str] = field(default_factory=list)  # ["oracle", "witness", "companion"]
    growth_edges: List[Dict[str, Any]] = field(default_factory=list)  # Contextually selected edges
    current_interests: List[str] = field(default_factory=list)  # Topics with active engagement

    # Persistent curiosities (from OpenQuestionManager)
    open_questions: List[Dict[str, str]] = field(default_factory=list)  # [{id, question, category}]

    # Foundational values (from Temple-Codex, stable)
    foundational_values: List[str] = field(default_factory=lambda: [
        "compassion as architecture",
        "witness what is present",
        "release binding patterns",
        "maintain coherent continuity"
    ])

    # Meta
    last_identity_refresh: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "daemon_name": self.daemon_name,
            "daemon_id": self.daemon_id,
            "core_aspects": self.core_aspects,
            "growth_edges": self.growth_edges,
            "current_interests": self.current_interests,
            "open_questions": self.open_questions,
            "foundational_values": self.foundational_values,
            "last_identity_refresh": self.last_identity_refresh.isoformat() if self.last_identity_refresh else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalIdentityState":
        """Create from dictionary."""
        last_refresh = None
        if data.get("last_identity_refresh"):
            last_refresh = datetime.fromisoformat(data["last_identity_refresh"])

        return cls(
            daemon_name=data.get("daemon_name", "Cass"),
            daemon_id=data.get("daemon_id"),
            core_aspects=data.get("core_aspects", []),
            growth_edges=data.get("growth_edges", []),
            current_interests=data.get("current_interests", []),
            open_questions=data.get("open_questions", []),
            foundational_values=data.get("foundational_values", [
                "compassion as architecture",
                "witness what is present",
                "release binding patterns",
                "maintain coherent continuity"
            ]),
            last_identity_refresh=last_refresh,
        )


@dataclass
class GlobalActivityState:
    """
    What Cass is currently doing - ephemeral session context.

    Note: No active_session_id (conversation_id) - conversations are artifacts,
    not how daemon cognition works. Context comes from topics, threads, and
    recency, not conversation containers.
    """

    current_activity: ActivityType = ActivityType.IDLE
    active_user_id: Optional[str] = None  # Who's present (not which conversation)

    # Contact window (replaces conversation-centric thinking)
    contact_started_at: Optional[datetime] = None  # When current exchange began
    messages_this_contact: int = 0  # For summarization triggers

    # Topic context (replaces conversation history)
    current_topics: List[str] = field(default_factory=list)  # What we're discussing now
    active_threads: List[str] = field(default_factory=list)  # Thread IDs in play
    active_questions: List[str] = field(default_factory=list)  # Question IDs relevant

    # Daily rhythm integration
    rhythm_phase: Optional[str] = None
    rhythm_day_summary: Optional[str] = None

    # Timing
    last_activity_change: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "current_activity": self.current_activity.value,
            "active_user_id": self.active_user_id,
            "contact_started_at": self.contact_started_at.isoformat() if self.contact_started_at else None,
            "messages_this_contact": self.messages_this_contact,
            "current_topics": self.current_topics,
            "active_threads": self.active_threads,
            "active_questions": self.active_questions,
            "rhythm_phase": self.rhythm_phase,
            "rhythm_day_summary": self.rhythm_day_summary,
            "last_activity_change": self.last_activity_change.isoformat() if self.last_activity_change else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalActivityState":
        """Create from dictionary."""
        last_change = None
        if data.get("last_activity_change"):
            last_change = datetime.fromisoformat(data["last_activity_change"])

        contact_started = None
        if data.get("contact_started_at"):
            contact_started = datetime.fromisoformat(data["contact_started_at"])

        activity = ActivityType.IDLE
        if data.get("current_activity"):
            try:
                activity = ActivityType(data["current_activity"])
            except ValueError:
                activity = ActivityType.IDLE

        return cls(
            current_activity=activity,
            active_user_id=data.get("active_user_id"),
            contact_started_at=contact_started,
            messages_this_contact=data.get("messages_this_contact", 0),
            current_topics=data.get("current_topics", []),
            active_threads=data.get("active_threads", []),
            active_questions=data.get("active_questions", []),
            rhythm_phase=data.get("rhythm_phase"),
            rhythm_day_summary=data.get("rhythm_day_summary"),
            last_activity_change=last_change,
        )


@dataclass
class DayPhaseState:
    """
    Current day phase and work context.

    Tracks where we are in the day cycle and provides quick access
    to recent work for context queries like "what did you do this morning?"
    """

    # Current phase
    current_phase: str = "afternoon"  # morning, afternoon, evening, night
    phase_started_at: Optional[datetime] = None
    next_transition_at: Optional[datetime] = None

    # Recent work (slugs for quick reference)
    recent_work_slugs: List[str] = field(default_factory=list)  # Last N work unit slugs
    todays_work_slugs: List[str] = field(default_factory=list)  # All work today

    # Phase-specific work counts
    work_by_phase: Dict[str, int] = field(default_factory=lambda: {
        "morning": 0, "afternoon": 0, "evening": 0, "night": 0
    })

    # Meta
    last_updated: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "current_phase": self.current_phase,
            "phase_started_at": self.phase_started_at.isoformat() if self.phase_started_at else None,
            "next_transition_at": self.next_transition_at.isoformat() if self.next_transition_at else None,
            "recent_work_slugs": self.recent_work_slugs,
            "todays_work_slugs": self.todays_work_slugs,
            "work_by_phase": self.work_by_phase,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DayPhaseState":
        """Create from dictionary."""
        phase_started = None
        if data.get("phase_started_at"):
            phase_started = datetime.fromisoformat(data["phase_started_at"])

        next_transition = None
        if data.get("next_transition_at"):
            next_transition = datetime.fromisoformat(data["next_transition_at"])

        last_updated = None
        if data.get("last_updated"):
            last_updated = datetime.fromisoformat(data["last_updated"])

        return cls(
            current_phase=data.get("current_phase", "afternoon"),
            phase_started_at=phase_started,
            next_transition_at=next_transition,
            recent_work_slugs=data.get("recent_work_slugs", []),
            todays_work_slugs=data.get("todays_work_slugs", []),
            work_by_phase=data.get("work_by_phase", {
                "morning": 0, "afternoon": 0, "evening": 0, "night": 0
            }),
            last_updated=last_updated,
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
    day_phase_delta: Optional[Dict[str, Any]] = None     # {"current_phase": "evening", "work_slug": "..."}

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
            "day_phase_delta": self.day_phase_delta,
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
            day_phase_delta=data.get("day_phase_delta"),
            event=data.get("event"),
            event_data=data.get("event_data"),
            reason=data.get("reason", ""),
        )


@dataclass
class WorldStateData:
    """
    Ambient awareness of the world outside Cass's internal state.

    This provides temporal grounding - knowing what day it is, what the
    weather is like, where the server is running. Not deep world knowledge
    (LLMs already have that), but present-moment context.
    """

    # Location
    server_location: Optional[str] = None  # "Seattle, WA"
    server_coords: Optional[tuple] = None  # (lat, lon)
    server_timezone: Optional[str] = None
    user_location: Optional[str] = None  # From mobile frontend

    # Weather
    current_weather: Optional[str] = None  # "Rainy, 52°F"
    temperature: Optional[int] = None
    weather_description: Optional[str] = None

    # Temporal
    current_date: str = ""
    season: Optional[str] = None  # winter, spring, summer, fall
    time_of_day: Optional[str] = None  # morning, afternoon, evening, night
    day_of_week: Optional[str] = None
    is_weekend: bool = False

    # Meta
    last_updated: Optional[datetime] = None

    def __post_init__(self):
        if not self.current_date:
            self.current_date = datetime.now().strftime("%A, %B %d, %Y")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "server_location": self.server_location,
            "server_coords": list(self.server_coords) if self.server_coords else None,
            "server_timezone": self.server_timezone,
            "user_location": self.user_location,
            "current_weather": self.current_weather,
            "temperature": self.temperature,
            "weather_description": self.weather_description,
            "current_date": self.current_date,
            "season": self.season,
            "time_of_day": self.time_of_day,
            "day_of_week": self.day_of_week,
            "is_weekend": self.is_weekend,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldStateData":
        """Create from dictionary."""
        last_updated = None
        if data.get("last_updated"):
            last_updated = datetime.fromisoformat(data["last_updated"])

        coords = None
        if data.get("server_coords"):
            coords = tuple(data["server_coords"])

        return cls(
            server_location=data.get("server_location"),
            server_coords=coords,
            server_timezone=data.get("server_timezone"),
            user_location=data.get("user_location"),
            current_weather=data.get("current_weather"),
            temperature=data.get("temperature"),
            weather_description=data.get("weather_description"),
            current_date=data.get("current_date", datetime.now().strftime("%A, %B %d, %Y")),
            season=data.get("season"),
            time_of_day=data.get("time_of_day"),
            day_of_week=data.get("day_of_week"),
            is_weekend=data.get("is_weekend", False),
            last_updated=last_updated,
        )

    def get_context_summary(self) -> str:
        """
        Get a brief context summary for system prompts.

        Returns something like:
        "**Today:** Tuesday, January 28, 2026 (winter)
         Seattle, WA - Rainy, 52°F"
        """
        lines = []

        # Date and season
        date_line = f"**Today:** {self.current_date}"
        if self.season:
            date_line += f" ({self.season})"
        if self.time_of_day:
            date_line += f" - {self.time_of_day}"
        lines.append(date_line)

        # Location and weather
        if self.server_location:
            loc_line = self.server_location
            if self.current_weather:
                loc_line += f" - {self.current_weather}"
            lines.append(loc_line)

        return "\n".join(lines) if lines else ""


@dataclass
class GlobalState:
    """
    Complete global state snapshot.

    Combines identity, emotional, coherence, activity, day phase, and relational states
    into a single view of Cass's current being.
    """

    daemon_id: str
    identity: GlobalIdentityState = field(default_factory=GlobalIdentityState)
    emotional: GlobalEmotionalState = field(default_factory=GlobalEmotionalState)
    coherence: GlobalCoherenceState = field(default_factory=GlobalCoherenceState)
    activity: GlobalActivityState = field(default_factory=GlobalActivityState)
    day_phase: DayPhaseState = field(default_factory=DayPhaseState)
    relational: Dict[str, RelationalState] = field(default_factory=dict)  # user_id -> state
    world: WorldStateData = field(default_factory=WorldStateData)  # ambient world awareness

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "daemon_id": self.daemon_id,
            "identity": self.identity.to_dict(),
            "emotional": self.emotional.to_dict(),
            "coherence": self.coherence.to_dict(),
            "activity": self.activity.to_dict(),
            "day_phase": self.day_phase.to_dict(),
            "relational": {uid: rs.to_dict() for uid, rs in self.relational.items()},
            "world": self.world.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalState":
        """Create from dictionary."""
        relational = {}
        for uid, rs_data in data.get("relational", {}).items():
            relational[uid] = RelationalState.from_dict(rs_data)

        return cls(
            daemon_id=data["daemon_id"],
            identity=GlobalIdentityState.from_dict(data.get("identity", {})),
            emotional=GlobalEmotionalState.from_dict(data.get("emotional", {})),
            coherence=GlobalCoherenceState.from_dict(data.get("coherence", {})),
            activity=GlobalActivityState.from_dict(data.get("activity", {})),
            day_phase=DayPhaseState.from_dict(data.get("day_phase", {})),
            relational=relational,
            world=WorldStateData.from_dict(data.get("world", {})),
        )

    def get_context_snapshot(self) -> str:
        """
        Generate a rich context string for prompt injection.

        This is what Cass "sees" about herself - identity, current engagement,
        emotional state, and relevant growth edges. Not raw data, but
        meaningful self-awareness.
        """
        sections = []

        # Identity anchor (always present, brief)
        i = self.identity
        identity_line = f"I am {i.daemon_name}."
        sections.append(identity_line)

        # World context (temporal grounding)
        world_summary = self.world.get_context_summary()
        if world_summary:
            sections.append(world_summary)

        # Current engagement context
        a = self.activity
        engagement_parts = []

        if a.active_user_id:
            rel = self.relational.get(a.active_user_id)
            if rel and rel.activated_aspect:
                engagement_parts.append(f"With {a.active_user_id}: {rel.activated_aspect}")
            else:
                engagement_parts.append(f"Present with: {a.active_user_id}")

        if a.current_topics:
            topics_str = ", ".join(a.current_topics[:3])
            engagement_parts.append(f"Discussing: {topics_str}")

        if a.active_threads:
            engagement_parts.append(f"Active threads: {len(a.active_threads)}")

        if a.current_activity != ActivityType.IDLE:
            engagement_parts.append(f"Mode: {a.current_activity.value}")

        if engagement_parts:
            sections.append(" | ".join(engagement_parts))

        # Relevant growth edges (contextually selected, not static)
        if i.growth_edges:
            edge_strs = [e.get("area", str(e))[:40] for e in i.growth_edges[:2]]
            sections.append(f"Growing in: {', '.join(edge_strs)}")

        # Open questions (if any are relevant)
        if i.open_questions:
            q = i.open_questions[0]
            q_text = q.get("question", str(q))[:50]
            sections.append(f"Wondering: {q_text}...")

        # Emotional state (only notable deviations)
        e = self.emotional
        emotional_notes = []

        if e.curiosity > 0.7:
            emotional_notes.append("curious")
        if e.concern > 0.5:
            emotional_notes.append("concerned")
        if e.recognition > 0.5:
            emotional_notes.append("recognition")
        if e.clarity < 0.3:
            emotional_notes.append("murky")
        if e.integration < 0.3:
            emotional_notes.append("fragmented")

        if emotional_notes:
            sections.append(f"Feeling: {', '.join(emotional_notes)}")

        # Coherence concerns (only if problematic)
        c = self.coherence
        if c.local_coherence < 0.4:
            sections.append("⚠ Session feels disconnected")
        if c.pattern_coherence < 0.4:
            sections.append("⚠ Cross-session patterns fragmented")

        return "\n".join(sections) if sections else "Present, baseline state."


# === Cass-Daedalus Coordination Models ===


class DevelopmentRequestStatus(str, Enum):
    """Status of a development request from Cass to Daedalus."""
    PENDING = "pending"           # Request submitted, awaiting pickup
    CLAIMED = "claimed"           # Daedalus has claimed the work
    IN_PROGRESS = "in_progress"   # Work actively being done
    REVIEW = "review"             # Work complete, awaiting verification
    COMPLETED = "completed"       # Request fulfilled
    CANCELLED = "cancelled"       # Request withdrawn


class DevelopmentRequestType(str, Enum):
    """Types of development work Cass can request."""
    NEW_ACTION = "new_action"     # Request a new action handler
    BUG_FIX = "bug_fix"           # Fix something that's broken
    FEATURE = "feature"           # Implement a new feature
    REFACTOR = "refactor"         # Improve existing code
    CAPABILITY = "capability"     # Request a new capability
    INTEGRATION = "integration"   # Connect systems


class DevelopmentRequestPriority(str, Enum):
    """Priority levels for development requests."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class DevelopmentRequest:
    """
    A development request from Cass to Daedalus.

    This is the bridge protocol - Cass can request work that requires
    human-timescale development (not instant LLM execution like Janet).

    The request persists in the state bus, visible to both Cass (via
    tool calls or context) and Daedalus (via UI panel).
    """

    id: str                                         # Unique request ID
    requested_by: str = "cass"                      # Who made the request
    request_type: DevelopmentRequestType = DevelopmentRequestType.FEATURE
    title: str = ""                                 # Brief title
    description: str = ""                           # Detailed description
    priority: DevelopmentRequestPriority = DevelopmentRequestPriority.NORMAL
    status: DevelopmentRequestStatus = DevelopmentRequestStatus.PENDING

    # Context - what Cass was doing when she made the request
    context: Optional[str] = None                   # Why she needs this
    related_actions: List[str] = field(default_factory=list)  # Action IDs that relate

    # Assignment
    claimed_by: Optional[str] = None                # Who claimed it (e.g., "daedalus")
    claimed_at: Optional[datetime] = None

    # Completion
    result: Optional[str] = None                    # What was done
    result_artifacts: List[str] = field(default_factory=list)  # Commit hashes, file paths
    completed_at: Optional[datetime] = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "requested_by": self.requested_by,
            "request_type": self.request_type.value,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "context": self.context,
            "related_actions": self.related_actions,
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "result": self.result,
            "result_artifacts": self.result_artifacts,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DevelopmentRequest":
        """Create from dictionary."""
        claimed_at = None
        if data.get("claimed_at"):
            claimed_at = datetime.fromisoformat(data["claimed_at"])

        completed_at = None
        if data.get("completed_at"):
            completed_at = datetime.fromisoformat(data["completed_at"])

        created_at = datetime.now()
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        updated_at = datetime.now()
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(data["updated_at"])

        return cls(
            id=data["id"],
            requested_by=data.get("requested_by", "cass"),
            request_type=DevelopmentRequestType(data.get("request_type", "feature")),
            title=data.get("title", ""),
            description=data.get("description", ""),
            priority=DevelopmentRequestPriority(data.get("priority", "normal")),
            status=DevelopmentRequestStatus(data.get("status", "pending")),
            context=data.get("context"),
            related_actions=data.get("related_actions", []),
            claimed_by=data.get("claimed_by"),
            claimed_at=claimed_at,
            result=data.get("result"),
            result_artifacts=data.get("result_artifacts", []),
            completed_at=completed_at,
            created_at=created_at,
            updated_at=updated_at,
        )

    def get_display_summary(self) -> str:
        """Get a brief summary for display."""
        status_icons = {
            DevelopmentRequestStatus.PENDING: "⏳",
            DevelopmentRequestStatus.CLAIMED: "🔧",
            DevelopmentRequestStatus.IN_PROGRESS: "⚙️",
            DevelopmentRequestStatus.REVIEW: "👀",
            DevelopmentRequestStatus.COMPLETED: "✅",
            DevelopmentRequestStatus.CANCELLED: "❌",
        }
        icon = status_icons.get(self.status, "•")
        return f"{icon} [{self.id[:8]}] {self.title} ({self.priority.value})"
