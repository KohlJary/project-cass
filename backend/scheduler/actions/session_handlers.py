"""
Session Action Handlers - Wrappers for session runners.

Each handler takes a context dict containing:
- definition: ActionDefinition
- duration_minutes: int
- runners: Dict[str, BaseSessionRunner]
- managers: Dict[str, Any]
- Any additional kwargs passed to execute()

Returns ActionResult.
"""

import logging
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


async def _run_session(
    context: Dict[str, Any],
    runner_key: str,
    session_kwargs: Dict[str, Any] = None
) -> ActionResult:
    """
    Generic session runner wrapper.

    Args:
        context: Execution context with runners, duration, etc.
        runner_key: Key to look up runner in context["runners"]
        session_kwargs: Additional kwargs for start_session()

    Returns:
        ActionResult with session outcome
    """
    runners = context.get("runners", {})
    runner = runners.get(runner_key)

    if not runner:
        return ActionResult(
            success=False,
            message=f"Runner not available: {runner_key}"
        )

    if runner.is_running:
        return ActionResult(
            success=False,
            message=f"Runner {runner_key} is already running"
        )

    duration = context.get("duration_minutes", 30)
    kwargs = {"duration_minutes": duration}
    if session_kwargs:
        kwargs.update(session_kwargs)

    try:
        session = await runner.start_session(**kwargs)

        if session:
            session_id = getattr(session, 'session_id', None) or getattr(session, 'id', None)
            logger.info(f"Started {runner_key} session: {session_id}")

            return ActionResult(
                success=True,
                message=f"{runner_key.replace('_', ' ').title()} session started",
                cost_usd=context["definition"].estimated_cost_usd,
                data={
                    "session_id": session_id,
                    "runner": runner_key,
                    "duration_minutes": duration
                }
            )
        else:
            return ActionResult(
                success=False,
                message=f"Failed to start {runner_key} session"
            )

    except Exception as e:
        logger.error(f"Session {runner_key} failed: {e}")
        return ActionResult(
            success=False,
            message=f"Session failed: {e}"
        )


async def reflection_action(context: Dict[str, Any]) -> ActionResult:
    """Solo reflection session."""
    theme = context.get("theme", "Private contemplation and self-examination")
    return await _run_session(context, "reflection", {
        "theme": theme,
        "trigger": "action"
    })


async def synthesis_action(context: Dict[str, Any]) -> ActionResult:
    """Insight synthesis session."""
    focus = context.get("focus")
    return await _run_session(context, "synthesis", {
        "focus": focus,
        "mode": "general"
    })


async def meta_reflection_action(context: Dict[str, Any]) -> ActionResult:
    """Meta-reflection session."""
    focus = context.get("focus")
    return await _run_session(context, "meta_reflection", {
        "focus": focus
    })


async def consolidation_action(context: Dict[str, Any]) -> ActionResult:
    """Knowledge consolidation session."""
    period_type = context.get("period_type", "daily")
    return await _run_session(context, "consolidation", {
        "period_type": period_type
    })


async def growth_edge_action(context: Dict[str, Any]) -> ActionResult:
    """Growth edge work session."""
    focus = context.get("focus")  # Specific growth edge, or None for self-directed
    return await _run_session(context, "growth_edge", {
        "focus": focus
    })


async def curiosity_action(context: Dict[str, Any]) -> ActionResult:
    """Curiosity exploration session."""
    # No focus - that's the point of curiosity
    return await _run_session(context, "curiosity", {})


async def world_state_action(context: Dict[str, Any]) -> ActionResult:
    """World state check session."""
    focus = context.get("focus")
    return await _run_session(context, "world_state", {
        "focus": focus
    })


async def research_action(context: Dict[str, Any]) -> ActionResult:
    """Research session."""
    focus = context.get("focus", "Self-directed research")
    mode = context.get("mode", "explore")
    return await _run_session(context, "research", {
        "focus": focus,
        "mode": mode,
        "trigger": "action"
    })


async def knowledge_building_action(context: Dict[str, Any]) -> ActionResult:
    """Knowledge building session."""
    focus = context.get("focus")
    return await _run_session(context, "knowledge_building", {
        "focus": focus
    })


async def writing_action(context: Dict[str, Any]) -> ActionResult:
    """Creative writing session."""
    focus = context.get("focus")
    return await _run_session(context, "writing", {
        "focus": focus
    })


async def creative_action(context: Dict[str, Any]) -> ActionResult:
    """Creative output session."""
    focus = context.get("focus")
    return await _run_session(context, "creative", {
        "focus": focus
    })


async def user_synthesis_action(context: Dict[str, Any]) -> ActionResult:
    """User model synthesis session."""
    return await _run_session(context, "user_synthesis", {})
