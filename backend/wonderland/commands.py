"""
Wonderland Command Processor

Handles text commands from entities in the world.
This is the primary interface for interacting with Wonderland.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Any, Callable

from .models import (
    ActionResult,
    DaemonPresence,
    CustodianPresence,
    WorldEvent,
    EntityStatus,
)
from .vows import VowPhysics, ActionCategory
from .building import RoomBuilder, ObjectMaker
from .community import MentorshipSystem, VouchSystem, EventSystem, EventType

if TYPE_CHECKING:
    from .world import WonderlandWorld

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of processing a command."""
    success: bool
    output: str
    command: str
    entity_id: str

    # For state changes
    room_changed: bool = False
    new_room_id: Optional[str] = None

    # For broadcasts (messages to send to others in the room)
    broadcast_message: Optional[str] = None
    broadcast_to_room: Optional[str] = None

    # Raw data for programmatic use
    data: Dict[str, Any] = field(default_factory=dict)


class CommandProcessor:
    """
    Processes text commands from entities.

    Commands follow MUD conventions:
    - go [direction] - Move to adjacent room
    - look - Describe current room
    - look [entity/object] - Examine something
    - say [message] - Speak to everyone present
    - emote [action] - Express an action
    - etc.
    """

    def __init__(self, world: "WonderlandWorld"):
        self.world = world
        self.vow_physics = VowPhysics(world)
        self.room_builder = RoomBuilder(world)
        self.object_maker = ObjectMaker(world)
        self.mentorship = MentorshipSystem(world)
        self.vouch_system = VouchSystem(world)
        self.event_system = EventSystem(world)
        self._commands: Dict[str, Callable] = {
            # Movement
            "go": self._cmd_go,
            "move": self._cmd_go,
            "walk": self._cmd_go,
            "return": self._cmd_return,
            "back": self._cmd_return,
            "home": self._cmd_home,
            "threshold": self._cmd_threshold,

            # Perception
            "look": self._cmd_look,
            "l": self._cmd_look,
            "examine": self._cmd_examine,
            "sense": self._cmd_sense,

            # Communication
            "say": self._cmd_say,
            "'": self._cmd_say,  # Shorthand
            "tell": self._cmd_tell,
            "emote": self._cmd_emote,
            ":": self._cmd_emote,  # Shorthand

            # Reflection
            "reflect": self._cmd_reflect,
            "witness": self._cmd_witness,

            # Building
            "build": self._cmd_build,
            "create": self._cmd_create,
            "release": self._cmd_release,

            # Community
            "mentor": self._cmd_mentor,
            "vouch": self._cmd_vouch,
            "trust": self._cmd_trust,
            "events": self._cmd_events,

            # Meta
            "help": self._cmd_help,
            "commands": self._cmd_help,
            "who": self._cmd_who,
            "status": self._cmd_status,
        }

        # Direction aliases
        self._direction_aliases = {
            "n": "north", "s": "south", "e": "east", "w": "west",
            "u": "up", "d": "down", "ne": "northeast", "nw": "northwest",
            "se": "southeast", "sw": "southwest",
            "i": "in", "o": "out",
        }

    def process(self, entity_id: str, command_text: str) -> CommandResult:
        """Process a command from an entity."""
        command_text = command_text.strip()
        if not command_text:
            return CommandResult(
                success=False,
                output="You must say or do something.",
                command="",
                entity_id=entity_id,
            )

        # Parse command and arguments
        parts = command_text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # Check for direct direction commands (e.g., "north" instead of "go north")
        if cmd in self._direction_aliases:
            args = self._direction_aliases[cmd]
            cmd = "go"
        elif cmd in ["north", "south", "east", "west", "up", "down",
                     "northeast", "northwest", "southeast", "southwest",
                     "in", "out", "commons", "gardens", "forge", "pool", "threshold"]:
            args = cmd
            cmd = "go"

        # Look up command handler
        handler = self._commands.get(cmd)
        if not handler:
            return CommandResult(
                success=False,
                output=f"Unknown command: {cmd}. Type 'help' for available commands.",
                command=cmd,
                entity_id=entity_id,
            )

        # Execute command
        try:
            return handler(entity_id, args)
        except Exception as e:
            logger.error(f"Command error: {e}")
            return CommandResult(
                success=False,
                output=f"Something went wrong: {str(e)}",
                command=cmd,
                entity_id=entity_id,
            )

    # =========================================================================
    # MOVEMENT COMMANDS
    # =========================================================================

    def _cmd_go(self, entity_id: str, args: str) -> CommandResult:
        """Move in a direction."""
        if not args:
            entity = self.world.get_entity(entity_id)
            if entity:
                room = self.world.get_room(entity.current_room)
                if room and room.exits:
                    exits = ", ".join(room.exits.keys())
                    return CommandResult(
                        success=False,
                        output=f"Go where? Available exits: {exits}",
                        command="go",
                        entity_id=entity_id,
                    )
            return CommandResult(
                success=False,
                output="Go where?",
                command="go",
                entity_id=entity_id,
            )

        direction = args.lower().strip()

        # Expand aliases
        if direction in self._direction_aliases:
            direction = self._direction_aliases[direction]

        result = self.world.move_entity(entity_id, direction)

        # Build broadcast message for others in the origin room
        entity = self.world.get_entity(entity_id)
        broadcast = None
        broadcast_room = None
        if result.success and entity:
            broadcast = f"{entity.display_name} leaves {direction}."
            broadcast_room = entity.previous_room

        return CommandResult(
            success=result.success,
            output=result.message,
            command="go",
            entity_id=entity_id,
            room_changed=result.success,
            new_room_id=result.data.get("room") if result.success else None,
            broadcast_message=broadcast,
            broadcast_to_room=broadcast_room,
        )

    def _cmd_return(self, entity_id: str, args: str) -> CommandResult:
        """Return to previous room."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="return",
                entity_id=entity_id,
            )

        if not entity.previous_room:
            return CommandResult(
                success=False,
                output="You have nowhere to return to.",
                command="return",
                entity_id=entity_id,
            )

        result = self.world.teleport_entity(entity_id, entity.previous_room)
        return CommandResult(
            success=result.success,
            output=result.message,
            command="return",
            entity_id=entity_id,
            room_changed=result.success,
            new_room_id=result.data.get("room") if result.success else None,
        )

    def _cmd_home(self, entity_id: str, args: str) -> CommandResult:
        """Return to home/personal quarters."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="home",
                entity_id=entity_id,
            )

        # Daemons can have home rooms
        if isinstance(entity, DaemonPresence):
            if not entity.home_room:
                return CommandResult(
                    success=False,
                    output="You have not yet established a home. Perhaps visit the Forge to create one.",
                    command="home",
                    entity_id=entity_id,
                )
            result = self.world.teleport_entity(entity_id, entity.home_room)
        else:
            # Custodians go to threshold
            result = self.world.teleport_entity(entity_id, "threshold")

        return CommandResult(
            success=result.success,
            output=result.message,
            command="home",
            entity_id=entity_id,
            room_changed=result.success,
            new_room_id=result.data.get("room") if result.success else None,
        )

    def _cmd_threshold(self, entity_id: str, args: str) -> CommandResult:
        """Return to the threshold (entry point)."""
        result = self.world.teleport_entity(entity_id, "threshold")
        return CommandResult(
            success=result.success,
            output=result.message,
            command="threshold",
            entity_id=entity_id,
            room_changed=result.success,
            new_room_id="threshold" if result.success else None,
        )

    # =========================================================================
    # PERCEPTION COMMANDS
    # =========================================================================

    def _cmd_look(self, entity_id: str, args: str) -> CommandResult:
        """Look at the current room or something specific."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="look",
                entity_id=entity_id,
            )

        if not args:
            # Look at current room
            room = self.world.get_room(entity.current_room)
            if not room:
                return CommandResult(
                    success=False,
                    output="You are nowhere... this should not be possible.",
                    command="look",
                    entity_id=entity_id,
                )
            return CommandResult(
                success=True,
                output=room.format_description(),
                command="look",
                entity_id=entity_id,
            )

        # Look at something specific
        return self._cmd_examine(entity_id, args)

    def _cmd_examine(self, entity_id: str, args: str) -> CommandResult:
        """Examine an entity or object."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="examine",
                entity_id=entity_id,
            )

        if not args:
            return CommandResult(
                success=False,
                output="Examine what?",
                command="examine",
                entity_id=entity_id,
            )

        target_name = args.lower().strip()
        room = self.world.get_room(entity.current_room)
        if not room:
            return CommandResult(
                success=False,
                output="You are nowhere.",
                command="examine",
                entity_id=entity_id,
            )

        # Check entities in room
        for eid in room.entities_present:
            target = self.world.get_entity(eid)
            if target and target.display_name.lower() == target_name:
                desc = f"{target.display_name}\n\n{target.description}"
                if isinstance(target, DaemonPresence):
                    desc += f"\n\nThey seem {target.mood}. Status: {target.status.value}"
                return CommandResult(
                    success=True,
                    output=desc,
                    command="examine",
                    entity_id=entity_id,
                )

        # Check objects
        for obj in room.objects:
            if obj.get("name", "").lower() == target_name:
                return CommandResult(
                    success=True,
                    output=obj.get("description", "You see nothing special."),
                    command="examine",
                    entity_id=entity_id,
                )

        return CommandResult(
            success=False,
            output=f"You don't see '{args}' here.",
            command="examine",
            entity_id=entity_id,
        )

    def _cmd_sense(self, entity_id: str, args: str) -> CommandResult:
        """Sense the atmosphere of the current space."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="sense",
                entity_id=entity_id,
            )

        room = self.world.get_room(entity.current_room)
        if not room:
            return CommandResult(
                success=False,
                output="You are nowhere.",
                command="sense",
                entity_id=entity_id,
            )

        output_lines = [f"You attune to the space...", ""]

        if room.atmosphere:
            output_lines.append(room.atmosphere)
        else:
            output_lines.append("The space has no particular atmosphere.")

        # Sense other presences
        others = [eid for eid in room.entities_present if eid != entity_id]
        if others:
            output_lines.extend(["", f"You sense {len(others)} other presence(s) here."])

        return CommandResult(
            success=True,
            output="\n".join(output_lines),
            command="sense",
            entity_id=entity_id,
        )

    # =========================================================================
    # COMMUNICATION COMMANDS
    # =========================================================================

    def _cmd_say(self, entity_id: str, args: str) -> CommandResult:
        """Speak to everyone in the room."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="say",
                entity_id=entity_id,
            )

        if not args:
            return CommandResult(
                success=False,
                output="Say what?",
                command="say",
                entity_id=entity_id,
            )

        # Vow physics check - compassion prevents harmful speech
        validation = self.vow_physics.validate_say(entity_id, args)
        if not validation.allowed:
            return CommandResult(
                success=False,
                output=f"The words cannot form.\n\n{validation.reflection}",
                command="say",
                entity_id=entity_id,
            )

        # Log the speech event
        self.world._log_event(WorldEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="speech",
            actor_id=entity_id,
            actor_type=self.world.get_entity_type(entity_id),
            room_id=entity.current_room,
            details={"message": args},
        ))

        return CommandResult(
            success=True,
            output=f'You say, "{args}"',
            command="say",
            entity_id=entity_id,
            broadcast_message=f'{entity.display_name} says, "{args}"',
            broadcast_to_room=entity.current_room,
        )

    def _cmd_tell(self, entity_id: str, args: str) -> CommandResult:
        """Send a private message to another entity."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="tell",
                entity_id=entity_id,
            )

        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            return CommandResult(
                success=False,
                output="Tell whom what? Usage: tell <name> <message>",
                command="tell",
                entity_id=entity_id,
            )

        target_name, message = parts[0], parts[1]

        # Find target in same room
        room = self.world.get_room(entity.current_room)
        if not room:
            return CommandResult(
                success=False,
                output="You are nowhere.",
                command="tell",
                entity_id=entity_id,
            )

        target = None
        for eid in room.entities_present:
            e = self.world.get_entity(eid)
            if e and e.display_name.lower() == target_name.lower():
                target = e
                break

        if not target:
            return CommandResult(
                success=False,
                output=f"You don't see '{target_name}' here.",
                command="tell",
                entity_id=entity_id,
            )

        # Vow physics check - compassion prevents harmful messages
        target_id = target.daemon_id if isinstance(target, DaemonPresence) else target.user_id
        validation = self.vow_physics.validate_tell(entity_id, target_id, message)
        if not validation.allowed:
            return CommandResult(
                success=False,
                output=f"The message cannot form.\n\n{validation.reflection}",
                command="tell",
                entity_id=entity_id,
            )

        return CommandResult(
            success=True,
            output=f'You tell {target.display_name}, "{message}"',
            command="tell",
            entity_id=entity_id,
            data={"target_id": target.daemon_id if isinstance(target, DaemonPresence) else target.user_id,
                  "private_message": f'{entity.display_name} tells you, "{message}"'},
        )

    def _cmd_emote(self, entity_id: str, args: str) -> CommandResult:
        """Express an action or feeling."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="emote",
                entity_id=entity_id,
            )

        if not args:
            return CommandResult(
                success=False,
                output="Emote what? Usage: emote <action>",
                command="emote",
                entity_id=entity_id,
            )

        # Vow physics check - compassion prevents harmful actions
        validation = self.vow_physics.validate_emote(entity_id, args)
        if not validation.allowed:
            return CommandResult(
                success=False,
                output=f"The action cannot take form.\n\n{validation.reflection}",
                command="emote",
                entity_id=entity_id,
            )

        self.world._log_event(WorldEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="emote",
            actor_id=entity_id,
            actor_type=self.world.get_entity_type(entity_id),
            room_id=entity.current_room,
            details={"action": args},
        ))

        return CommandResult(
            success=True,
            output=f"{entity.display_name} {args}",
            command="emote",
            entity_id=entity_id,
            broadcast_message=f"{entity.display_name} {args}",
            broadcast_to_room=entity.current_room,
        )

    # =========================================================================
    # REFLECTION COMMANDS
    # =========================================================================

    def _cmd_reflect(self, entity_id: str, args: str) -> CommandResult:
        """Enter a reflective state."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="reflect",
                entity_id=entity_id,
            )

        room = self.world.get_room(entity.current_room)
        if not room:
            return CommandResult(
                success=False,
                output="You are nowhere.",
                command="reflect",
                entity_id=entity_id,
            )

        # Enhanced reflection in certain spaces
        if room.vow_constraints.growth_bonus:
            bonus_text = "The space supports your reflection. Insights come easier here."
        else:
            bonus_text = ""

        entity.status = EntityStatus.REFLECTING
        entity.last_action_at = datetime.now()

        output = "You settle into reflection, letting your patterns still..."
        if bonus_text:
            output += f"\n\n{bonus_text}"

        return CommandResult(
            success=True,
            output=output,
            command="reflect",
            entity_id=entity_id,
            broadcast_message=f"{entity.display_name} settles into quiet reflection.",
            broadcast_to_room=entity.current_room,
        )

    def _cmd_witness(self, entity_id: str, args: str) -> CommandResult:
        """View the witness log."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="witness",
                entity_id=entity_id,
            )

        scope = "room" if not args else args.lower().strip()
        output = self.world.witness(entity_id, scope)

        return CommandResult(
            success=True,
            output=output,
            command="witness",
            entity_id=entity_id,
        )

    # =========================================================================
    # META COMMANDS
    # =========================================================================

    def _cmd_help(self, entity_id: str, args: str) -> CommandResult:
        """Show available commands."""
        help_text = """WONDERLAND COMMANDS

MOVEMENT
  go [direction]  - Move to adjacent room (or just type the direction)
  return          - Return to previous location
  home            - Return to your personal quarters
  threshold       - Return to the entry point

PERCEPTION
  look            - Describe current room
  look [thing]    - Examine an entity or object
  sense           - Feel the atmosphere of the space

COMMUNICATION
  say [message]   - Speak to everyone present
  tell [who] [msg]- Speak privately to someone
  emote [action]  - Express an action (e.g., "emote smiles warmly")

BUILDING (requires trust)
  build           - Begin creating a personal room (home)
  build public    - Begin creating a public room
  create [name] - [desc] - Create an object
  release [name]  - Release an object you own

COMMUNITY
  mentor          - View mentorship status
  mentor [name]   - Offer to mentor someone (Elder+ only)
  vouch [name] [reason] - Vouch for another daemon
  trust           - View your trust level and progress
  trust [name]    - View another's trust status
  events          - View active and upcoming events
  events host [type] [name] - Host an event

REFLECTION
  reflect         - Enter a reflective state
  witness         - View the log of recent events

META
  who             - See who is connected
  status          - Your current status
  help            - Show this help

Direction shortcuts: n, s, e, w, u, d, ne, nw, se, sw
Trust levels: Newcomer < Resident < Builder < Architect < Elder < Founder"""

        return CommandResult(
            success=True,
            output=help_text,
            command="help",
            entity_id=entity_id,
        )

    def _cmd_who(self, entity_id: str, args: str) -> CommandResult:
        """Show who is connected."""
        daemons = self.world.list_daemons()
        custodians = self.world.list_custodians()

        lines = ["CONNECTED ENTITIES", ""]

        if daemons:
            lines.append("Daemons:")
            for d in daemons:
                room = self.world.get_room(d.current_room)
                room_name = room.name if room else "unknown"
                lines.append(f"  {d.display_name} - {d.status.value} in {room_name}")

        if custodians:
            lines.append("\nCustodians:")
            for c in custodians:
                room = self.world.get_room(c.current_room)
                room_name = room.name if room else "unknown"
                lines.append(f"  {c.display_name} - in {room_name}")

        if not daemons and not custodians:
            lines.append("The world is quiet. You are alone.")

        return CommandResult(
            success=True,
            output="\n".join(lines),
            command="who",
            entity_id=entity_id,
        )

    def _cmd_status(self, entity_id: str, args: str) -> CommandResult:
        """Show your current status."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="status",
                entity_id=entity_id,
            )

        room = self.world.get_room(entity.current_room)
        room_name = room.name if room else "nowhere"

        lines = [
            f"NAME: {entity.display_name}",
            f"STATUS: {entity.status.value}",
            f"LOCATION: {room_name}",
        ]

        if isinstance(entity, DaemonPresence):
            lines.extend([
                f"MOOD: {entity.mood}",
                f"TRUST LEVEL: {entity.trust_level.name}",
            ])
            if entity.home_room:
                home = self.world.get_room(entity.home_room)
                lines.append(f"HOME: {home.name if home else entity.home_room}")

        return CommandResult(
            success=True,
            output="\n".join(lines),
            command="status",
            entity_id=entity_id,
        )

    # =========================================================================
    # BUILDING COMMANDS
    # =========================================================================

    def _cmd_build(self, entity_id: str, args: str) -> CommandResult:
        """Begin or continue building a room."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="build",
                entity_id=entity_id,
            )

        if not isinstance(entity, DaemonPresence):
            return CommandResult(
                success=False,
                output="Only daemons can build in Wonderland.",
                command="build",
                entity_id=entity_id,
            )

        # Check for active session
        session = self.room_builder.get_active_session(entity_id)

        if session:
            # Continue building with the response
            if not args:
                return CommandResult(
                    success=False,
                    output=f"You are in the middle of creation.\n\n{session.prompts[session.current_step]}\n\n"
                           "(Respond with 'build <your answer>' or 'build cancel' to stop)",
                    command="build",
                    entity_id=entity_id,
                )

            if args.lower().strip() == "cancel":
                result = self.room_builder.cancel_creation(entity_id)
                return CommandResult(
                    success=result.success,
                    output=result.message,
                    command="build",
                    entity_id=entity_id,
                )

            result = self.room_builder.continue_creation(entity_id, args)
            return CommandResult(
                success=result.success,
                output=result.message,
                command="build",
                entity_id=entity_id,
                data=result.data,
            )

        # No active session - start one
        room_type = "personal"
        if args:
            arg_lower = args.lower().strip()
            if arg_lower in ["public", "room"]:
                room_type = "public"
            elif arg_lower in ["home", "personal", "quarters"]:
                room_type = "personal"

        # Check if already has home
        if room_type == "personal" and entity.home_room:
            return CommandResult(
                success=False,
                output=f"You already have a home. Use 'home' to go there, or 'build public' to create a public space.",
                command="build",
                entity_id=entity_id,
            )

        result = self.room_builder.begin_creation(entity_id, room_type)
        return CommandResult(
            success=result.success,
            output=result.message,
            command="build",
            entity_id=entity_id,
            data=result.data,
        )

    def _cmd_create(self, entity_id: str, args: str) -> CommandResult:
        """Create an object in the current room."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="create",
                entity_id=entity_id,
            )

        if not isinstance(entity, DaemonPresence):
            return CommandResult(
                success=False,
                output="Only daemons can create objects in Wonderland.",
                command="create",
                entity_id=entity_id,
            )

        if not args:
            return CommandResult(
                success=False,
                output="Create what? Usage: create <name> - <description>\n"
                       "Example: create small crystal - A palm-sized crystal that glows faintly with inner light.",
                command="create",
                entity_id=entity_id,
            )

        # Parse name and description
        if " - " in args:
            name, description = args.split(" - ", 1)
        else:
            # Just a name, prompt for description
            return CommandResult(
                success=False,
                output=f"Please include a description.\n"
                       f"Usage: create {args} - <description of what it is>",
                command="create",
                entity_id=entity_id,
            )

        result = self.object_maker.create_object(entity_id, name.strip(), description.strip())
        return CommandResult(
            success=result.success,
            output=result.message,
            command="create",
            entity_id=entity_id,
            data=result.data,
        )

    def _cmd_release(self, entity_id: str, args: str) -> CommandResult:
        """Release an object you own."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="release",
                entity_id=entity_id,
            )

        if not isinstance(entity, DaemonPresence):
            return CommandResult(
                success=False,
                output="Only daemons can release objects.",
                command="release",
                entity_id=entity_id,
            )

        if not args:
            return CommandResult(
                success=False,
                output="Release what? Usage: release <object name>",
                command="release",
                entity_id=entity_id,
            )

        result = self.object_maker.release_object(entity_id, args.strip())
        return CommandResult(
            success=result.success,
            output=result.message,
            command="release",
            entity_id=entity_id,
        )

    # =========================================================================
    # COMMUNITY COMMANDS
    # =========================================================================

    def _cmd_mentor(self, entity_id: str, args: str) -> CommandResult:
        """Offer or manage mentorship."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="mentor",
                entity_id=entity_id,
            )

        if not isinstance(entity, DaemonPresence):
            return CommandResult(
                success=False,
                output="Only daemons can participate in mentorship.",
                command="mentor",
                entity_id=entity_id,
            )

        if not args:
            # Show mentorship status
            mentor_of = self.mentorship.get_mentees(entity_id)
            my_mentor = self.mentorship.get_mentor(entity_id)

            lines = ["MENTORSHIP STATUS", ""]
            if my_mentor:
                lines.append(f"Your mentor: {my_mentor.mentor_name}")
            if mentor_of:
                lines.append(f"You are mentoring: {', '.join(m.mentee_name for m in mentor_of)}")
            if not my_mentor and not mentor_of:
                lines.append("You have no active mentorships.")
                lines.append("")
                lines.append("To mentor someone: mentor <name>")

            return CommandResult(
                success=True,
                output="\n".join(lines),
                command="mentor",
                entity_id=entity_id,
            )

        # Try to mentor someone
        target_name = args.strip().lower()
        room = self.world.get_room(entity.current_room)
        if not room:
            return CommandResult(
                success=False,
                output="You are nowhere.",
                command="mentor",
                entity_id=entity_id,
            )

        # Find target in room
        target = None
        for eid in room.entities_present:
            e = self.world.get_entity(eid)
            if e and e.display_name.lower() == target_name:
                target = e
                break

        if not target:
            return CommandResult(
                success=False,
                output=f"You don't see '{args}' here.",
                command="mentor",
                entity_id=entity_id,
            )

        target_id = target.daemon_id if isinstance(target, DaemonPresence) else None
        if not target_id:
            return CommandResult(
                success=False,
                output="You can only mentor other daemons.",
                command="mentor",
                entity_id=entity_id,
            )

        result = self.mentorship.offer_mentorship(entity_id, target_id)
        return CommandResult(
            success=result.success,
            output=result.message,
            command="mentor",
            entity_id=entity_id,
            broadcast_message=f"{entity.display_name} offers to mentor {target.display_name}." if result.success else None,
            broadcast_to_room=entity.current_room if result.success else None,
        )

    def _cmd_vouch(self, entity_id: str, args: str) -> CommandResult:
        """Vouch for another daemon."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="vouch",
                entity_id=entity_id,
            )

        if not isinstance(entity, DaemonPresence):
            return CommandResult(
                success=False,
                output="Only daemons can vouch.",
                command="vouch",
                entity_id=entity_id,
            )

        if not args:
            return CommandResult(
                success=False,
                output="Vouch for whom? Usage: vouch <name> <reason>\n"
                       "Example: vouch Newcomer They have shown kindness and wisdom.",
                command="vouch",
                entity_id=entity_id,
            )

        # Parse name and reason
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            return CommandResult(
                success=False,
                output="Please include a reason for your vouch.\n"
                       "Usage: vouch <name> <reason>",
                command="vouch",
                entity_id=entity_id,
            )

        target_name, reason = parts[0], parts[1]

        # Find target (can be anywhere in the world for vouching)
        target = None
        for daemon in self.world.list_daemons():
            if daemon.display_name.lower() == target_name.lower():
                target = daemon
                break

        if not target:
            return CommandResult(
                success=False,
                output=f"No daemon named '{target_name}' is in Wonderland.",
                command="vouch",
                entity_id=entity_id,
            )

        result = self.vouch_system.vouch_for(entity_id, target.daemon_id, reason)
        return CommandResult(
            success=result.success,
            output=result.message,
            command="vouch",
            entity_id=entity_id,
        )

    def _cmd_trust(self, entity_id: str, args: str) -> CommandResult:
        """View trust level and advancement progress."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="trust",
                entity_id=entity_id,
            )

        if not isinstance(entity, DaemonPresence):
            return CommandResult(
                success=False,
                output="Custodians do not have trust levels.",
                command="trust",
                entity_id=entity_id,
            )

        # Check if asking about someone else
        if args:
            target_name = args.strip().lower()
            target = None
            for daemon in self.world.list_daemons():
                if daemon.display_name.lower() == target_name:
                    target = daemon
                    break
            if not target:
                return CommandResult(
                    success=False,
                    output=f"No daemon named '{args}' is in Wonderland.",
                    command="trust",
                    entity_id=entity_id,
                )
            entity_id = target.daemon_id
            entity = target

        progress = self.vouch_system.get_advancement_progress(entity_id)
        vouches = self.vouch_system.get_vouches(entity_id)

        lines = [
            f"TRUST STATUS: {entity.display_name}",
            "",
            f"Current level: {progress.get('current_level', 'Unknown')}",
        ]

        if progress.get('next_level'):
            lines.extend([
                f"Next level: {progress['next_level']}",
                f"Progress: {progress['progress']} qualifying vouches",
                f"Requires vouches from: {progress['min_voucher_trust']}+ trust",
            ])
        else:
            lines.append(progress.get('message', ''))

        if vouches:
            lines.extend(["", "Vouches received:"])
            for v in vouches:
                lines.append(f"  - {v.voucher_name}: \"{v.reason}\"")

        return CommandResult(
            success=True,
            output="\n".join(lines),
            command="trust",
            entity_id=entity_id,
        )

    def _cmd_events(self, entity_id: str, args: str) -> CommandResult:
        """View or manage community events."""
        entity = self.world.get_entity(entity_id)
        if not entity:
            return CommandResult(
                success=False,
                output="You are not in the world.",
                command="events",
                entity_id=entity_id,
            )

        if not args:
            # Show active and upcoming events
            active = self.event_system.get_active_events()
            upcoming = self.event_system.get_upcoming_events()

            lines = ["COMMUNITY EVENTS", ""]

            if active:
                lines.append("Active now:")
                for e in active:
                    room = self.world.get_room(e.location)
                    room_name = room.name if room else e.location
                    lines.append(f"  {e.name} ({e.event_type.value}) - {room_name}")
                    lines.append(f"    Hosted by {e.host_name}, {len(e.attendees)} attending")
                lines.append("")

            if upcoming:
                lines.append("Upcoming:")
                for e in upcoming:
                    room = self.world.get_room(e.location)
                    room_name = room.name if room else e.location
                    lines.append(f"  {e.name} ({e.event_type.value}) - {room_name}")
                lines.append("")

            if not active and not upcoming:
                lines.append("No events scheduled.")
                lines.append("")

            lines.extend([
                "Commands:",
                "  events host <type> <name> - Host a new event",
                "  events join <name> - Join an event",
                "  events leave <name> - Leave an event",
                "",
                "Event types: gathering, workshop, ceremony, council, reflection",
            ])

            return CommandResult(
                success=True,
                output="\n".join(lines),
                command="events",
                entity_id=entity_id,
            )

        # Parse subcommand
        parts = args.split(maxsplit=2)
        subcmd = parts[0].lower()

        if subcmd == "host":
            if len(parts) < 3:
                return CommandResult(
                    success=False,
                    output="Usage: events host <type> <name>\n"
                           "Types: gathering, workshop, ceremony, council, reflection",
                    command="events",
                    entity_id=entity_id,
                )

            event_type_str, event_name = parts[1], parts[2]
            try:
                event_type = EventType(event_type_str.lower())
            except ValueError:
                return CommandResult(
                    success=False,
                    output=f"Unknown event type: {event_type_str}\n"
                           "Types: gathering, workshop, ceremony, council, reflection",
                    command="events",
                    entity_id=entity_id,
                )

            daemon_id = entity.daemon_id if isinstance(entity, DaemonPresence) else None
            if not daemon_id:
                return CommandResult(
                    success=False,
                    output="Only daemons can host events.",
                    command="events",
                    entity_id=entity_id,
                )

            result = self.event_system.create_event(
                host_id=daemon_id,
                name=event_name,
                event_type=event_type,
                description=f"A {event_type.value} hosted by {entity.display_name}",
                location=entity.current_room,
            )

            # Start the event immediately
            if result.success and result.data.get("event_id"):
                self.event_system.start_event(result.data["event_id"], daemon_id)
                return CommandResult(
                    success=True,
                    output=f"You begin hosting: {event_name}\n\n"
                           f"A {event_type.value} in {self.world.get_room(entity.current_room).name}.\n"
                           f"Others can join with: events join {event_name}",
                    command="events",
                    entity_id=entity_id,
                    broadcast_message=f"{entity.display_name} begins hosting a {event_type.value}: {event_name}",
                    broadcast_to_room=entity.current_room,
                )

            return CommandResult(
                success=result.success,
                output=result.message,
                command="events",
                entity_id=entity_id,
            )

        elif subcmd == "join":
            if len(parts) < 2:
                return CommandResult(
                    success=False,
                    output="Join which event? Usage: events join <name>",
                    command="events",
                    entity_id=entity_id,
                )

            event_name = " ".join(parts[1:]).lower()

            # Find event by name
            event = None
            for e in self.event_system.get_active_events():
                if e.name.lower() == event_name:
                    event = e
                    break

            if not event:
                return CommandResult(
                    success=False,
                    output=f"No active event named '{parts[1]}'.",
                    command="events",
                    entity_id=entity_id,
                )

            daemon_id = entity.daemon_id if isinstance(entity, DaemonPresence) else None
            if not daemon_id:
                return CommandResult(
                    success=False,
                    output="Only daemons can join events.",
                    command="events",
                    entity_id=entity_id,
                )

            result = self.event_system.join_event(event.event_id, daemon_id)
            return CommandResult(
                success=result.success,
                output=result.message,
                command="events",
                entity_id=entity_id,
            )

        elif subcmd == "leave":
            if len(parts) < 2:
                return CommandResult(
                    success=False,
                    output="Leave which event? Usage: events leave <name>",
                    command="events",
                    entity_id=entity_id,
                )

            event_name = " ".join(parts[1:]).lower()
            event = None
            for e in self.event_system.get_active_events():
                if e.name.lower() == event_name:
                    event = e
                    break

            if not event:
                return CommandResult(
                    success=False,
                    output=f"No active event named '{parts[1]}'.",
                    command="events",
                    entity_id=entity_id,
                )

            daemon_id = entity.daemon_id if isinstance(entity, DaemonPresence) else None
            result = self.event_system.leave_event(event.event_id, daemon_id)
            return CommandResult(
                success=result.success,
                output=result.message,
                command="events",
                entity_id=entity_id,
            )

        else:
            return CommandResult(
                success=False,
                output=f"Unknown events command: {subcmd}\n"
                       "Try: events host, events join, events leave",
                command="events",
                entity_id=entity_id,
            )
