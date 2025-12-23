"""
Mind Palace Cartographer - Tools for mapping codebases into palaces.

The Cartographer helps Daedalus construct and maintain Mind Palaces by:
1. Analyzing code structure to suggest regions/buildings/rooms
2. Extracting function signatures for anchors
3. Detecting drift between code and palace
4. Proposing updates after code changes

This is the "autonomous cartography" engine from the spec.
"""

import ast
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
from .storage import PalaceStorage
from .languages import CodeElement, get_language_registry, LanguageSupport

logger = logging.getLogger(__name__)


@dataclass
class DriftReport:
    """Report on differences between palace and code."""
    room_name: str
    anchor_file: str
    issues: List[str]
    severity: str  # "info", "warning", "error"
    suggested_fix: Optional[str] = None


class Cartographer:
    """
    Maps codebases into Mind Palaces.

    Works with Daedalus to construct spatial representations of code,
    detect drift, and maintain synchronization.
    """

    def __init__(self, palace: Palace, storage: PalaceStorage):
        self.palace = palace
        self.storage = storage
        self.project_root = storage.project_root
        self.language_registry = get_language_registry()

    # =========================================================================
    # Code Analysis
    # =========================================================================

    def analyze_file(self, file_path: Path) -> Tuple[List[CodeElement], Optional[LanguageSupport]]:
        """
        Analyze a source file using the appropriate language support.

        Args:
            file_path: Path to the source file

        Returns:
            Tuple of (elements, language_support) - language_support is None if unsupported
        """
        language = self.language_registry.get_by_extension(file_path)
        if language is None:
            logger.debug(f"No language support for {file_path.suffix}")
            return [], None

        elements = language.analyze_file(file_path, self.project_root)
        return elements, language

    def analyze_python_file(self, file_path: Path) -> List[CodeElement]:
        """
        Analyze a Python file and extract code elements.

        Args:
            file_path: Path to the Python file

        Returns:
            List of discovered code elements

        Note: This is a convenience wrapper. For multi-language support,
        use analyze_file() which also returns the language support instance.
        """
        elements, _ = self.analyze_file(file_path)
        return elements

    # =========================================================================
    # Palace Construction
    # =========================================================================

    def suggest_region(self, directory: Path) -> Region:
        """
        Suggest a region based on a directory structure.

        Args:
            directory: Directory to analyze

        Returns:
            Suggested Region
        """
        name = directory.name
        description = f"Code in {directory.relative_to(self.project_root)}"

        # Look for README or __init__ docstring for better description
        readme = directory / "README.md"
        if readme.exists():
            with open(readme) as f:
                first_line = f.readline().strip()
                if first_line.startswith("#"):
                    description = first_line.lstrip("# ")

        init_file = directory / "__init__.py"
        if init_file.exists():
            try:
                with open(init_file) as f:
                    tree = ast.parse(f.read())
                docstring = ast.get_docstring(tree)
                if docstring:
                    description = docstring.split("\n")[0]
            except:
                pass

        # Find adjacent regions (sibling directories)
        adjacent = []
        if directory.parent.exists():
            for sibling in directory.parent.iterdir():
                if sibling.is_dir() and sibling != directory:
                    if not sibling.name.startswith("."):
                        adjacent.append(sibling.name)

        # Entry points are Python files in this directory
        entry_points = [
            str(f.relative_to(self.project_root))
            for f in directory.glob("*.py")
            if not f.name.startswith("_")
        ][:5]  # Limit to 5

        return Region(
            name=name,
            description=description,
            adjacent=adjacent[:5],
            entry_points=entry_points,
        )

    def suggest_building(self, module_path: Path, region_name: str) -> Building:
        """
        Suggest a building based on a Python module.

        Args:
            module_path: Path to the module file or directory
            region_name: Name of the containing region

        Returns:
            Suggested Building
        """
        if module_path.is_dir():
            name = module_path.name
            anchor_file = str((module_path / "__init__.py").relative_to(self.project_root))
        else:
            name = module_path.stem
            anchor_file = str(module_path.relative_to(self.project_root))

        # Analyze for purpose
        purpose = f"Module: {name}"
        elements = []

        if module_path.is_file():
            elements = self.analyze_python_file(module_path)
        elif (module_path / "__init__.py").exists():
            elements = self.analyze_python_file(module_path / "__init__.py")

        # Use docstring if available
        for e in elements:
            if e.element_type == "class" or (e.element_type == "function" and e.name == name):
                if e.docstring:
                    purpose = e.docstring.split("\n")[0]
                    break

        # Count floors based on nesting depth
        floors = 1
        if module_path.is_dir():
            max_depth = 0
            for f in module_path.rglob("*.py"):
                depth = len(f.relative_to(module_path).parts)
                max_depth = max(max_depth, depth)
            floors = max(1, max_depth)

        # Find main entrance (main class or function)
        main_entrance = None
        side_doors = []
        internal_only = []

        for e in elements:
            if e.name.startswith("_"):
                internal_only.append(e.name)
            elif e.element_type == "class" or (e.element_type == "function" and not e.name.startswith("_")):
                if main_entrance is None:
                    main_entrance = e.name
                else:
                    side_doors.append(e.name)

        return Building(
            name=name,
            region=region_name,
            purpose=purpose,
            floors=floors,
            main_entrance=main_entrance,
            side_doors=side_doors[:5],
            internal_only=internal_only[:5],
            anchor=Anchor(
                pattern=f"# {name}" if module_path.is_dir() else f"def |class ",
                file=anchor_file,
            ),
        )

    def suggest_room(
        self,
        element: CodeElement,
        building_name: str,
        language: Optional[LanguageSupport] = None,
    ) -> Room:
        """
        Suggest a room based on a code element.

        Args:
            element: The code element to map
            building_name: Name of the containing building
            language: Language support for anchor generation (auto-detected if None)

        Returns:
            Suggested Room
        """
        # Determine floor based on nesting (methods are floor 2+)
        floor = 1
        if element.element_type == "method":
            floor = 2

        # Build description from docstring
        description = element.docstring or f"{element.element_type.title()}: {element.name}"
        if len(description) > 200:
            description = description[:200] + "..."

        # Build contents from parameters
        contents = []
        for param_name, param_type in element.parameters:
            if param_name != "self":
                contents.append(Content(
                    name=param_name,
                    type=param_type or "Any",
                    purpose=f"Parameter: {param_name}",
                ))

        # Build exits from calls
        exits = []
        directions = ["north", "east", "south", "west", "up", "down"]
        for i, call in enumerate(element.calls[:6]):
            direction = directions[i % len(directions)]
            access = AccessLevel.INTERNAL if call.startswith("_") else AccessLevel.PUBLIC
            exits.append(Exit(
                direction=direction,
                destination=call,
                access=access,
            ))

        # Generate hazards from docstring hints
        hazards = []
        if element.docstring:
            doc_lower = element.docstring.lower()
            if "warning" in doc_lower or "caution" in doc_lower:
                hazards.append(Hazard(
                    type=HazardType.FRAGILE,
                    description="See docstring for warnings",
                    severity=2,
                ))
            if "deprecated" in doc_lower:
                hazards.append(Hazard(
                    type=HazardType.DEPRECATED,
                    description="This function is deprecated",
                    severity=2,
                ))
            if "todo" in doc_lower or "fixme" in doc_lower:
                hazards.append(Hazard(
                    type=HazardType.FRAGILE,
                    description="Has TODO/FIXME items",
                    severity=1,
                ))

        # Create signature hash for drift detection
        sig_hash = hashlib.md5(element.signature.encode()).hexdigest()[:8]

        # Generate anchor pattern using language support
        if language is None:
            # Try to auto-detect from file extension
            file_path = Path(element.file)
            language = self.language_registry.get_by_extension(file_path)

        if language is not None:
            anchor_pattern = language.generate_anchor_pattern(element)
            pattern = anchor_pattern.pattern
            is_regex = anchor_pattern.is_regex
        else:
            # Fallback for unknown languages
            pattern = f"def {element.simple_name}(" if element.element_type != "class" else f"class {element.simple_name}"
            is_regex = False

        return Room(
            name=element.name,
            building=building_name,
            floor=floor,
            description=description,
            anchor=Anchor(
                pattern=pattern,
                file=element.file,
                line=element.line,
                signature_hash=sig_hash,
                is_regex=is_regex,
            ),
            contents=contents,
            exits=exits,
            hazards=hazards,
            history=[HistoryEntry(
                date=datetime.now().strftime("%Y-%m-%d"),
                note="Initial mapping by Cartographer",
                author="Daedalus",
            )],
            last_modified=datetime.now().isoformat(),
            modified_by="Cartographer",
        )

    def map_directory(
        self,
        directory: Path,
        region_name: Optional[str] = None,
        recursive: bool = True,
    ) -> Tuple[int, int, int]:
        """
        Map a directory into the palace.

        Args:
            directory: Directory to map
            region_name: Region name (defaults to directory name)
            recursive: Whether to recursively map subdirectories

        Returns:
            Tuple of (regions_added, buildings_added, rooms_added)
        """
        directory = Path(directory)
        if not directory.is_absolute():
            directory = self.project_root / directory

        regions_added = 0
        buildings_added = 0
        rooms_added = 0

        # Create or get region
        if region_name is None:
            region_name = directory.name

        if region_name not in self.palace.regions:
            region = self.suggest_region(directory)
            region.name = region_name
            self.storage.add_region(self.palace, region)
            regions_added += 1

        # Map source files as buildings (supports multiple languages)
        supported_extensions = self.language_registry.supported_extensions()
        for ext in supported_extensions:
            pattern = f"*{ext}"
            for source_file in directory.glob(pattern):
                # Skip private files (except __init__.py for Python)
                if source_file.name.startswith("_") and source_file.name != "__init__.py":
                    continue

                building_name = source_file.stem
                if building_name == "__init__":
                    building_name = directory.name

                if building_name not in self.palace.buildings:
                    building = self.suggest_building(source_file, region_name)
                    self.storage.add_building(self.palace, building)
                    buildings_added += 1

                # Map functions/classes as rooms using language-aware analysis
                elements, language = self.analyze_file(source_file)
                for element in elements:
                    if element.name.startswith("_") and not element.name.startswith("__"):
                        continue  # Skip private, keep dunder

                    room_name = element.name
                    if room_name not in self.palace.rooms:
                        room = self.suggest_room(element, building_name, language)
                        self.storage.add_room(self.palace, room)
                        rooms_added += 1

        # Recursively map subdirectories
        if recursive:
            for subdir in directory.iterdir():
                if subdir.is_dir() and not subdir.name.startswith((".", "_")):
                    # Skip common non-source directories
                    if subdir.name in ("node_modules", "venv", "__pycache__", ".git", "dist", "build"):
                        continue
                    sub_region = f"{region_name}/{subdir.name}"
                    r, b, rm = self.map_directory(subdir, sub_region, recursive=True)
                    regions_added += r
                    buildings_added += b
                    rooms_added += rm

        return regions_added, buildings_added, rooms_added

    # =========================================================================
    # Drift Detection
    # =========================================================================

    def check_drift(self) -> List[DriftReport]:
        """
        Check for drift between palace and current code state.

        Returns:
            List of drift reports
        """
        reports = []

        for room_name, room in self.palace.rooms.items():
            if not room.anchor:
                continue

            anchor = room.anchor
            file_path = self.project_root / anchor.file

            if not file_path.exists():
                reports.append(DriftReport(
                    room_name=room_name,
                    anchor_file=anchor.file,
                    issues=["Anchor file no longer exists"],
                    severity="error",
                    suggested_fix=f"Remove room or update anchor to new location",
                ))
                continue

            # Check if pattern still exists
            try:
                with open(file_path) as f:
                    content = f.read()

                # Use regex or literal matching based on anchor type
                pattern_found = False
                if getattr(anchor, 'is_regex', False):
                    pattern_found = bool(re.search(anchor.pattern, content, re.MULTILINE))
                else:
                    pattern_found = anchor.pattern in content

                if not pattern_found:
                    reports.append(DriftReport(
                        room_name=room_name,
                        anchor_file=anchor.file,
                        issues=[f"Pattern '{anchor.pattern}' not found"],
                        severity="error",
                        suggested_fix="Function/class may have been renamed or removed",
                    ))
                    continue

                # Check signature hash if available
                if anchor.signature_hash:
                    elements, _ = self.analyze_file(file_path)
                    for element in elements:
                        if element.name == room_name or element.name.endswith(f".{room_name}"):
                            new_hash = hashlib.md5(element.signature.encode()).hexdigest()[:8]
                            if new_hash != anchor.signature_hash:
                                reports.append(DriftReport(
                                    room_name=room_name,
                                    anchor_file=anchor.file,
                                    issues=["Signature has changed"],
                                    severity="warning",
                                    suggested_fix=f"Update room contents/exits to match new signature",
                                ))
                            break

            except Exception as e:
                reports.append(DriftReport(
                    room_name=room_name,
                    anchor_file=anchor.file,
                    issues=[f"Error checking: {e}"],
                    severity="warning",
                ))

        return reports

    def sync_room(self, room_name: str) -> Optional[Room]:
        """
        Re-sync a room with its anchor in code.

        Args:
            room_name: Name of the room to sync

        Returns:
            Updated Room, or None if sync failed
        """
        room = self.palace.get_room(room_name)
        if not room or not room.anchor:
            return None

        file_path = self.project_root / room.anchor.file
        if not file_path.exists():
            return None

        elements = self.analyze_python_file(file_path)
        for element in elements:
            if element.name == room_name or element.name.endswith(f".{room_name}"):
                # Update room from current code
                updated = self.suggest_room(element, room.building)
                updated.history = room.history + [HistoryEntry(
                    date=datetime.now().strftime("%Y-%m-%d"),
                    note="Synced with code changes",
                    author="Cartographer",
                )]
                self.storage.add_room(self.palace, updated)
                self.palace.rooms[room_name] = updated
                return updated

        return None
