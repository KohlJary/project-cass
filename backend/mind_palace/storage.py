"""
Mind Palace Storage - Load and save palace data from/to .mind-palace/ directory.

Palace data is stored as YAML files in a structured directory hierarchy.
Designed to be portable - can be dropped into any project.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .models import (
    AccessLevel,
    Anchor,
    Building,
    Content,
    Entity,
    Exit,
    Hazard,
    HazardType,
    HistoryEntry,
    Palace,
    Region,
    Room,
    Topic,
)

logger = logging.getLogger(__name__)


class PalaceStorage:
    """
    Handles loading and saving Mind Palace data.

    Palace structure on disk:
    .mind-palace/
    ├── palace.yaml           # Top-level index
    ├── regions/
    │   └── {region}/
    │       ├── region.yaml
    │       └── buildings/
    │           └── {building}/
    │               ├── building.yaml
    │               └── rooms/
    │                   └── {room}.yaml
    └── entities/
        └── {entity}.yaml
    """

    PALACE_DIR = ".mind-palace"
    PALACE_INDEX = "palace.yaml"

    def __init__(self, project_root: Path):
        """
        Initialize storage for a project.

        Args:
            project_root: Path to the project root directory
        """
        self.project_root = Path(project_root)
        self.palace_dir = self.project_root / self.PALACE_DIR

    def exists(self) -> bool:
        """Check if a palace exists for this project."""
        return (self.palace_dir / self.PALACE_INDEX).exists()

    def initialize(self, name: str) -> Palace:
        """
        Initialize a new empty palace for this project.

        Args:
            name: Name for the palace (usually project name)

        Returns:
            New empty Palace instance
        """
        # Create directory structure
        self.palace_dir.mkdir(parents=True, exist_ok=True)
        (self.palace_dir / "regions").mkdir(exist_ok=True)
        (self.palace_dir / "entities").mkdir(exist_ok=True)

        # Create palace
        palace = Palace(
            name=name,
            version="1.0",
            created=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
        )

        # Save initial state
        self.save(palace)

        logger.info(f"Initialized new Mind Palace: {name} at {self.palace_dir}")
        return palace

    def load(self) -> Optional[Palace]:
        """
        Load the palace from disk.

        Returns:
            Palace instance, or None if no palace exists
        """
        if not self.exists():
            logger.warning(f"No palace found at {self.palace_dir}")
            return None

        # Load index
        index_path = self.palace_dir / self.PALACE_INDEX
        with open(index_path) as f:
            index = yaml.safe_load(f)

        palace = Palace(
            name=index.get("name", "unnamed"),
            version=index.get("version", "1.0"),
            created=index.get("created"),
            last_updated=index.get("last_updated"),
        )

        # Load regions
        regions_dir = self.palace_dir / "regions"
        if regions_dir.exists():
            for region_dir in regions_dir.iterdir():
                if region_dir.is_dir():
                    region = self._load_region(region_dir)
                    if region:
                        palace.regions[region.name] = region

                        # Load buildings in this region
                        buildings_dir = region_dir / "buildings"
                        if buildings_dir.exists():
                            for building_dir in buildings_dir.iterdir():
                                if building_dir.is_dir():
                                    building = self._load_building(building_dir)
                                    if building:
                                        palace.buildings[building.name] = building

                                        # Load rooms in this building
                                        rooms_dir = building_dir / "rooms"
                                        if rooms_dir.exists():
                                            for room_file in rooms_dir.glob("*.yaml"):
                                                room = self._load_room(room_file)
                                                if room:
                                                    palace.rooms[room.name] = room

        # Load entities
        entities_dir = self.palace_dir / "entities"
        if entities_dir.exists():
            for entity_file in entities_dir.glob("*.yaml"):
                entity = self._load_entity(entity_file)
                if entity:
                    palace.entities[entity.name] = entity

        logger.info(
            f"Loaded palace '{palace.name}': "
            f"{len(palace.regions)} regions, "
            f"{len(palace.buildings)} buildings, "
            f"{len(palace.rooms)} rooms, "
            f"{len(palace.entities)} entities"
        )

        return palace

    def save(self, palace: Palace) -> None:
        """
        Save the palace to disk.

        Args:
            palace: Palace instance to save
        """
        palace.last_updated = datetime.now().isoformat()

        # Save index
        index_path = self.palace_dir / self.PALACE_INDEX
        with open(index_path, "w") as f:
            yaml.dump(palace.to_dict(), f, default_flow_style=False, sort_keys=False)

        # Save regions
        for region in palace.regions.values():
            self._save_region(region)

        # Save buildings
        for building in palace.buildings.values():
            self._save_building(building)

        # Save rooms
        for room in palace.rooms.values():
            self._save_room(room)

        # Save entities
        for entity in palace.entities.values():
            self._save_entity(entity)

        logger.info(f"Saved palace '{palace.name}'")

    def _load_region(self, region_dir: Path) -> Optional[Region]:
        """Load a region from its directory."""
        region_file = region_dir / "region.yaml"
        if not region_file.exists():
            return None

        with open(region_file) as f:
            data = yaml.safe_load(f)

        return Region(
            name=data.get("name", region_dir.name),
            description=data.get("description", ""),
            adjacent=data.get("adjacent", []),
            entry_points=data.get("entry_points", []),
            tags=data.get("tags", []),
        )

    def _load_building(self, building_dir: Path) -> Optional[Building]:
        """Load a building from its directory."""
        building_file = building_dir / "building.yaml"
        if not building_file.exists():
            return None

        with open(building_file) as f:
            data = yaml.safe_load(f)

        anchor = None
        if data.get("anchor"):
            anchor = Anchor(
                pattern=data["anchor"].get("pattern", ""),
                file=data["anchor"].get("file", ""),
                is_regex=data["anchor"].get("is_regex", False),
            )

        return Building(
            name=data.get("name", building_dir.name),
            region=data.get("region", ""),
            purpose=data.get("purpose", ""),
            floors=data.get("floors", 1),
            main_entrance=data.get("main_entrance"),
            side_doors=data.get("side_doors", []),
            internal_only=data.get("internal_only", []),
            anchor=anchor,
            tags=data.get("tags", []),
            history=self._parse_history(data.get("history", [])),
        )

    def _load_room(self, room_file: Path) -> Optional[Room]:
        """Load a room from its file."""
        with open(room_file) as f:
            data = yaml.safe_load(f)

        anchor = None
        if data.get("anchor"):
            anchor = Anchor(
                pattern=data["anchor"].get("pattern", ""),
                file=data["anchor"].get("file", ""),
                line=data["anchor"].get("line"),
                signature_hash=data["anchor"].get("signature_hash"),
                last_verified=data["anchor"].get("last_verified"),
                is_regex=data["anchor"].get("is_regex", False),
            )

        contents = []
        for c in data.get("contents", []):
            contents.append(Content(
                name=c.get("name", ""),
                type=c.get("type", ""),
                purpose=c.get("purpose", ""),
                mutable=c.get("mutable", True),
            ))

        exits = []
        for e in data.get("exits", []):
            exits.append(Exit(
                direction=e.get("direction", ""),
                destination=e.get("destination", ""),
                condition=e.get("condition"),
                access=AccessLevel(e.get("access", "public")),
                bidirectional=e.get("bidirectional", False),
            ))

        hazards = []
        for h in data.get("hazards", []):
            hazards.append(Hazard(
                type=HazardType(h.get("type", "invariant")),
                description=h.get("description", ""),
                severity=h.get("severity", 1),
            ))

        return Room(
            name=data.get("name", room_file.stem),
            building=data.get("building", ""),
            floor=data.get("floor", 1),
            description=data.get("description", ""),
            anchor=anchor,
            contents=contents,
            exits=exits,
            hazards=hazards,
            history=self._parse_history(data.get("history", [])),
            tags=data.get("tags", []),
            last_modified=data.get("last_modified"),
            modified_by=data.get("modified_by"),
        )

    def _load_entity(self, entity_file: Path) -> Optional[Entity]:
        """Load an entity from its file."""
        with open(entity_file) as f:
            data = yaml.safe_load(f)

        topics = []
        for t in data.get("topics", []):
            topics.append(Topic(
                name=t.get("name", ""),
                how=t.get("how", ""),
                why=t.get("why", ""),
                watch_out=t.get("watch_out"),
                tunable=t.get("tunable", False),
            ))

        return Entity(
            name=data.get("name", entity_file.stem),
            location=data.get("location", ""),
            role=data.get("role", ""),
            topics=topics,
            personality=data.get("personality"),
            tags=data.get("tags", []),
        )

    def _parse_history(self, history_data: list) -> list:
        """Parse history entries from YAML data."""
        entries = []
        for h in history_data:
            entries.append(HistoryEntry(
                date=h.get("date", ""),
                note=h.get("note", ""),
                author=h.get("author"),
            ))
        return entries

    def _save_region(self, region: Region) -> None:
        """Save a region to disk."""
        region_dir = self.palace_dir / "regions" / self._safe_name(region.name)
        region_dir.mkdir(parents=True, exist_ok=True)

        region_file = region_dir / "region.yaml"
        with open(region_file, "w") as f:
            yaml.dump(region.to_dict(), f, default_flow_style=False, sort_keys=False)

    def _save_building(self, building: Building) -> None:
        """Save a building to disk."""
        region_dir = self.palace_dir / "regions" / self._safe_name(building.region)
        building_dir = region_dir / "buildings" / self._safe_name(building.name)
        building_dir.mkdir(parents=True, exist_ok=True)

        building_file = building_dir / "building.yaml"
        with open(building_file, "w") as f:
            yaml.dump(building.to_dict(), f, default_flow_style=False, sort_keys=False)

    def _save_room(self, room: Room) -> None:
        """Save a room to disk."""
        building = room.building
        # Find the region for this building
        region = None
        for r_name, r in self._find_region_for_building(building):
            region = r_name
            break

        if not region:
            # Default to a generic region
            region = "unmapped"

        rooms_dir = (
            self.palace_dir / "regions" / self._safe_name(region) /
            "buildings" / self._safe_name(building) / "rooms"
        )
        rooms_dir.mkdir(parents=True, exist_ok=True)

        room_file = rooms_dir / f"{self._safe_name(room.name)}.yaml"
        with open(room_file, "w") as f:
            yaml.dump(room.to_dict(), f, default_flow_style=False, sort_keys=False)

    def _find_region_for_building(self, building_name: str):
        """Find which region a building belongs to."""
        buildings_pattern = self.palace_dir / "regions" / "*" / "buildings" / building_name
        for match in self.palace_dir.glob(f"regions/*/buildings/{self._safe_name(building_name)}"):
            region_name = match.parent.parent.name
            yield region_name, match

    def _save_entity(self, entity: Entity) -> None:
        """Save an entity to disk."""
        entities_dir = self.palace_dir / "entities"
        entities_dir.mkdir(parents=True, exist_ok=True)

        entity_file = entities_dir / f"{self._safe_name(entity.name)}.yaml"
        with open(entity_file, "w") as f:
            yaml.dump(entity.to_dict(), f, default_flow_style=False, sort_keys=False)

    def _safe_name(self, name: str) -> str:
        """Convert a name to a filesystem-safe string."""
        return name.replace(" ", "-").replace("/", "-").replace("\\", "-").lower()

    # Convenience methods for adding elements

    def add_region(self, palace: Palace, region: Region) -> None:
        """Add a region to the palace and save it."""
        palace.regions[region.name] = region
        self._save_region(region)

    def add_building(self, palace: Palace, building: Building) -> None:
        """Add a building to the palace and save it."""
        palace.buildings[building.name] = building
        self._save_building(building)

    def add_room(self, palace: Palace, room: Room) -> None:
        """Add a room to the palace and save it."""
        palace.rooms[room.name] = room
        self._save_room(room)

    def add_entity(self, palace: Palace, entity: Entity) -> None:
        """Add an entity to the palace and save it."""
        palace.entities[entity.name] = entity
        self._save_entity(entity)
