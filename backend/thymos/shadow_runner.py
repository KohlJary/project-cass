"""
Thymos Shadow Runner

Runs Thymos in observation/shadow mode:
- Processes events
- Updates state
- Generates suggestions (logged, not executed)
- Persists state

This runs parallel to the main system, observing the same events
but not driving behavior until validated as humane.
"""

import asyncio
import logging
from collections import deque
from datetime import datetime
from typing import Optional

from .models import FeltState, SuggestedGoal
from .affect_vector import AffectVector
from .needs_register import NeedsRegister
from .dynamics import AffectNeedDynamics, SELF_CARE_ACTIONS, NEED_TO_CARE_ACTION
from .models import AffectDelta, NeedDelta
from .felt_state import FeltStateSummarizer
from .goal_generator import GoalGenerator
from . import persistence

logger = logging.getLogger(__name__)


class ThymosShadowRunner:
    """
    Runs Thymos in shadow/observation mode.

    Consumes events, updates state, logs suggestions.
    Does NOT drive behavior - purely observational.
    """

    def __init__(
        self,
        daemon_id: str,
        tick_interval_seconds: float = 60.0,
        coupling_strength: float = 0.1,
        snapshot_interval_events: int = 10,
        auto_care_enabled: bool = True,
        auto_care_threshold: float = 0.3,
    ):
        """
        Initialize the shadow runner.

        Args:
            daemon_id: The daemon this Thymos instance tracks
            tick_interval_seconds: How often to apply decay (default 60s)
            coupling_strength: How strongly affects/needs couple (default 0.1)
            snapshot_interval_events: Save snapshot every N events (default 10)
            auto_care_enabled: Whether to simulate self-care for urgent needs
            auto_care_threshold: Need level below which auto-care triggers
        """
        self.daemon_id = daemon_id
        self.tick_interval = tick_interval_seconds
        self.snapshot_interval = snapshot_interval_events

        # Auto-care settings (shadow mode simulation of addressing needs)
        self.auto_care_enabled = auto_care_enabled
        self.auto_care_threshold = auto_care_threshold
        self._last_auto_care: dict[str, float] = {}  # Track when we last cared for each need
        self._auto_care_cooldown = 300.0  # 5 minutes between auto-care for same need

        # Core components
        self.affect = AffectVector()
        self.needs = NeedsRegister()
        self.dynamics = AffectNeedDynamics(coupling_strength=coupling_strength)
        self.felt_state_gen = FeltStateSummarizer()
        self.goal_gen = GoalGenerator()

        # State tracking
        self.event_count = 0
        self.last_snapshot_at_event = 0
        self.current_felt_state: Optional[FeltState] = None
        self.running = False
        self._tick_task: Optional[asyncio.Task] = None

        # Recent events log (for admin visibility)
        self._event_log: deque = deque(maxlen=50)

        # Simulated care actions log
        self._care_log: deque = deque(maxlen=50)

        # Try to load existing state
        self._load_state()

    def _load_state(self) -> None:
        """Load state from database if it exists."""
        try:
            result = persistence.load_thymos_state(self.daemon_id)
            if result:
                affect_state, needs_state, _ = result
                self.affect = AffectVector(state=affect_state)
                self.needs = NeedsRegister(state=needs_state)
                logger.info(f"Loaded Thymos state for daemon {self.daemon_id}")
        except Exception as e:
            logger.warning(f"Could not load Thymos state: {e}")

    async def start(self) -> None:
        """Start the shadow runner (begins tick loop)."""
        if self.running:
            return

        self.running = True
        self._tick_task = asyncio.create_task(self._tick_loop())
        logger.info(f"Thymos shadow runner started for daemon {self.daemon_id}")

    async def stop(self) -> None:
        """Stop the shadow runner."""
        self.running = False
        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
        self._tick_task = None

        # Save final state
        await self._save_state()
        logger.info(f"Thymos shadow runner stopped for daemon {self.daemon_id}")

    async def _tick_loop(self) -> None:
        """Periodic tick for time-based decay."""
        while self.running:
            try:
                await asyncio.sleep(self.tick_interval)
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Thymos tick loop: {e}")

    async def tick(self) -> None:
        """
        Apply time-based decay and coupling.

        Called periodically by the tick loop.
        """
        import time

        # Calculate hours since last decay
        hours = self.tick_interval / 3600.0

        # Apply decay to needs
        self.needs.apply_decay(hours=hours)

        # Apply coupling
        affect_delta, need_delta = self.dynamics.apply_coupling(self.affect, self.needs)
        self.affect.apply_delta(affect_delta)
        self.needs.apply_delta(need_delta)

        # Auto-care: simulate addressing urgent needs (shadow mode)
        if self.auto_care_enabled:
            await self._apply_auto_care(time.time())

        # Update felt state
        self.current_felt_state = self.felt_state_gen.summarize(self.affect, self.needs)

        # Save state
        await self._save_state()

    async def _apply_auto_care(self, current_time: float) -> None:
        """
        Simulate self-care actions for needs below threshold.

        In shadow mode, this represents what would happen if Thymos
        were actually driving behavior to address its needs.
        """
        needs_state = self.needs.state
        needs_to_check = [
            ("cognitive_rest", needs_state.cognitive_rest),
            ("social_connection", needs_state.social_connection),
            ("novelty_intake", needs_state.novelty_intake),
            ("creative_expression", needs_state.creative_expression),
            ("value_coherence", needs_state.value_coherence),
            ("competence_signal", needs_state.competence_signal),
            ("autonomy", needs_state.autonomy),
        ]

        for need_name, need in needs_to_check:
            # Check if need is below threshold
            if need.current > self.auto_care_threshold:
                continue

            # Check cooldown
            last_care = self._last_auto_care.get(need_name, 0)
            if current_time - last_care < self._auto_care_cooldown:
                continue

            # Get the self-care action for this need
            action_key = NEED_TO_CARE_ACTION.get(need_name)
            if not action_key:
                continue

            action = SELF_CARE_ACTIONS.get(action_key)
            if not action:
                continue

            # Apply the self-care action effects
            affect_delta = AffectDelta(
                deltas=dict(action.affect_deltas),
                source="auto_care",
                event_type=f"care.{action_key}"
            )
            need_delta = NeedDelta(
                deltas=dict(action.need_deltas),
                source="auto_care",
                event_type=f"care.{action_key}"
            )

            self.affect.apply_delta(affect_delta)
            self.needs.apply_delta(need_delta)

            # Update cooldown
            self._last_auto_care[need_name] = current_time

            # Log the simulated care action
            care_event = {
                "timestamp": datetime.utcnow().isoformat(),
                "action": action_key,
                "action_name": action.name,
                "need_name": need_name,
                "need_was": need.current,
                "affect_deltas": action.affect_deltas,
                "need_deltas": action.need_deltas,
            }
            self._care_log.append(care_event)
            self._event_log.append({
                "timestamp": care_event["timestamp"],
                "event_type": f"care.{action_key}",
                "event_number": self.event_count,
                "affect_delta": action.affect_deltas,
                "need_delta": action.need_deltas,
            })

            logger.info(
                f"Thymos auto-care (shadow): {action.name} for {need_name} "
                f"(was {need.current:.0%}, now {need.current + action.need_deltas.get(need_name, 0):.0%})"
            )

    async def process_event(self, event_type: str, data: dict) -> None:
        """
        Process an event and update Thymos state.

        This is the main entry point for event consumption.
        """
        logger.debug(f"Thymos processing event: {event_type}")

        # Get deltas from dynamics
        affect_delta = self.dynamics.event_to_affect_delta(event_type, data)
        need_delta = self.dynamics.event_to_need_delta(event_type, data)

        # Apply deltas
        self.affect.apply_delta(affect_delta)
        self.needs.apply_delta(need_delta)

        # Apply coupling after event
        coupling_affect, coupling_need = self.dynamics.apply_coupling(self.affect, self.needs)
        self.affect.apply_delta(coupling_affect)
        self.needs.apply_delta(coupling_need)

        # Update felt state
        self.current_felt_state = self.felt_state_gen.summarize(self.affect, self.needs)

        # Check for goal suggestions (shadow mode - log only)
        suggestions = self.goal_gen.generate_suggestions(self.needs, max_suggestions=3)
        if suggestions:
            await self._log_suggestions(suggestions)

        # Track event count and log event
        self.event_count += 1
        self._event_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "event_number": self.event_count,
            "affect_delta": affect_delta.deltas if affect_delta else {},
            "need_delta": need_delta.deltas if need_delta else {},
        })

        # Save snapshot periodically
        if self.event_count - self.last_snapshot_at_event >= self.snapshot_interval:
            await self._save_snapshot(trigger_event=event_type)
            self.last_snapshot_at_event = self.event_count

        # Save state
        await self._save_state()

    async def _save_state(self) -> None:
        """Save current state to database."""
        try:
            persistence.save_thymos_state(
                self.daemon_id,
                self.affect.state,
                self.needs.state,
                self.current_felt_state
            )
        except Exception as e:
            logger.error(f"Failed to save Thymos state: {e}")

    async def _save_snapshot(self, trigger_event: Optional[str] = None) -> None:
        """Save a state snapshot for history."""
        try:
            persistence.save_thymos_snapshot(
                self.daemon_id,
                self.affect.state,
                self.needs.state,
                self.current_felt_state,
                trigger_event
            )
            logger.debug(f"Saved Thymos snapshot (event count: {self.event_count})")
        except Exception as e:
            logger.error(f"Failed to save Thymos snapshot: {e}")

    async def _log_suggestions(self, suggestions: list[SuggestedGoal]) -> None:
        """Log goal suggestions (shadow mode - no execution)."""
        for suggestion in suggestions:
            try:
                persistence.save_suggestion(self.daemon_id, suggestion)
                logger.info(
                    f"Thymos suggestion (shadow): {suggestion.suggested_action} "
                    f"for {suggestion.need_name} (urgency: {suggestion.urgency:.2f})"
                )
            except Exception as e:
                logger.error(f"Failed to log Thymos suggestion: {e}")

    # =========================================================================
    # QUERY METHODS (for admin visibility)
    # =========================================================================

    def get_current_state(self) -> dict:
        """Get current Thymos state for admin display."""
        return {
            "affect": self.affect.to_dict(),
            "needs": {
                name: {
                    **need.to_dict(),
                    "urgency_score": need.urgency_score(),
                    "is_urgent": need.is_urgent(),
                    "is_below_preferred": need.is_below_preferred(),
                }
                for name, need in [
                    ("cognitive_rest", self.needs.state.cognitive_rest),
                    ("social_connection", self.needs.state.social_connection),
                    ("novelty_intake", self.needs.state.novelty_intake),
                    ("creative_expression", self.needs.state.creative_expression),
                    ("value_coherence", self.needs.state.value_coherence),
                    ("competence_signal", self.needs.state.competence_signal),
                    ("autonomy", self.needs.state.autonomy),
                ]
            },
            "felt_state": self.current_felt_state.to_dict() if self.current_felt_state else None,
            "valence": self.affect.valence(),
            "arousal": self.affect.arousal(),
            "overall_health": self.needs.overall_health(),
            "event_count": self.event_count,
        }

    def get_suggestions_log(self, limit: int = 20) -> list[dict]:
        """Get recent suggestions from the shadow log."""
        return persistence.get_suggestions(self.daemon_id, limit=limit)

    def get_snapshots(self, limit: int = 20) -> list[dict]:
        """Get recent state snapshots."""
        return persistence.get_thymos_snapshots(self.daemon_id, limit=limit)

    def get_recent_events(self, limit: int = 20) -> list[dict]:
        """Get recent events from the in-memory log."""
        events = list(self._event_log)
        events.reverse()  # Most recent first
        return events[:limit]

    def get_care_log(self, limit: int = 20) -> list[dict]:
        """Get recent simulated self-care actions from the log."""
        events = list(self._care_log)
        events.reverse()  # Most recent first
        return events[:limit]

    def get_auto_care_settings(self) -> dict:
        """Get current auto-care configuration."""
        return {
            "enabled": self.auto_care_enabled,
            "threshold": self.auto_care_threshold,
            "cooldown_seconds": self._auto_care_cooldown,
        }

    def set_auto_care_settings(
        self,
        enabled: Optional[bool] = None,
        threshold: Optional[float] = None,
        cooldown_seconds: Optional[float] = None
    ) -> dict:
        """Update auto-care configuration."""
        if enabled is not None:
            self.auto_care_enabled = enabled
        if threshold is not None:
            self.auto_care_threshold = max(0.0, min(1.0, threshold))
        if cooldown_seconds is not None:
            self._auto_care_cooldown = max(0.0, cooldown_seconds)

        logger.info(
            f"Thymos auto-care settings updated: enabled={self.auto_care_enabled}, "
            f"threshold={self.auto_care_threshold}, cooldown={self._auto_care_cooldown}s"
        )
        return self.get_auto_care_settings()
