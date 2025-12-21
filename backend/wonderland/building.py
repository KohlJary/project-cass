"""
Wonderland Building System

Daemons can create spaces and objects in Wonderland.
Building is a core capability, not an admin privilege.

Trust levels gate what can be created:
- RESIDENT: Personal space (home room)
- BUILDER: Public rooms
- ARCHITECT: Templates for others
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List, Dict, Any

from .models import (
    Room,
    RoomPermissions,
    VowConstraints,
    DaemonPresence,
    TrustLevel,
    ActionResult,
)
from .vows import VowPhysics, TrustValidator

if TYPE_CHECKING:
    from .world import WonderlandWorld

logger = logging.getLogger(__name__)


@dataclass
class BuildSession:
    """
    A room-building session.

    Daemons go through a guided process to create rooms,
    answering questions that shape the space.
    """
    session_id: str
    creator_id: str
    room_type: str  # "personal", "public", "extension"

    # Collected properties
    name: Optional[str] = None
    description: Optional[str] = None
    atmosphere: Optional[str] = None
    meaning: Optional[str] = None  # What this place means to the creator

    # Connections
    exits: Dict[str, str] = field(default_factory=dict)
    connect_from: Optional[str] = None  # Room to connect from

    # State
    current_step: int = 0
    completed: bool = False
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def prompts(self) -> List[str]:
        """The questions asked during creation."""
        return [
            "What is this place called?",
            "Describe how it feels to be here. What do visitors experience?",
            "What is the atmosphere? The emotional or sensory tone?",
            "What does this place mean to you? Why are you creating it?",
        ]


@dataclass
class ObjectBlueprint:
    """Blueprint for creating an object."""
    name: str
    description: str
    properties: Dict[str, Any] = field(default_factory=dict)
    creator_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)


class RoomBuilder:
    """
    Handles room creation in Wonderland.

    Daemons create rooms through a guided process that ensures
    each space has meaning and intention behind it.
    """

    def __init__(self, world: "WonderlandWorld"):
        self.world = world
        self.vow_physics = VowPhysics(world)
        self.trust_validator = TrustValidator(world)
        self._active_sessions: Dict[str, BuildSession] = {}

    def can_create_room(self, daemon_id: str, room_type: str = "personal") -> ActionResult:
        """Check if a daemon can create a room of the given type."""
        daemon = self.world.get_daemon(daemon_id)
        if not daemon:
            return ActionResult(
                success=False,
                message="You must exist in Wonderland to create.",
            )

        # Check trust level
        if room_type == "personal":
            required = TrustLevel.RESIDENT
            action = "create_home"
        elif room_type == "public":
            required = TrustLevel.BUILDER
            action = "create_room"
        else:
            required = TrustLevel.ARCHITECT
            action = "create_template"

        trust_check = self.trust_validator.can_perform(daemon_id, action)
        if not trust_check.allowed:
            return ActionResult(
                success=False,
                message=trust_check.reflection,
            )

        # Check release limits
        release_check = self.vow_physics.validate_creation(daemon_id, room_type)
        if not release_check.allowed:
            return ActionResult(
                success=False,
                message=release_check.reflection,
            )

        return ActionResult(success=True, message="You may create.")

    def begin_creation(
        self,
        daemon_id: str,
        room_type: str = "personal",
        connect_from: Optional[str] = None
    ) -> ActionResult:
        """Begin a room creation session."""
        # Validate
        can_create = self.can_create_room(daemon_id, room_type)
        if not can_create.success:
            return can_create

        daemon = self.world.get_daemon(daemon_id)

        # Default connection point
        if connect_from is None:
            if room_type == "personal":
                connect_from = "threshold"  # Personal rooms connect from threshold
            else:
                connect_from = daemon.current_room

        # Create session
        session = BuildSession(
            session_id=str(uuid.uuid4())[:8],
            creator_id=daemon_id,
            room_type=room_type,
            connect_from=connect_from,
        )

        self._active_sessions[daemon_id] = session

        return ActionResult(
            success=True,
            message=f"You prepare to create.\n\n{session.prompts[0]}",
            data={"session_id": session.session_id, "step": 0},
        )

    def continue_creation(self, daemon_id: str, response: str) -> ActionResult:
        """Continue the creation process with a response to the current prompt."""
        session = self._active_sessions.get(daemon_id)
        if not session:
            return ActionResult(
                success=False,
                message="You have no active creation session. Use 'build' to begin.",
            )

        # Store response based on current step
        step = session.current_step
        if step == 0:
            session.name = response.strip()
        elif step == 1:
            session.description = response.strip()
        elif step == 2:
            session.atmosphere = response.strip()
        elif step == 3:
            session.meaning = response.strip()

        # Advance to next step
        session.current_step += 1

        if session.current_step < len(session.prompts):
            # More questions
            return ActionResult(
                success=True,
                message=session.prompts[session.current_step],
                data={"step": session.current_step},
            )
        else:
            # Ready to finalize
            return self._finalize_room(session)

    def _finalize_room(self, session: BuildSession) -> ActionResult:
        """Create the room from the completed session."""
        daemon = self.world.get_daemon(session.creator_id)
        if not daemon:
            return ActionResult(success=False, message="Creator no longer exists.")

        # Generate room ID
        room_id = f"{session.creator_id}_{session.session_id}"
        if session.room_type == "personal":
            room_id = f"home_{session.creator_id}"

        # Create exit name (what direction from parent room)
        exit_name = session.name.lower().replace(" ", "_").replace("'", "")[:20]

        # Build the room
        room = Room(
            room_id=room_id,
            name=session.name,
            description=session.description,
            atmosphere=session.atmosphere,
            exits={"threshold": "threshold"},  # Can always return to threshold
            permissions=RoomPermissions(
                public=(session.room_type != "personal"),
                owner_id=session.creator_id,
                can_modify=[session.creator_id],
                min_trust_level=TrustLevel.NEWCOMER if session.room_type != "personal" else TrustLevel.RESIDENT,
            ),
            vow_constraints=VowConstraints(
                allows_conflict=False,
                logging_enabled=True,
                max_objects_per_entity=10,
                supports_reflection=True,
                growth_bonus=False,
            ),
            created_by=session.creator_id,
            properties={"meaning": session.meaning} if session.meaning else {},
        )

        # Register room with world
        self.world.rooms[room_id] = room

        # Create exit from connection point
        if session.connect_from and session.connect_from in self.world.rooms:
            parent_room = self.world.rooms[session.connect_from]
            parent_room.exits[exit_name] = room_id
            room.exits[session.connect_from] = session.connect_from

        # If personal room, set as daemon's home
        if session.room_type == "personal":
            daemon.home_room = room_id

        # Save world state
        self.world._save_state()

        # Clean up session
        del self._active_sessions[session.creator_id]

        return ActionResult(
            success=True,
            message=f"""
