"""
Autonomous Scheduler - Cass's self-directed work orchestration.

This bridges Cass's decision engine with Synkratos execution.
Cass plans her day once (typically in the morning), queueing work
for each phase. Phase transitions trigger queued work execution.

Key distinction: Synkratos handles the mechanics of execution.
This module handles Cass's agency in choosing what to execute.

Architecture:
- plan_day(): Called once per day (morning or on startup)
- Decision engine plans work for all phases in one LLM call
- Work gets queued to PhaseQueueManager
- Phase transitions dispatch queued work
- No constant polling - efficient token usage
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from scheduler.core import Synkratos, ScheduledTask, TaskCategory, TaskPriority
    from state_bus import GlobalStateBus
    from state_models import StateDelta
    from .phase_queue import PhaseQueueManager
    from .day_phase import DayPhase

from .decision_engine import SchedulingDecisionEngine
from .work_unit import WorkUnit, WorkStatus
from .work_summary_store import (
    WorkSummaryStore,
    WorkSummary,
    ActionSummary,
    generate_slug,
)
from .day_phase import DayPhase

logger = logging.getLogger(__name__)


class AutonomousScheduler:
    """
    Cass's autonomous work scheduler.

    Plans the day's work once (in the morning or on startup), then
    phase transitions trigger execution. No constant polling.

    This is about Cass's agency in planning her own day.
    """

    # Whether to plan remaining phases on startup (if not morning)
    PLAN_ON_STARTUP = True

    # When True, skip LLM-based planning - Grimoire spells handle work queuing
    # via QUEUE statements in phase routine spells (morning_routine, phase_*, etc.)
    USE_SPELL_PLANNING = True

    def __init__(
        self,
        synkratos: "Synkratos",
        decision_engine: SchedulingDecisionEngine,
        state_bus: Optional["GlobalStateBus"] = None,
        daemon_id: str = "cass",
        action_registry: Optional[Any] = None,
    ):
        self.synkratos = synkratos
        self.decision_engine = decision_engine
        self.state_bus = state_bus
        self._daemon_id = daemon_id
        self._action_registry = action_registry

        # Phase queue for deferred work
        self._phase_queue: Optional["PhaseQueueManager"] = None

        # Work summary store for persistent summaries
        self._summary_store = WorkSummaryStore(daemon_id)

        # Current autonomous work
        self._current_work: Optional[WorkUnit] = None
        self._work_started_at: Optional[datetime] = None

        # State
        self._running = False
        self._enabled = True  # Feature flag

        # Daily planning state
        self._last_plan_date: Optional[datetime] = None
        self._todays_plan: Dict[str, List[WorkUnit]] = {}  # phase -> work units

        # History for state bus queries
        self._work_history: List[Dict[str, Any]] = []
        self._max_history = 50

    def set_phase_queue(self, phase_queue: "PhaseQueueManager") -> None:
        """Set the phase queue manager for deferred work scheduling."""
        from .phase_queue import PhaseQueueManager
        self._phase_queue = phase_queue
        logger.info("Phase queue manager connected to autonomous scheduler")

    def queue_for_phase(
        self,
        work_unit: WorkUnit,
        target_phase: "DayPhase",
        priority: int = 1,
    ) -> bool:
        """
        Queue a work unit for a specific day phase.

        Instead of executing immediately, the work will be held until
        the target phase begins, then dispatched to Synkratos.

        Args:
            work_unit: The work to queue
            target_phase: Which phase to execute in (morning/afternoon/evening/night)
            priority: Execution priority within the phase (lower = higher priority)

        Returns:
            True if queued successfully, False if no phase queue or queue full
        """
        if not self._phase_queue:
            logger.warning("Cannot queue for phase - no phase queue manager set")
            return False

        return self._phase_queue.queue_for_phase(work_unit, target_phase, priority)

    def get_best_phase_for_work(self, work_unit: WorkUnit) -> Optional["DayPhase"]:
        """
        Determine the best phase for a work unit based on its time preferences.

        Returns the phase that best matches the work unit's preferred time windows,
        or None if immediate execution is preferred.
        """
        from .day_phase import DayPhase

        if not work_unit.preferred_time_windows:
            return None  # No preference, execute immediately

        # Map hours to phases
        phase_hours = {
            DayPhase.NIGHT: range(22, 24),  # 22-23 (plus 0-5)
            DayPhase.MORNING: range(6, 12),
            DayPhase.AFTERNOON: range(12, 18),
            DayPhase.EVENING: range(18, 22),
        }

        # Score each phase by how well it matches preferences
        best_phase = None
        best_score = 0.0

        for phase, hours in phase_hours.items():
            phase_score = 0.0
            for window in work_unit.preferred_time_windows:
                # Check overlap between window and phase hours
                for hour in hours:
                    if window.start_hour <= hour < window.end_hour:
                        phase_score += window.preference_weight

            if phase_score > best_score:
                best_score = phase_score
                best_phase = phase

        return best_phase if best_score > 0 else None

    async def start(self) -> None:
        """Start the autonomous scheduler."""
        if self._running:
            logger.warning("Autonomous scheduler already running")
            return

        if not self._enabled:
            logger.info("Autonomous scheduling disabled by feature flag")
            return

        self._running = True

        if self.USE_SPELL_PLANNING:
            logger.info(
                "Autonomous scheduler started (spell-based mode) - "
                "Grimoire phase spells will queue work via QUEUE statements"
            )
        else:
            logger.info("Autonomous scheduler started (LLM plan-based mode)")

            # Plan the day if enabled and not already planned today
            # Brief delay to allow DayPhaseTracker to emit initial state to state bus
            if self.PLAN_ON_STARTUP:
                await asyncio.sleep(0.5)  # Allow phase tracker to initialize state
                await self._maybe_plan_day()

    async def stop(self) -> None:
        """Stop the autonomous scheduler."""
        self._running = False
        logger.info("Autonomous scheduler stopped")

    def enable(self) -> None:
        """Enable autonomous scheduling."""
        self._enabled = True
        logger.info("Autonomous scheduling enabled")

    def disable(self) -> None:
        """Disable autonomous scheduling."""
        self._enabled = False
        logger.info("Autonomous scheduling disabled")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def current_work(self) -> Optional[WorkUnit]:
        """Get the current autonomous work unit."""
        return self._current_work

    @property
    def is_working(self) -> bool:
        """Is Cass currently doing autonomous work?"""
        return self._current_work is not None

    @property
    def summary_store(self) -> WorkSummaryStore:
        """Get the work summary store for querying work history."""
        return self._summary_store

    async def _maybe_plan_day(self) -> None:
        """Plan the day if we haven't already planned today."""
        # When spell-based planning is enabled, Grimoire handles work queuing
        # via phase routine spells (morning_routine.spell, etc.)
        if self.USE_SPELL_PLANNING:
            logger.debug("Spell-based planning enabled - skipping LLM plan_day()")
            return

        today = datetime.now().date()

        # Check in-memory flag first (fast path for same-process restarts)
        if self._last_plan_date and self._last_plan_date.date() == today:
            logger.info("Day already planned (in-memory), skipping")
            return

        # Check persistent store for existing work summaries today
        # This handles restarts - if we've already planned, don't re-plan
        existing_work = self._summary_store.get_by_date(today)
        if existing_work:
            logger.info(
                f"Day already planned ({len(existing_work)} work items in DB) - skipping replan"
            )
            self._last_plan_date = datetime.now()  # Set in-memory flag
            return

        # Check budget before planning
        if self.synkratos.budget.get_total_remaining() < 0.10:
            logger.warning("Insufficient budget for daily planning")
            return

        await self.plan_day()

    async def plan_day(self) -> Dict[str, List[WorkUnit]]:
        """
        Plan the full day's autonomous work.

        Calls the decision engine once to plan work for all remaining phases,
        then queues work to the PhaseQueueManager.

        Returns:
            Dict mapping phase names to planned work units
        """
        logger.info("Planning the day's autonomous work...")

        # Get current phase to know which phases remain
        current_phase = DayPhase.AFTERNOON  # Default
        if self.state_bus:
            state = self.state_bus.read_state()
            if state.day_phase and state.day_phase.current_phase:
                try:
                    current_phase = DayPhase(state.day_phase.current_phase)
                except ValueError:
                    pass

        # Determine which phases to plan for
        phase_order = [DayPhase.MORNING, DayPhase.AFTERNOON, DayPhase.EVENING, DayPhase.NIGHT]
        current_idx = phase_order.index(current_phase)
        remaining_phases = phase_order[current_idx:]

        logger.info(f"Current phase: {current_phase.value}, planning for: {[p.value for p in remaining_phases]}")

        # Ask decision engine to plan for remaining phases
        plan = await self.decision_engine.plan_day(remaining_phases)

        if not plan:
            logger.warning("Decision engine returned no plan")
            plan = {}

        # Ensure morning always includes news check (world awareness)
        if DayPhase.MORNING in remaining_phases:
            from .templates import WORK_TEMPLATES
            morning_work = plan.get(DayPhase.MORNING, [])
            has_news = any(w.template_id == "world_check" for w in morning_work)
            if not has_news:
                news_template = WORK_TEMPLATES.get("world_check")
                if news_template:
                    news_work = news_template.instantiate(
                        motivation="Morning world awareness - staying connected to events"
                    )
                    # Insert at beginning of morning work
                    morning_work.insert(0, news_work)
                    plan[DayPhase.MORNING] = morning_work
                    logger.info("Added morning news check to plan")

        # Queue work to phase queue
        self._todays_plan = {}
        for phase, work_units in plan.items():
            self._todays_plan[phase.value] = work_units

            for i, work_unit in enumerate(work_units):
                if self._phase_queue:
                    self._phase_queue.queue_for_phase(
                        work_unit=work_unit,
                        target_phase=phase,
                        priority=i + 1,  # Order matters
                    )

        self._last_plan_date = datetime.now()

        # Emit planning complete event
        if self.state_bus:
            from state_models import StateDelta

            delta = StateDelta(
                source="autonomous_scheduler",
                event="day.planned",
                event_data={
                    "phases_planned": [p.value for p in plan.keys()],
                    "work_count": sum(len(units) for units in plan.values()),
                    "plan_summary": {
                        phase.value: [w.name for w in units]
                        for phase, units in plan.items()
                    },
                },
                reason="Cass planned her day's autonomous work",
            )
            self.state_bus.write_delta(delta)

        logger.info(
            f"Day planned: {sum(len(units) for units in plan.values())} work units "
            f"across {len(plan)} phases"
        )

        # Dispatch work for the current phase immediately
        # (since we won't get a phase transition event for it)
        if self._phase_queue and current_phase in plan:
            dispatched = await self._phase_queue.dispatch_current_phase(current_phase)
            if dispatched > 0:
                logger.info(
                    f"Dispatched {dispatched} work units for current phase ({current_phase.value})"
                )

        return {phase.value: units for phase, units in plan.items()}

    async def on_phase_changed(self, transition) -> None:
        """
        Handle phase transition - potentially trigger morning planning.

        Called by DayPhaseTracker when the phase changes.
        """
        if transition.to_phase == DayPhase.MORNING:
            if self.USE_SPELL_PLANNING:
                # Grimoire spells handle work queuing via phase events
                logger.info(
                    "Morning phase started - spell-based planning enabled, "
                    "Grimoire will queue work via morning_routine.spell"
                )
            else:
                # Legacy LLM-based planning
                logger.info("Morning phase started - planning the day")
                await self.plan_day()

    def get_todays_plan(self) -> Dict[str, List[Dict]]:
        """Get today's planned work by phase."""
        return {
            phase: [w.to_dict() for w in units]
            for phase, units in self._todays_plan.items()
        }

    # The direct execute path (_start_work -> _execute_work -> Synkratos
    # submit, with _run_session / _run_action_sequence / _complete_work) was
    # cut in #62: nothing called _start_work. Queued work runs through the
    # phase queue. current_work / work history stay for the admin views and
    # are empty, as they always were. (Kept on attic/stabilization.)

    def get_work_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent work history."""
        return self._work_history[:limit]

    def get_daily_summary(self) -> Dict[str, Any]:
        """Get summary of today's autonomous work."""
        today = datetime.now().date()

        today_work = [
            w for w in self._work_history
            if w.get("completed_at") and
            datetime.fromisoformat(w["completed_at"]).date() == today
        ]

        by_category = {}
        for w in today_work:
            cat = w.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = {"count": 0, "total_minutes": 0}
            by_category[cat]["count"] += 1
            by_category[cat]["total_minutes"] += w.get("duration_minutes") or 0

        return {
            "date": today.isoformat(),
            "total_work_units": len(today_work),
            "by_category": by_category,
            "current_work": self._current_work.to_dict() if self._current_work else None,
        }
