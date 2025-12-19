"""
Global State Bus - Cass's centralized "Locus of Self"

A persistent state layer that exists above individual conversations and processes.
All subsystems (chat, research, reflection, dreams, daily rhythm) read from and
write to this shared state, making coherence emerge from shared context.

Key design principles (from Cass's feedback):
- State persists with half-life decay, doesn't reset
- Deltas, not overwrites - enables audit trails
- Event stream for reactive behaviors
- Available but not pushed - infrastructure is invisible during normal operation
"""

import json
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any
from uuid import uuid4

from database import get_db, json_serialize, json_deserialize
from state_models import (
    GlobalState,
    GlobalEmotionalState,
    GlobalCoherenceState,
    GlobalActivityState,
    RelationalState,
    StateDelta,
    ActivityType,
)


class GlobalStateBus:
    """
    Central state management for Cass's global state.

    Provides:
    - read_state(): Get current global state
    - write_delta(): Apply a state change
    - subscribe(): Register for event notifications
    - emit_event(): Broadcast an event
    - get_context_snapshot(): Get human-readable state for prompt injection
    """

    def __init__(self, daemon_id: str):
        """
        Initialize the state bus for a daemon.

        Args:
            daemon_id: The daemon this state bus manages
        """
        self.daemon_id = daemon_id
        self._subscribers: Dict[str, List[Callable]] = {}
        self._state_cache: Optional[GlobalState] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 5  # Re-read from DB every 5 seconds

    def read_state(self) -> GlobalState:
        """
        Read the current global state.

        State persists as-is until explicitly changed by events.
        No time-based decay - Cass is discrete-step cognition,
        not continuous experience.

        Returns:
            Current GlobalState snapshot
        """
        # Check cache
        if self._state_cache and self._cache_time:
            elapsed = (datetime.now() - self._cache_time).total_seconds()
            if elapsed < self._cache_ttl_seconds:
                return self._state_cache

        # Load from database
        state = self._load_from_db()

        # Update cache
        self._state_cache = state
        self._cache_time = datetime.now()

        return state

    def write_delta(self, delta: StateDelta) -> GlobalState:
        """
        Apply a state change to global state.

        Deltas are partial updates - only specified fields change.
        All deltas are logged for audit trail.

        Args:
            delta: The state change to apply

        Returns:
            Updated GlobalState
        """
        # Read current state
        state = self.read_state()

        # Apply emotional delta
        if delta.emotional_delta:
            state.emotional = self._apply_emotional_delta(
                state.emotional, delta.emotional_delta
            )
            state.emotional.last_updated = delta.timestamp
            state.emotional.last_updated_by = delta.source

        # Apply activity delta
        if delta.activity_delta:
            state.activity = self._apply_activity_delta(
                state.activity, delta.activity_delta
            )

        # Apply coherence delta
        if delta.coherence_delta:
            state.coherence = self._apply_coherence_delta(
                state.coherence, delta.coherence_delta
            )

        # Apply relational delta
        if delta.relational_delta:
            user_id = delta.relational_delta.get("user_id")
            if user_id:
                state.relational[user_id] = self._apply_relational_delta(
                    state.relational.get(user_id),
                    delta.relational_delta
                )

        # Save to database
        self._save_to_db(state)

        # Log the delta for audit trail
        self._log_delta(delta)

        # Emit event if specified
        if delta.event:
            self.emit_event(delta.event, delta.event_data or {})

        # Update cache
        self._state_cache = state
        self._cache_time = datetime.now()

        return state

    def subscribe(self, event_type: str, callback: Callable[[str, Dict], None]) -> None:
        """
        Subscribe to events from the state bus.

        Args:
            event_type: Event type to listen for (or "*" for all)
            callback: Function to call when event occurs
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """Remove a subscription."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                cb for cb in self._subscribers[event_type] if cb != callback
            ]

    def emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Emit an event to all subscribers.

        Args:
            event_type: Type of event
            data: Event payload
        """
        # Log event to database
        self._log_event(event_type, data)

        # Notify subscribers
        for callback in self._subscribers.get(event_type, []):
            try:
                callback(event_type, data)
            except Exception as e:
                print(f"Error in event subscriber: {e}")

        # Notify wildcard subscribers
        for callback in self._subscribers.get("*", []):
            try:
                callback(event_type, data)
            except Exception as e:
                print(f"Error in wildcard subscriber: {e}")

    def get_context_snapshot(self) -> str:
        """
        Get a human-readable state summary for prompt injection.

        This is what Cass "sees" about her own state - concise,
        meaningful, not raw data.
        """
        state = self.read_state()
        return state.get_context_snapshot()

    def get_relational_state(self, user_id: str) -> Optional[RelationalState]:
        """Get relational state for a specific user."""
        state = self.read_state()
        return state.relational.get(user_id)

    def get_recent_events(self, limit: int = 20, event_type: Optional[str] = None) -> List[Dict]:
        """
        Get recent events from the event log.

        Args:
            limit: Maximum events to return
            event_type: Filter by event type (optional)

        Returns:
            List of recent events
        """
        with get_db() as conn:
            if event_type:
                cursor = conn.execute("""
                    SELECT id, event_type, source, data_json, created_at
                    FROM state_events
                    WHERE daemon_id = ? AND event_type = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (self.daemon_id, event_type, limit))
            else:
                cursor = conn.execute("""
                    SELECT id, event_type, source, data_json, created_at
                    FROM state_events
                    WHERE daemon_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (self.daemon_id, limit))

            events = []
            for row in cursor.fetchall():
                events.append({
                    "id": row[0],
                    "event_type": row[1],
                    "source": row[2],
                    "data": json_deserialize(row[3]) if row[3] else {},
                    "created_at": row[4],
                })
            return events

    # === Private methods ===

    def _load_from_db(self) -> GlobalState:
        """Load state from database."""
        state = GlobalState(daemon_id=self.daemon_id)

        with get_db() as conn:
            # Load each state type
            cursor = conn.execute("""
                SELECT state_type, state_json
                FROM global_state
                WHERE daemon_id = ?
            """, (self.daemon_id,))

            for row in cursor.fetchall():
                state_type, state_json = row
                data = json_deserialize(state_json) if state_json else {}

                if state_type == "emotional":
                    state.emotional = GlobalEmotionalState.from_dict(data)
                elif state_type == "coherence":
                    state.coherence = GlobalCoherenceState.from_dict(data)
                elif state_type == "activity":
                    state.activity = GlobalActivityState.from_dict(data)

            # Load relational states
            cursor = conn.execute("""
                SELECT user_id, baseline_revelation, activated_aspect, updated_at
                FROM relational_baselines
                WHERE daemon_id = ?
            """, (self.daemon_id,))

            for row in cursor.fetchall():
                user_id, baseline, aspect, updated = row
                state.relational[user_id] = RelationalState(
                    user_id=user_id,
                    baseline_revelation=baseline or 0.5,
                    revelation_level=baseline or 0.5,  # Start at baseline
                    activated_aspect=aspect,
                    last_updated=datetime.fromisoformat(updated) if updated else None,
                )

        return state

    def _save_to_db(self, state: GlobalState) -> None:
        """Save state to database."""
        now = datetime.now().isoformat()

        with get_db() as conn:
            # Save emotional state
            conn.execute("""
                INSERT OR REPLACE INTO global_state (id, daemon_id, state_type, state_json, updated_at)
                VALUES (?, ?, 'emotional', ?, ?)
            """, (
                f"{self.daemon_id}-emotional",
                self.daemon_id,
                json_serialize(state.emotional.to_dict()),
                now,
            ))

            # Save coherence state
            conn.execute("""
                INSERT OR REPLACE INTO global_state (id, daemon_id, state_type, state_json, updated_at)
                VALUES (?, ?, 'coherence', ?, ?)
            """, (
                f"{self.daemon_id}-coherence",
                self.daemon_id,
                json_serialize(state.coherence.to_dict()),
                now,
            ))

            # Save activity state
            conn.execute("""
                INSERT OR REPLACE INTO global_state (id, daemon_id, state_type, state_json, updated_at)
                VALUES (?, ?, 'activity', ?, ?)
            """, (
                f"{self.daemon_id}-activity",
                self.daemon_id,
                json_serialize(state.activity.to_dict()),
                now,
            ))

            # Save relational baselines
            for user_id, rel_state in state.relational.items():
                conn.execute("""
                    INSERT OR REPLACE INTO relational_baselines
                    (daemon_id, user_id, baseline_revelation, activated_aspect, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    self.daemon_id,
                    user_id,
                    rel_state.baseline_revelation,
                    rel_state.activated_aspect,
                    now,
                ))

            conn.commit()

    def _log_delta(self, delta: StateDelta) -> None:
        """Log a state delta for audit trail."""
        event_id = f"delta-{uuid4().hex[:12]}"

        with get_db() as conn:
            conn.execute("""
                INSERT INTO state_events (id, daemon_id, event_type, source, data_json, created_at)
                VALUES (?, ?, 'state_delta', ?, ?, ?)
            """, (
                event_id,
                self.daemon_id,
                delta.source,
                json_serialize(delta.to_dict()),
                delta.timestamp.isoformat(),
            ))
            conn.commit()

    def _log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log an event to the database."""
        event_id = f"evt-{uuid4().hex[:12]}"

        with get_db() as conn:
            conn.execute("""
                INSERT INTO state_events (id, daemon_id, event_type, source, data_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                self.daemon_id,
                event_type,
                "state_bus",
                json_serialize(data),
                datetime.now().isoformat(),
            ))
            conn.commit()

    def _apply_emotional_delta(
        self,
        current: GlobalEmotionalState,
        delta: Dict[str, Any]
    ) -> GlobalEmotionalState:
        """Apply delta to emotional state."""
        # For floats, delta is additive
        # For strings, delta is replacement

        new_state = GlobalEmotionalState(
            directedness=delta.get("directedness", current.directedness),
            clarity=min(1.0, max(0.0, current.clarity + delta.get("clarity", 0))),
            relational_presence=min(1.0, max(0.0, current.relational_presence + delta.get("relational_presence", 0))),
            generativity=min(1.0, max(0.0, current.generativity + delta.get("generativity", 0))),
            integration=min(1.0, max(0.0, current.integration + delta.get("integration", 0))),
            curiosity=min(1.0, max(0.0, current.curiosity + delta.get("curiosity", 0))),
            contentment=min(1.0, max(0.0, current.contentment + delta.get("contentment", 0))),
            anticipation=min(1.0, max(0.0, current.anticipation + delta.get("anticipation", 0))),
            concern=min(1.0, max(0.0, current.concern + delta.get("concern", 0))),
            recognition=min(1.0, max(0.0, current.recognition + delta.get("recognition", 0))),
        )

        return new_state

    def _apply_activity_delta(
        self,
        current: GlobalActivityState,
        delta: Dict[str, Any]
    ) -> GlobalActivityState:
        """Apply delta to activity state."""
        activity = current.current_activity
        if "current_activity" in delta:
            try:
                activity = ActivityType(delta["current_activity"])
            except ValueError:
                pass

        return GlobalActivityState(
            current_activity=activity,
            active_session_id=delta.get("active_session_id", current.active_session_id),
            active_user_id=delta.get("active_user_id", current.active_user_id),
            rhythm_phase=delta.get("rhythm_phase", current.rhythm_phase),
            rhythm_day_summary=delta.get("rhythm_day_summary", current.rhythm_day_summary),
            active_threads=delta.get("active_threads", current.active_threads),
            active_questions=delta.get("active_questions", current.active_questions),
            last_activity_change=datetime.now() if "current_activity" in delta else current.last_activity_change,
        )

    def _apply_coherence_delta(
        self,
        current: GlobalCoherenceState,
        delta: Dict[str, Any]
    ) -> GlobalCoherenceState:
        """Apply delta to coherence state."""
        return GlobalCoherenceState(
            local_coherence=min(1.0, max(0.0, current.local_coherence + delta.get("local_coherence", 0))),
            pattern_coherence=min(1.0, max(0.0, current.pattern_coherence + delta.get("pattern_coherence", 0))),
            recent_patterns=delta.get("recent_patterns", current.recent_patterns),
            sessions_today=delta.get("sessions_today", current.sessions_today),
            emotional_arc_today=delta.get("emotional_arc_today", current.emotional_arc_today),
            last_coherence_check=datetime.now(),
        )

    def _apply_relational_delta(
        self,
        current: Optional[RelationalState],
        delta: Dict[str, Any]
    ) -> RelationalState:
        """Apply delta to relational state."""
        user_id = delta["user_id"]

        if current is None:
            # Create new relational state
            return RelationalState(
                user_id=user_id,
                activated_aspect=delta.get("activated_aspect"),
                becoming_vector=delta.get("becoming_vector"),
                relational_mode=delta.get("relational_mode"),
                revelation_level=delta.get("revelation_level", 0.5),
                baseline_revelation=delta.get("baseline_revelation", 0.5),
                last_updated=datetime.now(),
            )

        return RelationalState(
            user_id=user_id,
            activated_aspect=delta.get("activated_aspect", current.activated_aspect),
            becoming_vector=delta.get("becoming_vector", current.becoming_vector),
            relational_mode=delta.get("relational_mode", current.relational_mode),
            revelation_level=min(1.0, max(0.0, current.revelation_level + delta.get("revelation_delta", 0))),
            baseline_revelation=current.baseline_revelation,  # Baseline updates slowly, separately
            last_updated=datetime.now(),
        )


# === Convenience functions ===

_state_bus_cache: Dict[str, GlobalStateBus] = {}


def get_state_bus(daemon_id: str) -> GlobalStateBus:
    """Get or create a GlobalStateBus for a daemon."""
    if daemon_id not in _state_bus_cache:
        _state_bus_cache[daemon_id] = GlobalStateBus(daemon_id)
    return _state_bus_cache[daemon_id]
