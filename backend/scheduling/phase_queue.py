"""
Phase-Based Work Queues.

Work units can be queued for specific day phases. When a phase begins,
Synkratos triggers the queued work for that phase.

This enables patterns like:
- Queue reflection work for morning
- Queue synthesis work for evening
- Queue maintenance tasks for night

The autonomous scheduler can decide what work to do AND when - queueing
work for the appropriate phase rather than executing immediately.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from scheduler.core import Synkratos, ScheduledTask
    from state_bus import GlobalStateBus
    from .work_summary_store import WorkSummaryStore

from .day_phase import DayPhase, PhaseTransition
from .work_unit import WorkUnit
from .work_summary_store import WorkSummary, ActionSummary, generate_slug

logger = logging.getLogger(__name__)


@dataclass
class QueuedWorkUnit:
    """A work unit queued for a specific phase."""
    work_unit: WorkUnit
    target_phase: DayPhase
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    priority: int = 1  # Lower = higher priority

    def to_dict(self) -> Dict[str, Any]:
        return {
            "work_unit": self.work_unit.to_dict(),
            "target_phase": self.target_phase.value,
            "queued_at": self.queued_at.isoformat(),
            "priority": self.priority,
        }


class PhaseQueueManager:
    """
    Manages work units queued for specific day phases.

    When the autonomous scheduler decides Cass should do work that fits
    a particular time of day, it can queue that work for the appropriate
    phase rather than executing immediately.

    On phase transitions, queued work is dispatched to Synkratos for
    execution in order of priority.
    """

    def __init__(
        self,
        synkratos: Optional["Synkratos"] = None,
        state_bus: Optional["GlobalStateBus"] = None,
        max_per_phase: int = 5,  # Max work units queued per phase
        summary_store: Optional["WorkSummaryStore"] = None,
        daemon_id: str = "cass",
        action_registry: Optional[Any] = None,
    ):
        self.synkratos = synkratos
        self.state_bus = state_bus
        self.max_per_phase = max_per_phase
        self._summary_store = summary_store
        self._daemon_id = daemon_id
        self._action_registry = action_registry

        # Queues for each phase
        self._phase_queues: Dict[DayPhase, List[QueuedWorkUnit]] = {
            phase: [] for phase in DayPhase
        }

        # History of dispatched work
        self._dispatch_history: List[Dict[str, Any]] = []
        self._max_history = 50

    def set_summary_store(self, store: "WorkSummaryStore") -> None:
        """Set the summary store after initialization."""
        self._summary_store = store

    def set_action_registry(self, action_registry: Any) -> None:
        """Set the action registry after initialization."""
        self._action_registry = action_registry

    def set_synkratos(self, synkratos: "Synkratos") -> None:
        """Set the Synkratos reference after initialization."""
        self.synkratos = synkratos

    def queue_for_phase(
        self,
        work_unit: WorkUnit,
        target_phase: DayPhase,
        priority: int = 1,
    ) -> bool:
        """
        Queue a work unit for a specific phase.

        Args:
            work_unit: The work to queue
            target_phase: Which phase to execute in
            priority: Execution priority (lower = higher priority)

        Returns:
            True if queued successfully, False if queue is full
        """
        queue = self._phase_queues[target_phase]

        if len(queue) >= self.max_per_phase:
            logger.warning(
                f"Phase queue {target_phase.value} full, rejecting {work_unit.name}"
            )
            return False

        queued = QueuedWorkUnit(
            work_unit=work_unit,
            target_phase=target_phase,
            priority=priority,
        )

        queue.append(queued)
        queue.sort(key=lambda q: q.priority)

        logger.info(
            f"Queued '{work_unit.name}' for {target_phase.value} "
            f"(priority {priority}, {len(queue)} in queue)"
        )

        # Emit state bus event
        if self.state_bus:
            from state_models import StateDelta

            delta = StateDelta(
                source="phase_queue",
                event="work_unit.queued_for_phase",
                event_data={
                    "work_unit_id": work_unit.id,
                    "work_unit_name": work_unit.name,
                    "target_phase": target_phase.value,
                    "priority": priority,
                    "queue_depth": len(queue),
                },
                reason=f"Queued {work_unit.name} for {target_phase.value} phase",
            )
            self.state_bus.write_delta(delta)

        # Note: Work is NOT dispatched immediately, even for the current phase.
        # Dispatch happens via:
        # 1. on_phase_changed() when a new phase begins
        # 2. dispatch_current_phase() called explicitly (e.g., at startup)
        # 3. process_current_phase_queue() for staggered execution during a phase
        #
        # This prevents all work from firing simultaneously when queued.

        return True

    def get_queue(self, phase: DayPhase) -> List[Dict[str, Any]]:
        """Get the current queue for a phase."""
        return [q.to_dict() for q in self._phase_queues[phase]]

    def get_all_queues(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all phase queues."""
        return {
            phase.value: self.get_queue(phase)
            for phase in DayPhase
        }

    def clear_queue(self, phase: DayPhase) -> int:
        """Clear all queued work for a phase. Returns count cleared."""
        count = len(self._phase_queues[phase])
        self._phase_queues[phase] = []
        logger.info(f"Cleared {count} items from {phase.value} queue")
        return count

    def remove_from_queue(self, phase: DayPhase, work_unit_id: str) -> bool:
        """Remove a specific work unit from a phase queue."""
        queue = self._phase_queues[phase]
        for i, queued in enumerate(queue):
            if queued.work_unit.id == work_unit_id:
                queue.pop(i)
                logger.info(f"Removed {work_unit_id} from {phase.value} queue")
                return True
        return False

    async def dispatch_current_phase(self, current_phase: DayPhase) -> int:
        """
        Dispatch queued work for the current phase.

        Called on startup when we're mid-phase and have work queued
        that was never dispatched via phase transition.

        Returns: Number of work units dispatched
        """
        queue = self._phase_queues[current_phase]

        if not queue:
            logger.debug(f"No work queued for current phase ({current_phase.value})")
            return 0

        logger.info(
            f"Dispatching {len(queue)} queued work units for current phase ({current_phase.value})"
        )

        # Emit startup dispatch event
        if self.state_bus:
            from state_models import StateDelta

            delta = StateDelta(
                source="phase_queue",
                event="phase_queue.startup_dispatch",
                event_data={
                    "phase": current_phase.value,
                    "work_count": len(queue),
                    "work_units": [q.work_unit.name for q in queue],
                },
                reason=f"Startup dispatch: {len(queue)} work units for {current_phase.value}",
            )
            self.state_bus.write_delta(delta)

        # Dispatch each work unit
        dispatched = []
        for queued in queue:
            success = await self._dispatch_work(queued)
            if success:
                dispatched.append(queued)

        # Clear dispatched items from queue
        for item in dispatched:
            self._phase_queues[current_phase].remove(item)

        return len(dispatched)

    async def dispatch_next_from_current_phase(self) -> Optional[str]:
        """
        Dispatch the next (highest priority) work unit from the current phase queue.

        This enables staggered execution during a phase - call this periodically
        (e.g., every 5-10 minutes) to process work one at a time instead of
        dispatching everything at once.

        Returns: The work unit ID that was dispatched, or None if queue empty
        """
        if not self.state_bus:
            logger.warning("Cannot dispatch - no state bus to determine current phase")
            return None

        state = self.state_bus.read_state()
        if not state.day_phase or not state.day_phase.current_phase:
            logger.warning("Cannot dispatch - no current phase in state")
            return None

        try:
            current_phase = DayPhase(state.day_phase.current_phase)
        except ValueError:
            logger.warning(f"Invalid phase value: {state.day_phase.current_phase}")
            return None

        queue = self._phase_queues[current_phase]
        if not queue:
            logger.debug(f"No work queued for current phase ({current_phase.value})")
            return None

        # Get highest priority item (queue is sorted by priority)
        queued = queue[0]

        logger.info(
            f"Dispatching next work from {current_phase.value} queue: {queued.work_unit.name}"
        )

        success = await self._dispatch_work(queued)
        if success:
            queue.remove(queued)
            return queued.work_unit.id

        return None

    def get_current_phase_queue_depth(self) -> int:
        """Get the number of items in the current phase's queue."""
        if not self.state_bus:
            return 0

        state = self.state_bus.read_state()
        if not state.day_phase or not state.day_phase.current_phase:
            return 0

        try:
            current_phase = DayPhase(state.day_phase.current_phase)
            return len(self._phase_queues[current_phase])
        except ValueError:
            return 0

    async def on_phase_changed(self, transition: PhaseTransition) -> None:
        """
        Handle phase transition - schedule delayed dispatch of queued work.

        This is called by DayPhaseTracker when the phase changes.
        We delay dispatch to allow spells triggered by the phase event
        to queue their work first.
        """
        new_phase = transition.to_phase

        # Schedule delayed dispatch to allow spells to queue work first
        # Spells are triggered by state bus events which fire before this callback
        # but may take time to complete their queueing
        delay_seconds = 30  # Give spells 30 seconds to queue work

        logger.info(
            f"Phase changed to {new_phase.value}, "
            f"scheduling dispatch in {delay_seconds}s to allow spell queueing"
        )

        # Check email inbox on phase transitions
        asyncio.create_task(self._check_email_on_phase_change(new_phase))

        asyncio.create_task(self._delayed_phase_dispatch(new_phase, delay_seconds, transition))

    async def _check_email_on_phase_change(self, phase: DayPhase) -> None:
        """Check email inbox when phase changes."""
        try:
            if not self._action_registry:
                logger.debug("Action registry not set - skipping email check")
                return

            logger.info(f"[Email] Checking inbox on phase change to {phase.value}")
            result = await self._action_registry.execute("email.check_inbox")

            if result.success:
                email_count = result.data.get("email_count", 0)
                if email_count > 0:
                    logger.info(f"[Email] Found {email_count} unprocessed emails")
                else:
                    logger.debug("[Email] Inbox is empty")
            else:
                logger.warning(f"[Email] Inbox check failed: {result.message}")

        except Exception as e:
            logger.error(f"[Email] Failed to check inbox on phase change: {e}")

    async def _delayed_phase_dispatch(
        self,
        phase: DayPhase,
        delay_seconds: float,
        transition: PhaseTransition
    ) -> None:
        """Dispatch phase queue after a delay."""
        await asyncio.sleep(delay_seconds)

        queue = self._phase_queues[phase]

        if not queue:
            logger.debug(f"No work queued for {phase.value} phase after delay")
            return

        logger.info(
            f"Delayed dispatch: {len(queue)} work units for {phase.value} phase"
        )

        # Emit phase dispatch event
        if self.state_bus:
            from state_models import StateDelta

            delta = StateDelta(
                source="phase_queue",
                event="phase_queue.dispatching",
                event_data={
                    "phase": phase.value,
                    "work_count": len(queue),
                    "work_units": [q.work_unit.name for q in queue],
                },
                reason=f"Dispatching {len(queue)} work units for {phase.value}",
            )
            self.state_bus.write_delta(delta)

        # Dispatch each work unit to Synkratos with staggered timing
        # This prevents all work from hitting Synkratos simultaneously
        dispatched = []
        stagger_delay_seconds = 60  # 1 minute between dispatches

        for i, queued in enumerate(queue):
            if i > 0:
                logger.info(f"Staggered dispatch: waiting {stagger_delay_seconds}s before next work unit")
                await asyncio.sleep(stagger_delay_seconds)

            success = await self._dispatch_work(queued)
            if success:
                dispatched.append(queued)

        # Clear dispatched items from queue
        for item in dispatched:
            self._phase_queues[phase].remove(item)

        # Record in history
        self._dispatch_history.append({
            "phase": phase.value,
            "transitioned_at": transition.transitioned_at.isoformat(),
            "work_count": len(dispatched),
            "work_units": [
                {"id": q.work_unit.id, "name": q.work_unit.name}
                for q in dispatched
            ],
        })
        if len(self._dispatch_history) > self._max_history:
            self._dispatch_history = self._dispatch_history[-self._max_history:]

    async def _dispatch_work(self, queued: QueuedWorkUnit) -> bool:
        """Dispatch a queued work unit to Synkratos."""
        if not self.synkratos:
            logger.error("Cannot dispatch work - Synkratos not set")
            return False

        try:
            from scheduler.core import ScheduledTask, TaskPriority
            from scheduler.budget import TaskCategory
            from datetime import date as date_type

            work_unit = queued.work_unit
            target_phase = queued.target_phase
            summary_store = self._summary_store

            # Map category to TaskCategory
            # Note: SYSTEM category doesn't have a queue in Synkratos, map to GROWTH
            category_map = {
                "reflection": TaskCategory.REFLECTION,
                "research": TaskCategory.RESEARCH,
                "growth": TaskCategory.GROWTH,
                "curiosity": TaskCategory.CURIOSITY,
                "creative": TaskCategory.CURIOSITY,
                "artstudy": TaskCategory.CURIOSITY,  # Art study uses curiosity budget
                "rss": TaskCategory.RESEARCH,  # RSS monitoring uses research budget
                "system": TaskCategory.GROWTH,  # System work uses growth queue
            }
            task_category = category_map.get(
                work_unit.category, TaskCategory.REFLECTION
            )

            # Capture references for closure
            action_registry = self._action_registry
            state_bus = self.state_bus

            # Create handler that executes actions and saves summary
            async def handler(**kwargs) -> Dict[str, Any]:
                work_unit.start()
                logger.info(f"Executing phase-queued work: {work_unit.name}")

                # Execute action sequence if available
                success = True
                error_msg = None
                total_cost = 0.0

                if work_unit.action_sequence and action_registry:
                    for action_id in work_unit.action_sequence:
                        logger.info(f"  Running action: {action_id}")
                        result = await action_registry.execute(
                            action_id,
                            duration_minutes=work_unit.estimated_duration_minutes,
                            focus=work_unit.focus,
                            work_unit_id=work_unit.id,
                        )

                        total_cost += result.cost_usd

                        # Record action result on work unit
                        work_unit.record_action(
                            action_id=action_id,
                            action_type=action_id.split(".")[-1] if "." in action_id else action_id,
                            summary=result.message,
                            result=result.data,
                            artifacts=result.data.get("artifacts", []),
                        )

                        if not result.success:
                            success = False
                            error_msg = result.message
                            logger.warning(f"  Action {action_id} failed: {result.message}")
                            if result.data.get("abort_sequence"):
                                break
                elif not work_unit.action_sequence:
                    logger.warning(f"Work unit {work_unit.name} has no action_sequence")

                if success:
                    work_unit.complete({"dispatched_from_phase_queue": True, "cost_usd": total_cost})
                else:
                    work_unit.fail(error_msg or "Action execution failed")

                # Save work summary if store is available
                if summary_store:
                    try:
                        work_date = date_type.today()
                        slug = generate_slug(
                            work_unit.name,
                            work_unit.id,
                            work_date,
                            target_phase.value
                        )

                        # Build action summaries from recorded results
                        action_summaries = []
                        for i, ar in enumerate(work_unit.action_results):
                            action_slug = f"{slug}/action-{i}-{ar['action_id'].replace('.', '-')}"
                            action_summaries.append(
                                ActionSummary(
                                    action_id=ar["action_id"],
                                    action_type=ar["action_type"],
                                    slug=action_slug,
                                    summary=ar["summary"],
                                    artifacts=ar.get("artifacts", []),
                                )
                            )

                        summary = WorkSummary(
                            work_unit_id=work_unit.id,
                            slug=slug,
                            name=work_unit.name,
                            template_id=work_unit.template_id,
                            phase=target_phase.value,
                            category=work_unit.category or "reflection",
                            focus=work_unit.focus,
                            motivation=work_unit.motivation,
                            date=work_date,
                            started_at=work_unit.started_at,
                            completed_at=work_unit.completed_at,
                            duration_minutes=work_unit.duration_minutes or 0,
                            summary=f"Completed {work_unit.name}" + (
                                f" with focus on {work_unit.focus}" if work_unit.focus else ""
                            ),
                            key_insights=[],
                            questions_addressed=[],
                            questions_raised=[],
                            action_summaries=action_summaries,
                            artifacts=work_unit.artifacts,
                            success=success,
                            error=error_msg,
                            cost_usd=total_cost,
                        )

                        saved_slug = summary_store.save(summary)
                        logger.info(f"Saved work summary: {saved_slug}")

                        # Emit state bus delta for day_phase work tracking
                        if state_bus:
                            from state_models import StateDelta
                            delta = StateDelta(
                                source="phase_queue_manager",
                                day_phase_delta={
                                    "work_slug": saved_slug,
                                    "current_phase": target_phase.value,
                                },
                                event="work_unit.completed",
                                event_data={
                                    "work_unit_id": work_unit.id,
                                    "name": work_unit.name,
                                    "phase": target_phase.value,
                                    "success": success,
                                    "slug": saved_slug,
                                },
                                reason=f"Phase queue work completed: {work_unit.name}",
                            )
                            state_bus.write_delta(delta)
                    except Exception as e:
                        logger.error(f"Failed to save work summary: {e}")

                return {"success": success}

            task = ScheduledTask(
                task_id=work_unit.id,
                name=f"[Phase] {work_unit.name}",
                category=task_category,
                priority=TaskPriority.NORMAL,
                handler=handler,
                estimated_cost_usd=work_unit.estimated_cost_usd,
                context={
                    "work_unit": work_unit.to_dict(),
                    "from_phase_queue": True,
                    "target_phase": queued.target_phase.value,
                },
            )

            self.synkratos.submit_task(task)
            logger.info(
                f"Dispatched '{work_unit.name}' from {queued.target_phase.value} queue"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to dispatch work unit: {e}", exc_info=True)
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get status of all phase queues."""
        return {
            "queues": {
                phase.value: {
                    "count": len(self._phase_queues[phase]),
                    "work_units": [
                        {"id": q.work_unit.id, "name": q.work_unit.name, "priority": q.priority}
                        for q in self._phase_queues[phase]
                    ],
                }
                for phase in DayPhase
            },
            "recent_dispatches": self._dispatch_history[-5:],
            "max_per_phase": self.max_per_phase,
        }
