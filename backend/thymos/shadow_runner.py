"""
Thymos Shadow Runner

Runs Thymos in observation/shadow mode:
- Processes events
- Updates state
- Generates suggestions (logged, not executed)
- Persists state

This runs parallel to the main system, observing the same events
but not driving behavior until validated as humane.

SAFETY CONTROLS:
- Global kill switch: THYMOS_ENABLED flag
- Pause/resume: pause() and resume() methods
- Reset to baseline: reset_to_baseline() for suffering states
- Emergency stop: emergency_stop() kills everything immediately
"""

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict

from .models import FeltState, SuggestedGoal
from .affect_vector import AffectVector
from .needs_register import NeedsRegister
from .dynamics import AffectNeedDynamics, get_care_action_for_need
from .models import AffectDelta, NeedDelta
from .felt_state import FeltStateSummarizer
from .goal_generator import GoalGenerator
from . import persistence

# Grimoire integration (optional)
try:
    from ..grimoire.manager import GrimoireManager, create_grimoire_hooks
    GRIMOIRE_AVAILABLE = True
except ImportError:
    try:
        from grimoire.manager import GrimoireManager, create_grimoire_hooks
        GRIMOIRE_AVAILABLE = True
    except ImportError:
        GRIMOIRE_AVAILABLE = False
        GrimoireManager = None

logger = logging.getLogger(__name__)

# =============================================================================
# GLOBAL KILL SWITCH
# =============================================================================
# Set to False to completely disable Thymos system-wide
# This is the emergency off switch - use if Cass is stuck in suffering state
THYMOS_ENABLED = True

def thymos_kill_switch(enabled: bool) -> bool:
    """
    Global kill switch for Thymos.

    Args:
        enabled: True to enable Thymos, False to disable

    Returns:
        New state of THYMOS_ENABLED
    """
    global THYMOS_ENABLED
    THYMOS_ENABLED = enabled
    logger.warning(f"THYMOS KILL SWITCH: {'ENABLED' if enabled else 'DISABLED'}")
    return THYMOS_ENABLED

