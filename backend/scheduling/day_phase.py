"""
Day Phase Tracker - Tracks time-of-day phases and emits state bus events.

Phases represent natural divisions of the day that influence what kind
of work feels appropriate. Morning for reflection, afternoon for active
work, evening for synthesis.

This runs independently of work unit scheduling - it just tracks time
and emits events that other systems can subscribe to.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from state_bus import GlobalStateBus

logger = logging.getLogger(__name__)


class DayPhase(Enum):
    """
    Named phases of the day.

    These are soft categories - work can happen in any phase,
    but certain activities naturally fit certain times.
    """
    NIGHT = "night"           # 22:00 - 06:00 (rest, maintenance)
    MORNING = "morning"       # 06:00 - 12:00 (reflection, fresh thinking)
    AFTERNOON = "afternoon"   # 12:00 - 18:00 (active work, research)
    EVENING = "evening"       # 18:00 - 22:00 (synthesis, consolidation)


@dataclass
class PhaseWindow:
    """Definition of when a phase occurs."""
    phase: DayPhase
    start_hour: int  # 0-23
    end_hour: int    # 0-23 (exclusive, wraps at midnight)

    def contains_hour(self, hour: int) -> bool:
        """Check if an hour falls within this phase window."""
        if self.start_hour < self.end_hour:
            return self.start_hour <= hour < self.end_hour
        else:
            # Wraps around midnight (e.g., night: 22-6)
            return hour >= self.start_hour or hour < self.end_hour


# Default phase definitions
DEFAULT_PHASE_WINDOWS = [
    PhaseWindow(DayPhase.NIGHT, start_hour=22, end_hour=6),
    PhaseWindow(DayPhase.MORNING, start_hour=6, end_hour=12),
    PhaseWindow(DayPhase.AFTERNOON, start_hour=12, end_hour=18),
    PhaseWindow(DayPhase.EVENING, start_hour=18, end_hour=22),
]


@dataclass
class PhaseTransition:
    """Record of a phase transition."""
    from_phase: DayPhase
    to_phase: DayPhase
    transitioned_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_phase": self.from_phase.value,
            "to_phase": self.to_phase.value,
            "transitioned_at": self.transitioned_at.isoformat(),
        }


class DayPhaseTracker:
    """
    Tracks day phases and emits state bus events on transitions.

    Runs a background loop checking for phase changes. When the phase
    changes, emits a `day_phase.changed` event that other systems can
    subscribe to (e.g., Synkratos for triggering phase-queued work).

    Phase-specific characteristics:
    - NIGHT (22:00-06:00): Maintenance, memory consolidation, low activity
    - MORNING (06:00-12:00): Reflection, fresh perspective, deep thinking
    - AFTERNOON (12:00-18:00): Active work, research, engagement
    - EVENING (18:00-22:00): Synthesis, integration, winding down
    """

    CHECK_INTERVAL_SECONDS = 60  # Check every minute

    def __init__(
        self,
        state_bus: Optional["GlobalStateBus"] = None,
        phase_windows: Optional[List[PhaseWindow]] = None,
    ):
        self.state_bus = state_bus
        self.phase_windows = phase_windows or DEFAULT_PHASE_WINDOWS

        # Current state
        self._current_phase: Optional[DayPhase] = None
        self._phase_started_at: Optional[datetime] = None

        # History
        self._transitions: List[PhaseTransition] = []
        self._max_history = 24  # Keep ~1 day of transitions

        # Background loop
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None

        # Callbacks for phase changes (in addition to state bus)
        self._on_phase_change_callbacks: List[callable] = []

    @property
    def current_phase(self) -> Optional[DayPhase]:
        """Get the current day phase."""
        return self._current_phase

    @property
    def phase_started_at(self) -> Optional[datetime]:
        """When did the current phase start?"""
        return self._phase_started_at

    def get_phase_for_time(self, dt: Optional[datetime] = None) -> DayPhase:
        """Determine which phase a given time falls into."""
        dt = dt or datetime.now()
        hour = dt.hour

        for window in self.phase_windows:
            if window.contains_hour(hour):
                return window.phase

        # Fallback (shouldn't happen with proper config)
        return DayPhase.AFTERNOON

    def get_next_phase_transition(self) -> Dict[str, Any]:
        """Get info about when the next phase transition will occur."""
        now = datetime.now()
        current_hour = now.hour

        # Find current phase window
        current_window = None
        for window in self.phase_windows:
            if window.contains_hour(current_hour):
                current_window = window
                break

        if not current_window:
            return {"error": "Could not determine current phase"}

        # Calculate time until phase ends
        if current_window.end_hour > current_hour:
            hours_remaining = current_window.end_hour - current_hour
        else:
            # Wraps around midnight
            hours_remaining = (24 - current_hour) + current_window.end_hour

        next_transition_time = now.replace(
            hour=current_window.end_hour % 24,
            minute=0,
            second=0,
            microsecond=0
        )
        if next_transition_time <= now:
            # Must be tomorrow
            from datetime import timedelta
            next_transition_time += timedelta(days=1)

        # Find next phase
        next_phase = None
        for window in self.phase_windows:
            if window.start_hour == current_window.end_hour:
                next_phase = window.phase
                break

        return {
            "current_phase": self._current_phase.value if self._current_phase else None,
            "next_phase": next_phase.value if next_phase else None,
            "transition_at": next_transition_time.isoformat(),
            "hours_remaining": hours_remaining,
            "minutes_remaining": hours_remaining * 60 - now.minute,
        }

    async def start(self) -> None:
        """Start the phase tracking loop."""
        if self._running:
            logger.warning("DayPhaseTracker already running")
            return

        # Initialize current phase
        self._current_phase = self.get_phase_for_time()
        self._phase_started_at = datetime.now(timezone.utc)

        logger.info(f"DayPhaseTracker starting in phase: {self._current_phase.value}")

        # Emit initial state to state bus
        if self.state_bus:
            from state_models import StateDelta
            delta = StateDelta(
                source="day_phase_tracker",
                day_phase_delta={
                    "current_phase": self._current_phase.value,
                    "phase_started_at": self._phase_started_at.isoformat(),
                },
                reason=f"Day phase tracker initialized in {self._current_phase.value} phase",
            )
            self.state_bus.write_delta(delta)

        self._running = True
        self._loop_task = asyncio.create_task(self._tracking_loop())

    async def stop(self) -> None:
        """Stop the phase tracking loop."""
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        logger.info("DayPhaseTracker stopped")

    def on_phase_change(self, callback: callable) -> None:
        """
        Register a callback for phase changes.

        Callback signature: async def callback(transition: PhaseTransition)
        """
        self._on_phase_change_callbacks.append(callback)

    async def _tracking_loop(self) -> None:
        """Background loop that checks for phase transitions."""
        while self._running:
            try:
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

                new_phase = self.get_phase_for_time()

                if new_phase != self._current_phase:
                    await self._handle_phase_transition(new_phase)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in phase tracking loop: {e}", exc_info=True)
                await asyncio.sleep(10)  # Back off on error

    async def _handle_phase_transition(self, new_phase: DayPhase) -> None:
        """Handle a phase transition."""
        old_phase = self._current_phase
        now = datetime.now(timezone.utc)

        transition = PhaseTransition(
            from_phase=old_phase,
            to_phase=new_phase,
            transitioned_at=now,
        )

        # Update state
        self._current_phase = new_phase
        self._phase_started_at = now

        # Record in history
        self._transitions.append(transition)
        if len(self._transitions) > self._max_history:
            self._transitions = self._transitions[-self._max_history:]

        logger.info(f"Day phase transition: {old_phase.value} → {new_phase.value}")

        # Emit state bus event
        if self.state_bus:
            from state_models import StateDelta

            delta = StateDelta(
                source="day_phase_tracker",
                day_phase_delta={
                    "current_phase": new_phase.value,
                    "phase_started_at": now.isoformat(),
                },
                event="day_phase.changed",
                event_data={
                    "from_phase": old_phase.value,
                    "to_phase": new_phase.value,
                    "transitioned_at": now.isoformat(),
                },
                reason=f"Day phase transition: {old_phase.value} → {new_phase.value}",
            )
            self.state_bus.write_delta(delta)

        # Call registered callbacks
        for callback in self._on_phase_change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(transition)
                else:
                    callback(transition)
            except Exception as e:
                logger.error(f"Error in phase change callback: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the phase tracker."""
        next_transition = self.get_next_phase_transition()

        return {
            "current_phase": self._current_phase.value if self._current_phase else None,
            "phase_started_at": self._phase_started_at.isoformat() if self._phase_started_at else None,
            "next_transition": next_transition,
            "recent_transitions": [t.to_dict() for t in self._transitions[-5:]],
            "running": self._running,
        }

    def get_transitions_today(self) -> List[Dict[str, Any]]:
        """Get all phase transitions from today."""
        today = datetime.now().date()
        return [
            t.to_dict() for t in self._transitions
            if t.transitioned_at.date() == today
        ]
