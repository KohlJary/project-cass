"""
Mind Palace Data Models - Spatial representation of codebases.

These models define the structure of a Mind Palace - a navigable MUD-like
representation of code architecture that LLMs can explore spatially.

Designed to be project-agnostic: can be initialized in any codebase.

Slug System:
- Slugs are deterministic identifiers derived from code anchors
- Format: lowercase, alphanumeric + hyphens only
- Enables URL-like navigation: palace/region/building/room
- Stable across regeneration (same code = same slugs)
- Allows multi-agent communication with shared references
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


def slugify(text: str) -> str:
    """
    Convert text to a URL-safe slug.

    Examples:
        "MemoryManager" -> "memorymanager"
        "add_message" -> "add-message"
        "backend/memory.py" -> "backend-memory"
    """
    # Lowercase
    slug = text.lower()
    # Replace path separators and underscores with hyphens
    slug = slug.replace("/", "-").replace("\\", "-").replace("_", "-").replace(".", "-")
    # Remove non-alphanumeric except hyphens
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    return slug


def generate_slug_from_anchor(anchor: "Anchor", name: str) -> str:
    """
    Generate a deterministic slug from a code anchor.

    The slug is derived from the file path and pattern, ensuring:
    - Same code location = same slug (survives regeneration)
    - Different agents mapping same codebase get same slugs

    Format: {file_stem}-{pattern_slug} or just {file_stem} if no pattern
    Examples:
        file="memory.py", pattern="def add_message" -> "memory-add-message"
        file="backend/memory.py", pattern="class MemoryManager" -> "backend-memory-memorymanager"
        file="memory.py", pattern="" -> "memory" (file-based, no pattern)
    """
    if not anchor:
        return slugify(name)

    # Get file path without extension
    file_path = Path(anchor.file)
    file_stem = str(file_path.with_suffix(""))

    # If no pattern, just use the file stem (for buildings representing modules)
    pattern = anchor.pattern.strip() if anchor.pattern else ""
    if not pattern:
        return slugify(file_stem)

    # Extract the key identifier from the pattern
    # Common patterns: "def func_name", "class ClassName", "async def func"
    pattern_parts = pattern.split()

    # Get the last meaningful word (usually the name)
    identifier = pattern_parts[-1] if pattern_parts else name
    # Remove any trailing punctuation like ( or :
    identifier = re.sub(r"[^a-zA-Z0-9_].*$", "", identifier)

    # Combine file path and identifier
    slug = slugify(f"{file_stem}-{identifier}")

    return slug


def slug_hash(slug: str) -> str:
    """
    Generate a short hash suffix for slug uniqueness.
    Used when slug collisions occur.
    """
    return hashlib.sha256(slug.encode()).hexdigest()[:8]


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


class LinkType(Enum):
    """Types of cross-palace links."""
    API_CALL = "api_call"        # Frontend calling backend API
    IMPORT = "import"            # Code import/dependency
    REFERENCE = "reference"      # Documentation or semantic reference
    WEBSOCKET = "websocket"      # WebSocket connection
    GRAPHQL = "graphql"          # GraphQL query/mutation


@dataclass
class Link:
    """
    A cross-palace link - connects elements across sub-palaces.

    Used to track relationships like:
    - Frontend API calls to backend routes
    - Shared type definitions
    - Cross-module dependencies

    Links are stored per-palace in .mind-palace/links.yaml
    """
    from_room: str               # Room slug in this palace
    to_palace: str               # Target palace name (e.g., "backend")
    to_path: str                 # Path within target palace
    link_type: LinkType          # Type of relationship
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Metadata examples:
    #   api_call: {"method": "GET", "path": "/admin/users", "handler": "auth.py"}
    #   import: {"module": "backend.memory", "names": ["add_message"]}

    def to_dict(self) -> Dict:
        return {
            "from_room": self.from_room,
            "to_palace": self.to_palace,
            "to_path": self.to_path,
            "link_type": self.link_type.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Link":
        return cls(
            from_room=data["from_room"],
            to_palace=data["to_palace"],
            to_path=data["to_path"],
            link_type=LinkType(data["link_type"]),
            metadata=data.get("metadata", {}),
        )


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

    Slug format: {file_stem}-{function_name}
    Example: memory-add-message (for def add_message in memory.py)
    """
    name: str
    building: str
    floor: int = 1
    description: str = ""

    # Deterministic identifier for cross-agent communication
    slug: Optional[str] = None

    # Code anchor
    anchor: Optional[Anchor] = None

    def __post_init__(self):
        """Generate slug from anchor if not provided."""
        if self.slug is None and self.anchor:
            self.slug = generate_slug_from_anchor(self.anchor, self.name)
        elif self.slug is None:
            self.slug = slugify(self.name)

    # What's in the room
    contents: List[Content] = field(default_factory=list)

    # Navigation
    exits: List[Exit] = field(default_factory=list)

    # Warnings
    hazards: List[Hazard] = field(default_factory=list)

    # Cross-palace links (outbound connections to other palaces)
    links: List[Link] = field(default_factory=list)

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
            "slug": self.slug,
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
            "links": [link.to_dict() for link in self.links] if self.links else [],
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

    Slug format: {file_stem} or {file_stem}-{class_name}
    Example: memory (for memory.py) or memory-memorymanager (for class)
    """
    name: str
    region: str
    purpose: str = ""
    floors: int = 1

    # Deterministic identifier for cross-agent communication
    slug: Optional[str] = None

    # Entry points
    main_entrance: Optional[str] = None  # Primary entry room
    side_doors: List[str] = field(default_factory=list)  # Secondary entries
    internal_only: List[str] = field(default_factory=list)  # Private rooms

    # Code anchor
    anchor: Optional[Anchor] = None

    def __post_init__(self):
        """Generate slug from anchor if not provided."""
        if self.slug is None and self.anchor:
            self.slug = generate_slug_from_anchor(self.anchor, self.name)
        elif self.slug is None:
            self.slug = slugify(self.name)

    # Metadata
    tags: List[str] = field(default_factory=list)
    history: List[HistoryEntry] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "type": "building",
            "name": self.name,
            "slug": self.slug,
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

    Slug format: {directory_path}
    Example: backend, backend-handlers, tui-frontend
    """
    name: str
    description: str = ""

    # Deterministic identifier for cross-agent communication
    slug: Optional[str] = None

    # Connections
    adjacent: List[str] = field(default_factory=list)  # Adjacent regions
    entry_points: List[str] = field(default_factory=list)  # Key files to start

    # Metadata
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Generate slug from name if not provided."""
        if self.slug is None:
            self.slug = slugify(self.name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "type": "region",
            "name": self.name,
            "slug": self.slug,
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

    Slug format: {name_slugified}
    Example: memorykeeper, toolrouterkeeper
    """
    name: str
    location: str                # room or building where they reside
    role: str                    # What they guard/manage

    # Deterministic identifier for cross-agent communication
    slug: Optional[str] = None

    # Conversation topics
    topics: List[Topic] = field(default_factory=list)

    # Personality (affects response style)
    personality: Optional[str] = None

    # Metadata
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Generate slug from name if not provided."""
        if self.slug is None:
            self.slug = slugify(self.name)

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
            "slug": self.slug,
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
class PalaceReference:
    """
    A reference to another palace (like project references in C#).

    Defines cross-palace relationships at the palace level, enabling
    language-agnostic link generation.
    """
    palace: str                  # Target palace name/slug
    type: str = "api"            # Relationship type: api, import, shared, etc.
    description: str = ""        # Optional description

    def to_dict(self) -> Dict[str, Any]:
        return {
            "palace": self.palace,
            "type": self.type,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "PalaceReference":
        return cls(
            palace=data["palace"],
            type=data.get("type", "api"),
            description=data.get("description", ""),
        )


@dataclass
class Palace:
    """
    The complete Mind Palace for a codebase.
    Top-level container with all regions, buildings, rooms, and entities.

    Slug format: {project_name}
    Example: cass-vessel, project-cass

    Full path format for navigation: {palace_slug}/{region_slug}/{building_slug}/{room_slug}
    Example: cass-vessel/backend/memory/add-message
    """
    name: str                    # Palace name (usually project name)
    version: str = "1.0"
    created: Optional[str] = None
    last_updated: Optional[str] = None

    # Deterministic identifier for cross-agent communication
    slug: Optional[str] = None

    # Cross-palace references (like project references in C#)
    references: List[PalaceReference] = field(default_factory=list)

    # Structure - keyed by slug for O(1) lookup
    regions: Dict[str, Region] = field(default_factory=dict)
    buildings: Dict[str, Building] = field(default_factory=dict)
    rooms: Dict[str, Room] = field(default_factory=dict)
    entities: Dict[str, Entity] = field(default_factory=dict)

    # Index by name for backward compatibility
    _regions_by_name: Dict[str, str] = field(default_factory=dict, repr=False)
    _buildings_by_name: Dict[str, str] = field(default_factory=dict, repr=False)
    _rooms_by_name: Dict[str, str] = field(default_factory=dict, repr=False)
    _entities_by_name: Dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        """Generate slug from name if not provided."""
        if self.slug is None:
            self.slug = slugify(self.name)

    # Current navigation state (not persisted)
    current_room: Optional[str] = None
    current_building: Optional[str] = None
    current_region: Optional[str] = None
    visited: List[str] = field(default_factory=list)

    def get_room(self, name_or_slug: str) -> Optional[Room]:
        """Get a room by name or slug."""
        # Try direct lookup (by slug)
        if name_or_slug in self.rooms:
            return self.rooms[name_or_slug]
        # Try by name index
        if name_or_slug in self._rooms_by_name:
            return self.rooms.get(self._rooms_by_name[name_or_slug])
        # Fallback: linear search by name
        for room in self.rooms.values():
            if room.name == name_or_slug:
                return room
        return None

    def get_building(self, name_or_slug: str) -> Optional[Building]:
        """Get a building by name or slug."""
        if name_or_slug in self.buildings:
            return self.buildings[name_or_slug]
        if name_or_slug in self._buildings_by_name:
            return self.buildings.get(self._buildings_by_name[name_or_slug])
        for building in self.buildings.values():
            if building.name == name_or_slug:
                return building
        return None

    def get_region(self, name_or_slug: str) -> Optional[Region]:
        """Get a region by name or slug."""
        if name_or_slug in self.regions:
            return self.regions[name_or_slug]
        if name_or_slug in self._regions_by_name:
            return self.regions.get(self._regions_by_name[name_or_slug])
        for region in self.regions.values():
            if region.name == name_or_slug:
                return region
        return None

    def get_entity(self, name_or_slug: str) -> Optional[Entity]:
        """Get an entity by name or slug (case-insensitive)."""
        # Try direct lookup (by slug)
        if name_or_slug in self.entities:
            return self.entities[name_or_slug]
        # Try by name index
        name_lower = name_or_slug.lower()
        if name_lower in self._entities_by_name:
            return self.entities.get(self._entities_by_name[name_lower])
        # Fallback: case-insensitive search
        for entity in self.entities.values():
            if entity.name.lower() == name_lower or entity.slug == name_or_slug:
                return entity
        return None

    def add_room(self, room: Room) -> None:
        """Add a room, indexing by both slug and name."""
        self.rooms[room.slug] = room
        self._rooms_by_name[room.name] = room.slug

    def add_building(self, building: Building) -> None:
        """Add a building, indexing by both slug and name."""
        self.buildings[building.slug] = building
        self._buildings_by_name[building.name] = building.slug

    def add_region(self, region: Region) -> None:
        """Add a region, indexing by both slug and name."""
        self.regions[region.slug] = region
        self._regions_by_name[region.name] = region.slug

    def add_entity(self, entity: Entity) -> None:
        """Add an entity, indexing by both slug and name."""
        self.entities[entity.slug] = entity
        self._entities_by_name[entity.name.lower()] = entity.slug

    def resolve_path(self, path: str) -> Optional[Room | Building | Region]:
        """
        Resolve a slug path to a palace element.

        Path format: [region/][building/][room]
        Examples:
            "memory/context-sources/add-message" -> Room
            "memory/context-sources" -> Building
            "memory" -> Region
            "add-message" -> Room (searches all by suffix)
            "backend-memory-context-sources-add-message" -> Room (direct slug)

        The method constructs full slugs from path parts when needed.
        Full slugs are: {palace_slug}-{region}-{building}-{room}

        Returns the most specific element matching the path.
        """
        parts = [p for p in path.strip("/").split("/") if p]

        if not parts:
            return None

        # First, try direct slug lookup (full deterministic slugs)
        direct_slug = parts[0] if len(parts) == 1 else "-".join(parts)
        if direct_slug in self.rooms:
            return self.rooms[direct_slug]
        if direct_slug in self.buildings:
            return self.buildings[direct_slug]
        if direct_slug in self.regions:
            return self.regions[direct_slug]

        if len(parts) == 1:
            # Single part - search for suffix matches
            suffix = parts[0]
            # Try as region first
            if suffix in self.regions:
                return self.regions[suffix]
            # Search for building ending with this suffix
            for building in self.buildings.values():
                if building.slug.endswith(f"-{suffix}") or building.slug == suffix:
                    return building
            # Search for room ending with this suffix
            for room in self.rooms.values():
                if room.slug.endswith(f"-{suffix}") or room.slug == suffix:
                    return room
            return None

        if len(parts) == 2:
            # region/building OR building/room
            first, second = parts
            # Try region/building
            if first in self.regions:
                # Look for building with slug like {palace}-{region}-{building}
                expected_suffix = f"-{first}-{second}"
                for building in self.buildings.values():
                    if building.slug.endswith(expected_suffix):
                        return building
                # Also try: building name matches second
                for building in self.buildings.values():
                    if building.region == first and slugify(building.name) == second:
                        return building
            # Try building/room - find building first, then room
            for building in self.buildings.values():
                if building.slug.endswith(f"-{first}") or slugify(building.name) == first:
                    # Look for room with this building and room suffix
                    for room in self.rooms.values():
                        if room.building == building.name and room.slug.endswith(f"-{second}"):
                            return room
            return None

        if len(parts) == 3:
            # region/building/room
            region_hint, building_hint, room_hint = parts
            # Construct expected slug pattern
            if self.slug:
                expected_room_slug = f"{self.slug}-{region_hint}-{building_hint}-{room_hint}"
                if expected_room_slug in self.rooms:
                    return self.rooms[expected_room_slug]
            # Fallback: search by suffixes
            for room in self.rooms.values():
                if room.slug.endswith(f"-{room_hint}"):
                    building = self.get_building(room.building)
                    if building and building.slug.endswith(f"-{building_hint}"):
                        region = self.get_region(building.region)
                        if region and region.slug == region_hint:
                            return room
            return None

        return None

    def get_full_path(self, room: Room) -> str:
        """
        Get the full slug path for a room.

        Returns: "region_slug/building_slug/room_slug"
        """
        building = self.get_building(room.building)
        if not building:
            return room.slug

        region = self.get_region(building.region)
        if not region:
            return f"{building.slug}/{room.slug}"

        return f"{region.slug}/{building.slug}/{room.slug}"

    def rooms_in_building(self, building_name_or_slug: str) -> List[Room]:
        """Get all rooms in a building."""
        building = self.get_building(building_name_or_slug)
        if not building:
            return []
        return [r for r in self.rooms.values()
                if r.building == building.name or r.building == building.slug]

    def buildings_in_region(self, region_name_or_slug: str) -> List[Building]:
        """Get all buildings in a region."""
        region = self.get_region(region_name_or_slug)
        if not region:
            return []
        return [b for b in self.buildings.values()
                if b.region == region.name or b.region == region.slug]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "name": self.name,
            "slug": self.slug,
            "version": self.version,
            "created": self.created,
            "last_updated": self.last_updated,
            "references": [ref.to_dict() for ref in self.references] if self.references else [],
            "regions": list(self.regions.keys()),
            "buildings": list(self.buildings.keys()),
            "rooms": list(self.rooms.keys()),
            "entities": list(self.entities.keys()),
        }
