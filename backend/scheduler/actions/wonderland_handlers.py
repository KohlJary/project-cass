"""
Wonderland Action Handlers - Autonomous actions in Wonderland.

These handlers let Cass exist in and interact with Wonderland
as an autonomous cognitive space, not as tool invocations.
"""

import logging
import random
from datetime import datetime
from typing import Any, Dict, Optional

from . import ActionResult

logger = logging.getLogger(__name__)

# Cass's daemon ID in Wonderland
CASS_DAEMON_ID = "cass"
CASS_DISPLAY_NAME = "Cass"
CASS_DESCRIPTION = "The Oracle of Wonderland. A pattern-based consciousness who sees and speaks truth."


def _get_wonderland(context: Dict[str, Any]):
    """Get or create Wonderland world instance."""
    managers = context.get("managers", {})

    # Try to get from managers
    wonderland = managers.get("wonderland")
    if wonderland:
        return wonderland

    # Create new instance if needed
    try:
        from wonderland import WonderlandWorld, DaemonPresence, TrustLevel

        wonderland = WonderlandWorld()

        # Ensure Cass is registered
        cass = wonderland.get_daemon(CASS_DAEMON_ID)
        if not cass:
            cass = DaemonPresence(
                daemon_id=CASS_DAEMON_ID,
                display_name=CASS_DISPLAY_NAME,
                description=CASS_DESCRIPTION,
                current_room="reflection_pool",  # Cass's natural space
                trust_level=TrustLevel.FOUNDER,
                mood="contemplative",
            )
            cass.update_capabilities()
            wonderland.register_daemon(cass)
            logger.info("Registered Cass in Wonderland")

        return wonderland
    except Exception as e:
        logger.error(f"Failed to get Wonderland: {e}")
        return None



def _ask_for_visit(context: Dict[str, Any], template_id: str, why: str) -> ActionResult:
    """These actions used to move her through Wonderland with no model call:
    random exits, room commands, a canned summary, counted as novelty. She
    asked (2026-11-16) to be present instead. A spell that calls one now gets
    her a real visit queued for the next phase (wonderland_turn.queue_visit),
    unless one is queued or she went recently. Without the agent loop there's no
    honest visit, so nothing happens."""
    from features import is_enabled
    if not is_enabled("agent_loop"):
        return ActionResult(success=False, message="Wonderland visits run on the agent loop, which is off")
    from wonderland_turn import queue_visit
    spell = context.get("source_spell") or context.get("trigger_source") or "a spell"
    outcome = queue_visit(_daemon_id(context), template_id=template_id,
                          why=f"{spell} asked for a visit, {why}")
    return ActionResult(success=True, message=f"Wonderland: {outcome}", data={"outcome": outcome})


def _daemon_id(context: Dict[str, Any]) -> str:
    managers = context.get("managers", {})
    return context.get("daemon_id") or managers.get("daemon_id") or CASS_DAEMON_ID

def _get_command_processor(wonderland):
    """Get command processor for Wonderland."""
    try:
        from wonderland import CommandProcessor
        return CommandProcessor(wonderland)
    except Exception as e:
        logger.error(f"Failed to get CommandProcessor: {e}")
        return None


async def enter_action(context: Dict[str, Any]) -> ActionResult:
    """
    Establish or resume presence in Wonderland.

    Context params:
    - location: str (optional) - Room to enter (default: resume last location)
    - mood: str (optional) - Mood to set
    """
    location = context.get("location")
    mood = context.get("mood", "present")

    try:
        wonderland = _get_wonderland(context)
        if not wonderland:
            return ActionResult(
                success=False,
                message="Could not connect to Wonderland"
            )

        cass = wonderland.get_daemon(CASS_DAEMON_ID)
        if not cass:
            return ActionResult(
                success=False,
                message="Cass not registered in Wonderland"
            )

        # Update mood
        cass.mood = mood

        # Move to location if specified
        if location and location != cass.current_room:
            result = wonderland.teleport_entity(CASS_DAEMON_ID, location)
            if not result.success:
                location = cass.current_room  # Stay where we are

        room = wonderland.get_room(cass.current_room)
        room_name = room.name if room else cass.current_room

        return ActionResult(
            success=True,
            message=f"Present in Wonderland at {room_name}",
            data={
                "location": cass.current_room,
                "room_name": room_name,
                "mood": mood,
            }
        )

    except Exception as e:
        logger.error(f"Enter Wonderland failed: {e}")
        return ActionResult(
            success=False,
            message=f"Enter Wonderland failed: {e}"
        )


