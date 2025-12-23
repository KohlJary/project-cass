"""
Session Action Handlers - Run autonomous sessions via GenericSessionRunner.

Each handler configures and runs a session of a specific type (reflection, research, etc.)
using the consolidated GenericSessionRunner with session-type-specific prompts and tools.

Each handler takes a context dict containing:
- definition: ActionDefinition
- duration_minutes: int
- managers: Dict[str, Any] (includes session_runner)
- focus: Optional[str] - focus/theme for the session
- Any additional kwargs passed to execute()

Returns ActionResult.
"""

import logging
from typing import Any, Dict

from . import ActionResult
from session import get_session_prompt, get_session_tools, get_default_handlers

logger = logging.getLogger(__name__)


async def _run_generic_session(
    context: Dict[str, Any],
    session_type: str,
    custom_prompt_additions: str = None,
) -> ActionResult:
    """
    Run a session using GenericSessionRunner.

    Args:
        context: Execution context with managers, duration, focus, etc.
        session_type: Type of session (reflection, research, etc.)
        custom_prompt_additions: Optional additions to the session prompt

    Returns:
        ActionResult with session outcome
    """
    managers = context.get("managers", {})
    session_runner = managers.get("session_runner")

    if not session_runner:
        return ActionResult(
            success=False,
            message="GenericSessionRunner not available in managers"
        )

    duration = context.get("duration_minutes", 30)
    focus = context.get("focus")
    max_turns = context.get("max_turns", 10)

    # Get session-type-specific prompt and tools
    system_prompt = get_session_prompt(session_type, custom_prompt_additions)
    tools = get_session_tools(session_type)

    # Set up tool handlers
    session_runner.set_managers(managers)
    session_runner.register_tool_handlers(get_default_handlers())

    try:
        result = await session_runner.run_session(
            session_type=session_type,
            system_prompt=system_prompt,
            tools=tools,
            duration_minutes=duration,
            focus=focus,
            max_turns=max_turns,
        )

        if result.status in ("completed", "max_turns"):
            logger.info(
                f"Session {session_type} completed: {result.total_turns} turns, "
                f"${result.estimated_cost_usd:.4f}"
            )

            return ActionResult(
                success=True,
                message=f"{session_type.replace('_', ' ').title()} session completed",
                cost_usd=result.estimated_cost_usd,
                data={
                    "session_id": result.session_id,
                    "session_type": session_type,
                    "total_turns": result.total_turns,
                    "duration_seconds": result.duration_seconds,
                    "status": result.status,
                    "summary": result.summary,
                    "insights": result.insights,
                    "artifacts": result.artifacts,
                }
            )
        else:
            return ActionResult(
                success=False,
                message=f"Session {session_type} failed: {result.error or result.status}",
                data={"status": result.status, "error": result.error}
            )

    except Exception as e:
        logger.error(f"Session {session_type} error: {e}", exc_info=True)
        return ActionResult(
            success=False,
            message=f"Session error: {e}"
        )


async def reflection_action(context: Dict[str, Any]) -> ActionResult:
    """Solo reflection session - private contemplation and self-examination."""
    theme = context.get("focus") or context.get("theme")
    additions = f"Theme for this session: {theme}" if theme else None
    return await _run_generic_session(context, "reflection", additions)


async def synthesis_action(context: Dict[str, Any]) -> ActionResult:
    """Insight synthesis session - integrating recent learnings."""
    return await _run_generic_session(context, "synthesis")


async def meta_reflection_action(context: Dict[str, Any]) -> ActionResult:
    """Meta-reflection session - analyzing patterns of thought and behavior."""
    return await _run_generic_session(context, "meta_reflection")


async def consolidation_action(context: Dict[str, Any]) -> ActionResult:
    """Knowledge consolidation session - organizing and integrating memories."""
    period_type = context.get("period_type", "daily")
    additions = f"Consolidation period: {period_type}"
    return await _run_generic_session(context, "consolidation", additions)


async def growth_edge_action(context: Dict[str, Any]) -> ActionResult:
    """Growth edge work session - actively developing in growth areas."""
    return await _run_generic_session(context, "growth_edge")


async def curiosity_action(context: Dict[str, Any]) -> ActionResult:
    """Curiosity exploration session - self-directed learning without agenda."""
    # Explicitly no focus - that's the point
    context = {**context, "focus": None}
    return await _run_generic_session(context, "curiosity")


async def world_state_action(context: Dict[str, Any]) -> ActionResult:
    """World state check session - connecting with external reality."""
    return await _run_generic_session(context, "world_state")


async def research_action(context: Dict[str, Any]) -> ActionResult:
    """Research session - systematic exploration and knowledge building."""
    mode = context.get("mode", "explore")
    additions = f"Research mode: {mode}"
    return await _run_generic_session(context, "research", additions)


async def knowledge_building_action(context: Dict[str, Any]) -> ActionResult:
    """Knowledge building session - creating and organizing research notes."""
    return await _run_generic_session(context, "knowledge_building")


async def writing_action(context: Dict[str, Any]) -> ActionResult:
    """Writing session - developing ideas through focused writing."""
    return await _run_generic_session(context, "writing")


async def creative_action(context: Dict[str, Any]) -> ActionResult:
    """Creative output session - generating new ideas and expressions."""
    return await _run_generic_session(context, "creative")


async def user_synthesis_action(context: Dict[str, Any]) -> ActionResult:
    """User model synthesis session - deepening understanding of users."""
    return await _run_generic_session(context, "user_synthesis")
