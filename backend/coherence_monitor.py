"""
Coherence Monitor - First reactive subscriber to the Global State Bus.

This module implements fragmentation detection for Cass's autonomous operation.
It subscribes to session lifecycle events and state deltas, analyzing patterns
to detect when things might be going wrong.

Design principles:
- Reactive: Responds to events, doesn't poll
- Non-blocking: Event handlers complete in <10ms
- Fixed memory: Rolling windows with bounded size
- Observable: Emits warnings as events for other systems to react

Event subscriptions:
- session.started: Track when autonomous activities begin
- session.ended: Monitor completion reasons
- state_delta: Track emotional state changes

Warning events emitted:
- coherence.fragmentation_detected: Session failure patterns
- coherence.emotional_volatility: Rapid emotional swings
- coherence.behavioral_anomaly: Activity pattern deviation
- coherence.crisis: Low coherence scores
"""

import logging
from collections import deque
from datetime import datetime, timedelta
from statistics import mean, variance
from typing import Dict, Any, Optional, Deque, List
from uuid import uuid4

from coherence_models import (
    SessionSnapshot,
    EmotionalSnapshot,
    FragmentationWarning,
    CoherenceHealthReport,
    CoherenceConfig,
    WarningLevel,
    FragmentationType,
)

logger = logging.getLogger(__name__)


