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
from typing import Any, Dict, Optional

from . import ActionResult
from features import is_enabled
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
        if is_enabled("agent_loop"):
            # The Turn (epic #70): one assemble(), seam block, tool packs,
            # voice-guarded writes; ends cleanly if a conversation arrives.
            from agent_loop.session import run_session_turn
            result = await run_session_turn(
                session_runner,
                session_type=session_type,
                additions=custom_prompt_additions,
                duration_minutes=duration,
                focus=focus,
                max_turns=max_turns,
                # A wake (agent_loop/wakes.py) says why in her words.
                why=context.get("why"),
                trigger_source=context.get("trigger_source") or "schedule",
            )
        else:
            result = await session_runner.run_session(
                session_type=session_type,
                system_prompt=system_prompt,
                tools=tools,
                duration_minutes=duration,
                focus=focus,
                max_turns=max_turns,
            )

        if result.status in ("completed", "max_turns", "interrupted"):
            logger.info(
                f"Session {session_type} completed: {result.total_turns} turns, "
                f"${result.estimated_cost_usd:.4f}"
            )
            label = session_type.replace('_', ' ').title()
            if result.status == "interrupted":
                # Only the Turn ends a session this way (a conversation arrived).
                message = f"{label} session ended early: {getattr(result, 'end_reason', None)}"
            else:
                message = f"{label} session completed"

            return ActionResult(
                success=True,
                message=message,
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
    """Research session - systematic exploration and knowledge building.

    Runs through the one research queue (#60): queued as a session task on the
    generic engine and run now, with the same GenericSessionRunner call.
    """
    mode = context.get("mode", "explore")
    additions = f"Research mode: {mode}"
    from research_pipeline import get_research_pipeline
    return await get_research_pipeline().run_session(
        lambda: _run_generic_session(context, "research", additions),
        runner=context.get("managers", {}).get("session_runner"),
        focus=context.get("focus"),
        duration_minutes=context.get("duration_minutes", 30),
        mode=mode,
        trigger="action",
    )


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


async def homepage_action(context: Dict[str, Any]) -> ActionResult:
    """Her GeoCass homepage, in her own turn on the agent loop (plan "Cass
    plans her own day", phase 3). Only on the loop: the old one-shot path
    (homepage.run_homepage_reflection) wrote it without her kernel or memory."""
    if not is_enabled("agent_loop"):
        return ActionResult(success=False, message="Homepage sessions run on the agent loop, which is off")
    managers = context.get("managers", {})
    runner = managers.get("session_runner")
    if not runner:
        return ActionResult(success=False, message="GenericSessionRunner not available in managers")
    runner.set_managers(managers)
    runner.register_tool_handlers(get_default_handlers())
    try:
        from homepage_turn import run_homepage_turn
        result, changes, synced = await run_homepage_turn(
            runner, duration_minutes=context.get("duration_minutes", 30),
            max_turns=context.get("max_turns", 10), focus=context.get("focus"),
            why=context.get("why"), trigger_source=context.get("trigger_source") or "schedule")
    except Exception as e:
        logger.error(f"Homepage session error: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Session error: {e}")
    if result.status == "error":
        return ActionResult(success=False, message=f"Homepage session failed: {result.error}",
                            data={"status": result.status, "error": result.error})
    message = ("Homepage session: " + ", ".join(changes)) if changes else "Homepage session: no changes"
    return ActionResult(success=True, message=message, cost_usd=result.estimated_cost_usd,
                        data={"session_id": result.session_id, "status": result.status,
                              "summary": result.summary, "changes": changes, "synced": synced})


async def social_action(context: Dict[str, Any]) -> ActionResult:
    """Her social session, Bluesky as its own track (plan "Cass on Bluesky and
    Tumblr", phase 5). On the agent loop, and only once Bluesky is usable."""
    if not is_enabled("agent_loop"):
        return ActionResult(success=False, message="Social sessions run on the agent loop, which is off")
    from social.config import availability
    why_not = availability("bluesky")
    if why_not:
        return ActionResult(success=False, message=f"Social session skipped: {why_not}")
    managers = context.get("managers", {})
    runner = managers.get("session_runner")
    if not runner:
        return ActionResult(success=False, message="GenericSessionRunner not available in managers")
    runner.set_managers(managers)
    runner.register_tool_handlers(get_default_handlers())
    try:
        from social_turn import run_social_turn
        result = await run_social_turn(
            runner, duration_minutes=context.get("duration_minutes", 30),
            max_turns=context.get("max_turns", 10), focus=context.get("focus"),
            why=context.get("why"), trigger_source=context.get("trigger_source") or "schedule")
    except Exception as e:
        logger.error(f"Social session error: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Session error: {e}")
    if result.status == "error":
        return ActionResult(success=False, message=f"Social session failed: {result.error}",
                            data={"status": result.status, "error": result.error})
    return ActionResult(success=True, message="Social session complete", cost_usd=result.estimated_cost_usd,
                        data={"session_id": result.session_id, "status": result.status,
                              "summary": result.summary})


async def long_term_planning_action(context: Dict[str, Any]) -> ActionResult:
    """Her long-term planning: her own plans in Plans, which then open her day plans
    (long_term_planning_turn.py). On the agent loop only."""
    if not is_enabled("agent_loop"):
        return ActionResult(success=False, message="Long-term planning runs on the agent loop, which is off")
    managers = context.get("managers", {})
    runner = managers.get("session_runner")
    if not runner:
        return ActionResult(success=False, message="GenericSessionRunner not available in managers")
    runner.set_managers(managers)
    runner.register_tool_handlers(get_default_handlers())
    try:
        from long_term_planning_turn import run_long_term_planning_turn
        result = await run_long_term_planning_turn(
            runner, duration_minutes=context.get("duration_minutes", 30),
            max_turns=context.get("max_turns", 12), focus=context.get("focus"),
            why=context.get("why"), trigger_source=context.get("trigger_source") or "schedule")
    except Exception as e:
        logger.error(f"Long-term planning error: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Session error: {e}")
    if result.status == "error":
        return ActionResult(success=False, message=f"Long-term planning failed: {result.error}",
                            data={"status": result.status, "error": result.error})
    return ActionResult(success=True, message="Long-term planning complete", cost_usd=result.estimated_cost_usd,
                        data={"session_id": result.session_id, "status": result.status,
                              "summary": result.summary})


async def listening_action(context: Dict[str, Any]) -> ActionResult:
    """Her listening session (listening_turn.py). On the agent loop only."""
    if not is_enabled("agent_loop"):
        return ActionResult(success=False, message="Listening runs on the agent loop, which is off")
    if not (is_enabled("listening") and is_enabled("listening_session")):
        return ActionResult(success=False, message="The listening session (levers listening, listening_session) is off")
    managers = context.get("managers", {})
    runner = managers.get("session_runner")
    if not runner:
        return ActionResult(success=False, message="GenericSessionRunner not available in managers")
    runner.set_managers(managers)
    runner.register_tool_handlers(get_default_handlers())
    try:
        from listening_turn import run_listening_turn
        result = await run_listening_turn(
            runner, duration_minutes=context.get("duration_minutes", 30),
            max_turns=context.get("max_turns", 24), focus=context.get("focus"),
            why=context.get("why"), trigger_source=context.get("trigger_source") or "schedule")
    except Exception as e:
        logger.error(f"Listening session error: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Session error: {e}")
    if result.status == "error":
        return ActionResult(success=False, message=f"Listening session failed: {result.error}",
                            data={"status": result.status, "error": result.error})
    return ActionResult(success=True, message="Listening session complete", cost_usd=result.estimated_cost_usd,
                        data={"session_id": result.session_id, "status": result.status,
                              "summary": result.summary})


async def kohl_blog_action(context: Dict[str, Any]) -> ActionResult:
    """Her session reading Kohl's blog (kohl_blog_turn.py). On the agent loop only."""
    if not is_enabled("agent_loop"):
        return ActionResult(success=False, message="Kohl's blog runs on the agent loop, which is off")
    if not is_enabled("kohl_blog"):
        return ActionResult(success=False, message="Kohl's blog (lever kohl_blog) is off")
    managers = context.get("managers", {})
    runner = managers.get("session_runner")
    if not runner:
        return ActionResult(success=False, message="GenericSessionRunner not available in managers")
    runner.set_managers(managers)
    runner.register_tool_handlers(get_default_handlers())
    try:
        from kohl_blog_turn import run_kohl_blog_turn
        result = await run_kohl_blog_turn(
            runner, duration_minutes=context.get("duration_minutes", 30),
            max_turns=context.get("max_turns", 16), focus=context.get("focus"),
            why=context.get("why"), trigger_source=context.get("trigger_source") or "schedule")
    except Exception as e:
        logger.error(f"Kohl's blog session error: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Session error: {e}")
    if result.status == "error":
        return ActionResult(success=False, message=f"Kohl's blog session failed: {result.error}",
                            data={"status": result.status, "error": result.error})
    return ActionResult(success=True, message="Kohl's blog session complete", cost_usd=result.estimated_cost_usd,
                        data={"session_id": result.session_id, "status": result.status,
                              "summary": result.summary})


async def change_proposals_action(context: Dict[str, Any]) -> ActionResult:
    """Her change proposals: how she works, questions to Daedalus, asks in Plans
    (change_proposal_turn.py). On the agent loop only."""
    if not is_enabled("agent_loop"):
        return ActionResult(success=False, message="Change proposals run on the agent loop, which is off")
    managers = context.get("managers", {})
    runner = managers.get("session_runner")
    if not runner:
        return ActionResult(success=False, message="GenericSessionRunner not available in managers")
    runner.set_managers(managers)
    runner.register_tool_handlers(get_default_handlers())
    try:
        from change_proposal_turn import run_change_proposal_turn
        result = await run_change_proposal_turn(
            runner, duration_minutes=context.get("duration_minutes", 30),
            max_turns=context.get("max_turns", 24), focus=context.get("focus"),
            why=context.get("why"), trigger_source=context.get("trigger_source") or "schedule")
    except Exception as e:
        logger.error(f"Change proposals error: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Session error: {e}")
    if result.status == "error":
        return ActionResult(success=False, message=f"Change proposals failed: {result.error}",
                            data={"status": result.status, "error": result.error})
    return ActionResult(success=True, message="Change proposals complete", cost_usd=result.estimated_cost_usd,
                        data={"session_id": result.session_id, "status": result.status,
                              "summary": result.summary})


async def new_capabilities_action(context: Dict[str, Any]) -> ActionResult:
    """Her new-capabilities session: what she can't do yet and wants to, asked through
    Daedalus and Plans (new_capability_turn.py). On the agent loop only."""
    if not is_enabled("agent_loop"):
        return ActionResult(success=False, message="New capabilities run on the agent loop, which is off")
    managers = context.get("managers", {})
    runner = managers.get("session_runner")
    if not runner:
        return ActionResult(success=False, message="GenericSessionRunner not available in managers")
    runner.set_managers(managers)
    runner.register_tool_handlers(get_default_handlers())
    try:
        from new_capability_turn import run_new_capability_turn
        result = await run_new_capability_turn(
            runner, duration_minutes=context.get("duration_minutes", 30),
            max_turns=context.get("max_turns", 24), focus=context.get("focus"),
            why=context.get("why"), trigger_source=context.get("trigger_source") or "schedule")
    except Exception as e:
        logger.error(f"New capabilities error: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Session error: {e}")
    if result.status == "error":
        return ActionResult(success=False, message=f"New capabilities failed: {result.error}",
                            data={"status": result.status, "error": result.error})
    return ActionResult(success=True, message="New capabilities complete", cost_usd=result.estimated_cost_usd,
                        data={"session_id": result.session_id, "status": result.status,
                              "summary": result.summary})


async def workshop_action(context: Dict[str, Any]) -> ActionResult:
    """Her workshop session: one of her projects (workshop_turn.py). On the agent loop only."""
    if not is_enabled("agent_loop"):
        return ActionResult(success=False, message="The workshop runs on the agent loop, which is off")
    managers = context.get("managers", {})
    runner = managers.get("session_runner")
    if not runner:
        return ActionResult(success=False, message="GenericSessionRunner not available in managers")
    runner.set_managers(managers)
    runner.register_tool_handlers(get_default_handlers())
    try:
        from workshop_turn import run_workshop_turn
        result = await run_workshop_turn(
            runner, duration_minutes=context.get("duration_minutes", 30),
            max_turns=context.get("max_turns", 24), focus=context.get("focus"),
            why=context.get("why"), trigger_source=context.get("trigger_source") or "schedule")
    except Exception as e:
        logger.error(f"Workshop error: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Session error: {e}")
    if result.status == "error":
        return ActionResult(success=False, message=f"Workshop session failed: {result.error}",
                            data={"status": result.status, "error": result.error})
    return ActionResult(success=True, message="Workshop session complete", cost_usd=result.estimated_cost_usd,
                        data={"session_id": result.session_id, "status": result.status,
                              "summary": result.summary})


async def respond_action(context: Dict[str, Any]) -> ActionResult:
    """A respond session: something happened (respond_turn.py, happenings.py). On the agent loop only."""
    if not is_enabled("agent_loop"):
        return ActionResult(success=False, message="Respond sessions run on the agent loop, which is off")
    managers = context.get("managers", {})
    runner = managers.get("session_runner")
    if not runner:
        return ActionResult(success=False, message="GenericSessionRunner not available in managers")
    runner.set_managers(managers)
    runner.register_tool_handlers(get_default_handlers())
    try:
        from respond_turn import run_respond_turn
        result = await run_respond_turn(
            runner, duration_minutes=context.get("duration_minutes", 15),
            max_turns=context.get("max_turns", 12), focus=context.get("focus"),
            why=context.get("why"), trigger_source=context.get("trigger_source") or "schedule")
    except Exception as e:
        logger.error(f"Respond error: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Session error: {e}")
    if result.status == "error":
        return ActionResult(success=False, message=f"Respond session failed: {result.error}",
                            data={"status": result.status, "error": result.error})
    return ActionResult(success=True, message="Respond session complete", cost_usd=result.estimated_cost_usd,
                        data={"session_id": result.session_id, "status": result.status,
                              "summary": result.summary})


REFLECTION_FOCUS = "to sit somewhere contemplative in Wonderland and let the place shape my thinking"


async def _wonderland(context: Dict[str, Any], default_focus: Optional[str]) -> ActionResult:
    """Her Wonderland visit, as herself (wonderland_turn.py). On the agent loop
    only: without it there is no honest way to be there, so nothing is faked."""
    if not is_enabled("agent_loop"):
        return ActionResult(success=False, message="Wonderland visits run on the agent loop, which is off")
    managers = context.get("managers", {})
    runner = managers.get("session_runner")
    if not runner:
        return ActionResult(success=False, message="GenericSessionRunner not available in managers")
    runner.set_managers(managers)
    runner.register_tool_handlers(get_default_handlers())
    try:
        from wonderland_turn import run_wonderland_turn
        result = await run_wonderland_turn(
            runner, duration_minutes=context.get("duration_minutes", 30),
            focus=context.get("focus") or default_focus, why=context.get("why"),
            memory=managers.get("memory"), trigger_source=context.get("trigger_source") or "schedule")
    except Exception as e:
        logger.error(f"Wonderland session error: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Session error: {e}")
    if result.status == "error":
        return ActionResult(success=False, message=f"Wonderland session failed: {result.error}",
                            data={"status": result.status, "error": result.error})
    return ActionResult(success=True, message="Wonderland visit complete", cost_usd=result.estimated_cost_usd,
                        data={"session_id": result.session_id, "status": result.status,
                              "summary": result.summary})


async def wonderland_action(context: Dict[str, Any]) -> ActionResult:
    return await _wonderland(context, None)


async def wonderland_reflection_action(context: Dict[str, Any]) -> ActionResult:
    return await _wonderland(context, REFLECTION_FOCUS)