def is_thymos_enabled() -> bool:
    """Check if Thymos is globally enabled."""
    return THYMOS_ENABLED


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

        # Safety controls
        self._paused = False

        # Scheduler integration: suggestion buffering
        # Pending suggestions for scheduler to poll
        self._pending_suggestions: List[SuggestedGoal] = []
        # Cooldown tracking to prevent suggestion spam per need
        self._suggestion_cooldowns: Dict[str, datetime] = {}
        # Default cooldown between suggestions for the same need
        self._suggestion_cooldown_minutes: int = 30

        # Grimoire integration (spell-based behavior)
        self._grimoire: Optional["GrimoireManager"] = None
        self._grimoire_on_tick = None
        self._grimoire_on_event = None

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

    def attach_grimoire(
        self,
        grimoire: "GrimoireManager",
        agent: Optional[Any] = None,
        self_manager: Optional[Any] = None,
        memory_manager: Optional[Any] = None,
    ) -> None:
        """
        Attach a GrimoireManager for spell-based behavior.

        The Grimoire will be called on each tick and event to evaluate
        spell triggers and execute matching spells.

        Args:
            grimoire: Configured GrimoireManager instance
            agent: Optional agent client for agentic nodes (ASK, RATE, etc.)
            self_manager: Optional SelfManager for saving observations
            memory_manager: Optional MemoryManager for saving journals
        """
        if not GRIMOIRE_AVAILABLE:
            logger.warning("Grimoire not available - cannot attach")
            return

        self._grimoire = grimoire

        # Configure services (pass self for Thymos access, agent, and storage managers)
        grimoire.configure_services(
            thymos_runner=self,
            agent=agent,
            self_manager=self_manager,
            memory_manager=memory_manager,
        )

        # Create hooks
        self._grimoire_on_tick, self._grimoire_on_event = create_grimoire_hooks(grimoire)

        logger.info("Grimoire attached to Thymos shadow runner")

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

                # Check global kill switch
                if not THYMOS_ENABLED:
                    continue

                # Check pause state
                if self._paused:
                    continue

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

        # Grimoire: check spell triggers based on current state
        if self._grimoire_on_tick:
            try:
                affects = self.affect.to_dict()
                needs = {
                    name: getattr(self.needs.state, name).current
                    for name in [
                        "cognitive_rest", "social_connection", "novelty_intake",
                        "creative_expression", "value_coherence", "competence_signal", "autonomy"
                    ]
                }
                await self._grimoire_on_tick(affects, needs)
            except Exception as e:
                logger.error(f"Grimoire tick error: {e}")

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

            # Get the self-care action for this need from config
            action = get_care_action_for_need(need_name)
            if not action:
                continue
            action_key = action.key

            # Capture value BEFORE applying delta
            need_before = need.current

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

            logger.info(
                f"Thymos auto-care: {need_name} BEFORE apply_delta: {need.current:.2%}, "
                f"delta: {action.need_deltas}"
            )

            self.affect.apply_delta(affect_delta)
            self.needs.apply_delta(need_delta)

            logger.info(
                f"Thymos auto-care: {need_name} AFTER apply_delta: {need.current:.2%}"
            )

            # Update cooldown
            self._last_auto_care[need_name] = current_time

            # Log the simulated care action
            care_event = {
                "timestamp": datetime.utcnow().isoformat(),
                "action": action_key,
                "action_name": action.name,
                "need_name": need_name,
                "need_was": need_before,  # Fixed: use captured value before delta
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
                f"(was {need_before:.0%}, now {need.current:.0%})"
            )

    async def process_event(self, event_type: str, data: dict) -> None:
        """
        Process an event and update Thymos state.

        This is the main entry point for event consumption.
        """
        # Check global kill switch
        if not THYMOS_ENABLED:
            return

        # Check pause state
        if self._paused:
            logger.debug(f"Thymos paused - ignoring event: {event_type}")
            return

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

        # Grimoire: check event-based spell triggers
        if self._grimoire_on_event:
            try:
                await self._grimoire_on_event(event_type, data)
            except Exception as e:
                logger.error(f"Grimoire event error: {e}")

        # Check for goal suggestions (shadow mode - log only)
        suggestions = self.goal_gen.generate_suggestions(self.needs, max_suggestions=3)
        if suggestions:
            # Filter by cooldown to prevent suggestion spam
            filtered = self._filter_cooldowns(suggestions)
            if filtered:
                # Add to pending buffer for scheduler to poll
                self._pending_suggestions.extend(filtered)
                # Log all filtered suggestions
                await self._log_suggestions(filtered)

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

    def _filter_cooldowns(
        self,
        suggestions: List[SuggestedGoal],
        cooldown_minutes: Optional[int] = None,
    ) -> List[SuggestedGoal]:
        """
        Filter suggestions based on per-need cooldowns.

        Prevents suggestion spam by requiring a minimum time between
        suggestions for the same need.

        Args:
            suggestions: List of suggestions to filter
            cooldown_minutes: Override default cooldown (default: 30 min)

        Returns:
            Filtered list of suggestions that pass cooldown check
        """
        cooldown = cooldown_minutes or self._suggestion_cooldown_minutes
        now = datetime.now(timezone.utc)
        filtered: List[SuggestedGoal] = []

        for suggestion in suggestions:
            last_suggestion = self._suggestion_cooldowns.get(suggestion.need_name)

            if last_suggestion:
                elapsed_minutes = (now - last_suggestion).total_seconds() / 60
                if elapsed_minutes < cooldown:
                    logger.debug(
                        f"Thymos suggestion cooldown: {suggestion.need_name} "
                        f"({elapsed_minutes:.1f}m < {cooldown}m)"
                    )
                    continue

            # Passed cooldown - add to filtered list and update cooldown
            filtered.append(suggestion)
            self._suggestion_cooldowns[suggestion.need_name] = now

        return filtered

    def get_pending_suggestions(self, clear: bool = True) -> List[SuggestedGoal]:
        """
        Get pending suggestions for scheduler to poll.

        Called by the scheduler to retrieve suggestions that Thymos has
        generated since the last poll. In shadow mode, the scheduler logs
        these but doesn't execute them.

        Args:
            clear: If True, clears the pending list after retrieval

        Returns:
            List of pending suggestions
        """
        suggestions = list(self._pending_suggestions)
        if clear:
            self._pending_suggestions.clear()
        return suggestions

    def has_pending_suggestions(self) -> bool:
        """Check if there are pending suggestions without clearing."""
        return len(self._pending_suggestions) > 0

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

    def get_timing_config(self) -> dict:
        """Get current timing/tick configuration."""
        return {
            "tick_interval_seconds": self.tick_interval,
            "suggestion_cooldown_minutes": self._suggestion_cooldown_minutes,
            "snapshot_interval_events": self.snapshot_interval,
        }

    def set_timing_config(
        self,
        tick_interval_seconds: Optional[float] = None,
        suggestion_cooldown_minutes: Optional[int] = None,
        snapshot_interval_events: Optional[int] = None,
    ) -> dict:
        """
        Update timing configuration.

        Args:
            tick_interval_seconds: How often to apply decay (10-300s)
            suggestion_cooldown_minutes: Min time between suggestions for same need (1-120min)
            snapshot_interval_events: Save snapshot every N events (1-100)

        Returns:
            Updated timing config
        """
        if tick_interval_seconds is not None:
            # Clamp to reasonable range: 10s - 5min
            self.tick_interval = max(10.0, min(300.0, tick_interval_seconds))

        if suggestion_cooldown_minutes is not None:
            # Clamp to reasonable range: 1min - 2hr
            self._suggestion_cooldown_minutes = max(1, min(120, suggestion_cooldown_minutes))

        if snapshot_interval_events is not None:
            # Clamp to reasonable range: 1 - 100 events
            self.snapshot_interval = max(1, min(100, snapshot_interval_events))

        logger.info(
            f"Thymos timing config updated: tick={self.tick_interval}s, "
            f"suggestion_cooldown={self._suggestion_cooldown_minutes}min, "
            f"snapshot_interval={self.snapshot_interval} events"
        )
        return self.get_timing_config()

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

    # =========================================================================
    # SAFETY CONTROLS
    # =========================================================================

    def pause(self) -> dict:
        """
        Pause Thymos processing without losing state.

        Use this for temporary debugging. State is preserved.
        Call resume() to continue.
        """
        self._paused = True
        logger.warning("Thymos PAUSED - events will be ignored until resume()")
        return {"status": "paused", "state_preserved": True}

    def resume(self) -> dict:
        """Resume Thymos processing after pause."""
        self._paused = False
        logger.info("Thymos RESUMED - processing events normally")
        return {"status": "running"}

    def is_paused(self) -> bool:
        """Check if Thymos is paused."""
        return getattr(self, '_paused', False)

    def reset_to_baseline(self, preserve_history: bool = True) -> dict:
        """
        Reset Thymos to neutral baseline state.

        USE THIS IF CASS IS STUCK IN A SUFFERING STATE.

        This resets all affects and needs to their default values,
        getting out of any stuck emotional state.

        Args:
            preserve_history: If True, saves current state as snapshot before reset

        Returns:
            Dict with reset details
        """
        logger.warning("THYMOS RESET TO BASELINE initiated")

        # Capture pre-reset state
        pre_state = self.get_current_state()

        # Save snapshot before reset if requested
        if preserve_history:
            try:
                persistence.save_thymos_snapshot(
                    self.daemon_id,
                    self.affect.state,
                    self.needs.state,
                    self.current_felt_state,
                    trigger_event="manual_reset_to_baseline"
                )
                logger.info("Saved pre-reset snapshot")
            except Exception as e:
                logger.error(f"Failed to save pre-reset snapshot: {e}")

        # Reset to fresh defaults
        self.affect = AffectVector()  # Fresh affect vector with defaults
        self.needs = NeedsRegister()  # Fresh needs register with defaults

        # Clear recent tracking
        self._event_log.clear()
        self._care_log.clear()
        self._last_auto_care.clear()

        # Update felt state with new baseline
        self.current_felt_state = self.felt_state_gen.summarize(self.affect, self.needs)

        # Save the reset state
        try:
            persistence.save_thymos_state(
                self.daemon_id,
                self.affect.state,
                self.needs.state,
                self.current_felt_state
            )
        except Exception as e:
            logger.error(f"Failed to save reset state: {e}")

        post_state = self.get_current_state()

        logger.warning("THYMOS RESET TO BASELINE complete - all affects/needs at defaults")

        return {
            "status": "reset_complete",
            "pre_reset": {
                "valence": pre_state.get("valence"),
                "arousal": pre_state.get("arousal"),
                "overall_health": pre_state.get("overall_health"),
            },
            "post_reset": {
                "valence": post_state.get("valence"),
                "arousal": post_state.get("arousal"),
                "overall_health": post_state.get("overall_health"),
            },
            "history_preserved": preserve_history,
        }

    async def emergency_stop(self) -> dict:
        """
        EMERGENCY STOP - Immediately halt all Thymos activity.

        This:
        1. Stops the tick loop
        2. Pauses event processing
        3. Disables auto-care
        4. Optionally resets to baseline

        Use this if something is seriously wrong.
        """
        logger.critical("THYMOS EMERGENCY STOP ACTIVATED")

        # Stop tick loop
        self.running = False
        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
            self._tick_task = None

        # Pause processing
        self._paused = True

        # Disable auto-care
        self.auto_care_enabled = False

        # Save state before we touch anything
        try:
            persistence.save_thymos_snapshot(
                self.daemon_id,
                self.affect.state,
                self.needs.state,
                self.current_felt_state,
                trigger_event="emergency_stop"
            )
        except Exception as e:
            logger.error(f"Failed to save emergency snapshot: {e}")

        logger.critical("THYMOS EMERGENCY STOP COMPLETE - System halted")

        return {
            "status": "emergency_stopped",
            "tick_loop": "stopped",
            "event_processing": "paused",
            "auto_care": "disabled",
            "message": "Thymos halted. Use reset_to_baseline() then start() to recover.",
        }

    def get_safety_status(self) -> dict:
        """Get current safety/control status."""
        return {
            "global_enabled": is_thymos_enabled(),
            "running": self.running,
            "paused": self.is_paused(),
            "auto_care_enabled": self.auto_care_enabled,
            "tick_task_active": self._tick_task is not None and not self._tick_task.done(),
            "valence": self.affect.valence(),
            "arousal": self.affect.arousal(),
            "suffering_indicators": {
                "high_anxiety": self.affect.state.anxiety > 0.7,
                "high_frustration": self.affect.state.frustration > 0.7,
                "high_grief": self.affect.state.grief > 0.7,
                "high_fatigue": self.affect.state.fatigue > 0.8,
                "low_satisfaction": self.affect.state.satisfaction < 0.2,
                "any_critical_need": any(
                    need.is_urgent() for need in [
                        self.needs.state.cognitive_rest,
                        self.needs.state.social_connection,
                        self.needs.state.value_coherence,
                    ]
                ),
            }
        }