class CoherenceMonitor:
    """
    Monitors Cass's coherence through reactive event subscription.

    This is the first subscriber to prove the reactive pattern works.
    It watches for patterns that indicate fragmentation or instability.
    """

    def __init__(
        self,
        state_bus: Any,  # GlobalStateBus, but avoid circular import
        config: Optional[CoherenceConfig] = None,
    ):
        """
        Initialize the coherence monitor.

        Args:
            state_bus: The GlobalStateBus to subscribe to and emit warnings through
            config: Optional configuration, uses defaults if not provided
        """
        self.state_bus = state_bus
        self.config = config or CoherenceConfig()

        # Rolling windows for analysis
        self._sessions: Deque[SessionSnapshot] = deque(maxlen=self.config.session_window_size)
        self._emotional_snapshots: Deque[EmotionalSnapshot] = deque(maxlen=self.config.emotional_window_size)
        self._activity_counts: Dict[str, int] = {}

        # Goal/synthesis tracking for intellectual health
        self._questions_created: int = 0
        self._questions_resolved: int = 0
        self._synthesis_artifacts: Dict[str, float] = {}  # slug -> confidence
        self._recent_insights: int = 0

        # Active warnings (cleared after retention period)
        self._active_warnings: List[FragmentationWarning] = []

        # Monitor state
        self._started_at: Optional[datetime] = None
        self._last_event_at: Optional[datetime] = None
        self._events_processed: int = 0
        self._subscribed: bool = False

    def start(self) -> None:
        """
        Start monitoring by subscribing to events.

        Call this during application startup after the state bus is ready.
        """
        if self._subscribed:
            logger.warning("CoherenceMonitor already started")
            return

        # Subscribe to events
        self.state_bus.subscribe("session.started", self._on_session_started)
        self.state_bus.subscribe("session.ended", self._on_session_ended)
        self.state_bus.subscribe("state_delta", self._on_state_delta)

        # Subscribe to goal/synthesis events for intellectual health tracking
        self.state_bus.subscribe("goal.question_created", self._on_question_created)
        self.state_bus.subscribe("goal.question_updated", self._on_question_updated)
        self.state_bus.subscribe("goal.synthesis_created", self._on_synthesis_created)
        self.state_bus.subscribe("goal.synthesis_updated", self._on_synthesis_updated)

        self._started_at = datetime.now()
        self._subscribed = True

        logger.info("CoherenceMonitor started - subscribed to session, state_delta, and goal events")

    def stop(self) -> None:
        """
        Stop monitoring by unsubscribing from events.

        Call this during application shutdown.
        """
        if not self._subscribed:
            return

        self.state_bus.unsubscribe("session.started", self._on_session_started)
        self.state_bus.unsubscribe("session.ended", self._on_session_ended)
        self.state_bus.unsubscribe("state_delta", self._on_state_delta)
        self.state_bus.unsubscribe("goal.question_created", self._on_question_created)
        self.state_bus.unsubscribe("goal.question_updated", self._on_question_updated)
        self.state_bus.unsubscribe("goal.synthesis_created", self._on_synthesis_created)
        self.state_bus.unsubscribe("goal.synthesis_updated", self._on_synthesis_updated)

        self._subscribed = False
        logger.info("CoherenceMonitor stopped")

    def get_health_report(self) -> CoherenceHealthReport:
        """
        Generate a health report with current metrics.

        Returns:
            CoherenceHealthReport with current state
        """
        # Clean up old warnings
        self._cleanup_old_warnings()

        # Calculate session metrics
        sessions_list = list(self._sessions)
        session_error_rate = 0.0
        recent_failures = 0

        if sessions_list:
            failures = [s for s in sessions_list if s.is_failure]
            session_error_rate = len(failures) / len(sessions_list)
            # Count failures in last 5 sessions
            recent_failures = sum(1 for s in sessions_list[-5:] if s.is_failure)

        # Calculate emotional variance
        emotional_variance = self._calculate_emotional_variance()

        # Get coherence from state bus
        state = self.state_bus.read_state()
        local_coherence = state.coherence.local_coherence
        pattern_coherence = state.coherence.pattern_coherence

        # Determine overall health
        is_healthy = (
            len(self._active_warnings) == 0 or
            all(w.level in (WarningLevel.INFO, WarningLevel.CAUTION) for w in self._active_warnings)
        )

        # Calculate intellectual health metrics
        synthesis_count = len(self._synthesis_artifacts)
        avg_synthesis_confidence = 0.0
        if self._synthesis_artifacts:
            avg_synthesis_confidence = mean(self._synthesis_artifacts.values())

        return CoherenceHealthReport(
            is_healthy=is_healthy,
            active_warnings=list(self._active_warnings),
            sessions_tracked=len(sessions_list),
            session_error_rate=session_error_rate,
            recent_failures=recent_failures,
            emotional_snapshots_tracked=len(self._emotional_snapshots),
            emotional_variance=emotional_variance,
            local_coherence=local_coherence,
            pattern_coherence=pattern_coherence,
            activity_distribution=dict(self._activity_counts),
            questions_created=self._questions_created,
            questions_resolved=self._questions_resolved,
            recent_insights=self._recent_insights,
            synthesis_count=synthesis_count,
            avg_synthesis_confidence=avg_synthesis_confidence,
            monitor_started_at=self._started_at,
            last_event_at=self._last_event_at,
            events_processed=self._events_processed,
        )

    # === Event Handlers ===

    def _on_session_started(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle session.started events."""
        self._events_processed += 1
        self._last_event_at = datetime.now()

        activity_type = data.get("activity_type", "unknown")
        self._activity_counts[activity_type] = self._activity_counts.get(activity_type, 0) + 1

        logger.debug(f"CoherenceMonitor: session started - {activity_type}")

    def _on_session_ended(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Handle session.ended events.

        This is where we detect session failure patterns.
        """
        self._events_processed += 1
        self._last_event_at = datetime.now()

        # Create snapshot
        snapshot = SessionSnapshot(
            session_id=data.get("session_id", "unknown"),
            activity_type=data.get("activity_type", "unknown"),
            completion_reason=data.get("completion_reason", "unknown"),
            duration_actual=data.get("duration_actual", 0.0) or 0.0,
            iteration_count=data.get("iteration_count", 0),
            tool_calls=data.get("tool_calls", 0),
            timestamp=datetime.now(),
        )

        self._sessions.append(snapshot)

        logger.debug(
            f"CoherenceMonitor: session ended - {snapshot.activity_type} "
            f"({snapshot.completion_reason})"
        )

        # Check for failure patterns
        self._check_session_failures(snapshot)

    def _on_state_delta(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Handle state_delta events.

        This is where we track emotional volatility.
        """
        self._events_processed += 1
        self._last_event_at = datetime.now()

        # Extract emotional state if present
        emotional_delta = data.get("emotional_delta")
        if not emotional_delta:
            return

        # We need to read current state to get absolute values
        state = self.state_bus.read_state()
        snapshot = EmotionalSnapshot.from_state(
            state.emotional.to_dict(),
            datetime.now()
        )

        self._emotional_snapshots.append(snapshot)

        # Check for emotional volatility
        self._check_emotional_volatility(snapshot)

        # Check for coherence crisis
        self._check_coherence_crisis()

    def _on_question_created(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle goal.question_created events."""
        self._events_processed += 1
        self._last_event_at = datetime.now()
        self._questions_created += 1

        logger.debug(f"CoherenceMonitor: question created - {data.get('question_id')}")

    def _on_question_updated(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle goal.question_updated events."""
        self._events_processed += 1
        self._last_event_at = datetime.now()

        update_types = data.get("update_type", [])

        # Track insights
        if "insight_added" in update_types:
            self._recent_insights += 1

        # Track resolutions
        if "status_resolved" in update_types:
            self._questions_resolved += 1

        logger.debug(f"CoherenceMonitor: question updated - {data.get('question_id')} ({update_types})")

    def _on_synthesis_created(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle goal.synthesis_created events."""
        self._events_processed += 1
        self._last_event_at = datetime.now()

        slug = data.get("slug", "unknown")
        confidence = data.get("confidence", 0.3)
        self._synthesis_artifacts[slug] = confidence

        logger.debug(f"CoherenceMonitor: synthesis created - {slug} (confidence: {confidence})")

    def _on_synthesis_updated(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle goal.synthesis_updated events."""
        self._events_processed += 1
        self._last_event_at = datetime.now()

        slug = data.get("slug", "unknown")
        new_confidence = data.get("new_confidence")

        if new_confidence is not None and slug in self._synthesis_artifacts:
            old_confidence = self._synthesis_artifacts[slug]
            self._synthesis_artifacts[slug] = new_confidence

            # Check for significant confidence drop
            if old_confidence - new_confidence >= 0.2:
                self._emit_warning(
                    warning_type=FragmentationType.COHERENCE_CRISIS,
                    level=WarningLevel.CAUTION,
                    message=f"Synthesis confidence dropped: {slug} ({old_confidence:.2f} → {new_confidence:.2f})",
                    metrics={
                        "slug": slug,
                        "old_confidence": old_confidence,
                        "new_confidence": new_confidence,
                        "drop": old_confidence - new_confidence,
                    },
                    trigger_event="goal.synthesis_updated",
                )

        logger.debug(f"CoherenceMonitor: synthesis updated - {slug}")

    # === Pattern Detection ===

    def _check_session_failures(self, latest: SessionSnapshot) -> None:
        """
        Check for session failure patterns.

        Emits coherence.fragmentation_detected if:
        - N consecutive failures, OR
        - Failure rate exceeds threshold
        """
        sessions_list = list(self._sessions)
        if not sessions_list:
            return

        # Check consecutive failures in recent sessions
        recent = sessions_list[-self.config.failure_count_threshold:]
        consecutive_failures = sum(1 for s in recent if s.is_failure)

        if consecutive_failures >= self.config.failure_count_threshold:
            self._emit_warning(
                warning_type=FragmentationType.SESSION_FAILURES,
                level=WarningLevel.WARNING,
                message=f"{consecutive_failures} consecutive session failures detected",
                metrics={
                    "consecutive_failures": consecutive_failures,
                    "recent_sessions": [
                        {"activity": s.activity_type, "reason": s.completion_reason}
                        for s in recent
                    ],
                },
                trigger_event="session.ended",
                trigger_data={"session_id": latest.session_id},
            )
            return

        # Check overall failure rate
        failures = [s for s in sessions_list if s.is_failure]
        failure_rate = len(failures) / len(sessions_list)

        if failure_rate >= self.config.failure_rate_threshold and len(sessions_list) >= 5:
            self._emit_warning(
                warning_type=FragmentationType.SESSION_FAILURES,
                level=WarningLevel.CAUTION,
                message=f"High session failure rate: {failure_rate:.1%}",
                metrics={
                    "failure_rate": failure_rate,
                    "total_sessions": len(sessions_list),
                    "failures": len(failures),
                },
                trigger_event="session.ended",
                trigger_data={"session_id": latest.session_id},
            )

    def _check_emotional_volatility(self, latest: EmotionalSnapshot) -> None:
        """
        Check for emotional volatility.

        Emits coherence.emotional_volatility if variance exceeds thresholds.
        """
        variance_dict = self._calculate_emotional_variance()
        if not variance_dict:
            return

        # Check if any dimension has high variance
        high_variance_dims = [
            (dim, var)
            for dim, var in variance_dict.items()
            if var >= self.config.variance_threshold
        ]

        if high_variance_dims:
            self._emit_warning(
                warning_type=FragmentationType.EMOTIONAL_VOLATILITY,
                level=WarningLevel.CAUTION,
                message=f"High emotional volatility in: {', '.join(d for d, _ in high_variance_dims)}",
                metrics={
                    "high_variance_dimensions": {d: round(v, 4) for d, v in high_variance_dims},
                    "all_variance": {k: round(v, 4) for k, v in variance_dict.items()},
                    "snapshots_analyzed": len(self._emotional_snapshots),
                },
                trigger_event="state_delta",
            )
            return

        # Check for concern spike
        if latest.concern >= self.config.concern_spike_threshold:
            self._emit_warning(
                warning_type=FragmentationType.EMOTIONAL_VOLATILITY,
                level=WarningLevel.INFO,
                message=f"Elevated concern level: {latest.concern:.2f}",
                metrics={
                    "concern": latest.concern,
                    "threshold": self.config.concern_spike_threshold,
                },
                trigger_event="state_delta",
            )

    def _check_coherence_crisis(self) -> None:
        """
        Check for coherence crisis.

        Emits coherence.crisis if coherence scores drop below thresholds.
        """
        state = self.state_bus.read_state()
        local = state.coherence.local_coherence
        pattern = state.coherence.pattern_coherence

        if local < self.config.local_coherence_threshold:
            self._emit_warning(
                warning_type=FragmentationType.COHERENCE_CRISIS,
                level=WarningLevel.WARNING,
                message=f"Local coherence critically low: {local:.2f}",
                metrics={
                    "local_coherence": local,
                    "threshold": self.config.local_coherence_threshold,
                },
                trigger_event="state_delta",
            )

        if pattern < self.config.pattern_coherence_threshold:
            self._emit_warning(
                warning_type=FragmentationType.COHERENCE_CRISIS,
                level=WarningLevel.WARNING,
                message=f"Pattern coherence critically low: {pattern:.2f}",
                metrics={
                    "pattern_coherence": pattern,
                    "threshold": self.config.pattern_coherence_threshold,
                },
                trigger_event="state_delta",
            )

        # Check integration crisis
        if len(self._emotional_snapshots) > 0:
            latest = self._emotional_snapshots[-1]
            if latest.integration < self.config.integration_crisis_threshold:
                self._emit_warning(
                    warning_type=FragmentationType.COHERENCE_CRISIS,
                    level=WarningLevel.CAUTION,
                    message=f"Integration fragmented: {latest.integration:.2f}",
                    metrics={
                        "integration": latest.integration,
                        "threshold": self.config.integration_crisis_threshold,
                    },
                    trigger_event="state_delta",
                )

    def _calculate_emotional_variance(self) -> Dict[str, float]:
        """
        Calculate variance for each emotional dimension.

        Returns:
            Dict mapping dimension name to variance value
        """
        snapshots = list(self._emotional_snapshots)
        if len(snapshots) < 3:
            return {}

        dimensions = ["clarity", "integration", "concern", "generativity", "curiosity"]
        result = {}

        for dim in dimensions:
            values = [getattr(s, dim) for s in snapshots]
            try:
                result[dim] = variance(values)
            except Exception:
                result[dim] = 0.0

        return result

    # === Warning Management ===

    def _emit_warning(
        self,
        warning_type: FragmentationType,
        level: WarningLevel,
        message: str,
        metrics: Dict[str, Any],
        trigger_event: Optional[str] = None,
        trigger_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Create and emit a warning event.

        Deduplicates warnings of the same type within a short window.
        """
        # Check for duplicate warning (same type in last 5 minutes)
        cutoff = datetime.now() - timedelta(minutes=5)
        recent_same_type = [
            w for w in self._active_warnings
            if w.warning_type == warning_type and w.triggered_at > cutoff
        ]

        if recent_same_type:
            logger.debug(f"Suppressing duplicate warning: {warning_type.value}")
            return

        # Create warning
        warning = FragmentationWarning(
            id=f"warn-{uuid4().hex[:12]}",
            warning_type=warning_type,
            level=level,
            message=message,
            metrics=metrics,
            trigger_event=trigger_event,
            trigger_data=trigger_data,
        )

        self._active_warnings.append(warning)

        # Emit event
        event_type = f"coherence.{warning_type.value}"
        self.state_bus.emit_event(event_type, warning.to_event_data())

        logger.info(f"CoherenceMonitor emitted: {event_type} - {message}")

    def _cleanup_old_warnings(self) -> None:
        """Remove warnings older than retention period."""
        cutoff = datetime.now() - timedelta(minutes=self.config.warning_retention_minutes)
        self._active_warnings = [
            w for w in self._active_warnings
            if w.triggered_at > cutoff
        ]


# === Convenience function ===

_monitor_instance: Optional[CoherenceMonitor] = None


def get_coherence_monitor() -> Optional[CoherenceMonitor]:
    """Get the global coherence monitor instance."""
    return _monitor_instance


def init_coherence_monitor(state_bus: Any, config: Optional[CoherenceConfig] = None) -> CoherenceMonitor:
    """
    Initialize the global coherence monitor.

    Args:
        state_bus: The GlobalStateBus instance
        config: Optional configuration

    Returns:
        The initialized CoherenceMonitor
    """
    global _monitor_instance

    if _monitor_instance is not None:
        logger.warning("CoherenceMonitor already initialized, returning existing instance")
        return _monitor_instance

    _monitor_instance = CoherenceMonitor(state_bus, config)
    _monitor_instance.start()

    return _monitor_instance
