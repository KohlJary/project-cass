"""
Coherence Monitor Models - Data structures for fragmentation detection.

These models support the CoherenceMonitor, the first reactive subscriber
to the global state bus. The monitor detects patterns that indicate
fragmentation or instability in Cass's operation.

Design principles:
- Fixed memory footprint (rolling windows, not unbounded lists)
- Immutable snapshots for thread safety
- Clear thresholds for actionable warnings
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum


class WarningLevel(str, Enum):
    """Severity levels for coherence warnings."""
    INFO = "info"           # Worth noting, not concerning
    CAUTION = "caution"     # Approaching thresholds
    WARNING = "warning"     # Threshold crossed, attention needed
    CRITICAL = "critical"   # Multiple thresholds, intervention may be needed


class FragmentationType(str, Enum):
    """Types of fragmentation the monitor can detect."""
    SESSION_FAILURES = "session_failures"       # Repeated session errors
    EMOTIONAL_VOLATILITY = "emotional_volatility"  # Rapid emotional swings
    BEHAVIORAL_ANOMALY = "behavioral_anomaly"   # Activity pattern deviation
    COHERENCE_CRISIS = "coherence_crisis"       # Low coherence scores


@dataclass(frozen=True)
class SessionSnapshot:
    """
    Immutable snapshot of a session for rolling window analysis.

    Captured from session.ended events. Contains only what's needed
    for pattern detection, not full session state.
    """
    session_id: str
    activity_type: str
    completion_reason: str  # "time_limit", "error", "consecutive_failures", etc.
    duration_actual: float  # minutes
    iteration_count: int
    tool_calls: int
    timestamp: datetime

    @property
    def is_failure(self) -> bool:
        """Check if this session ended in failure."""
        return self.completion_reason in ("error", "consecutive_failures", "exception")

    @property
    def is_normal(self) -> bool:
        """Check if this session completed normally."""
        return self.completion_reason in ("time_limit", "completed", "goal_reached")


@dataclass(frozen=True)
class EmotionalSnapshot:
    """
    Immutable snapshot of emotional state for volatility analysis.

    Captured from state_delta events that include emotional_delta.
    """
    timestamp: datetime

    # Core dimensions (0.0 - 1.0)
    clarity: float
    integration: float
    concern: float
    generativity: float
    curiosity: float

    @classmethod
    def from_state(cls, emotional_state: Dict[str, Any], timestamp: datetime) -> "EmotionalSnapshot":
        """Create snapshot from GlobalEmotionalState dict."""
        return cls(
            timestamp=timestamp,
            clarity=emotional_state.get("clarity", 0.5),
            integration=emotional_state.get("integration", 0.5),
            concern=emotional_state.get("concern", 0.0),
            generativity=emotional_state.get("generativity", 0.5),
            curiosity=emotional_state.get("curiosity", 0.5),
        )


@dataclass
class FragmentationWarning:
    """
    A coherence warning to be emitted back to the state bus.

    These warnings are events themselves - other systems can subscribe
    to react (e.g., trigger a reflection session, notify admin).
    """
    id: str
    warning_type: FragmentationType
    level: WarningLevel
    message: str

    # Context for the warning
    metrics: Dict[str, Any] = field(default_factory=dict)
    triggered_at: datetime = field(default_factory=datetime.now)

    # What triggered it
    trigger_event: Optional[str] = None
    trigger_data: Optional[Dict[str, Any]] = None

    def to_event_data(self) -> Dict[str, Any]:
        """Convert to event data for state bus emission."""
        return {
            "warning_id": self.id,
            "warning_type": self.warning_type.value,
            "level": self.level.value,
            "message": self.message,
            "metrics": self.metrics,
            "triggered_at": self.triggered_at.isoformat(),
            "trigger_event": self.trigger_event,
        }


@dataclass
class CoherenceHealthReport:
    """
    Current health status of the coherence monitor.

    Returned by the /api/coherence/health endpoint.
    """
    # Status
    is_healthy: bool
    active_warnings: List[FragmentationWarning] = field(default_factory=list)

    # Session metrics (rolling window)
    sessions_tracked: int = 0
    session_error_rate: float = 0.0  # 0.0 - 1.0
    recent_failures: int = 0

    # Emotional metrics (rolling window)
    emotional_snapshots_tracked: int = 0
    emotional_variance: Dict[str, float] = field(default_factory=dict)  # dimension -> variance

    # Coherence metrics (from global state)
    local_coherence: float = 0.5
    pattern_coherence: float = 0.5

    # Activity metrics
    activity_distribution: Dict[str, int] = field(default_factory=dict)  # activity -> count

    # Intellectual health metrics
    questions_created: int = 0
    questions_resolved: int = 0
    recent_insights: int = 0
    synthesis_count: int = 0
    avg_synthesis_confidence: float = 0.0

    # Monitor meta
    monitor_started_at: Optional[datetime] = None
    last_event_at: Optional[datetime] = None
    events_processed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "is_healthy": self.is_healthy,
            "active_warnings": [w.to_event_data() for w in self.active_warnings],
            "sessions": {
                "tracked": self.sessions_tracked,
                "error_rate": round(self.session_error_rate, 3),
                "recent_failures": self.recent_failures,
            },
            "emotional": {
                "snapshots_tracked": self.emotional_snapshots_tracked,
                "variance": {k: round(v, 4) for k, v in self.emotional_variance.items()},
            },
            "coherence": {
                "local": round(self.local_coherence, 3),
                "pattern": round(self.pattern_coherence, 3),
            },
            "activity_distribution": self.activity_distribution,
            "intellectual": {
                "questions_created": self.questions_created,
                "questions_resolved": self.questions_resolved,
                "recent_insights": self.recent_insights,
                "synthesis_count": self.synthesis_count,
                "avg_synthesis_confidence": round(self.avg_synthesis_confidence, 3),
            },
            "monitor": {
                "started_at": self.monitor_started_at.isoformat() if self.monitor_started_at else None,
                "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
                "events_processed": self.events_processed,
            },
        }


@dataclass
class CoherenceConfig:
    """
    Configuration for coherence monitoring thresholds.

    These can be tuned based on observed patterns. Start conservative,
    adjust as we learn what's normal for Cass.
    """
    # Rolling window sizes
    session_window_size: int = 20       # How many sessions to track
    emotional_window_size: int = 50     # How many emotional snapshots
    warning_retention_minutes: int = 60  # How long to keep warnings active

    # Session failure thresholds
    failure_count_threshold: int = 3    # N failures in window triggers warning
    failure_rate_threshold: float = 0.3 # 30% failure rate triggers warning

    # Emotional volatility thresholds
    variance_threshold: float = 0.15    # High variance in any dimension
    concern_spike_threshold: float = 0.5  # Concern level above this
    integration_crisis_threshold: float = 0.3  # Integration below this

    # Coherence thresholds
    local_coherence_threshold: float = 0.3   # Below this is fragmented
    pattern_coherence_threshold: float = 0.3 # Below this is fragmented

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CoherenceConfig":
        """Create from dictionary (e.g., from config.py)."""
        return cls(
            session_window_size=data.get("session_window_size", 20),
            emotional_window_size=data.get("emotional_window_size", 50),
            warning_retention_minutes=data.get("warning_retention_minutes", 60),
            failure_count_threshold=data.get("failure_count_threshold", 3),
            failure_rate_threshold=data.get("failure_rate_threshold", 0.3),
            variance_threshold=data.get("variance_threshold", 0.15),
            concern_spike_threshold=data.get("concern_spike_threshold", 0.5),
            integration_crisis_threshold=data.get("integration_crisis_threshold", 0.3),
            local_coherence_threshold=data.get("local_coherence_threshold", 0.3),
            pattern_coherence_threshold=data.get("pattern_coherence_threshold", 0.3),
        )
