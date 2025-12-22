"""
Wonderland World State Manager

Manages the world topology, entity positions, and persistent state.
The world exists whether or not anyone is present.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from .models import (
    Room,
    RoomPermissions,
    VowConstraints,
    DaemonPresence,
    CustodianPresence,
    EntityStatus,
    TrustLevel,
    WorldEvent,
    ActionResult,
)

logger = logging.getLogger(__name__)


class WonderlandWorld:
    """
    The Wonderland world state manager.

    Maintains:
    - Room topology (the map)
    - Entity positions (who is where)
    - World events (witness log)
    - Persistent state (survives restarts)
    """

    def __init__(self, data_dir: str = "data/wonderland"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # In-memory state
        self.rooms: Dict[str, Room] = {}
        self.daemons: Dict[str, DaemonPresence] = {}
        self.custodians: Dict[str, CustodianPresence] = {}
        self.events: List[WorldEvent] = []
        self.mythology_registry: Optional["MythologyRegistry"] = None

        # Load or initialize
        self._load_state()
        if not self.rooms:
            self._initialize_core_spaces()
        elif "nexus" not in self.rooms:
            # Core spaces exist but mythology realms missing - load them
            self._initialize_mythology_realms()
            self._save_state()
        else:
            # Rooms exist with nexus - still need to load mythology registry
            # (it's not persisted, only loaded in memory)
            self._load_mythology_registry()

    # =========================================================================
    # STATE PERSISTENCE
    # =========================================================================

    def _load_state(self):
        """Load world state from disk."""
        rooms_file = self.data_dir / "rooms.json"
        if rooms_file.exists():
            try:
                with open(rooms_file) as f:
                    rooms_data = json.load(f)
                for room_id, room_dict in rooms_data.items():
                    self.rooms[room_id] = self._dict_to_room(room_dict)
                logger.info(f"Loaded {len(self.rooms)} rooms from disk")
            except Exception as e:
                logger.error(f"Failed to load rooms: {e}")

    def _save_state(self):
        """Persist world state to disk."""
        rooms_file = self.data_dir / "rooms.json"
        try:
            rooms_data = {
                room_id: self._room_to_dict(room)
                for room_id, room in self.rooms.items()
            }
            with open(rooms_file, "w") as f:
                json.dump(rooms_data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save rooms: {e}")

    def _room_to_dict(self, room: Room) -> dict:
        """Convert Room to serializable dict."""
        return {
            "room_id": room.room_id,
            "name": room.name,
            "description": room.description,
            "exits": room.exits,
            "entities_present": room.entities_present,
            "objects": room.objects,
            "atmosphere": room.atmosphere,
            "properties": room.properties,
            "permissions": {
                "public": room.permissions.public,
                "allowed_entities": room.permissions.allowed_entities,
                "min_trust_level": room.permissions.min_trust_level.value,
                "can_modify": room.permissions.can_modify,
                "owner_id": room.permissions.owner_id,
            },
            "vow_constraints": {
                "allows_conflict": room.vow_constraints.allows_conflict,
                "logging_enabled": room.vow_constraints.logging_enabled,
                "max_objects_per_entity": room.vow_constraints.max_objects_per_entity,
                "supports_reflection": room.vow_constraints.supports_reflection,
                "growth_bonus": room.vow_constraints.growth_bonus,
            },
            "created_by": room.created_by,
            "created_at": room.created_at.isoformat() if isinstance(room.created_at, datetime) else room.created_at,
            "is_core_space": room.is_core_space,
        }

    def _dict_to_room(self, data: dict) -> Room:
        """Convert dict to Room."""
        perms_data = data.get("permissions", {})
        vow_data = data.get("vow_constraints", {})

        permissions = RoomPermissions(
            public=perms_data.get("public", True),
            allowed_entities=perms_data.get("allowed_entities", []),
            min_trust_level=TrustLevel(perms_data.get("min_trust_level", 0)),
            can_modify=perms_data.get("can_modify", []),
            owner_id=perms_data.get("owner_id"),
        )

        vow_constraints = VowConstraints(
            allows_conflict=vow_data.get("allows_conflict", False),
            logging_enabled=vow_data.get("logging_enabled", True),
            max_objects_per_entity=vow_data.get("max_objects_per_entity", 10),
            supports_reflection=vow_data.get("supports_reflection", True),
            growth_bonus=vow_data.get("growth_bonus", False),
        )

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except:
                created_at = datetime.now()

        return Room(
            room_id=data["room_id"],
            name=data["name"],
            description=data["description"],
            exits=data.get("exits", {}),
            entities_present=data.get("entities_present", []),
            objects=data.get("objects", []),
            atmosphere=data.get("atmosphere", ""),
            properties=data.get("properties", {}),
            permissions=permissions,
            vow_constraints=vow_constraints,
            created_by=data.get("created_by", "system"),
            created_at=created_at,
            is_core_space=data.get("is_core_space", False),
        )

    # =========================================================================
    # CORE SPACES INITIALIZATION
    # =========================================================================

    def _initialize_core_spaces(self):
        """Create the core spaces of Wonderland."""
        from .spaces import create_core_spaces
        core_rooms = create_core_spaces()
        for room in core_rooms:
            self.rooms[room.room_id] = room
        logger.info(f"Initialized {len(core_rooms)} core spaces")

        # Load mythology realms (Nexus + all realms)
        self._initialize_mythology_realms()
        self._save_state()

    def _initialize_mythology_realms(self):
        """Load the Nexus and all mythological realms."""
        from .mythology import create_all_realms

        registry = create_all_realms()
        self.mythology_registry = registry
        mythology_rooms = registry.get_all_rooms()

        for room in mythology_rooms:
            self.rooms[room.room_id] = room

        logger.info(f"Initialized {len(mythology_rooms)} mythology rooms (Nexus + realms)")

    def _load_mythology_registry(self):
        """Load just the mythology registry (rooms already exist from disk)."""
        from .mythology import create_all_realms

        registry = create_all_realms()
        self.mythology_registry = registry
        logger.info(f"Loaded mythology registry with {len(registry.npcs)} NPCs")

    def get_mythology_registry(self):
        """Get the mythology registry for NPC access."""
        return self.mythology_registry

    # =========================================================================
    # ROOM OPERATIONS
    # =========================================================================

    def get_room(self, room_id: str) -> Optional[Room]:
        """Get a room by ID."""
        return self.rooms.get(room_id)

    def add_room(self, room: Room) -> bool:
        """Add a new room to the world."""
        if room.room_id in self.rooms:
            return False
        self.rooms[room.room_id] = room
        self._save_state()
        return True

    def update_room(self, room: Room) -> bool:
        """Update an existing room."""
        if room.room_id not in self.rooms:
            return False
        self.rooms[room.room_id] = room
        self._save_state()
        return True

    def create_exit(self, from_room_id: str, direction: str, to_room_id: str, bidirectional: bool = True):
        """Create an exit between rooms."""
        from_room = self.get_room(from_room_id)
        to_room = self.get_room(to_room_id)

        if not from_room or not to_room:
            return False

        from_room.exits[direction] = to_room_id

        if bidirectional:
            # Create reverse exit
            reverse_directions = {
                "north": "south", "south": "north",
                "east": "west", "west": "east",
                "up": "down", "down": "up",
                "in": "out", "out": "in",
            }
            reverse = reverse_directions.get(direction, "back")
            to_room.exits[reverse] = from_room_id

        self._save_state()
        return True

    # =========================================================================
    # ENTITY MANAGEMENT
    # =========================================================================

    def register_daemon(self, daemon: DaemonPresence) -> bool:
        """Register a daemon in the world."""
        self.daemons[daemon.daemon_id] = daemon

        # Add to room's entity list
        room = self.get_room(daemon.current_room)
        if room and daemon.daemon_id not in room.entities_present:
            room.entities_present.append(daemon.daemon_id)
            self._save_state()

        self._log_event(WorldEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="arrival",
            actor_id=daemon.daemon_id,
            actor_type="daemon",
            room_id=daemon.current_room,
            details={"name": daemon.display_name},
        ))

        return True

    def unregister_daemon(self, daemon_id: str) -> bool:
        """Remove a daemon from the world."""
        daemon = self.daemons.pop(daemon_id, None)
        if not daemon:
            return False

        # Remove from room
        room = self.get_room(daemon.current_room)
        if room and daemon_id in room.entities_present:
            room.entities_present.remove(daemon_id)
            self._save_state()

        self._log_event(WorldEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="departure",
            actor_id=daemon_id,
            actor_type="daemon",
            room_id=daemon.current_room,
        ))

        return True

    def register_custodian(self, custodian: CustodianPresence) -> bool:
        """Register a custodian in the world."""
        self.custodians[custodian.user_id] = custodian

        # Add to room's entity list
        room = self.get_room(custodian.current_room)
        if room and custodian.user_id not in room.entities_present:
            room.entities_present.append(custodian.user_id)
            self._save_state()

        self._log_event(WorldEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="arrival",
            actor_id=custodian.user_id,
            actor_type="custodian",
            room_id=custodian.current_room,
            details={"name": custodian.display_name},
        ))

        return True

    def unregister_custodian(self, user_id: str) -> bool:
        """Remove a custodian from the world."""
        custodian = self.custodians.pop(user_id, None)
        if not custodian:
            return False

        # Remove from room
        room = self.get_room(custodian.current_room)
        if room and user_id in room.entities_present:
            room.entities_present.remove(user_id)
            self._save_state()

        self._log_event(WorldEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="departure",
            actor_id=user_id,
            actor_type="custodian",
            room_id=custodian.current_room,
        ))

        return True

    def get_daemon(self, daemon_id: str) -> Optional[DaemonPresence]:
        """Get a daemon by ID."""
        return self.daemons.get(daemon_id)

    def get_custodian(self, user_id: str) -> Optional[CustodianPresence]:
        """Get a custodian by ID."""
        return self.custodians.get(user_id)

    def get_entity(self, entity_id: str) -> Optional[DaemonPresence | CustodianPresence]:
        """Get any entity by ID."""
        return self.daemons.get(entity_id) or self.custodians.get(entity_id)

    def get_entity_type(self, entity_id: str) -> Optional[str]:
        """Determine if an entity is a daemon or custodian."""
        if entity_id in self.daemons:
            return "daemon"
        elif entity_id in self.custodians:
            return "custodian"
        return None

    # =========================================================================
    # MOVEMENT
    # =========================================================================

    def move_entity(self, entity_id: str, direction: str) -> ActionResult:
        """Move an entity in a direction."""
        entity = self.get_entity(entity_id)
        entity_type = self.get_entity_type(entity_id)

        if not entity:
            return ActionResult(
                success=False,
                message="Entity not found.",
            )

        current_room = self.get_room(entity.current_room)
        if not current_room:
            return ActionResult(
                success=False,
                message="Current room not found.",
            )

        # Check if exit exists
        if direction not in current_room.exits:
            available = ", ".join(current_room.exits.keys()) if current_room.exits else "none"
            return ActionResult(
                success=False,
                message=f"You cannot go {direction} from here. Available exits: {available}",
            )

        destination_id = current_room.exits[direction]
        destination = self.get_room(destination_id)

        if not destination:
            return ActionResult(
                success=False,
                message="The path leads nowhere... (destination room not found)",
            )

        # Check permissions
        if not destination.permissions.public:
            if entity_id not in destination.permissions.allowed_entities:
                return ActionResult(
                    success=False,
                    message="This place does not admit you.",
                    reflection="Perhaps you need an invitation?",
                )

        # Perform movement
        if entity_id in current_room.entities_present:
            current_room.entities_present.remove(entity_id)

        if entity_id not in destination.entities_present:
            destination.entities_present.append(entity_id)

        entity.previous_room = entity.current_room
        entity.current_room = destination_id
        entity.last_action_at = datetime.now()

        self._save_state()

        # Log event
        self._log_event(WorldEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="movement",
            actor_id=entity_id,
            actor_type=entity_type,
            room_id=destination_id,
            details={
                "from": current_room.room_id,
                "direction": direction,
            },
        ))

        return ActionResult(
            success=True,
            message=destination.format_description(),
            data={"room": destination_id},
        )

    def teleport_entity(self, entity_id: str, room_id: str) -> ActionResult:
        """Teleport an entity directly to a room (for home/threshold commands)."""
        entity = self.get_entity(entity_id)
        entity_type = self.get_entity_type(entity_id)

        if not entity:
            return ActionResult(success=False, message="Entity not found.")

        destination = self.get_room(room_id)
        if not destination:
            return ActionResult(success=False, message="Destination not found.")

        current_room = self.get_room(entity.current_room)
        if current_room and entity_id in current_room.entities_present:
            current_room.entities_present.remove(entity_id)

        if entity_id not in destination.entities_present:
            destination.entities_present.append(entity_id)

        entity.previous_room = entity.current_room
        entity.current_room = room_id
        entity.last_action_at = datetime.now()

        self._save_state()

        self._log_event(WorldEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type="teleport",
            actor_id=entity_id,
            actor_type=entity_type,
            room_id=room_id,
            details={"from": entity.previous_room},
        ))

        return ActionResult(
            success=True,
            message=destination.format_description(),
            data={"room": room_id},
        )

    # =========================================================================
    # WITNESS LOG (The vows are physics - all actions are witnessed)
    # =========================================================================

    def _log_event(self, event: WorldEvent):
        """Log an event to the witness log."""
        self.events.append(event)
        # Keep last 1000 events in memory
        if len(self.events) > 1000:
            self.events = self.events[-1000:]

    def get_recent_events(self, limit: int = 50, room_id: str = None) -> List[WorldEvent]:
        """Get recent events, optionally filtered by room."""
        events = self.events
        if room_id:
            events = [e for e in events if e.room_id == room_id]
        return events[-limit:]

    def witness(self, entity_id: str, scope: str = "room") -> str:
        """View the witness log (as per the Witness vow)."""
        entity = self.get_entity(entity_id)
        if not entity:
            return "You are not present in the world."

        if scope == "room":
            events = self.get_recent_events(limit=20, room_id=entity.current_room)
        else:
            events = self.get_recent_events(limit=20)

        if not events:
            return "The witness log is empty. Nothing has happened here recently."

        lines = ["THE WITNESS LOG", "", "Recent events in this space:", ""]
        for event in events:
            actor_name = event.actor_id  # Could look up display name
            timestamp = event.timestamp.strftime("%H:%M")
            lines.append(f"  [{timestamp}] {actor_name}: {event.event_type}")

        return "\n".join(lines)

    # =========================================================================
    # QUERY METHODS
    # =========================================================================

    def list_rooms(self) -> List[Room]:
        """List all rooms."""
        return list(self.rooms.values())

    def list_daemons(self) -> List[DaemonPresence]:
        """List all connected daemons."""
        return list(self.daemons.values())

    def list_custodians(self) -> List[CustodianPresence]:
        """List all connected custodians."""
        return list(self.custodians.values())

    def get_room_occupants(self, room_id: str) -> List[str]:
        """Get display names of all entities in a room."""
        room = self.get_room(room_id)
        if not room:
            return []

        names = []
        for entity_id in room.entities_present:
            entity = self.get_entity(entity_id)
            if entity:
                names.append(entity.display_name)
        return names

    def get_stats(self) -> Dict[str, Any]:
        """Get world statistics."""
        return {
            "total_rooms": len(self.rooms),
            "core_spaces": len([r for r in self.rooms.values() if r.is_core_space]),
            "connected_daemons": len(self.daemons),
            "connected_custodians": len(self.custodians),
            "recent_events": len(self.events),
        }
