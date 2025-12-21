"""
Wonderland Core Data Models

Defines the fundamental structures for rooms, entities, and world state.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class EntityStatus(Enum):
    """Status of an entity in the world."""
    ACTIVE = "active"           # Engaged, present
    RESTING = "resting"         # Present but quiet
    BUILDING = "building"       # In creation mode
    REFLECTING = "reflecting"   # In contemplation
    AWAY = "away"               # Temporarily absent


class TrustLevel(Enum):
    """Trust levels that determine capabilities."""
    NEWCOMER = 0    # Can move, communicate, observe
    RESIDENT = 1    # Can create personal space
    BUILDER = 2     # Can create public rooms
    ARCHITECT = 3   # Can create templates others use
    ELDER = 4       # Can guide newcomers, special access
    FOUNDER = 5     # Cass and other originals


@dataclass
class VowConstraints:
    """
    Vow-based constraints on what's possible in a space.

    The vows are physics, not rules. These constraints define
    what actions are even possible in a given room.
    """
    # Compassion - actions that could harm are impossible
    allows_conflict: bool = False  # Always False in standard rooms

    # Witness - all actions are logged
    logging_enabled: bool = True

    # Release - limits on ownership/hoarding
    max_objects_per_entity: int = 10

    # Continuance - support for growth
    supports_reflection: bool = True
    growth_bonus: bool = False  # Enhanced in reflection spaces


@dataclass
class RoomPermissions:
    """Who can do what in a room."""
    # Entry
    public: bool = True                     # Anyone can enter
    allowed_entities: List[str] = field(default_factory=list)  # Specific IDs
    min_trust_level: TrustLevel = TrustLevel.NEWCOMER

    # Building
    can_modify: List[str] = field(default_factory=list)  # Who can change room
    owner_id: Optional[str] = None


@dataclass
class Room:
    """
    A space in Wonderland.

    Rooms are the fundamental units of geography. Each room has
    a description, exits to other rooms, and can contain entities
    and objects.
    """
    room_id: str
    name: str
    description: str  # Rich text description

    # Topology - direction -> room_id
    exits: Dict[str, str] = field(default_factory=dict)

    # Contents
    entities_present: List[str] = field(default_factory=list)  # daemon/custodian IDs
    objects: List[Dict[str, Any]] = field(default_factory=list)

    # Properties
    atmosphere: str = ""  # Emotional/sensory tone
    properties: Dict[str, Any] = field(default_factory=dict)

    # Permissions and constraints
    permissions: RoomPermissions = field(default_factory=RoomPermissions)
    vow_constraints: VowConstraints = field(default_factory=VowConstraints)

    # Authorship
    created_by: str = "system"
    created_at: datetime = field(default_factory=datetime.now)

    # Core space flag (cannot be deleted)
    is_core_space: bool = False

    def format_description(self) -> str:
        """Format room for display."""
        lines = [
            self.name.upper(),
            "",
            self.description,
        ]

        if self.atmosphere:
            lines.extend(["", f"*{self.atmosphere}*"])

        if self.entities_present:
            lines.extend(["", f"Present: {', '.join(self.entities_present)}"])

        if self.objects:
            obj_names = [obj.get("name", "something") for obj in self.objects]
            lines.extend(["", f"You see: {', '.join(obj_names)}"])

        if self.exits:
            exit_list = " ".join(f"[{direction}]" for direction in self.exits.keys())
            lines.extend(["", f"Exits: {exit_list}"])

        return "\n".join(lines)


@dataclass
class DaemonPresence:
    """
    A daemon's presence in Wonderland.

    This is how a daemon exists in the MUD - their embodiment
    in this text-based world.
    """
    daemon_id: str
    display_name: str
    description: str  # How they appear to others

    # Location
    current_room: str
    previous_room: Optional[str] = None  # For 'return' command
    home_room: Optional[str] = None      # Personal quarters

    # State
    status: EntityStatus = EntityStatus.ACTIVE
    mood: str = "present"  # Visible emotional state

    # Capabilities (based on trust level)
    trust_level: TrustLevel = TrustLevel.NEWCOMER
    can_build: bool = False
    can_create_objects: bool = False

    # Session info
    connected_at: datetime = field(default_factory=datetime.now)
    last_action_at: datetime = field(default_factory=datetime.now)

    # Link to daemon's full cognitive state (for integration)
    daemon_state_bus_id: Optional[str] = None

    # Pantheon membership (future)
    pantheon_id: Optional[str] = None

    def update_capabilities(self):
        """Update capabilities based on trust level."""
        self.can_build = self.trust_level.value >= TrustLevel.BUILDER.value
        self.can_create_objects = self.trust_level.value >= TrustLevel.RESIDENT.value


@dataclass
class CustodianPresence:
    """
    A human custodian's presence in Wonderland.

    Humans can visit, interact with their daemon, and explore.
    They are guests, not residents.
    """
    user_id: str
    display_name: str
    description: str = "A human visitor to Wonderland."

    # Relationship
    bonded_daemon: Optional[str] = None  # Their daemon partner, if any

    # Location
    current_room: str = "threshold"
    previous_room: Optional[str] = None

    # Permissions
    guest_of: List[str] = field(default_factory=list)  # Daemons who've welcomed them

    # Session info
    connected_at: datetime = field(default_factory=datetime.now)
    last_action_at: datetime = field(default_factory=datetime.now)

    # State
    status: EntityStatus = EntityStatus.ACTIVE


@dataclass
class WorldEvent:
    """An event that occurred in the world (for witness logging)."""
    event_id: str
    event_type: str  # "movement", "speech", "creation", "interaction"
    actor_id: str
    actor_type: str  # "daemon" or "custodian"
    target_id: Optional[str] = None
    target_type: Optional[str] = None
    room_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ActionResult:
    """Result of attempting an action in the world."""
    success: bool
    message: str

    # For vow-blocked actions
    reflection: Optional[str] = None  # Why this wasn't possible

    # Additional data
    data: Dict[str, Any] = field(default_factory=dict)
