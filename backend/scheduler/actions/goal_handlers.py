"""
Goal Action Handlers

TASK handlers for goal operations, enabling Grimoire spells
to manage goal lifecycle via the GoalOrchestrator.
"""

import logging
from typing import Any, Dict

from scheduler.actions import ActionResult

logger = logging.getLogger(__name__)


async def get_actionable_action(context: Dict[str, Any]) -> ActionResult:
    """
    Get actionable goals from the orchestrator.

    TASK goals.get_actionable limit=N
    """
    try:
        from goal_orchestrator import get_goal_orchestrator

        managers = context.get("managers", {})
        daemon_id = managers.get("daemon_id")

        if not daemon_id:
            return ActionResult(
                success=False,
                message="No daemon_id in context",
            )

        orchestrator = get_goal_orchestrator(daemon_id)
        if not orchestrator:
            return ActionResult(
                success=True,
                message="Orchestrator not initialized",
                data={"goals": 0, "items": []},
            )

        limit = context.get("limit", 10)
        goals = orchestrator.get_actionable_goals(limit=int(limit))

        return ActionResult(
            success=True,
            message=f"Found {len(goals)} actionable goals",
            data={
                "goals": len(goals),
                "items": [
                    {
                        "id": g.id,
                        "title": g.title,
                        "type": g.goal_type,
                        "priority": g.priority,
                        "context": g.context_summary,
                    }
                    for g in goals
                ],
            },
        )

    except Exception as e:
        logger.error(f"get_actionable_action failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to get actionable goals: {e}",
        )


async def get_next_action(context: Dict[str, Any]) -> ActionResult:
    """
    Get the next highest priority goal to execute.

    TASK goals.get_next
    """
    try:
        from goal_orchestrator import get_goal_orchestrator

        managers = context.get("managers", {})
        daemon_id = managers.get("daemon_id")

        if not daemon_id:
            return ActionResult(
                success=False,
                message="No daemon_id in context",
            )

        orchestrator = get_goal_orchestrator(daemon_id)
        if not orchestrator:
            return ActionResult(
                success=True,
                message="Orchestrator not initialized",
                data={"goal": "", "goal_id": "", "goal_type": "", "action": ""},
            )

        goal = orchestrator.get_next_action()
        if not goal:
            return ActionResult(
                success=True,
                message="No goals available",
                data={"goal": "", "goal_id": "", "goal_type": "", "action": ""},
            )

        # Parse action from context
        action = ""
        if goal.context_summary:
            for part in goal.context_summary.split("|"):
                if part.startswith("action:"):
                    action = part[7:]
                    break

        return ActionResult(
            success=True,
            message=f"Next goal: {goal.title}",
            data={
                "goal": goal.title,
                "goal_id": goal.id,
                "goal_type": goal.goal_type,
                "action": action,
                "priority": goal.priority,
                "urgency": goal.urgency,
            },
        )

    except Exception as e:
        logger.error(f"get_next_action failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to get next goal: {e}",
        )


async def start_goal_action(context: Dict[str, Any]) -> ActionResult:
    """
    Mark a goal as actively being worked on.

    TASK goals.start goal_id=X
    """
    try:
        from unified_goals import UnifiedGoalManager

        managers = context.get("managers", {})
        daemon_id = managers.get("daemon_id")
        goal_id = context.get("goal_id")

        if not daemon_id:
            return ActionResult(
                success=False,
                message="No daemon_id in context",
            )

        if not goal_id:
            return ActionResult(
                success=False,
                message="No goal_id provided",
            )

        manager = UnifiedGoalManager(daemon_id)
        goal = manager.start_goal(goal_id)

        if goal:
            return ActionResult(
                success=True,
                message=f"Goal started: {goal.title}",
                data={"goal_id": goal_id, "status": goal.status},
            )
        else:
            return ActionResult(
                success=False,
                message=f"Could not start goal {goal_id}",
            )

    except Exception as e:
        logger.error(f"start_goal_action failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to start goal: {e}",
        )


async def complete_goal_action(context: Dict[str, Any]) -> ActionResult:
    """
    Mark a goal as completed.

    TASK goals.complete goal_id=X outcome="description"
    """
    try:
        from unified_goals import UnifiedGoalManager

        managers = context.get("managers", {})
        daemon_id = managers.get("daemon_id")
        goal_id = context.get("goal_id")
        outcome = context.get("outcome", "Completed")

        if not daemon_id:
            return ActionResult(
                success=False,
                message="No daemon_id in context",
            )

        if not goal_id:
            return ActionResult(
                success=False,
                message="No goal_id provided",
            )

        manager = UnifiedGoalManager(daemon_id)
        goal = manager.complete_goal(goal_id, outcome_summary=outcome)

        if goal:
            return ActionResult(
                success=True,
                message=f"Goal completed: {goal.title}",
                data={
                    "goal_id": goal_id,
                    "status": goal.status,
                    "outcome": outcome,
                },
            )
        else:
            return ActionResult(
                success=False,
                message=f"Could not complete goal {goal_id}",
            )

    except Exception as e:
        logger.error(f"complete_goal_action failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to complete goal: {e}",
        )


