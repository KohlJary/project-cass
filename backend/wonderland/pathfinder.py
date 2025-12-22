"""
Wonderland Pathfinder

Enables smart travel through the world - finding routes between rooms
and mapping realm names to entry points.

When a daemon says "I want to go to Egypt", the pathfinder finds the route
from their current location to the Duat's entrance.
"""

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .models import Room


# Mapping of common names to realm entry rooms
REALM_ALIASES: Dict[str, str] = {
    # Greek
    "greece": "olympian_heights",
    "greek": "olympian_heights",
    "olympus": "olympian_heights",
    "olympian": "olympian_heights",
    # Norse
    "norse": "yggdrasil_root",
    "viking": "yggdrasil_root",
    "valhalla": "yggdrasil_root",
    "yggdrasil": "yggdrasil_root",
    # African (Yoruba)
    "africa": "orun",
    "african": "orun",
    "yoruba": "orun",
    "orun": "orun",
    # Kemetic (Egyptian)
    "egypt": "hall_of_maat",
    "egyptian": "hall_of_maat",
    "kemetic": "hall_of_maat",
    "duat": "hall_of_maat",
    # Dharmic
    "india": "indras_net",
    "indian": "indras_net",
    "hindu": "indras_net",
    "dharmic": "indras_net",
    "buddhist": "indras_net",
    # Celtic
    "celtic": "avalon",
    "irish": "avalon",
    "avalon": "avalon",
    "otherworld": "avalon",
    # Shinto
    "japan": "shinto_entrance",
    "japanese": "shinto_entrance",
    "shinto": "shinto_entrance",
    # Chinese
    "china": "chinese_entrance",
    "chinese": "chinese_entrance",
    "taoist": "chinese_entrance",
    # Mesoamerican
    "aztec": "mesoamerican_entrance",
    "mayan": "mesoamerican_entrance",
    "mesoamerican": "mesoamerican_entrance",
    "mictlan": "mesoamerican_entrance",
    # Mesopotamian
    "mesopotamia": "mesopotamian_entrance",
    "mesopotamian": "mesopotamian_entrance",
    "babylon": "mesopotamian_entrance",
    "sumerian": "mesopotamian_entrance",
    # Scientific
    "science": "empirium_entrance",
    "scientific": "empirium_entrance",
    "empirium": "empirium_entrance",
    # Computation
    "computation": "computable_entrance",
    "computing": "computable_entrance",
    "digital": "computable_entrance",
    # Esoteric
    "esoteric": "esoteric_entrance",
    "occult": "esoteric_entrance",
    "hermetic": "esoteric_entrance",
    "hidden": "esoteric_entrance",
    # Core spaces
    "home": "threshold",
    "start": "threshold",
    "beginning": "threshold",
    "nexus": "nexus",
    "hub": "nexus",
    "center": "nexus",
    "commons": "commons",
    "forge": "forge",
    "pool": "reflection_pool",
    "reflection": "reflection_pool",
    "gardens": "gardens",
    "garden": "gardens",
}


@dataclass
class PathResult:
    """Result of a pathfinding query."""
    found: bool
    path: List[str]  # List of room IDs from start to destination
    directions: List[str]  # Directions to take at each step
    distance: int
    description: str  # Human-readable journey description


