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

import asyncio
import json
import logging
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any, TYPE_CHECKING
from uuid import uuid4

from database import get_db, json_serialize, json_deserialize

if TYPE_CHECKING:
    from queryable_source import QueryableSource
    from query_models import StateQuery, QueryResult
    from capability_registry import CapabilityRegistry, CapabilityMatch

logger = logging.getLogger(__name__)
from state_models import (
    GlobalState,
    GlobalEmotionalState,
    GlobalCoherenceState,
    GlobalActivityState,
    DayPhaseState,
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

        # Query interface
        self._queryable_sources: Dict[str, "QueryableSource"] = {}
        self._query_cache: Dict[str, tuple] = {}  # (result, timestamp)
        self._query_cache_ttl_seconds = 60

        # Semantic capability registry (lazy initialized)
        self._capability_registry: Optional["CapabilityRegistry"] = None

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

        # Apply day phase delta
        if delta.day_phase_delta:
            state.day_phase = self._apply_day_phase_delta(
                state.day_phase, delta.day_phase_delta
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
                elif state_type == "day_phase":
                    state.day_phase = DayPhaseState.from_dict(data)

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

            # Save day_phase state
            conn.execute("""
                INSERT OR REPLACE INTO global_state (id, daemon_id, state_type, state_json, updated_at)
                VALUES (?, ?, 'day_phase', ?, ?)
            """, (
                f"{self.daemon_id}-day_phase",
                self.daemon_id,
                json_serialize(state.day_phase.to_dict()),
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

        # Handle contact_started_at parsing
        contact_started = current.contact_started_at
        if "contact_started_at" in delta:
            val = delta["contact_started_at"]
            if isinstance(val, str):
                try:
                    contact_started = datetime.fromisoformat(val)
                except ValueError:
                    contact_started = datetime.now()
            elif isinstance(val, datetime):
                contact_started = val

        return GlobalActivityState(
            current_activity=activity,
            active_user_id=delta.get("active_user_id", current.active_user_id),
            contact_started_at=contact_started,
            messages_this_contact=delta.get("messages_this_contact", current.messages_this_contact),
            current_topics=delta.get("current_topics", current.current_topics),
            active_threads=delta.get("active_threads", current.active_threads),
            active_questions=delta.get("active_questions", current.active_questions),
            rhythm_phase=delta.get("rhythm_phase", current.rhythm_phase),
            rhythm_day_summary=delta.get("rhythm_day_summary", current.rhythm_day_summary),
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

    def _apply_day_phase_delta(
        self,
        current: DayPhaseState,
        delta: Dict[str, Any]
    ) -> DayPhaseState:
        """Apply delta to day phase state."""
        # Handle work slug updates
        recent_slugs = list(current.recent_work_slugs)
        todays_slugs = list(current.todays_work_slugs)
        work_by_phase = dict(current.work_by_phase)

        if "work_slug" in delta:
            slug = delta["work_slug"]
            recent_slugs.insert(0, slug)
            recent_slugs = recent_slugs[:10]  # Keep last 10
            todays_slugs.append(slug)

            # Increment phase counter
            phase = delta.get("current_phase", current.current_phase)
            if phase in work_by_phase:
                work_by_phase[phase] = work_by_phase.get(phase, 0) + 1

        # Handle phase change
        phase_started = current.phase_started_at
        if "current_phase" in delta and delta["current_phase"] != current.current_phase:
            phase_started = datetime.now()
            # Reset today's work on new day (if night->morning transition)
            if delta["current_phase"] == "morning" and current.current_phase == "night":
                todays_slugs = []
                work_by_phase = {"morning": 0, "afternoon": 0, "evening": 0, "night": 0}

        return DayPhaseState(
            current_phase=delta.get("current_phase", current.current_phase),
            phase_started_at=phase_started,
            next_transition_at=delta.get("next_transition_at") or current.next_transition_at,
            recent_work_slugs=recent_slugs,
            todays_work_slugs=todays_slugs,
            work_by_phase=work_by_phase,
            last_updated=datetime.now(),
        )

    # === Query Interface ===

    def register_source(self, source: "QueryableSource") -> None:
        """
        Register a queryable source with the state bus.

        Args:
            source: The QueryableSource implementation to register
        """
        from queryable_source import RefreshStrategy

        source_id = source.source_id
        if source_id in self._queryable_sources:
            logger.warning(f"Replacing existing source: {source_id}")

        self._queryable_sources[source_id] = source
        source._is_registered = True

        logger.info(f"Registered queryable source: {source_id} (strategy: {source.refresh_strategy.value})")

        # Index capabilities for semantic search
        if self._capability_registry:
            asyncio.create_task(self._register_source_capabilities(source))

        # Start background refresh for SCHEDULED sources
        # Only create task if event loop is running (may be registered before startup)
        if source.refresh_strategy == RefreshStrategy.SCHEDULED:
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(source.start_scheduled_refresh())
            except RuntimeError:
                # No running event loop - will be started via start_scheduled_refreshes()
                logger.debug(f"Deferred scheduled refresh for {source_id} (no running loop)")

    def unregister_source(self, source_id: str) -> None:
        """
        Unregister a queryable source.

        Args:
            source_id: ID of the source to remove
        """
        if source_id in self._queryable_sources:
            source = self._queryable_sources[source_id]
            source.stop_scheduled_refresh()
            source._is_registered = False
            del self._queryable_sources[source_id]
            logger.info(f"Unregistered queryable source: {source_id}")

    def list_sources(self) -> List[str]:
        """List all registered source IDs."""
        return list(self._queryable_sources.keys())

    def get_source_schema(self, source_id: str) -> Optional[Dict]:
        """
        Get schema for a source.

        Args:
            source_id: ID of the source

        Returns:
            Schema dict or None if source not found
        """
        source = self._queryable_sources.get(source_id)
        if source:
            return source.schema.to_dict()
        return None

    async def query(
        self,
        query: "StateQuery",
        use_cache: bool = True
    ) -> "QueryResult":
        """
        Execute a structured query against a registered source.

        Args:
            query: The StateQuery to execute
            use_cache: Whether to use cached results (default True)

        Returns:
            QueryResult with data and metadata

        Raises:
            SourceNotFoundError: If source is not registered
            QueryValidationError: If query is invalid
            QueryExecutionError: If execution fails
        """
        from query_models import StateQuery, QueryResult
        from queryable_source import (
            SourceNotFoundError,
            QueryValidationError,
            QueryExecutionError,
            RefreshStrategy,
        )

        source_id = query.source
        source = self._queryable_sources.get(source_id)

        if not source:
            raise SourceNotFoundError(source_id, self.list_sources())

        # Validate query
        errors = source.validate_query(query)
        if errors:
            raise QueryValidationError(source_id, errors)

        # Check cache
        cache_key = f"{source_id}:{query.to_json()}"
        if use_cache and cache_key in self._query_cache:
            cached_result, cached_at = self._query_cache[cache_key]
            age = (datetime.now() - cached_at).total_seconds()
            if age < self._query_cache_ttl_seconds:
                # Update staleness info
                cached_result.is_stale = True
                cached_result.cache_age_seconds = age
                return cached_result

        # Ensure rollups are fresh for LAZY sources
        if source.refresh_strategy == RefreshStrategy.LAZY:
            await source.ensure_rollups_fresh()

        # Execute query
        try:
            result = await source.execute_query(query)
        except Exception as e:
            raise QueryExecutionError(source_id, query, str(e))

        # Cache result
        self._query_cache[cache_key] = (result, datetime.now())

        return result

    def describe_sources(self) -> Dict[str, Dict]:
        """
        Get schemas for all registered sources.

        Useful for building LLM tool documentation.

        Returns:
            Dict mapping source_id to schema dict
        """
        return {
            source_id: source.schema.to_dict()
            for source_id, source in self._queryable_sources.items()
        }

    def describe_sources_for_llm(self) -> str:
        """
        Generate a human-readable description of all sources for LLM context.

        Returns:
            Formatted string describing available sources
        """
        if not self._queryable_sources:
            return "No queryable sources registered."

        parts = ["Available data sources:"]
        for source_id, source in self._queryable_sources.items():
            parts.append("")
            parts.append(source.describe_for_llm())

        return "\n".join(parts)

    def get_rollup_summary(self) -> Dict[str, Dict]:
        """
        Get precomputed rollups from all sources.

        Returns immediately with cached aggregates - no recomputation.

        Returns:
            Dict mapping source_id to rollup values
        """
        return {
            source_id: source.get_precomputed_rollups()
            for source_id, source in self._queryable_sources.items()
        }

    async def refresh_all_rollups(self) -> None:
        """
        Force refresh rollups on all sources.

        Useful for admin commands or testing.
        """
        for source_id, source in self._queryable_sources.items():
            try:
                await source.refresh_rollups()
                logger.info(f"Refreshed rollups for {source_id}")
            except Exception as e:
                logger.error(f"Failed to refresh rollups for {source_id}: {e}")

    def start_scheduled_refreshes(self) -> None:
        """
        Start scheduled refresh loops for all SCHEDULED strategy sources.

        Call this from startup_event after the event loop is running.
        Sources registered before the event loop was running will have
        their refresh loops started here.
        """
        from queryable_source import RefreshStrategy

        for source_id, source in self._queryable_sources.items():
            if source.refresh_strategy == RefreshStrategy.SCHEDULED:
                if not source._scheduled_refresh_task or source._scheduled_refresh_task.done():
                    asyncio.create_task(source.start_scheduled_refresh())
                    logger.info(f"Started scheduled refresh for {source_id}")

    # === Capability Registry ===

    def set_capability_registry(self, registry: "CapabilityRegistry") -> None:
        """
        Set the capability registry for semantic discovery.

        Args:
            registry: Initialized CapabilityRegistry instance
        """
        self._capability_registry = registry
        logger.info("Capability registry attached to state bus")

        # Note: Existing sources will be indexed when start_capability_indexing() is called
        # from the startup event (where we have an event loop)

    async def start_capability_indexing(self) -> None:
        """
        Index all existing sources in the capability registry.

        Call this from startup_event after the event loop is running.
        """
        if not self._capability_registry:
            return

        for source in self._queryable_sources.values():
            await self._register_source_capabilities(source)

    async def _register_source_capabilities(self, source: "QueryableSource") -> None:
        """Register a source's capabilities in the semantic index."""
        if not self._capability_registry:
            return

        try:
            count = await self._capability_registry.register_source(source)
            logger.debug(f"Indexed {count} capabilities from {source.source_id}")
        except Exception as e:
            logger.error(f"Failed to index capabilities for {source.source_id}: {e}")

    async def find_capabilities(
        self,
        query: str,
        limit: int = 5,
        source_filter: Optional[str] = None,
        tag_filter: Optional[List[str]] = None,
    ) -> List["CapabilityMatch"]:
        """
        Find relevant capabilities by semantic similarity.

        This is the interface for natural language capability discovery.
        Cass can ask "What data do we have about user engagement?" and
        get back relevant metrics from any registered source.

        Args:
            query: Natural language description of what data is needed
            limit: Maximum number of results
            source_filter: Optional source ID to filter by
            tag_filter: Optional tags to filter by

        Returns:
            List of matching capabilities, sorted by relevance
        """
        if not self._capability_registry:
            logger.warning("No capability registry configured")
            return []

        return await self._capability_registry.find_capabilities(
            query=query,
            limit=limit,
            source_filter=source_filter,
            tag_filter=tag_filter,
        )

    async def list_all_capabilities(self) -> Dict[str, List[Dict]]:
        """
        List all registered capabilities grouped by source.

        Returns:
            Dict mapping source_id to list of metric info dicts
        """
        if not self._capability_registry:
            return {}

        return await self._capability_registry.list_all_capabilities()

    def format_capabilities_for_llm(self, matches: List["CapabilityMatch"]) -> str:
        """
        Format capability matches for LLM consumption.

        Args:
            matches: List of capability matches

        Returns:
            Human-readable formatted string
        """
        if not self._capability_registry:
            return "Capability registry not configured."

        return self._capability_registry.format_for_llm(matches)


# === Convenience functions ===

_state_bus_cache: Dict[str, GlobalStateBus] = {}


def get_state_bus(daemon_id: str) -> GlobalStateBus:
    """Get or create a GlobalStateBus for a daemon."""
    if daemon_id not in _state_bus_cache:
        _state_bus_cache[daemon_id] = GlobalStateBus(daemon_id)
    return _state_bus_cache[daemon_id]
