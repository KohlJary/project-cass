"""
PalaceRegistry - Cross-sub-palace linking and unified resolution.

Manages multiple sub-palaces (backend, admin-frontend, tui-frontend, etc.)
and provides unified path resolution across all of them.

Path format: {sub-palace}/{region}/{building}/{room}
Example: backend/memory/memory-add-message
         admin-frontend/api/client-fetch-summary

Usage:
    registry = PalaceRegistry(project_root)
    registry.discover()  # Find all sub-palaces

    # Resolve cross-palace path
    room = registry.resolve_path("backend/memory/memory-add-message")

    # Get specific sub-palace
    backend_palace = registry.get_palace("backend")
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union
import json

from .models import Palace, Region, Building, Room, Entity, Link, LinkType
from .storage import PalaceStorage


# Known sub-palace directories
DEFAULT_SUB_PALACES = [
    "backend",
    "admin-frontend",
    "tui-frontend",
    "mobile-frontend",
]


@dataclass
class PalaceRegistry:
    """
    Registry of all sub-palaces in a project.

    Provides unified path resolution and cross-palace navigation.
    """
    project_root: Path

    # Loaded palaces keyed by sub-palace name
    palaces: Dict[str, Palace] = field(default_factory=dict)

    # Storage instances for each palace
    _storages: Dict[str, PalaceStorage] = field(default_factory=dict, repr=False)

    # Set of discovered sub-palace names
    _discovered: Set[str] = field(default_factory=set, repr=False)

    def __post_init__(self):
        self.project_root = Path(self.project_root)

    def discover(self, sub_palace_names: Optional[List[str]] = None) -> List[str]:
        """
        Discover available sub-palaces in the project.

        Args:
            sub_palace_names: Specific sub-palaces to look for.
                            If None, uses DEFAULT_SUB_PALACES.

        Returns:
            List of discovered sub-palace names.
        """
        names = sub_palace_names or DEFAULT_SUB_PALACES
        self._discovered.clear()

        for name in names:
            palace_dir = self.project_root / name / ".mind-palace"
            if palace_dir.exists() and (palace_dir / "palace.yaml").exists():
                self._discovered.add(name)

        # Also check root .mind-palace for entities
        root_palace = self.project_root / ".mind-palace"
        if root_palace.exists() and (root_palace / "palace.yaml").exists():
            self._discovered.add("root")

        return list(self._discovered)

    def load(self, name: str) -> Optional[Palace]:
        """
        Load a sub-palace by name.

        Args:
            name: Sub-palace name (e.g., "backend", "admin-frontend")

        Returns:
            Loaded Palace instance, or None if not found.
        """
        if name in self.palaces:
            return self.palaces[name]

        if name == "root":
            palace_path = self.project_root
        else:
            palace_path = self.project_root / name

        storage = PalaceStorage(palace_path)
        if not storage.exists():
            return None

        palace = storage.load()
        if palace:
            self.palaces[name] = palace
            self._storages[name] = storage

        return palace

    def load_all(self) -> Dict[str, Palace]:
        """
        Load all discovered sub-palaces.

        Returns:
            Dict mapping sub-palace names to Palace instances.
        """
        if not self._discovered:
            self.discover()

        for name in self._discovered:
            self.load(name)

        return self.palaces

    def get_palace(self, name: str) -> Optional[Palace]:
        """
        Get a palace by name, loading if necessary.

        Args:
            name: Sub-palace name

        Returns:
            Palace instance or None
        """
        if name not in self.palaces:
            self.load(name)
        return self.palaces.get(name)

    def resolve_path(
        self,
        path: str,
        from_palace: Optional[str] = None
    ) -> Optional[Union[Room, Building, Region]]:
        """
        Resolve a path to a palace element, searching across sub-palaces.

        Path formats:
            - "backend/memory/memory-add-message" - Full cross-palace path
            - "memory/memory-add-message" - Search all palaces
            - "memory-add-message" - Search all palaces for room

        Args:
            path: Slug path to resolve
            from_palace: Optional starting palace for relative paths

        Returns:
            Resolved Room, Building, or Region, or None
        """
        parts = [p for p in path.strip("/").split("/") if p]

        if not parts:
            return None

        # Check if first part is a known sub-palace
        if parts[0] in self._discovered or parts[0] in self.palaces:
            palace_name = parts[0]
            palace = self.get_palace(palace_name)
            if palace:
                remaining_path = "/".join(parts[1:])
                if remaining_path:
                    return palace.resolve_path(remaining_path)
                else:
                    # Just the palace name - return first region or None
                    return None

        # Not a sub-palace prefix - search all palaces
        if not self.palaces:
            self.load_all()

        # If from_palace specified, try it first
        search_order = list(self.palaces.keys())
        if from_palace and from_palace in search_order:
            search_order.remove(from_palace)
            search_order.insert(0, from_palace)

        for palace_name in search_order:
            palace = self.palaces[palace_name]
            result = palace.resolve_path(path)
            if result:
                return result

        return None

    def get_full_path(
        self,
        element: Union[Room, Building, Region],
        palace_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Get the full cross-palace path for an element.

        Args:
            element: Palace element (Room, Building, or Region)
            palace_name: Sub-palace containing the element

        Returns:
            Full path like "backend/memory/memory-add-message"
        """
        if palace_name is None:
            # Find which palace contains this element
            for name, palace in self.palaces.items():
                if isinstance(element, Room) and element.slug in palace.rooms:
                    palace_name = name
                    break
                elif isinstance(element, Building) and element.slug in palace.buildings:
                    palace_name = name
                    break
                elif isinstance(element, Region) and element.slug in palace.regions:
                    palace_name = name
                    break

        if palace_name is None:
            return None

        palace = self.palaces.get(palace_name)
        if not palace:
            return None

        local_path = palace.get_full_path(element)
        if local_path:
            return f"{palace_name}/{local_path}"

        return None

    def find_cross_references(
        self,
        room: Room,
        palace_name: str
    ) -> List[Tuple[str, str, Room]]:
        """
        Find rooms in other palaces that might reference this room.

        This is a placeholder for future API endpoint mapping.
        For now, it searches for rooms with matching slugs or names.

        Args:
            room: Source room to find references for
            palace_name: Palace containing the source room

        Returns:
            List of (target_palace, relationship, target_room) tuples
        """
        references = []

        for other_name, palace in self.palaces.items():
            if other_name == palace_name:
                continue

            # Check for exits that reference this room's slug
            for other_room in palace.rooms.values():
                if other_room.exits:
                    for exit in other_room.exits:
                        if exit.destination == room.slug or exit.destination == room.name:
                            references.append((other_name, "exit_to", other_room))

        return references

    def get_all_rooms(self) -> Dict[str, List[Room]]:
        """
        Get all rooms across all palaces.

        Returns:
            Dict mapping palace name to list of rooms
        """
        if not self.palaces:
            self.load_all()

        return {
            name: list(palace.rooms.values())
            for name, palace in self.palaces.items()
        }

    def get_all_entities(self) -> Dict[str, List[Entity]]:
        """
        Get all entities across all palaces.

        Returns:
            Dict mapping palace name to list of entities
        """
        if not self.palaces:
            self.load_all()

        return {
            name: list(palace.entities.values())
            for name, palace in self.palaces.items()
        }

    def stats(self) -> Dict[str, Dict[str, int]]:
        """
        Get statistics for all loaded palaces.

        Returns:
            Dict with counts per palace
        """
        if not self.palaces:
            self.load_all()

        return {
            name: {
                "regions": len(palace.regions),
                "buildings": len(palace.buildings),
                "rooms": len(palace.rooms),
                "entities": len(palace.entities),
            }
            for name, palace in self.palaces.items()
        }

    def load_unified_graph(self) -> Dict:
        """
        Load and merge call graphs from all sub-palaces.

        Returns:
            Unified graph with nodes and edges across all palaces
        """
        unified = {"nodes": [], "edges": []}

        # Each sub-palace may have its own graph
        for name in self._discovered:
            if name == "root":
                graph_path = self.project_root / ".mind-palace" / "codebase-graph.json"
            else:
                graph_path = self.project_root / name / ".mind-palace" / "codebase-graph.json"

            if graph_path.exists():
                with open(graph_path) as f:
                    graph = json.load(f)

                # Prefix node IDs with palace name for uniqueness
                for node in graph.get("nodes", []):
                    node["palace"] = name
                    node["original_id"] = node.get("id")
                    # Only prefix if not already cross-palace
                    if "/" not in str(node.get("id", "")):
                        node["id"] = f"{name}/{node['id']}"
                    unified["nodes"].append(node)

                for edge in graph.get("edges", []):
                    edge["palace"] = name
                    # Prefix source and target
                    if "/" not in str(edge.get("source", "")):
                        edge["source"] = f"{name}/{edge['source']}"
                    if "/" not in str(edge.get("target", "")):
                        edge["target"] = f"{name}/{edge['target']}"
                    unified["edges"].append(edge)

        return unified

    # ========== Cross-Palace Link Aggregation ==========

    def load_all_links(self) -> Dict[str, List[Link]]:
        """
        Load links from all sub-palaces.

        Returns:
            Dict mapping sub-palace name to list of links from that palace.
        """
        if not self._discovered:
            self.discover()

        all_links: Dict[str, List[Link]] = {}

        for name in self._discovered:
            # Ensure storage is loaded
            if name not in self._storages:
                self.load(name)

            storage = self._storages.get(name)
            if storage:
                links = storage.load_links()
                if links:
                    all_links[name] = links

        return all_links

    def find_links_to(
        self,
        target_palace: str,
        target_path: Optional[str] = None
    ) -> List[Tuple[str, Link]]:
        """
        Find all links pointing to a specific palace/path.

        Args:
            target_palace: Target palace name (e.g., "backend")
            target_path: Optional specific path within the palace

        Returns:
            List of (source_palace, Link) tuples
        """
        all_links = self.load_all_links()
        results: List[Tuple[str, Link]] = []

        for palace_name, links in all_links.items():
            for link in links:
                if link.to_palace == target_palace:
                    if target_path is None or link.to_path == target_path:
                        results.append((palace_name, link))
                    elif target_path and link.to_path.startswith(target_path):
                        # Partial path match (e.g., target_path="admin" matches "admin/users")
                        results.append((palace_name, link))

        return results

    def find_links_from(
        self,
        room_slug: str,
        palace_name: Optional[str] = None
    ) -> List[Tuple[str, Link]]:
        """
        Find all links originating from a room.

        Args:
            room_slug: Room slug to search for
            palace_name: Optional palace to search in (searches all if None)

        Returns:
            List of (source_palace, Link) tuples
        """
        all_links = self.load_all_links()
        results: List[Tuple[str, Link]] = []

        palaces_to_search = [palace_name] if palace_name else list(all_links.keys())

        for name in palaces_to_search:
            links = all_links.get(name, [])
            for link in links:
                if link.from_room == room_slug:
                    results.append((name, link))

        return results

    def get_link_summary(self) -> Dict[str, Dict[str, int]]:
        """
        Get summary statistics of cross-palace links.

        Returns:
            Dict with link counts per palace and by type
        """
        all_links = self.load_all_links()

        summary: Dict[str, Dict[str, int]] = {}

        for palace_name, links in all_links.items():
            palace_summary = {
                "total": len(links),
                "by_type": {},
                "by_target": {},
            }

            for link in links:
                # Count by type
                link_type = link.link_type.value
                palace_summary["by_type"][link_type] = palace_summary["by_type"].get(link_type, 0) + 1

                # Count by target palace
                palace_summary["by_target"][link.to_palace] = palace_summary["by_target"].get(link.to_palace, 0) + 1

            summary[palace_name] = palace_summary

        return summary