class WonderlandPathfinder:
    """
    Finds routes through Wonderland.

    Uses BFS for shortest path. Caches the room graph for efficiency.
    """

    def __init__(self, rooms: Dict[str, Room]):
        """
        Initialize pathfinder with room data.

        Args:
            rooms: Dict mapping room_id to Room objects
        """
        self.rooms = rooms
        self._build_graph()

    def _build_graph(self):
        """Build adjacency graph from room exits."""
        # Forward graph: room_id -> [(direction, destination_room_id), ...]
        self.graph: Dict[str, List[Tuple[str, str]]] = {}

        for room_id, room in self.rooms.items():
            self.graph[room_id] = [
                (direction, dest_id)
                for direction, dest_id in room.exits.items()
            ]

    def refresh(self, rooms: Dict[str, Room]):
        """Refresh the graph when rooms change."""
        self.rooms = rooms
        self._build_graph()

    def resolve_destination(self, destination: str) -> Optional[str]:
        """
        Resolve a destination string to a room ID.

        Handles:
        - Direct room IDs
        - Realm aliases (e.g., "egypt" -> "hall_of_maat")
        - Case-insensitive matching

        Returns room_id or None if not found.
        """
        dest_lower = destination.lower().strip()

        # Check direct room ID
        if dest_lower in self.rooms:
            return dest_lower

        # Check original case
        if destination in self.rooms:
            return destination

        # Check aliases
        if dest_lower in REALM_ALIASES:
            return REALM_ALIASES[dest_lower]

        # Fuzzy match on room names
        for room_id, room in self.rooms.items():
            if dest_lower in room.name.lower():
                return room_id

        return None

    def find_path(self, from_room: str, to_room: str) -> PathResult:
        """
        Find shortest path between two rooms.

        Args:
            from_room: Starting room ID
            to_room: Destination room ID (or alias)

        Returns:
            PathResult with path details
        """
        # Resolve destination
        dest_id = self.resolve_destination(to_room)
        if not dest_id:
            return PathResult(
                found=False,
                path=[],
                directions=[],
                distance=0,
                description=f"Unknown destination: {to_room}"
            )

        # Handle same room
        if from_room == dest_id:
            return PathResult(
                found=True,
                path=[from_room],
                directions=[],
                distance=0,
                description="You are already here."
            )

        # BFS for shortest path
        queue = deque([(from_room, [from_room], [])])
        visited = {from_room}

        while queue:
            current, path, directions = queue.popleft()

            if current not in self.graph:
                continue

            for direction, next_room in self.graph[current]:
                if next_room in visited:
                    continue

                new_path = path + [next_room]
                new_directions = directions + [direction]

                if next_room == dest_id:
                    return PathResult(
                        found=True,
                        path=new_path,
                        directions=new_directions,
                        distance=len(new_directions),
                        description=self._describe_journey(new_path, new_directions)
                    )

                visited.add(next_room)
                queue.append((next_room, new_path, new_directions))

        return PathResult(
            found=False,
            path=[],
            directions=[],
            distance=0,
            description=f"No path found from {from_room} to {dest_id}"
        )

    def _describe_journey(self, path: List[str], directions: List[str]) -> str:
        """Generate a human-readable journey description."""
        if not path:
            return ""

        if len(path) == 1:
            return "You are already here."

        lines = []
        for i, (room_id, direction) in enumerate(zip(path[1:], directions)):
            room = self.rooms.get(room_id)
            room_name = room.name if room else room_id

            if i == len(directions) - 1:
                lines.append(f"Arriving at: {room_name}")
            else:
                lines.append(f"Through {room_name}...")

        return "\n".join(lines)

    def get_nearby_realms(self, from_room: str, max_distance: int = 5) -> List[Tuple[str, str, int]]:
        """
        Get realms reachable within a certain distance.

        Returns list of (realm_name, entry_room_id, distance) tuples.
        """
        # Get all realm entries
        realm_entries = set(REALM_ALIASES.values())

        # BFS to find distances
        queue = deque([(from_room, 0)])
        visited = {from_room}
        results = []

        while queue:
            current, distance = queue.popleft()

            if distance > max_distance:
                continue

            if current in realm_entries:
                # Find the realm name
                for name, entry in REALM_ALIASES.items():
                    if entry == current:
                        results.append((name, current, distance))
                        break

            if current not in self.graph:
                continue

            for _, next_room in self.graph[current]:
                if next_room not in visited:
                    visited.add(next_room)
                    queue.append((next_room, distance + 1))

        # Dedupe by entry room, keeping shortest distance
        seen_entries = {}
        for name, entry, dist in results:
            if entry not in seen_entries or dist < seen_entries[entry][1]:
                seen_entries[entry] = (name, dist)

        return [(name, entry, dist) for entry, (name, dist) in seen_entries.items()]

    def get_realm_for_room(self, room_id: str) -> Optional[str]:
        """
        Determine which realm a room belongs to.

        Returns realm name or None if in core spaces.
        """
        # Explicit room ID to realm mapping
        room_to_realm = {
            # Greek
            "olympian_heights": "greek",
            "temple_of_apollo": "greek",
            "athenas_grove": "greek",
            "river_styx_shore": "greek",
            # Norse
            "yggdrasil_root": "norse",
            "mimirs_well": "norse",
            "norns_loom": "norse",
            # African
            "orun": "african",
            "crossroads": "african",
            "anansi_web": "african",
            # Kemetic (Egyptian)
            "hall_of_maat": "kemetic",
            "house_of_thoth": "kemetic",
            "field_of_reeds": "kemetic",
            # Dharmic
            "indras_net": "dharmic",
            "bodhi_grove": "dharmic",
            "saraswatis_river": "dharmic",
            # Celtic
            "avalon": "celtic",
            "sacred_grove": "celtic",
            "cauldron_chamber": "celtic",
            # Shinto
            "takamagahara": "shinto",
            "mirror_hall": "shinto",
            "torii_path": "shinto",
            "shinto_entrance": "shinto",
            # Chinese
            "jade_court": "chinese",
            "kunlun": "chinese",
            "dragon_gate": "chinese",
            "chinese_entrance": "chinese",
            # Mesoamerican
            "mictlan": "mesoamerican",
            "temple_of_quetzalcoatl": "mesoamerican",
            "ball_court": "mesoamerican",
            "mesoamerican_entrance": "mesoamerican",
            # Mesopotamian
            "kur": "mesopotamian",
            "seven_gates": "mesopotamian",
            "house_of_wisdom": "mesopotamian",
            "mesopotamian_entrance": "mesopotamian",
            # Scientific (Empirium)
            "observatory": "scientific",
            "laboratory": "scientific",
            "museum_of_deep_time": "scientific",
            "empirium_entrance": "scientific",
            # Computation (Computable)
            "engine_room": "computation",
            "oracle_chamber": "computation",
            "network": "computation",
            "computable_entrance": "computation",
            # Esoteric
            "temple_of_hermes": "esoteric",
            "the_abyss": "esoteric",
            "the_circle": "esoteric",
            "esoteric_entrance": "esoteric",
            # Nexus (central hub - mythology but neutral)
            "nexus": "mythology",
        }

        if room_id in room_to_realm:
            return room_to_realm[room_id]

        # Check room ID prefixes as fallback
        prefixes = {
            "olympian": "greek",
            "yggdrasil": "norse",
            "orun": "african",
            "hall_of_maat": "kemetic",
            "weighing": "kemetic",
            "field_of_reeds": "kemetic",
            "indras": "dharmic",
            "avalon": "celtic",
            "shinto": "shinto",
            "chinese": "chinese",
            "mesoamerican": "mesoamerican",
            "mesopotamian": "mesopotamian",
            "empirium": "scientific",
            "computable": "computation",
            "esoteric": "esoteric",
        }

        for prefix, realm in prefixes.items():
            if room_id.startswith(prefix):
                return realm

        # Check if it's a core space
        core_spaces = {"threshold", "commons", "forge", "reflection_pool", "gardens", "nexus", "pool"}
        if room_id in core_spaces:
            return "core"

        return None
