"""
Activity Dashboard - Real-time activity tracking for Cass's vessel.

This module subscribes to events across the system and aggregates them
into a comprehensive activity dashboard. Unlike the coherence monitor
which looks for problems, this tracks normal activity for visibility.

Design principles:
- Rolling window with hourly/daily buckets
- Non-blocking event handlers
- Memory-bounded storage (fixed-size windows)
- Provides both real-time counts and historical trends

Event subscriptions:
- session.started / session.ended: Autonomous activity
- conversation.* : Conversation activity
- memory.*: Memory storage events
- goal.*: Intellectual activity
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Deque, List

logger = logging.getLogger(__name__)


@dataclass
class ActivityBucket:
    """A time bucket for activity aggregation."""
    hour: datetime  # Truncated to the hour
    sessions_started: int = 0
    sessions_completed: int = 0
    sessions_failed: int = 0
    conversations_created: int = 0
    messages_exchanged: int = 0
    memories_stored: int = 0
    questions_created: int = 0
    questions_resolved: int = 0
    syntheses_created: int = 0
    insights_generated: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hour": self.hour.isoformat(),
            "sessions": {
                "started": self.sessions_started,
                "completed": self.sessions_completed,
                "failed": self.sessions_failed,
            },
            "conversations": {
                "created": self.conversations_created,
                "messages": self.messages_exchanged,
            },
            "memory": {
                "stored": self.memories_stored,
            },
            "intellectual": {
                "questions_created": self.questions_created,
                "questions_resolved": self.questions_resolved,
                "syntheses": self.syntheses_created,
                "insights": self.insights_generated,
            },
        }


@dataclass
class ActivitySummary:
    """Summary of activity over a time period."""
    period: str  # "1h", "24h", "7d"
    start_time: datetime
    end_time: datetime

    # Totals
    total_sessions: int = 0
    session_success_rate: float = 0.0
    total_messages: int = 0
    total_memories: int = 0
    total_questions: int = 0
    total_syntheses: int = 0
    total_insights: int = 0

    # Activity by type
    sessions_by_type: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "period": self.period,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "totals": {
                "sessions": self.total_sessions,
                "session_success_rate": round(self.session_success_rate, 3),
                "messages": self.total_messages,
                "memories": self.total_memories,
                "questions": self.total_questions,
                "syntheses": self.total_syntheses,
                "insights": self.total_insights,
            },
            "sessions_by_type": self.sessions_by_type,
        }


class ActivityDashboard:
    """
    Tracks activity across Cass's vessel for dashboard display.

    Provides both real-time counters and historical trends with
    hourly granularity for the past 7 days.
    """

    # Keep 7 days of hourly buckets
    MAX_HOURLY_BUCKETS = 24 * 7

    def __init__(self, state_bus: Any):
        """
        Initialize the activity dashboard.

        Args:
            state_bus: The GlobalStateBus to subscribe to
        """
        self.state_bus = state_bus

        # Hourly activity buckets (rolling window)
        self._hourly_buckets: Deque[ActivityBucket] = deque(maxlen=self.MAX_HOURLY_BUCKETS)

        # Real-time counters (since last reset)
        self._current_bucket: Optional[ActivityBucket] = None

        # Session type tracking
        self._session_types: Dict[str, int] = {}

        # Monitor state
        self._started_at: Optional[datetime] = None
        self._last_event_at: Optional[datetime] = None
        self._events_processed: int = 0
        self._subscribed: bool = False

    def start(self) -> None:
        """Start tracking by subscribing to events."""
        if self._subscribed:
            logger.warning("ActivityDashboard already started")
            return

        # Session events
        self.state_bus.subscribe("session.started", self._on_session_started)
        self.state_bus.subscribe("session.ended", self._on_session_ended)

        # Conversation events
        self.state_bus.subscribe("conversation.created", self._on_conversation_created)
        self.state_bus.subscribe("conversation.message_added", self._on_message_added)

        # Memory events
        self.state_bus.subscribe("memory.conversation.stored", self._on_memory_stored)

        # Goal events
        self.state_bus.subscribe("goal.question_created", self._on_question_created)
        self.state_bus.subscribe("goal.question_updated", self._on_question_updated)
        self.state_bus.subscribe("goal.synthesis_created", self._on_synthesis_created)

        self._started_at = datetime.now()
        self._current_bucket = self._get_or_create_bucket(self._started_at)
        self._subscribed = True

        logger.info("ActivityDashboard started - subscribed to activity events")

    def stop(self) -> None:
        """Stop tracking by unsubscribing from events."""
        if not self._subscribed:
            return

        self.state_bus.unsubscribe("session.started", self._on_session_started)
        self.state_bus.unsubscribe("session.ended", self._on_session_ended)
        self.state_bus.unsubscribe("conversation.created", self._on_conversation_created)
        self.state_bus.unsubscribe("conversation.message_added", self._on_message_added)
        self.state_bus.unsubscribe("memory.conversation.stored", self._on_memory_stored)
        self.state_bus.unsubscribe("goal.question_created", self._on_question_created)
        self.state_bus.unsubscribe("goal.question_updated", self._on_question_updated)
        self.state_bus.unsubscribe("goal.synthesis_created", self._on_synthesis_created)

        self._subscribed = False
        logger.info("ActivityDashboard stopped")

    def get_current_activity(self) -> Dict[str, Any]:
        """
        Get current activity counters.

        Returns:
            Dict with current hour's activity plus meta info
        """
        bucket = self._get_or_create_bucket(datetime.now())

        return {
            "current_hour": bucket.to_dict() if bucket else {},
            "session_types": dict(self._session_types),
            "meta": {
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "last_event_at": self._last_event_at.isoformat() if self._last_event_at else None,
                "events_processed": self._events_processed,
                "hourly_buckets_stored": len(self._hourly_buckets),
            },
        }

    def get_summary(self, period: str = "24h") -> ActivitySummary:
        """
        Get activity summary for a time period.

        Args:
            period: One of "1h", "24h", "7d"

        Returns:
            ActivitySummary for the period
        """
        now = datetime.now()

        if period == "1h":
            start = now - timedelta(hours=1)
        elif period == "24h":
            start = now - timedelta(hours=24)
        elif period == "7d":
            start = now - timedelta(days=7)
        else:
            start = now - timedelta(hours=24)
            period = "24h"

        # Filter buckets in range
        relevant_buckets = [
            b for b in self._hourly_buckets
            if b.hour >= start
        ]

        # Include current bucket if in range
        if self._current_bucket and self._current_bucket.hour >= start:
            relevant_buckets.append(self._current_bucket)

        # Aggregate
        total_sessions = sum(b.sessions_started for b in relevant_buckets)
        completed = sum(b.sessions_completed for b in relevant_buckets)
        failed = sum(b.sessions_failed for b in relevant_buckets)

        success_rate = 0.0
        if completed + failed > 0:
            success_rate = completed / (completed + failed)

        return ActivitySummary(
            period=period,
            start_time=start,
            end_time=now,
            total_sessions=total_sessions,
            session_success_rate=success_rate,
            total_messages=sum(b.messages_exchanged for b in relevant_buckets),
            total_memories=sum(b.memories_stored for b in relevant_buckets),
            total_questions=sum(b.questions_created for b in relevant_buckets),
            total_syntheses=sum(b.syntheses_created for b in relevant_buckets),
            total_insights=sum(b.insights_generated for b in relevant_buckets),
            sessions_by_type=dict(self._session_types),
        )

    def get_hourly_trend(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get hourly activity trend.

        Args:
            hours: Number of hours to include

        Returns:
            List of hourly buckets (oldest first)
        """
        cutoff = datetime.now() - timedelta(hours=hours)

        result = [
            b.to_dict() for b in self._hourly_buckets
            if b.hour >= cutoff
        ]

        # Add current bucket
        if self._current_bucket:
            result.append(self._current_bucket.to_dict())

        return result

    # === Event Handlers ===

    def _on_session_started(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle session.started events."""
        self._events_processed += 1
        self._last_event_at = datetime.now()

        bucket = self._get_or_create_bucket(datetime.now())
        bucket.sessions_started += 1

        activity_type = data.get("activity_type", "unknown")
        self._session_types[activity_type] = self._session_types.get(activity_type, 0) + 1

    def _on_session_ended(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle session.ended events."""
        self._events_processed += 1
        self._last_event_at = datetime.now()

        bucket = self._get_or_create_bucket(datetime.now())

        completion_reason = data.get("completion_reason", "unknown")
        if completion_reason in ("error", "consecutive_failures", "exception"):
            bucket.sessions_failed += 1
        else:
            bucket.sessions_completed += 1

    def _on_conversation_created(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle conversation.created events."""
        self._events_processed += 1
        self._last_event_at = datetime.now()

        bucket = self._get_or_create_bucket(datetime.now())
        bucket.conversations_created += 1

    def _on_message_added(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle conversation.message_added events."""
        self._events_processed += 1
        self._last_event_at = datetime.now()

        bucket = self._get_or_create_bucket(datetime.now())
        bucket.messages_exchanged += 1

    def _on_memory_stored(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle memory.conversation.stored events."""
        self._events_processed += 1
        self._last_event_at = datetime.now()

        bucket = self._get_or_create_bucket(datetime.now())
        bucket.memories_stored += 1

    def _on_question_created(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle goal.question_created events."""
        self._events_processed += 1
        self._last_event_at = datetime.now()

        bucket = self._get_or_create_bucket(datetime.now())
        bucket.questions_created += 1

    def _on_question_updated(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle goal.question_updated events - track insights and resolutions."""
        self._events_processed += 1
        self._last_event_at = datetime.now()

        update_types = data.get("update_type", [])
        bucket = self._get_or_create_bucket(datetime.now())

        if "insight_added" in update_types:
            bucket.insights_generated += 1

        if "status_resolved" in update_types:
            bucket.questions_resolved += 1

    def _on_synthesis_created(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle goal.synthesis_created events."""
        self._events_processed += 1
        self._last_event_at = datetime.now()

        bucket = self._get_or_create_bucket(datetime.now())
        bucket.syntheses_created += 1

    # === Bucket Management ===

    def _get_or_create_bucket(self, timestamp: datetime) -> ActivityBucket:
        """
        Get or create an activity bucket for the given timestamp.

        Rotates to a new bucket when the hour changes.
        """
        # Truncate to hour
        bucket_hour = timestamp.replace(minute=0, second=0, microsecond=0)

        # Check if current bucket is still valid
        if self._current_bucket and self._current_bucket.hour == bucket_hour:
            return self._current_bucket

        # Need a new bucket
        if self._current_bucket:
            # Archive the old bucket
            self._hourly_buckets.append(self._current_bucket)

        # Create new bucket
        self._current_bucket = ActivityBucket(hour=bucket_hour)
        return self._current_bucket


# === Convenience functions ===

_dashboard_instance: Optional[ActivityDashboard] = None


def get_activity_dashboard() -> Optional[ActivityDashboard]:
    """Get the global activity dashboard instance."""
    return _dashboard_instance


def init_activity_dashboard(state_bus: Any) -> ActivityDashboard:
    """
    Initialize the global activity dashboard.

    Args:
        state_bus: The GlobalStateBus instance

    Returns:
        The initialized ActivityDashboard
    """
    global _dashboard_instance

    if _dashboard_instance is not None:
        logger.warning("ActivityDashboard already initialized, returning existing instance")
        return _dashboard_instance

    _dashboard_instance = ActivityDashboard(state_bus)
    _dashboard_instance.start()

    return _dashboard_instance
