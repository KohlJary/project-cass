"""
Mind Palace Storage - Load and save palace data from/to .mind-palace/ directory.

Palace data is stored as YAML files in a structured directory hierarchy.
Designed to be portable - can be dropped into any project.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    Link,
    LinkType,
    Palace,
    PalaceReference,
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

        # Parse references
        references = []
        for ref_data in index.get("references", []):
            try:
                references.append(PalaceReference.from_dict(ref_data))
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping invalid reference: {e}")

        palace = Palace(
            name=index.get("name", "unnamed"),
            version=index.get("version", "1.0"),
            created=index.get("created"),
            last_updated=index.get("last_updated"),
            references=references,
        )

        # Load regions
        regions_dir = self.palace_dir / "regions"
        if regions_dir.exists():
            for region_dir in regions_dir.iterdir():
                if region_dir.is_dir():
                    region = self._load_region(region_dir)
                    if region:
                        # Use add_region to index by both slug and name
                        palace.add_region(region)

                        # Load buildings in this region
                        buildings_dir = region_dir / "buildings"
                        if buildings_dir.exists():
                            for building_dir in buildings_dir.iterdir():
                                if building_dir.is_dir():
                                    building = self._load_building(building_dir)
                                    if building:
                                        # Use add_building to index by both slug and name
                                        palace.add_building(building)

                                        # Load rooms in this building
                                        rooms_dir = building_dir / "rooms"
                                        if rooms_dir.exists():
                                            for room_file in rooms_dir.glob("*.yaml"):
                                                room = self._load_room(room_file)
                                                if room:
                                                    # Use add_room to index by both slug and name
                                                    palace.add_room(room)

        # Load entities
        entities_dir = self.palace_dir / "entities"
        if entities_dir.exists():
            for entity_file in entities_dir.glob("*.yaml"):
                entity = self._load_entity(entity_file)
                if entity:
                    # Use add_entity to index by both slug and name
                    palace.add_entity(entity)

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

    # ========== Cross-Palace Links ==========

    LINKS_FILE = "links.yaml"

    def load_links(self) -> List[Link]:
        """
        Load cross-palace links from links.yaml.

        Returns:
            List of Link objects, or empty list if no links file exists
        """
        links_path = self.palace_dir / self.LINKS_FILE
        if not links_path.exists():
            return []

        with open(links_path) as f:
            data = yaml.safe_load(f)

        if not data or "links" not in data:
            return []

        links = []
        for link_data in data["links"]:
            try:
                links.append(Link.from_dict(link_data))
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping invalid link: {e}")

        logger.info(f"Loaded {len(links)} cross-palace links from {links_path}")
        return links

    def save_links(self, links: List[Link]) -> None:
        """
        Save cross-palace links to links.yaml.

        Args:
            links: List of Link objects to save
        """
        links_path = self.palace_dir / self.LINKS_FILE

        data = {
            "version": "1.0",
            "updated": datetime.now().isoformat(),
            "links": [link.to_dict() for link in links],
        }

        with open(links_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Saved {len(links)} cross-palace links to {links_path}")

    def add_links(self, new_links: List[Link]) -> int:
        """
        Add links to existing links (deduplicating).

        Args:
            new_links: Links to add

        Returns:
            Number of new links added
        """
        existing = self.load_links()

        # Create a set of existing link signatures for deduplication
        existing_sigs = {
            (l.from_room, l.to_palace, l.to_path, l.link_type)
            for l in existing
        }

        added = 0
        for link in new_links:
            sig = (link.from_room, link.to_palace, link.to_path, link.link_type)
            if sig not in existing_sigs:
                existing.append(link)
                existing_sigs.add(sig)
                added += 1

        if added > 0:
            self.save_links(existing)

        return added

    def _load_region(self, region_dir: Path) -> Optional[Region]:
        """Load a region from its directory."""
        region_file = region_dir / "region.yaml"
        if not region_file.exists():
            return None

        with open(region_file) as f:
            data = yaml.safe_load(f)

        return Region(
            name=data.get("name", region_dir.name),
            slug=data.get("slug"),  # Will auto-generate if None
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
            slug=data.get("slug"),  # Will auto-generate if None
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

        links = []
        for l in data.get("links", []):
            try:
                links.append(Link.from_dict(l))
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping invalid link in {room_file}: {e}")

        return Room(
            name=data.get("name", room_file.stem),
            slug=data.get("slug"),  # Will auto-generate if None
            building=data.get("building", ""),
            floor=data.get("floor", 1),
            description=data.get("description", ""),
            anchor=anchor,
            contents=contents,
            exits=exits,
            hazards=hazards,
            links=links,
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
            slug=data.get("slug"),  # Will auto-generate if None
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
        palace.add_region(region)  # Indexes by slug and name
        self._save_region(region)

    def add_building(self, palace: Palace, building: Building) -> None:
        """Add a building to the palace and save it."""
        palace.add_building(building)  # Indexes by slug and name
        self._save_building(building)

    def add_room(self, palace: Palace, room: Room) -> None:
        """Add a room to the palace and save it."""
        palace.add_room(room)  # Indexes by slug and name
        self._save_room(room)

    def add_entity(self, palace: Palace, entity: Entity) -> None:
        """Add an entity to the palace and save it."""
        palace.add_entity(entity)  # Indexes by slug and name
        self._save_entity(entity)
