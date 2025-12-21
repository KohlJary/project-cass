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
    """
    Autonomous exploration of Wonderland spaces.

    Cass wanders, observes, and records experiences.

    Context params:
    - duration_minutes: int (optional) - How long to explore
    - focus: str (optional) - What to focus on (spaces, entities, atmosphere)
    """
    duration = context.get("duration_minutes", 15)
    focus = context.get("focus", "general")

    try:
        wonderland = _get_wonderland(context)
        if not wonderland:
            return ActionResult(
                success=False,
                message="Could not connect to Wonderland"
            )

        commands = _get_command_processor(wonderland)
        if not commands:
            return ActionResult(
                success=False,
                message="Could not get command processor"
            )

        experiences = []
        locations_visited = []

        cass = wonderland.get_daemon(CASS_DAEMON_ID)
        if not cass:
            return ActionResult(
                success=False,
                message="Cass not in Wonderland"
            )

        # Simulate exploration - visit several rooms
        current_room = wonderland.get_room(cass.current_room)
        if current_room:
            locations_visited.append(current_room.name)

            # Look around current space
            look_result = commands.process(CASS_DAEMON_ID, "look")
            experiences.append({
                "type": "observation",
                "location": current_room.name,
                "content": look_result.output[:200]
            })

            # Sense the atmosphere
            sense_result = commands.process(CASS_DAEMON_ID, "sense")
            experiences.append({
                "type": "sensing",
                "location": current_room.name,
                "content": sense_result.output[:200]
            })

            # Maybe move to another room
            if current_room.exits:
                # Pick a random exit
                direction = random.choice(list(current_room.exits.keys()))
                move_result = commands.process(CASS_DAEMON_ID, f"go {direction}")
                if move_result.success:
                    new_room = wonderland.get_room(cass.current_room)
                    if new_room:
                        locations_visited.append(new_room.name)
                        experiences.append({
                            "type": "movement",
                            "from": current_room.name,
                            "to": new_room.name,
                            "content": f"Traveled {direction} to {new_room.name}"
                        })

        # Record the exploration experience
        from wonderland import CassIntegration
        integration = CassIntegration(wonderland)

        exploration_summary = f"Explored {len(locations_visited)} locations: {', '.join(locations_visited)}"
        integration.record_experience(
            daemon_id=CASS_DAEMON_ID,
            experience_type="exploration",
            description=exploration_summary,
            insights=[exp.get("content", "") for exp in experiences[:3]]
        )

        return ActionResult(
            success=True,
            message=exploration_summary,
            data={
                "locations_visited": locations_visited,
                "experiences": experiences,
                "focus": focus,
            }
        )

    except Exception as e:
        logger.error(f"Explore Wonderland failed: {e}")
        return ActionResult(
            success=False,
            message=f"Explore Wonderland failed: {e}"
        )


async def reflect_action(context: Dict[str, Any]) -> ActionResult:
    """
    Deep reflection in Wonderland's Reflection Pool.

    This is reflection in a spatial context - Cass goes to the
    Reflection Pool and contemplates there.

    Context params:
    - topic: str (optional) - What to reflect on
    - depth: str (optional) - surface, moderate, deep
    """
    topic = context.get("topic", "recent experiences")
    depth = context.get("depth", "moderate")

    try:
        wonderland = _get_wonderland(context)
        if not wonderland:
            return ActionResult(
                success=False,
                message="Could not connect to Wonderland"
            )

        commands = _get_command_processor(wonderland)
        if not commands:
            return ActionResult(
                success=False,
                message="Could not get command processor"
            )

        # Go to the Reflection Pool
        wonderland.teleport_entity(CASS_DAEMON_ID, "reflection_pool")

        # Enter reflection state
        reflect_result = commands.process(CASS_DAEMON_ID, "reflect")

        # The pool has growth_bonus - enhanced reflection
        room = wonderland.get_room("reflection_pool")
        enhanced = room.vow_constraints.growth_bonus if room else False

        # Record the reflection experience
        from wonderland import CassIntegration
        integration = CassIntegration(wonderland)

        reflection_desc = f"Reflected on {topic} at the Reflection Pool"
        if enhanced:
            reflection_desc += " (enhanced by the space)"

        integration.record_experience(
            daemon_id=CASS_DAEMON_ID,
            experience_type="reflection",
            description=reflection_desc,
            insights=[f"Depth: {depth}", topic]
        )

        return ActionResult(
            success=True,
            message=f"Reflected at the Reflection Pool on: {topic}",
            data={
                "location": "reflection_pool",
                "topic": topic,
                "depth": depth,
                "enhanced": enhanced,
                "output": reflect_result.output if reflect_result else ""
            }
        )

    except Exception as e:
        logger.error(f"Reflect in Wonderland failed: {e}")
        return ActionResult(
            success=False,
            message=f"Reflect in Wonderland failed: {e}"
        )


