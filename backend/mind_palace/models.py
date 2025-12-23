"""
Mind Palace Data Models - Spatial representation of codebases.

These models define the structure of a Mind Palace - a navigable MUD-like
representation of code architecture that LLMs can explore spatially.

Designed to be project-agnostic: can be initialized in any codebase.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class HazardType(Enum):
    """Types of hazards (architectural warnings) in rooms."""
    INVARIANT = "invariant"      # Must always be true
    EDGE_CASE = "edge_case"      # Known tricky situation
    PERFORMANCE = "performance"  # Performance-sensitive
    SECURITY = "security"        # Security-relevant
    DEPRECATED = "deprecated"    # Marked for removal
    FRAGILE = "fragile"          # Easy to break


class AccessLevel(Enum):
    """Access levels for exits (calls between rooms)."""
    PUBLIC = "public"            # Normal public interface
    INTERNAL = "internal"        # Internal/private
    PROTECTED = "protected"      # Subclass access
    DANGEROUS = "dangerous"      # Use with caution


@dataclass
class Anchor:
    """
    Code anchor - ties a palace element to actual source code.
    Used for drift detection and synchronization.
    """
    pattern: str                 # Search pattern (e.g., "def spawn_daemon")
    file: str                    # Relative file path
    line: Optional[int] = None   # Line number (if known)
    signature_hash: Optional[str] = None  # Hash for drift detection
    last_verified: Optional[str] = None   # ISO timestamp of last sync
    is_regex: bool = False       # Whether pattern is a regex (vs literal)


@dataclass
class HistoryEntry:
    """A modification history entry for a palace element."""
    date: str                    # ISO date
    note: str                    # What changed
    author: Optional[str] = None # Who made the change


@dataclass
class Hazard:
    """A hazard (warning/invariant) posted in a room."""
    type: HazardType
    description: str
    severity: int = 1            # 1-3, higher is more critical


@dataclass
class Exit:
    """An exit from a room (represents a call/dependency)."""
    direction: str               # NORTH, EAST, DOWN, etc.
    destination: str             # Target room name
    condition: Optional[str] = None      # When this exit is taken
    access: AccessLevel = AccessLevel.PUBLIC
    bidirectional: bool = False  # Can you come back this way?


@dataclass
class Content:
    """Something contained in a room (variable, data structure, etc.)."""
    name: str
    type: str
    purpose: str
    mutable: bool = True


@dataclass
class Topic:
    """A conversation topic for an entity."""
    name: str
    how: str                     # How it works
    why: str                     # Why it's designed this way
    watch_out: Optional[str] = None  # Gotchas
    tunable: bool = False        # Can be configured


@dataclass
class Room:
    """
    A room in the Mind Palace - represents a function, class, or method.
    The atomic navigable unit.
    """
    name: str
    building: str
    floor: int = 1
    description: str = ""

    # Code anchor
    anchor: Optional[Anchor] = None

    # What's in the room
    contents: List[Content] = field(default_factory=list)

    # Navigation
    exits: List[Exit] = field(default_factory=list)

    # Warnings
    hazards: List[Hazard] = field(default_factory=list)

    # History
    history: List[HistoryEntry] = field(default_factory=list)

    # Metadata
    tags: List[str] = field(default_factory=list)
    last_modified: Optional[str] = None
    modified_by: Optional[str] = None

    def get_exit(self, direction: str) -> Optional[Exit]:
        """Get exit by direction."""
        direction = direction.upper()
        for exit in self.exits:
            if exit.direction.upper() == direction:
                return exit
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "type": "room",
            "name": self.name,
            "building": self.building,
            "floor": self.floor,
            "description": self.description,
            "anchor": {
                "pattern": self.anchor.pattern,
                "file": self.anchor.file,
                "line": self.anchor.line,
                "signature_hash": self.anchor.signature_hash,
                "is_regex": self.anchor.is_regex,
            } if self.anchor else None,
            "contents": [
                {"name": c.name, "type": c.type, "purpose": c.purpose, "mutable": c.mutable}
                for c in self.contents
            ],
            "exits": [
                {
                    "direction": e.direction,
                    "destination": e.destination,
                    "condition": e.condition,
                    "access": e.access.value,
                }
                for e in self.exits
            ],
            "hazards": [
                {"type": h.type.value, "description": h.description, "severity": h.severity}
                for h in self.hazards
            ],
            "history": [
                {"date": h.date, "note": h.note, "author": h.author}
                for h in self.history
            ],
            "tags": self.tags,
            "last_modified": self.last_modified,
            "modified_by": self.modified_by,
        }


@dataclass
class Building:
    """
    A building in the Mind Palace - represents a module or coherent unit.
    Contains rooms across multiple floors.
    """
    name: str
    region: str
    purpose: str = ""
    floors: int = 1

    # Entry points
    main_entrance: Optional[str] = None  # Primary entry room
    side_doors: List[str] = field(default_factory=list)  # Secondary entries
    internal_only: List[str] = field(default_factory=list)  # Private rooms

    # Code anchor
    anchor: Optional[Anchor] = None

    # Metadata
    tags: List[str] = field(default_factory=list)
    history: List[HistoryEntry] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "type": "building",
            "name": self.name,
            "region": self.region,
            "purpose": self.purpose,
            "floors": self.floors,
            "main_entrance": self.main_entrance,
            "side_doors": self.side_doors,
            "internal_only": self.internal_only,
            "anchor": {
                "pattern": self.anchor.pattern,
                "file": self.anchor.file,
                "is_regex": self.anchor.is_regex,
            } if self.anchor else None,
            "tags": self.tags,
            "history": [
                {"date": h.date, "note": h.note, "author": h.author}
                for h in self.history
            ],
        }


@dataclass
class Region:
    """
    A region in the Mind Palace - represents an architectural domain.
    The highest level of organization (neighborhood/district).
    """
    name: str
    description: str = ""

    # Connections
    adjacent: List[str] = field(default_factory=list)  # Adjacent regions
    entry_points: List[str] = field(default_factory=list)  # Key files to start

    # Metadata
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "type": "region",
            "name": self.name,
            "description": self.description,
            "adjacent": self.adjacent,
            "entry_points": self.entry_points,
            "tags": self.tags,
        }


@dataclass
class Entity:
    """
    An entity (NPC) in the Mind Palace - embodies subsystem knowledge.
    Can be "asked" about topics to retrieve operational knowledge.
    """
    name: str
    location: str                # room or building where they reside
    role: str                    # What they guard/manage

    # Conversation topics
    topics: List[Topic] = field(default_factory=list)

    # Personality (affects response style)
    personality: Optional[str] = None

    # Metadata
    tags: List[str] = field(default_factory=list)

    def get_topic(self, topic_name: str) -> Optional[Topic]:
        """Find a topic by name (case-insensitive partial match)."""
        topic_name = topic_name.lower()
        for topic in self.topics:
            if topic_name in topic.name.lower():
                return topic
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "type": "entity",
            "name": self.name,
            "location": self.location,
            "role": self.role,
            "personality": self.personality,
            "topics": [
                {
                    "name": t.name,
                    "how": t.how,
                    "why": t.why,
                    "watch_out": t.watch_out,
                    "tunable": t.tunable,
                }
                for t in self.topics
            ],
            "tags": self.tags,
        }


@dataclass
class Palace:
    """
    The complete Mind Palace for a codebase.
    Top-level container with all regions, buildings, rooms, and entities.
    """
    name: str                    # Palace name (usually project name)
    version: str = "1.0"
    created: Optional[str] = None
    last_updated: Optional[str] = None

    # Structure
    regions: Dict[str, Region] = field(default_factory=dict)
    buildings: Dict[str, Building] = field(default_factory=dict)
    rooms: Dict[str, Room] = field(default_factory=dict)
    entities: Dict[str, Entity] = field(default_factory=dict)

    # Current navigation state (not persisted)
    current_room: Optional[str] = None
    current_building: Optional[str] = None
    current_region: Optional[str] = None
    visited: List[str] = field(default_factory=list)

    def get_room(self, name: str) -> Optional[Room]:
        """Get a room by name."""
        return self.rooms.get(name)

    def get_building(self, name: str) -> Optional[Building]:
        """Get a building by name."""
        return self.buildings.get(name)

    def get_region(self, name: str) -> Optional[Region]:
        """Get a region by name."""
        return self.regions.get(name)

    def get_entity(self, name: str) -> Optional[Entity]:
        """Get an entity by name (case-insensitive)."""
        name_lower = name.lower()
        for entity_name, entity in self.entities.items():
            if entity_name.lower() == name_lower:
                return entity
        return None

    def rooms_in_building(self, building_name: str) -> List[Room]:
        """Get all rooms in a building."""
        return [r for r in self.rooms.values() if r.building == building_name]

    def buildings_in_region(self, region_name: str) -> List[Building]:
        """Get all buildings in a region."""
        return [b for b in self.buildings.values() if b.region == region_name]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "created": self.created,
            "last_updated": self.last_updated,
            "regions": list(self.regions.keys()),
            "buildings": list(self.buildings.keys()),
            "rooms": list(self.rooms.keys()),
            "entities": list(self.entities.keys()),
        }
