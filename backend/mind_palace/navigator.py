"""
Mind Palace Navigator - MUD-style navigation through code architecture.

Provides natural language navigation commands that feel like exploring a text adventure.
Designed for LLM agents (Daedalus) to navigate codebases spatially.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .models import (
    AccessLevel,
    Building,
    Entity,
    Exit,
    Hazard,
    Palace,
    Region,
    Room,
)

# Type alias for path resolution result
PathTarget = Room | Building | Region

logger = logging.getLogger(__name__)


@dataclass
class NavigationResult:
    """Result of a navigation command."""
    success: bool
    message: str
    room: Optional[Room] = None
    building: Optional[Building] = None
    region: Optional[Region] = None
    entity: Optional[Entity] = None


class Navigator:
    """
    MUD-style navigator for Mind Palace exploration.

    Commands:
    - look: Describe current location
    - go <direction>: Move through an exit
    - enter <building>: Enter a building
    - ascend/descend: Move between floors
    - map: Show current building layout
    - where is <thing>: Find something in the palace
    - ask <entity> about <topic>: Query an entity
    - history: Show modification history for current room
    - exits: List available exits
    - hazards: List hazards in current room
    """

    # Direction aliases
    DIRECTION_ALIASES = {
        "n": "north", "s": "south", "e": "east", "w": "west",
        "u": "up", "d": "down",
        "ne": "northeast", "nw": "northwest",
        "se": "southeast", "sw": "southwest",
        "in": "in", "out": "out",
    }

    def __init__(self, palace: Palace):
        self.palace = palace
        self._current_room: Optional[str] = None
        self._current_building: Optional[str] = None
        self._current_region: Optional[str] = None
        self._visited: List[str] = []

    @property
    def current_room(self) -> Optional[Room]:
        if self._current_room:
            return self.palace.get_room(self._current_room)
        return None

    @property
    def current_building(self) -> Optional[Building]:
        if self._current_building:
            return self.palace.get_building(self._current_building)
        return None

    @property
    def current_region(self) -> Optional[Region]:
        if self._current_region:
            return self.palace.get_region(self._current_region)
        return None

    def teleport(self, target: str) -> NavigationResult:
        """
        Instantly move to a room (for initialization or shortcuts).

        Supports multiple formats:
        - Room name: "add_message"
        - Room slug: "memory-add-message"
        - Full path: "backend/memory/add-message"
        - Partial path: "memory/add-message"
        """
        # First try path resolution
        if "/" in target:
            element = self.palace.resolve_path(target)
            if element:
                if isinstance(element, Room):
                    return self._teleport_to_room(element)
                elif isinstance(element, Building):
                    return self._teleport_to_building(element)
                elif isinstance(element, Region):
                    return self._teleport_to_region(element)

        # Try as room name or slug
        room = self.palace.get_room(target)
        if room:
            return self._teleport_to_room(room)

        # Try as building
        building = self.palace.get_building(target)
        if building:
            return self._teleport_to_building(building)

        # Try as region
        region = self.palace.get_region(target)
        if region:
            return self._teleport_to_region(region)

        return NavigationResult(
            success=False,
            message=f"Unknown location: {target}"
        )

    def _teleport_to_room(self, room: Room) -> NavigationResult:
        """Teleport directly to a room."""
        building = self.palace.get_building(room.building)
        region = self.palace.get_region(building.region) if building else None

        self._current_room = room.slug or room.name
        self._current_building = room.building
        self._current_region = building.region if building else None

        if self._current_room not in self._visited:
            self._visited.append(self._current_room)

        path = self.palace.get_full_path(room)
        return NavigationResult(
            success=True,
            message=f"You appear in {room.name}. [{path}]",
            room=room,
            building=building,
            region=region,
        )

    def _teleport_to_building(self, building: Building) -> NavigationResult:
        """Teleport to a building (outside rooms)."""
        region = self.palace.get_region(building.region)

        self._current_room = None
        self._current_building = building.slug or building.name
        self._current_region = building.region

        return NavigationResult(
            success=True,
            message=f"You arrive at {building.name}.",
            building=building,
            region=region,
        )

    def _teleport_to_region(self, region: Region) -> NavigationResult:
        """Teleport to a region (outside buildings)."""
        self._current_room = None
        self._current_building = None
        self._current_region = region.slug or region.name

        return NavigationResult(
            success=True,
            message=f"You enter the {region.name} region.",
            region=region,
        )

    def look(self) -> str:
        """Describe the current location in detail."""
        if not self.current_room:
            return self._describe_outside()

        room = self.current_room
        building = self.current_building
        region = self.current_region

        lines = []

        # Location header
        location = f"**{room.name}**"
        if building:
            location += f", floor {room.floor} of {building.name}"
        if region:
            location += f" ({region.name})"
        lines.append(location)
        lines.append("")

        # Description
        if room.description:
            lines.append(room.description)
            lines.append("")

        # Contents
        if room.contents:
            lines.append("**You notice:**")
            for content in room.contents:
                lines.append(f"  • {content.name} ({content.type}) - {content.purpose}")
            lines.append("")

        # Exits
        if room.exits:
            lines.append("**Exits:**")
            for exit in room.exits:
                exit_desc = f"  {exit.direction.upper()}: {exit.destination}"
                if exit.condition:
                    exit_desc += f" ({exit.condition})"
                if exit.access == AccessLevel.INTERNAL:
                    exit_desc += " [internal]"
                elif exit.access == AccessLevel.DANGEROUS:
                    exit_desc += " [dangerous]"
                lines.append(exit_desc)
            lines.append("")

        # Hazards
        if room.hazards:
            lines.append("**⚠ Hazards posted:**")
            for hazard in room.hazards:
                severity_marker = "!" * hazard.severity
                lines.append(f"  {severity_marker} [{hazard.type.value}] {hazard.description}")
            lines.append("")

        # Anchor info (for sync awareness)
        if room.anchor:
            lines.append(f"*Anchored to: `{room.anchor.pattern}` in {room.anchor.file}*")

        return "\n".join(lines)

    def _describe_outside(self) -> str:
        """Describe being outside any room."""
        if self._current_building:
            building = self.current_building
            lines = [
                f"You are outside, in front of **{building.name}**.",
                "",
                f"{building.purpose}",
                "",
                f"This building has {building.floors} floor(s).",
            ]
            if building.main_entrance:
                lines.append(f"Main entrance: {building.main_entrance}")
            if building.side_doors:
                lines.append(f"Side doors: {', '.join(building.side_doors)}")
            return "\n".join(lines)

        if self._current_region:
            region = self.current_region
            buildings = self.palace.buildings_in_region(region.name)
            lines = [
                f"You are in the **{region.name}** region.",
                "",
                f"{region.description}",
                "",
                "**Buildings here:**",
            ]
            for b in buildings:
                lines.append(f"  • {b.name} - {b.purpose[:50]}...")
            return "\n".join(lines)

        # Completely outside
        lines = [
            "You stand at the entrance to the Mind Palace.",
            "",
            "**Regions available:**",
        ]
        for name, region in self.palace.regions.items():
            lines.append(f"  • {name} - {region.description[:50]}...")
        lines.append("")
        lines.append("Use `enter <region>` to explore.")
        return "\n".join(lines)

    def go(self, direction: str) -> NavigationResult:
        """Move through an exit in the given direction."""
        if not self.current_room:
            return NavigationResult(
                success=False,
                message="You're not in a room. Use `enter <building>` first."
            )

        # Normalize direction
        direction = self.DIRECTION_ALIASES.get(direction.lower(), direction.lower())

        exit = self.current_room.get_exit(direction)
        if not exit:
            available = [e.direction for e in self.current_room.exits]
            return NavigationResult(
                success=False,
                message=f"No exit to the {direction}. Available: {', '.join(available)}"
            )

        # Check for internal access
        if exit.access == AccessLevel.INTERNAL:
            logger.info(f"Accessing internal room: {exit.destination}")

        return self.teleport(exit.destination)

    def enter(self, target: str) -> NavigationResult:
        """Enter a building or region."""
        # Try as building first
        building = self.palace.get_building(target)
        if building:
            self._current_building = target
            self._current_region = building.region

            # Enter through main entrance if available
            if building.main_entrance:
                return self.teleport(building.main_entrance)
            else:
                # Just enter the building, not a specific room
                self._current_room = None
                return NavigationResult(
                    success=True,
                    message=f"You enter {building.name}. {building.purpose}",
                    building=building,
                )

        # Try as region
        region = self.palace.get_region(target)
        if region:
            self._current_region = target
            self._current_building = None
            self._current_room = None
            return NavigationResult(
                success=True,
                message=f"You enter the {region.name} region. {region.description}",
                region=region,
            )

        return NavigationResult(
            success=False,
            message=f"Unknown location: {target}"
        )

    def ascend(self) -> NavigationResult:
        """Move up a floor."""
        return self.go("up")

    def descend(self) -> NavigationResult:
        """Move down a floor."""
        return self.go("down")

    def exits(self) -> str:
        """List all exits from current room."""
        if not self.current_room:
            return "You're not in a room."

        lines = ["**Available exits:**"]
        for exit in self.current_room.exits:
            desc = f"  {exit.direction.upper()}: → {exit.destination}"
            if exit.condition:
                desc += f" (when: {exit.condition})"
            if exit.access != AccessLevel.PUBLIC:
                desc += f" [{exit.access.value}]"
            lines.append(desc)

        return "\n".join(lines) if len(lines) > 1 else "No exits."

    def hazards(self) -> str:
        """List all hazards in current room."""
        if not self.current_room:
            return "You're not in a room."

        if not self.current_room.hazards:
            return "No hazards posted in this room."

        lines = ["**⚠ Hazards in this room:**"]
        for h in self.current_room.hazards:
            severity = "!" * h.severity
            lines.append(f"  {severity} [{h.type.value.upper()}] {h.description}")

        return "\n".join(lines)

    def history(self) -> str:
        """Show modification history for current room."""
        if not self.current_room:
            return "You're not in a room."

        if not self.current_room.history:
            return "No recorded history for this room."

        lines = [f"**History of {self.current_room.name}:**"]
        for entry in self.current_room.history:
            author = f" ({entry.author})" if entry.author else ""
            lines.append(f"  • {entry.date}{author}: {entry.note}")

        return "\n".join(lines)

    def map(self) -> str:
        """Show ASCII map of current building."""
        if not self.current_building:
            return self._region_map()

        building = self.current_building
        rooms = self.palace.rooms_in_building(building.name)

        if not rooms:
            return f"Building {building.name} has no mapped rooms."

        # Group rooms by floor
        floors: dict = {}
        for room in rooms:
            if room.floor not in floors:
                floors[room.floor] = []
            floors[room.floor].append(room)

        lines = [f"**Map of {building.name}**", ""]

        for floor_num in sorted(floors.keys(), reverse=True):
            floor_rooms = floors[floor_num]
            lines.append(f"Floor {floor_num}:")
            lines.append("┌" + "─" * 40 + "┐")

            for room in floor_rooms:
                marker = "→ " if room.name == self._current_room else "  "
                hazard_count = len(room.hazards)
                hazard_marker = f" ⚠{hazard_count}" if hazard_count > 0 else ""
                room_line = f"│ {marker}{room.name[:30]:<30}{hazard_marker:>6} │"
                lines.append(room_line)

            lines.append("└" + "─" * 40 + "┘")
            lines.append("")

        return "\n".join(lines)

    def _region_map(self) -> str:
        """Show map of current region or all regions."""
        if self._current_region:
            region = self.current_region
            buildings = self.palace.buildings_in_region(region.name)

            lines = [f"**Map of {region.name}**", ""]
            for b in buildings:
                marker = "→ " if b.name == self._current_building else "  "
                lines.append(f"{marker}[{b.name}] - {b.purpose[:40]}...")
            return "\n".join(lines)

        # Show all regions
        lines = ["**Mind Palace Overview**", ""]
        for name, region in self.palace.regions.items():
            building_count = len(self.palace.buildings_in_region(name))
            lines.append(f"  [{name}] ({building_count} buildings)")
            lines.append(f"    {region.description[:60]}...")
            if region.adjacent:
                lines.append(f"    Adjacent to: {', '.join(region.adjacent)}")
            lines.append("")

        return "\n".join(lines)

    def where_is(self, target: str) -> str:
        """Find something in the palace and describe path to it."""
        target_lower = target.lower()

        # Check rooms
        for name, room in self.palace.rooms.items():
            if target_lower in name.lower():
                building = self.palace.get_building(room.building)
                region_name = building.region if building else "unknown"
                path = self._find_path(room.name)
                return (
                    f"**{room.name}** is a room in {room.building}, "
                    f"floor {room.floor} ({region_name} region).\n\n"
                    f"Path: {path}"
                )

        # Check buildings
        for name, building in self.palace.buildings.items():
            if target_lower in name.lower():
                return (
                    f"**{building.name}** is a building in the {building.region} region.\n"
                    f"Purpose: {building.purpose}\n"
                    f"Enter with: `enter {building.name}`"
                )

        # Check entities
        for name, entity in self.palace.entities.items():
            if target_lower in name.lower():
                return (
                    f"**{entity.name}** can be found at {entity.location}.\n"
                    f"Role: {entity.role}\n"
                    f"Topics: {', '.join(t.name for t in entity.topics)}"
                )

        return f"Could not find '{target}' in the palace."

    def _find_path(self, destination: str) -> str:
        """Find a path from current location to destination."""
        if not self._current_room:
            room = self.palace.get_room(destination)
            if room:
                return f"`enter {room.building}` → `teleport {destination}`"
            return f"`teleport {destination}`"

        # Simple path - just describe the destination
        # TODO: Implement actual pathfinding using exits
        dest_room = self.palace.get_room(destination)
        if dest_room:
            if dest_room.building == self._current_building:
                return f"Same building, floor {dest_room.floor}"
            return f"`enter {dest_room.building}` → floor {dest_room.floor}"

        return "Path not found"

    def entities(self) -> str:
        """List all entities in the palace."""
        if not self.palace.entities:
            return "No entities in the palace."

        lines = ["**Entities in the Mind Palace:**", ""]

        for name, entity in sorted(self.palace.entities.items()):
            lines.append(f"**{name}**")
            lines.append(f"  Location: {entity.location}")
            lines.append(f"  Role: {entity.role[:80]}...")
            topics = [t.name for t in entity.topics]
            lines.append(f"  Topics: {', '.join(topics)}")
            lines.append("")

        lines.append(f"*{len(self.palace.entities)} entities total.*")
        lines.append("")
        lines.append("Use `ask <entity> about <topic>` to query.")

        return "\n".join(lines)

    def ask(self, entity_name: str, topic: str) -> str:
        """Ask an entity about a topic."""
        entity = self.palace.get_entity(entity_name)
        if not entity:
            # Try partial match
            for name, e in self.palace.entities.items():
                if entity_name.lower() in name.lower():
                    entity = e
                    break

        if not entity:
            available = list(self.palace.entities.keys())
            return f"Unknown entity: {entity_name}. Known entities: {', '.join(available)}"

        topic_obj = entity.get_topic(topic)
        if not topic_obj:
            available_topics = [t.name for t in entity.topics]
            return (
                f"{entity.name} doesn't know about '{topic}'.\n"
                f"Available topics: {', '.join(available_topics)}"
            )

        # Format the response
        lines = [f"**{entity.name}** speaks about *{topic_obj.name}*:", ""]

        if entity.personality:
            lines.append(f"*{entity.personality}*")
            lines.append("")

        lines.append(f"**How:** {topic_obj.how}")
        lines.append("")
        lines.append(f"**Why:** {topic_obj.why}")

        if topic_obj.watch_out:
            lines.append("")
            lines.append(f"**⚠ Watch out:** {topic_obj.watch_out}")

        if topic_obj.tunable:
            lines.append("")
            lines.append("*This is tunable/configurable.*")

        return "\n".join(lines)

    def execute(self, command: str) -> str:
        """Parse and execute a natural language navigation command."""
        parts = command.strip().lower().split(maxsplit=1)
        if not parts:
            return self.look()

        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        # Navigation commands
        if cmd == "look" or cmd == "l":
            return self.look()

        if cmd == "go" or cmd in self.DIRECTION_ALIASES or cmd in [
            "north", "south", "east", "west", "up", "down",
            "northeast", "northwest", "southeast", "southwest"
        ]:
            direction = arg if cmd == "go" else cmd
            result = self.go(direction)
            if result.success:
                return result.message + "\n\n" + self.look()
            return result.message

        if cmd == "enter":
            result = self.enter(arg)
            if result.success:
                return result.message + "\n\n" + self.look()
            return result.message

        if cmd == "teleport" or cmd == "tp":
            result = self.teleport(arg)
            if result.success:
                return result.message + "\n\n" + self.look()
            return result.message

        if cmd == "ascend" or cmd == "up":
            result = self.ascend()
            if result.success:
                return result.message + "\n\n" + self.look()
            return result.message

        if cmd == "descend" or cmd == "down":
            result = self.descend()
            if result.success:
                return result.message + "\n\n" + self.look()
            return result.message

        if cmd == "map" or cmd == "m":
            return self.map()

        if cmd == "exits" or cmd == "x":
            return self.exits()

        if cmd == "hazards" or cmd == "h":
            return self.hazards()

        if cmd == "history":
            return self.history()

        if cmd == "where" and arg.startswith("is "):
            return self.where_is(arg[3:])

        if cmd == "entities" or cmd == "keepers":
            return self.entities()

        if cmd == "ask":
            # Parse "ask <entity> about <topic>"
            if " about " in arg:
                entity_part, topic_part = arg.split(" about ", 1)
                return self.ask(entity_part.strip(), topic_part.strip())
            return "Usage: ask <entity> about <topic>"

        if cmd == "help" or cmd == "?":
            return self._help()

        return f"Unknown command: {cmd}. Type 'help' for available commands."

    def _help(self) -> str:
        """Show available commands."""
        return """**Mind Palace Navigation Commands:**

**Movement:**
  look (l)          - Describe current location
  go <direction>    - Move through an exit (n/s/e/w/u/d)
  enter <place>     - Enter a building or region
  teleport <room>   - Jump directly to a room
  ascend/descend    - Move between floors

**Information:**
  map (m)           - Show building/region layout
  exits (x)         - List available exits
  hazards (h)       - List hazards in current room
  history           - Show room modification history
  where is <thing>  - Find something in the palace

**Entities:**
  entities (keepers)         - List all entities in the palace
  ask <entity> about <topic> - Query an entity's knowledge

**Examples:**
  go north
  enter daemon-lifecycle
  ask Persistence-Keeper about recovery
  where is spawn_daemon
"""
