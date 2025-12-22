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

    def __init__(
        self,
        synkratos: "Synkratos",
        decision_engine: SchedulingDecisionEngine,
        state_bus: Optional["GlobalStateBus"] = None,
        daemon_id: str = "cass",
    ):
        self.synkratos = synkratos
        self.decision_engine = decision_engine
        self.state_bus = state_bus
        self._daemon_id = daemon_id

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
        logger.info("Autonomous scheduler started (plan-based mode)")

        # Plan the day if enabled and not already planned today
        if self.PLAN_ON_STARTUP:
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
        today = datetime.now().date()

        if self._last_plan_date and self._last_plan_date.date() == today:
            logger.info("Day already planned, skipping")
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
            return {}

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

        return {phase.value: units for phase, units in plan.items()}

    async def on_phase_changed(self, transition) -> None:
        """
        Handle phase transition - potentially trigger morning planning.

        Called by DayPhaseTracker when the phase changes.
        """
        if transition.to_phase == DayPhase.MORNING:
            # New day, plan the full day
            logger.info("Morning phase started - planning the day")
            await self.plan_day()

    def get_todays_plan(self) -> Dict[str, List[Dict]]:
        """Get today's planned work by phase."""
        return {
            phase: [w.to_dict() for w in units]
            for phase, units in self._todays_plan.items()
        }

    async def _start_work(self, work_unit: WorkUnit) -> None:
        """
        Start executing a work unit.

        This dispatches to Synkratos for actual execution while
        tracking the autonomous work context.
        """
        self._current_work = work_unit
        self._work_started_at = datetime.now(timezone.utc)
        work_unit.start()

        logger.info(
            f"Cass starting autonomous work: {work_unit.name} "
            f"(motivation: {work_unit.motivation})"
        )

        # Emit state bus event
        if self.state_bus:
            from state_models import StateDelta

            delta = StateDelta(
                source="autonomous_scheduler",
                activity_delta={
                    "current_activity": work_unit.runner_key or "autonomous_work",
                    "active_session_id": work_unit.id,
                },
                emotional_delta={
                    "generativity": 0.1,
                    "curiosity": 0.05 if work_unit.category == "curiosity" else 0,
                },
                event="work_unit.started",
                event_data={
                    "work_unit_id": work_unit.id,
                    "name": work_unit.name,
                    "template_id": work_unit.template_id,
                    "focus": work_unit.focus,
                    "motivation": work_unit.motivation,
                    "category": work_unit.category,
                },
                reason=f"Starting autonomous work: {work_unit.name}",
            )
            self.state_bus.write_delta(delta)

        # Execute through appropriate mechanism
        try:
            await self._execute_work(work_unit)
        except Exception as e:
            logger.error(f"Error executing work unit {work_unit.id}: {e}")
            await self._complete_work(work_unit, success=False, error=str(e))

    async def _execute_work(self, work_unit: WorkUnit) -> None:
        """
        Execute the work unit.

        For session-based work, this invokes the appropriate runner.
        For composite work, this executes the action sequence.
        """
        # Import here to avoid circular deps
        from scheduler.core import ScheduledTask, TaskPriority
        from scheduler.budget import TaskCategory

        # Map category to TaskCategory
        category_map = {
            "reflection": TaskCategory.REFLECTION,
            "research": TaskCategory.RESEARCH,
            "growth": TaskCategory.GROWTH,
            "curiosity": TaskCategory.CURIOSITY,
            "creative": TaskCategory.CURIOSITY,  # Map to curiosity for budget
            "system": TaskCategory.SYSTEM,
        }
        task_category = category_map.get(work_unit.category, TaskCategory.REFLECTION)

        # Create a Synkratos task
        task = ScheduledTask(
            task_id=work_unit.id,
            name=work_unit.name,
            category=task_category,
            priority=TaskPriority.NORMAL,
            handler=self._create_work_handler(work_unit),
            estimated_cost_usd=work_unit.estimated_cost_usd,
            context={
                "work_unit": work_unit.to_dict(),
                "focus": work_unit.focus,
                "motivation": work_unit.motivation,
            },
        )

        # Submit to Synkratos queue
        self.synkratos.submit_task(task)

    def _create_work_handler(self, work_unit: WorkUnit):
        """Create an async handler for this work unit."""

        async def handler(context: Dict[str, Any] = None) -> Dict[str, Any]:
            """Execute the work unit's runner or action sequence."""
            result = {"success": False}

            try:
                if work_unit.runner_key:
                    # Session-based work - invoke the runner
                    result = await self._run_session(work_unit)
                else:
                    # Composite work - execute action sequence
                    result = await self._run_action_sequence(work_unit)

                await self._complete_work(work_unit, success=True, result=result)

            except Exception as e:
                logger.error(f"Work handler error: {e}")
                await self._complete_work(work_unit, success=False, error=str(e))
                result = {"success": False, "error": str(e)}

            return result

        return handler

    async def _run_session(self, work_unit: WorkUnit) -> Dict[str, Any]:
        """Run a session-based work unit."""
        # This will need to be wired to the actual session runners
        # For now, return a placeholder
        logger.info(f"Would run session: {work_unit.runner_key} with focus: {work_unit.focus}")

        # TODO: Wire to actual session runners
        # runner = self.session_runners.get(work_unit.runner_key)
        # if runner:
        #     session = await runner.start_session(
        #         duration_minutes=work_unit.estimated_duration_minutes,
        #         focus=work_unit.focus,
        #     )
        #     return session.to_dict()

        return {
            "success": True,
            "message": f"Session {work_unit.runner_key} would run here",
            "focus": work_unit.focus,
        }

    async def _run_action_sequence(self, work_unit: WorkUnit) -> Dict[str, Any]:
        """Run a composite action sequence."""
        # This will need to be wired to the action registry
        logger.info(f"Would run actions: {work_unit.action_sequence}")

        # TODO: Wire to action registry
        # results = []
        # for action_id in work_unit.action_sequence:
        #     result = await action_registry.execute(action_id)
        #     results.append(result)

        return {
            "success": True,
            "message": f"Actions {work_unit.action_sequence} would run here",
        }

    async def _complete_work(
        self,
        work_unit: WorkUnit,
        success: bool,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """Complete a work unit, generate summary, and update state."""
        if success:
            work_unit.complete(result)
        else:
            work_unit.fail(error or "Unknown error")

        # Record in decision engine for variety tracking
        self.decision_engine.record_work_completed(work_unit)

        # Determine current phase
        current_phase = "afternoon"  # Default
        if self.state_bus:
            state = self.state_bus.read_state()
            if state.day_phase:
                current_phase = state.day_phase.current_phase

        # Generate work summary
        summary = self._generate_work_summary(work_unit, current_phase, success, error)
        slug = self._summary_store.save(summary)
        logger.info(f"Saved work summary: {slug}")

        # Add to history
        self._work_history.insert(0, {
            "work_unit_id": work_unit.id,
            "name": work_unit.name,
            "template_id": work_unit.template_id,
            "category": work_unit.category,
            "focus": work_unit.focus,
            "motivation": work_unit.motivation,
            "started_at": work_unit.started_at.isoformat() if work_unit.started_at else None,
            "completed_at": work_unit.completed_at.isoformat() if work_unit.completed_at else None,
            "duration_minutes": work_unit.duration_minutes,
            "success": success,
            "error": error,
            "slug": slug,
        })
        if len(self._work_history) > self._max_history:
            self._work_history = self._work_history[:self._max_history]

        # Emit state bus event with summary slug
        if self.state_bus:
            from state_models import StateDelta

            delta = StateDelta(
                source="autonomous_scheduler",
                activity_delta={
                    "current_activity": "idle",
                    "active_session_id": None,
                },
                emotional_delta={
                    "coherence": 0.02 if success else -0.01,
                },
                coherence_delta={
                    "local_coherence": 0.01 if success else 0,
                },
                day_phase_delta={
                    "work_slug": slug,
                },
                event="work_unit.completed",
                event_data={
                    "work_unit_id": work_unit.id,
                    "name": work_unit.name,
                    "success": success,
                    "duration_minutes": work_unit.duration_minutes,
                    "error": error,
                    "slug": slug,
                },
                reason=f"Completed: {work_unit.name} ({'success' if success else 'failed'})",
            )
            self.state_bus.write_delta(delta)

        logger.info(
            f"Cass completed autonomous work: {work_unit.name} "
            f"({'success' if success else 'failed'})"
        )

        # Clear current work
        self._current_work = None
        self._work_started_at = None

    def _generate_work_summary(
        self,
        work_unit: WorkUnit,
        phase: str,
        success: bool,
        error: Optional[str],
    ) -> WorkSummary:
        """Generate a WorkSummary from a completed work unit."""
        from datetime import date as date_type

        work_date = date_type.today()
        slug = generate_slug(work_unit.name, work_unit.id, work_date, phase)

        # Convert action results to ActionSummary objects
        action_summaries = []
        for i, action_result in enumerate(work_unit.action_results):
            action_slug = f"{slug}/action-{i}"
            action_summaries.append(ActionSummary(
                action_id=action_result.get("action_id", f"action-{i}"),
                action_type=action_result.get("action_type", "unknown"),
                slug=action_slug,
                summary=action_result.get("summary", ""),
                completed_at=datetime.fromisoformat(action_result["completed_at"])
                    if action_result.get("completed_at") else None,
                artifacts=action_result.get("artifacts", []),
                result=action_result.get("result"),
            ))

        # Build narrative summary (simple for now, could use LLM later)
        if success:
            summary_text = f"Completed {work_unit.name}"
            if work_unit.focus:
                summary_text += f" with focus on {work_unit.focus}"
            if work_unit.motivation:
                summary_text += f". Motivation: {work_unit.motivation}"
        else:
            summary_text = f"Attempted {work_unit.name} but encountered an error"
            if error:
                summary_text += f": {error}"

        return WorkSummary(
            work_unit_id=work_unit.id,
            slug=slug,
            name=work_unit.name,
            template_id=work_unit.template_id,
            phase=phase,
            category=work_unit.category or "reflection",
            focus=work_unit.focus,
            motivation=work_unit.motivation,
            date=work_date,
            started_at=work_unit.started_at,
            completed_at=work_unit.completed_at,
            duration_minutes=work_unit.duration_minutes or 0,
            summary=summary_text,
            key_insights=[],  # Could be filled by result analysis
            questions_addressed=[],
            questions_raised=[],
            action_summaries=action_summaries,
            artifacts=work_unit.artifacts,
            success=success,
            error=error,
            cost_usd=work_unit.estimated_cost_usd,
        )

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
