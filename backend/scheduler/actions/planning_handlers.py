"""
Planning Action Handlers - LLM-based day planning actions.

These actions use the decision engine to create emergent, adaptive daily plans
based on Cass's current state, needs, and growth edges.
"""

import logging
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


async def generate_day_plan_action(context: Dict[str, Any]) -> ActionResult:
    """
    Generate an emergent day plan using the LLM decision engine.

    This action:
    1. Gathers Cass's current state (emotional, needs, growth edges)
    2. Uses the decision engine to plan work for remaining phases
    3. Queues the planned work via the phase queue manager

    Expects managers to contain:
    - autonomous_scheduler: The AutonomousScheduler instance
    """
    managers = context.get("managers", {})
    scheduler = managers.get("autonomous_scheduler")

    if not scheduler:
        return ActionResult(
            success=False,
            message="autonomous_scheduler not available"
        )

    # Check if spell-based planning is enabled (would skip LLM planning)
    if getattr(scheduler, 'USE_SPELL_PLANNING', False):
        # Temporarily disable spell-based planning for this action
        # We want to use LLM planning for emergent scheduling
        logger.info("Day planning action: using LLM-based planning")

    try:
        # Call the scheduler's plan_day method which uses the decision engine
        plan = await scheduler.plan_day()

        if not plan:
            return ActionResult(
                success=True,
                message="No work planned - budget low or no viable options",
                cost_usd=0.05,  # Small cost for the decision process
                data={"phases_planned": 0, "work_units": 0}
            )

        # Count what was planned
        total_work = sum(len(units) for units in plan.values())
        phases_planned = list(plan.keys())

        # Build summary of what was planned
        plan_summary = {}
        for phase, units in plan.items():
            plan_summary[phase] = [unit.get("name", "Unknown") if isinstance(unit, dict) else unit.name for unit in units]

        logger.info(f"Day planning complete: {total_work} work units across {len(phases_planned)} phases")

        return ActionResult(
            success=True,
            message=f"Planned {total_work} work units for phases: {', '.join(phases_planned)}",
            cost_usd=0.10,  # Cost for the LLM planning call
            data={
                "phases_planned": len(phases_planned),
                "work_units": total_work,
                "plan_summary": plan_summary,
            }
        )

    except Exception as e:
        logger.error(f"Day planning failed: {e}")
        return ActionResult(
            success=False,
            message=f"Day planning failed: {e}"
        )


async def replan_phase_action(context: Dict[str, Any]) -> ActionResult:
    """
    Replan a specific phase based on current state.

    Use this when circumstances have changed and the current phase's
    planned work needs adjustment.

    Expects managers to contain:
    - autonomous_scheduler: The AutonomousScheduler instance

    Context should include:
    - phase: The phase to replan (e.g., "afternoon")
    """
    managers = context.get("managers", {})
    scheduler = managers.get("autonomous_scheduler")
    phase = context.get("phase")

    if not scheduler:
        return ActionResult(
            success=False,
            message="autonomous_scheduler not available"
        )

    if not phase:
        return ActionResult(
            success=False,
            message="No phase specified for replanning"
        )

    try:
        from scheduling.day_phase import DayPhase

        # Parse phase
        try:
            target_phase = DayPhase(phase)
        except ValueError:
            return ActionResult(
                success=False,
                message=f"Invalid phase: {phase}"
            )

        # Clear current queue for this phase
        if scheduler._phase_queue:
            scheduler._phase_queue.clear_phase(target_phase)

        # Replan just this phase
        plan = await scheduler.decision_engine.plan_day([target_phase])

        if not plan or target_phase not in plan:
            return ActionResult(
                success=True,
                message=f"No work planned for {phase}",
                data={"phase": phase, "work_units": 0}
            )

        # Queue the new work
        work_units = plan[target_phase]
        for i, work_unit in enumerate(work_units):
            if scheduler._phase_queue:
                scheduler._phase_queue.queue_for_phase(
                    work_unit=work_unit,
                    target_phase=target_phase,
                    priority=i + 1,
                )

        return ActionResult(
            success=True,
            message=f"Replanned {phase}: {len(work_units)} work units queued",
            cost_usd=0.05,
            data={
                "phase": phase,
                "work_units": len(work_units),
                "work_names": [w.name for w in work_units],
            }
        )

    except Exception as e:
        logger.error(f"Phase replanning failed: {e}")
        return ActionResult(
            success=False,
            message=f"Phase replanning failed: {e}"
        )