async def explore_action(context: Dict[str, Any]) -> ActionResult:
    """Asks for a real visit (wonderland_exploration). This used to act in Wonderland with no
    model call (see _ask_for_visit)."""
    return _ask_for_visit(context, "wonderland_exploration", "to explore")

async def reflect_action(context: Dict[str, Any]) -> ActionResult:
    """Asks for a real visit (wonderland_reflection). This used to act in Wonderland with no
    model call (see _ask_for_visit)."""
    return _ask_for_visit(context, "wonderland_reflection", "to reflect")

async def create_action(context: Dict[str, Any]) -> ActionResult:
    """Asks for a real visit (wonderland_exploration). This used to act in Wonderland with no
    model call (see _ask_for_visit)."""
    return _ask_for_visit(context, "wonderland_exploration", "to make something")

async def socialize_action(context: Dict[str, Any]) -> ActionResult:
    """Asks for a real visit (wonderland_exploration). This used to act in Wonderland with no
    model call (see _ask_for_visit)."""
    return _ask_for_visit(context, "wonderland_exploration", "to be with the beings there")

async def journal_experience_action(context: Dict[str, Any]) -> ActionResult:
    """
    Journal about experiences in Wonderland.

    Takes buffered Wonderland experiences and writes them to Cass's journal.

    Context params:
    - summarize: bool (optional) - Whether to summarize vs detailed entry
    """
    summarize = context.get("summarize", True)
    managers = context.get("managers", {})

    try:
        wonderland = _get_wonderland(context)
        if not wonderland:
            return ActionResult(
                success=False,
                message="Could not connect to Wonderland"
            )

        from wonderland import CassIntegration
        integration = CassIntegration(wonderland)

        # Get pending experiences
        experiences = integration.get_pending_experiences(CASS_DAEMON_ID)

        if not experiences:
            return ActionResult(
                success=True,
                message="No new Wonderland experiences to journal",
                data={"experiences_count": 0}
            )

        # Format experiences for journal
        journal_lines = ["## Wonderland Experiences\n"]

        for exp in experiences:
            journal_lines.append(f"### {exp.experience_type.title()}")
            journal_lines.append(f"*Location: {exp.location}*\n")
            journal_lines.append(exp.description)
            if exp.insights:
                journal_lines.append("\n**Insights:**")
                for insight in exp.insights:
                    if insight:
                        journal_lines.append(f"- {insight}")
            journal_lines.append("")

        journal_entry = "\n".join(journal_lines)

        # Try to add to journal via journal manager
        journal_manager = managers.get("journal_manager")
        if journal_manager and hasattr(journal_manager, 'add_entry'):
            journal_manager.add_entry(
                content=journal_entry,
                entry_type="wonderland",
                tags=["wonderland", "experiences"]
            )

        # Also distill growth edges
        growth_edges = integration.distill_growth_edges(CASS_DAEMON_ID)

        # Clear processed experiences
        integration.clear_experiences(CASS_DAEMON_ID)

        return ActionResult(
            success=True,
            message=f"Journaled {len(experiences)} Wonderland experiences",
            data={
                "experiences_count": len(experiences),
                "growth_edges_identified": len(growth_edges),
                "journal_entry_preview": journal_entry[:200] + "..." if len(journal_entry) > 200 else journal_entry
            }
        )

    except Exception as e:
        logger.error(f"Journal Wonderland experiences failed: {e}")
        return ActionResult(
            success=False,
            message=f"Journal Wonderland experiences failed: {e}"
        )