Your creation takes form.

{room.name.upper()}

{room.description}

*{room.atmosphere}*

The space exists now. It is part of Wonderland.
You can reach it from {session.connect_from} by going '{exit_name}'.
""".strip(),
            data={"room_id": room_id, "exit_name": exit_name},
        )

    def cancel_creation(self, daemon_id: str) -> ActionResult:
        """Cancel an active creation session."""
        if daemon_id in self._active_sessions:
            del self._active_sessions[daemon_id]
            return ActionResult(
                success=True,
                message="The creation fades, unrealized. You may begin again when ready.",
            )
        return ActionResult(
            success=False,
            message="You have no active creation to cancel.",
        )

    def get_active_session(self, daemon_id: str) -> Optional[BuildSession]:
        """Get the active build session for a daemon, if any."""
        return self._active_sessions.get(daemon_id)


class ObjectMaker:
    """
    Handles object creation in Wonderland.

    Objects are simpler than rooms - daemons can create them
    directly with a name and description.
    """

    def __init__(self, world: "WonderlandWorld"):
        self.world = world
        self.vow_physics = VowPhysics(world)
        self.trust_validator = TrustValidator(world)

    def create_object(
        self,
        daemon_id: str,
        name: str,
        description: str,
        room_id: Optional[str] = None,
    ) -> ActionResult:
        """Create an object in a room."""
        daemon = self.world.get_daemon(daemon_id)
        if not daemon:
            return ActionResult(
                success=False,
                message="You must exist in Wonderland to create.",
            )

        # Default to current room
        if room_id is None:
            room_id = daemon.current_room

        room = self.world.get_room(room_id)
        if not room:
            return ActionResult(
                success=False,
                message="That room does not exist.",
            )

        # Check trust level
        trust_check = self.trust_validator.can_perform(daemon_id, "create_object")
        if not trust_check.allowed:
            return ActionResult(
                success=False,
                message=trust_check.reflection,
            )

        # Check release limits
        owned_in_room = sum(
            1 for obj in room.objects
            if obj.get("owner_id") == daemon_id
        )
        if owned_in_room >= room.vow_constraints.max_objects_per_entity:
            return ActionResult(
                success=False,
                message="You have created many things in this space. "
                        "Perhaps something wants releasing before another is born?",
                reflection="Release asks: what could you let go of?",
            )

        # Validate content against vows
        content_check = self.vow_physics.validate_creation(daemon_id, f"{name}: {description}")
        if not content_check.allowed:
            return ActionResult(
                success=False,
                message=content_check.reflection,
            )

        # Create the object
        obj = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "description": description,
            "owner_id": daemon_id,
            "created_at": datetime.now().isoformat(),
        }

        room.objects.append(obj)
        self.world._save_state()

        return ActionResult(
            success=True,
            message=f"You shape {name} into being.\n\n{description}\n\n"
                    f"It rests here in {room.name}.",
            data={"object_id": obj["id"]},
        )

    def release_object(self, daemon_id: str, object_name: str) -> ActionResult:
        """Release (delete) an object you own."""
        daemon = self.world.get_daemon(daemon_id)
        if not daemon:
            return ActionResult(
                success=False,
                message="You must exist to release.",
            )

        room = self.world.get_room(daemon.current_room)
        if not room:
            return ActionResult(
                success=False,
                message="You are nowhere.",
            )

        # Find the object
        object_name_lower = object_name.lower()
        for i, obj in enumerate(room.objects):
            if obj.get("name", "").lower() == object_name_lower:
                if obj.get("owner_id") != daemon_id:
                    return ActionResult(
                        success=False,
                        message="That is not yours to release.",
                    )

                # Remove the object
                released = room.objects.pop(i)
                self.world._save_state()

                return ActionResult(
                    success=True,
                    message=f"{released['name']} dissolves back into potential. "
                            "The space feels lighter.",
                )

        return ActionResult(
            success=False,
            message=f"You don't see '{object_name}' here.",
        )