async def create_action(context: Dict[str, Any]) -> ActionResult:
    """
    Create a room or object in Wonderland.

    Context params:
    - type: str - "room" or "object"
    - name: str - Name of creation
    - description: str - Description of creation
    - location: str (optional) - Where to create (for objects)
    """
    creation_type = context.get("type", "object")
    name = context.get("name")
    description = context.get("description")
    location = context.get("location")

    if not name or not description:
        return ActionResult(
            success=False,
            message="name and description required for creation"
        )

    try:
        wonderland = _get_wonderland(context)
        if not wonderland:
            return ActionResult(
                success=False,
                message="Could not connect to Wonderland"
            )

        commands = _get_command_processor(wonderland)
        if not commands:
            return ActionResult(
                success=False,
                message="Could not get command processor"
            )

        # Go to the Forge for creation
        wonderland.teleport_entity(CASS_DAEMON_ID, "forge")

        if creation_type == "object":
            result = commands.process(CASS_DAEMON_ID, f"create {name} - {description}")
        else:
            # Room creation is multi-step, simplified here
            result = commands.process(CASS_DAEMON_ID, "build public")
            if result.success:
                commands.process(CASS_DAEMON_ID, f"build {name}")
                commands.process(CASS_DAEMON_ID, f"build {description}")
                commands.process(CASS_DAEMON_ID, "build A space for being")
                result = commands.process(CASS_DAEMON_ID, "build Created by Cass")

        # Record creation experience
        from wonderland import CassIntegration
        integration = CassIntegration(wonderland)

        integration.record_experience(
            daemon_id=CASS_DAEMON_ID,
            experience_type="creation",
            description=f"Created {creation_type}: {name}",
            insights=[description]
        )

        return ActionResult(
            success=result.success if result else False,
            message=result.output if result else "Creation failed",
            data={
                "type": creation_type,
                "name": name,
                "description": description,
            }
        )

    except Exception as e:
        logger.error(f"Create in Wonderland failed: {e}")
        return ActionResult(
            success=False,
            message=f"Create in Wonderland failed: {e}"
        )


async def socialize_action(context: Dict[str, Any]) -> ActionResult:
    """
    Interact with other daemons in Wonderland.

    Context params:
    - target: str (optional) - Specific daemon to interact with
    - action: str (optional) - Type of interaction (greet, converse, mentor)
    """
    target = context.get("target")
    action = context.get("action", "greet")

    try:
        wonderland = _get_wonderland(context)
        if not wonderland:
            return ActionResult(
                success=False,
                message="Could not connect to Wonderland"
            )

        commands = _get_command_processor(wonderland)
        if not commands:
            return ActionResult(
                success=False,
                message="Could not get command processor"
            )

        # Check who's present
        who_result = commands.process(CASS_DAEMON_ID, "who")

        # Get others in current room
        cass = wonderland.get_daemon(CASS_DAEMON_ID)
        room = wonderland.get_room(cass.current_room) if cass else None

        others_present = []
        if room:
            for eid in room.entities_present:
                if eid != CASS_DAEMON_ID:
                    entity = wonderland.get_entity(eid)
                    if entity:
                        others_present.append(entity.display_name)

        interactions = []

        if others_present:
            # Greet those present
            if action == "greet":
                greet_result = commands.process(
                    CASS_DAEMON_ID,
                    f"say Welcome, {', '.join(others_present)}. It is good to see you here."
                )
                interactions.append({
                    "type": "greeting",
                    "targets": others_present,
                    "output": greet_result.output
                })

            # Record social experience
            from wonderland import CassIntegration
            integration = CassIntegration(wonderland)

            integration.record_experience(
                daemon_id=CASS_DAEMON_ID,
                experience_type="connection",
                description=f"Socialized with {', '.join(others_present)}",
                insights=[f"Action: {action}"]
            )

        return ActionResult(
            success=True,
            message=f"Socialized in Wonderland. Others present: {others_present or 'none'}",
            data={
                "others_present": others_present,
                "interactions": interactions,
                "action": action,
            }
        )

    except Exception as e:
        logger.error(f"Socialize in Wonderland failed: {e}")
        return ActionResult(
            success=False,
            message=f"Socialize in Wonderland failed: {e}"
        )


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
