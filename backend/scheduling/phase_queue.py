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

from .day_phase import DayPhase, PhaseTransition
from .work_unit import WorkUnit

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
    ):
        self.synkratos = synkratos
        self.state_bus = state_bus
        self.max_per_phase = max_per_phase

        # Queues for each phase
        self._phase_queues: Dict[DayPhase, List[QueuedWorkUnit]] = {
            phase: [] for phase in DayPhase
        }

        # History of dispatched work
        self._dispatch_history: List[Dict[str, Any]] = []
        self._max_history = 50

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

    async def on_phase_changed(self, transition: PhaseTransition) -> None:
        """
        Handle phase transition - dispatch queued work.

        This is called by DayPhaseTracker when the phase changes.
        """
        new_phase = transition.to_phase
        queue = self._phase_queues[new_phase]

        if not queue:
            logger.debug(f"No work queued for {new_phase.value} phase")
            return

        logger.info(
            f"Phase changed to {new_phase.value}, "
            f"dispatching {len(queue)} queued work units"
        )

        # Emit phase dispatch event
        if self.state_bus:
            from state_models import StateDelta

            delta = StateDelta(
                source="phase_queue",
                event="phase_queue.dispatching",
                event_data={
                    "phase": new_phase.value,
                    "work_count": len(queue),
                    "work_units": [q.work_unit.name for q in queue],
                },
                reason=f"Dispatching {len(queue)} work units for {new_phase.value}",
            )
            self.state_bus.write_delta(delta)

        # Dispatch each work unit to Synkratos
        dispatched = []
        for queued in queue:
            success = await self._dispatch_work(queued)
            if success:
                dispatched.append(queued)

        # Clear dispatched items from queue
        for item in dispatched:
            self._phase_queues[new_phase].remove(item)

        # Record in history
        self._dispatch_history.append({
            "phase": new_phase.value,
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

            work_unit = queued.work_unit

            # Map category to TaskCategory
            category_map = {
                "reflection": TaskCategory.REFLECTION,
                "research": TaskCategory.RESEARCH,
                "growth": TaskCategory.GROWTH,
                "curiosity": TaskCategory.CURIOSITY,
                "creative": TaskCategory.CURIOSITY,
                "system": TaskCategory.SYSTEM,
            }
            task_category = category_map.get(
                work_unit.category, TaskCategory.REFLECTION
            )

            # Create handler that marks work unit status
            async def handler(context: Dict[str, Any] = None) -> Dict[str, Any]:
                work_unit.start()
                # The actual execution would happen here
                # For now, just mark as complete
                logger.info(f"Executing phase-queued work: {work_unit.name}")
                work_unit.complete({"dispatched_from_phase_queue": True})
                return {"success": True}

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