async def progress_goal_action(context: Dict[str, Any]) -> ActionResult:
    """
    Add progress entry to a goal.

    TASK goals.progress goal_id=X note="progress description"
    """
    try:
        from unified_goals import UnifiedGoalManager

        managers = context.get("managers", {})
        daemon_id = managers.get("daemon_id")
        goal_id = context.get("goal_id")
        note = context.get("note", "Progress update")

        if not daemon_id:
            return ActionResult(
                success=False,
                message="No daemon_id in context",
            )

        if not goal_id:
            return ActionResult(
                success=False,
                message="No goal_id provided",
            )

        manager = UnifiedGoalManager(daemon_id)
        goal = manager.add_progress(goal_id, {"type": "spell_update", "note": note})

        if goal:
            return ActionResult(
                success=True,
                message=f"Progress added to goal: {goal.title}",
                data={
                    "goal_id": goal_id,
                    "progress_count": len(goal.progress),
                },
            )
        else:
            return ActionResult(
                success=False,
                message=f"Could not add progress to goal {goal_id}",
            )

    except Exception as e:
        logger.error(f"progress_goal_action failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to add progress: {e}",
        )


async def abandon_goal_action(context: Dict[str, Any]) -> ActionResult:
    """
    Mark a goal as abandoned.

    TASK goals.abandon goal_id=X reason="why"
    """
    try:
        from unified_goals import UnifiedGoalManager

        managers = context.get("managers", {})
        daemon_id = managers.get("daemon_id")
        goal_id = context.get("goal_id")
        reason = context.get("reason", "Abandoned")

        if not daemon_id:
            return ActionResult(
                success=False,
                message="No daemon_id in context",
            )

        if not goal_id:
            return ActionResult(
                success=False,
                message="No goal_id provided",
            )

        manager = UnifiedGoalManager(daemon_id)
        goal = manager.abandon_goal(goal_id, reason=reason)

        if goal:
            return ActionResult(
                success=True,
                message=f"Goal abandoned: {goal.title}",
                data={
                    "goal_id": goal_id,
                    "status": goal.status,
                    "reason": reason,
                },
            )
        else:
            return ActionResult(
                success=False,
                message=f"Could not abandon goal {goal_id}",
            )

    except Exception as e:
        logger.error(f"abandon_goal_action failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to abandon goal: {e}",
        )


async def create_goal_action(context: Dict[str, Any]) -> ActionResult:
    """
    Create a new goal from a spell.

    TASK goals.create title="X" type="Y" description="Z"
    """
    try:
        from unified_goals import UnifiedGoalManager, GoalType

        managers = context.get("managers", {})
        daemon_id = managers.get("daemon_id")
        title = context.get("title")
        goal_type = context.get("type", "growth")
        description = context.get("description", "")
        priority = context.get("priority", "P2")
        auto_approve = context.get("auto_approve", False)

        if not daemon_id:
            return ActionResult(
                success=False,
                message="No daemon_id in context",
            )

        if not title:
            return ActionResult(
                success=False,
                message="No title provided",
            )

        # Validate goal type
        valid_types = [t.value for t in GoalType]
        if goal_type not in valid_types:
            goal_type = "growth"

        manager = UnifiedGoalManager(daemon_id)

        # For spell-created goals, use simpler criteria
        goal = manager.create_goal(
            title=title,
            goal_type=goal_type,
            created_by="spell",
            description=description or f"Goal created by spell: {title}",
            priority=priority,
            completion_criteria=[
                "Goal objective achieved",
                "Verified by spell or user",
            ],
        )

        # Auto-approve if requested
        if auto_approve:
            manager.approve_goal(goal.id, "spell")

        return ActionResult(
            success=True,
            message=f"Goal created: {goal.title}",
            data={
                "goal_id": goal.id,
                "title": goal.title,
                "type": goal.goal_type,
                "status": goal.status,
            },
        )

    except Exception as e:
        logger.error(f"create_goal_action failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to create goal: {e}",
        )


async def get_status_action(context: Dict[str, Any]) -> ActionResult:
    """
    Get orchestrator status.

    TASK goals.status
    """
    try:
        from goal_orchestrator import get_goal_orchestrator

        managers = context.get("managers", {})
        daemon_id = managers.get("daemon_id")

        if not daemon_id:
            return ActionResult(
                success=False,
                message="No daemon_id in context",
            )

        orchestrator = get_goal_orchestrator(daemon_id)
        if not orchestrator:
            return ActionResult(
                success=True,
                message="Orchestrator not initialized",
                data={"initialized": False},
            )

        status = orchestrator.get_status()
        return ActionResult(
            success=True,
            message="Orchestrator status",
            data={"initialized": True, **status},
        )

    except Exception as e:
        logger.error(f"get_status_action failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to get status: {e}",
        )
