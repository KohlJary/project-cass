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

    # =========================================================================
    # Graph Export & Visualization
    # =========================================================================

    def build_call_graph(self, directory: Optional[Path] = None) -> Dict[str, Any]:
        """
        Build a complete call graph from source code analysis.

        This creates a data-first representation of all code relationships,
        independent of the palace YAML files.

        Args:
            directory: Directory to analyze (defaults to project root)

        Returns:
            Dict with 'nodes', 'edges', 'modules', and 'stats'
        """
        if directory is None:
            directory = self.project_root
        elif not directory.is_absolute():
            directory = self.project_root / directory

        nodes = {}  # name -> node data
        edges = []  # list of {source, target, type}
        modules = {}  # module_name -> list of node names

        # Collect all supported files
        supported_extensions = self.language_registry.supported_extensions()
        source_files = []
        for ext in supported_extensions:
            source_files.extend(directory.rglob(f"*{ext}"))

        # Filter out common non-source directories
        skip_dirs = {"node_modules", "venv", "__pycache__", ".git", "dist", "build", ".venv", "env"}
        source_files = [
            f for f in source_files
            if not any(skip in f.parts for skip in skip_dirs)
        ]

        # First pass: collect all nodes
        for source_file in source_files:
            try:
                elements, language = self.analyze_file(source_file)
                rel_path = source_file.relative_to(self.project_root)
                module_name = str(rel_path.with_suffix("")).replace("/", ".")

                if module_name not in modules:
                    modules[module_name] = []

                for element in elements:
                    node_id = f"{module_name}.{element.name}"
                    nodes[node_id] = {
                        "id": node_id,
                        "name": element.name,
                        "simple_name": element.simple_name,
                        "type": element.element_type,
                        "module": module_name,
                        "file": str(rel_path),
                        "line": element.line,
                        "signature": element.signature,
                        "docstring": (element.docstring or "")[:200],
                        "calls": element.calls,
                        "called_by": [],  # populated in second pass
                        "complexity": len(element.calls),  # simple proxy
                    }
                    modules[module_name].append(node_id)

            except Exception as e:
                logger.warning(f"Error analyzing {source_file}: {e}")
                continue

        # Second pass: build edges and populate called_by
        for node_id, node in nodes.items():
            for call in node["calls"]:
                # Try to resolve the call to a known node
                target_id = self._resolve_call(call, node["module"], nodes)
                if target_id:
                    edges.append({
                        "source": node_id,
                        "target": target_id,
                        "type": "calls",
                    })
                    # Add to called_by
                    if target_id in nodes:
                        nodes[target_id]["called_by"].append(node_id)

        # Calculate additional stats
        stats = {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "total_modules": len(modules),
            "total_files": len(source_files),
            "nodes_by_type": {},
            "most_called": [],
            "most_complex": [],
            "entry_points": [],  # nodes with no callers
            "leaf_nodes": [],    # nodes that call nothing
        }

        # Count by type
        for node in nodes.values():
            t = node["type"]
            stats["nodes_by_type"][t] = stats["nodes_by_type"].get(t, 0) + 1

        # Find most called (by called_by count)
        by_callers = sorted(nodes.values(), key=lambda n: len(n["called_by"]), reverse=True)
        stats["most_called"] = [
            {"id": n["id"], "callers": len(n["called_by"])}
            for n in by_callers[:10]
        ]

        # Find most complex (by calls count)
        by_calls = sorted(nodes.values(), key=lambda n: len(n["calls"]), reverse=True)
        stats["most_complex"] = [
            {"id": n["id"], "calls": len(n["calls"])}
            for n in by_calls[:10]
        ]

        # Entry points (no callers)
        stats["entry_points"] = [
            n["id"] for n in nodes.values()
            if len(n["called_by"]) == 0 and n["type"] in ("function", "class")
        ][:20]

        # Leaf nodes (call nothing)
        stats["leaf_nodes"] = [
            n["id"] for n in nodes.values()
            if len(n["calls"]) == 0
        ][:20]

        return {
            "nodes": nodes,
            "edges": edges,
            "modules": modules,
            "stats": stats,
            "project": self.palace.name if self.palace else str(self.project_root.name),
            "generated_at": datetime.now().isoformat(),
        }

    def _resolve_call(self, call: str, current_module: str, nodes: Dict) -> Optional[str]:
        """Try to resolve a call name to a known node ID."""
        # Direct match
        if call in nodes:
            return call

        # Try with current module prefix
        full_name = f"{current_module}.{call}"
        if full_name in nodes:
            return full_name

        # Try to find by simple name
        for node_id, node in nodes.items():
            if node["simple_name"] == call:
                return node_id

        return None

    def export_graph_json(self, directory: Optional[Path] = None, output_path: Optional[Path] = None) -> str:
        """
        Export the call graph as JSON.

        Args:
            directory: Directory to analyze
            output_path: Where to save (if None, returns string)

        Returns:
            JSON string
        """
        import json

        graph = self.build_call_graph(directory)
        json_str = json.dumps(graph, indent=2)

        if output_path:
            output_path = Path(output_path)
            output_path.write_text(json_str)
            logger.info(f"Exported graph to {output_path}")

        return json_str

    def visualize_dot(self, directory: Optional[Path] = None, output_path: Optional[Path] = None) -> str:
        """
        Generate Graphviz DOT format visualization.

        Args:
            directory: Directory to analyze
            output_path: Where to save .dot file

        Returns:
            DOT format string
        """
        graph = self.build_call_graph(directory)

        # Color scheme for different types
        colors = {
            "class": "#9333EA",      # Purple
            "function": "#06B6D4",   # Cyan
            "method": "#14B8A6",     # Teal
            "module": "#F59E0B",     # Amber
        }

        lines = [
            "digraph CodebaseGraph {",
            "  rankdir=LR;",
            "  bgcolor=\"#0A0A0F\";",
            "  node [style=filled, fontcolor=white, fontname=\"Helvetica\"];",
            "  edge [color=\"#4B5563\"];",
            "",
            "  // Modules as subgraphs",
        ]

        # Group nodes by module
        for module_name, node_ids in graph["modules"].items():
            safe_module = module_name.replace(".", "_").replace("-", "_")
            lines.append(f"  subgraph cluster_{safe_module} {{")
            lines.append(f"    label=\"{module_name}\";")
            lines.append(f"    style=rounded;")
            lines.append(f"    color=\"#374151\";")
            lines.append(f"    fontcolor=\"#9CA3AF\";")

            for node_id in node_ids:
                node = graph["nodes"].get(node_id)
                if node:
                    safe_id = node_id.replace(".", "_").replace("-", "_")
                    color = colors.get(node["type"], "#6B7280")
                    label = node["simple_name"]
                    # Size based on importance (callers)
                    callers = len(node["called_by"])
                    fontsize = min(8 + callers * 2, 20)
                    lines.append(f"    {safe_id} [label=\"{label}\", fillcolor=\"{color}\", fontsize={fontsize}];")

            lines.append("  }")
            lines.append("")

        # Add edges
        lines.append("  // Edges")
        for edge in graph["edges"]:
            safe_source = edge["source"].replace(".", "_").replace("-", "_")
            safe_target = edge["target"].replace(".", "_").replace("-", "_")
            lines.append(f"  {safe_source} -> {safe_target};")

        lines.append("}")

        dot_str = "\n".join(lines)

        if output_path:
            output_path = Path(output_path)
            output_path.write_text(dot_str)
            logger.info(f"Exported DOT to {output_path}")

        return dot_str

    def visualize_html(
        self,
        directory: Optional[Path] = None,
        output_path: Optional[Path] = None,
        entity_coverage: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Generate an interactive HTML visualization using D3.js force-directed graph.

        Args:
            directory: Directory to analyze
            output_path: Where to save .html file
            entity_coverage: Dict mapping module prefixes to entity names (for coverage overlay)

        Returns:
            HTML string
        """
        import json

        graph = self.build_call_graph(directory)

        # Default entity coverage based on common keeper names
        if entity_coverage is None:
            entity_coverage = {
                "conversations": "ConversationKeeper",
                "memory": "MemoryKeeper",
                "self_model": "SelfModelKeeper",
                "goals": "GoalsKeeper",
                "goal_planner": "GoalsKeeper",
                "scheduler": "SchedulingKeeper",
                "background_tasks": "SchedulingKeeper",
                "outreach": "OutreachKeeper",
                "research": "ResearchKeeper",
                "research_session": "SessionRunnerKeeper",
                "solo_reflection": "SessionRunnerKeeper",
                "journal": "JournalKeeper",
                "users": "UserKeeper",
                "projects": "ProjectKeeper",
                "wiki": "WikiKeeper",
                "dreaming": "DreamKeeper",
                "wonderland": "WonderlandKeeper",
                "janet": "JanetKeeper",
                "agent_client": "LLMKeeper",
                "claude_client": "LLMKeeper",
                "openai_client": "LLMKeeper",
                "handlers": "ToolRouterKeeper",
                "admin_api": "AdminAPIKeeper",
                "routes.admin": "AdminAPIKeeper",
                "narrative": "NarrativeKeeper",
                "state_bus": "StateBusKeeper",
                "database": "PersistenceKeeper",
                "migrations": "PersistenceKeeper",
            }

        # Convert to D3 format
        d3_nodes = []
        d3_links = []
        node_index = {}
        modules_set = set()

        for i, (node_id, node) in enumerate(graph["nodes"].items()):
            node_index[node_id] = i
            module = node["module"]
            modules_set.add(module)

            # Check entity coverage
            entity = None
            for prefix, ent_name in entity_coverage.items():
                if module.startswith(prefix) or prefix in module:
                    entity = ent_name
                    break

            d3_nodes.append({
                "id": node_id,
                "name": node["simple_name"],
                "type": node["type"],
                "module": module,
                "file": node["file"],
                "line": node["line"],
                "callers": len(node["called_by"]),
                "calls": len(node["calls"]),
                "entity": entity,
            })

        for edge in graph["edges"]:
            if edge["source"] in node_index and edge["target"] in node_index:
                d3_links.append({
                    "source": node_index[edge["source"]],
                    "target": node_index[edge["target"]],
                })

        # Build module list with coverage info
        modules_list = []
        for module in sorted(modules_set):
            entity = None
            for prefix, ent_name in entity_coverage.items():
                if module.startswith(prefix) or prefix in module:
                    entity = ent_name
                    break
            modules_list.append({"name": module, "entity": entity})

        d3_data = json.dumps({"nodes": d3_nodes, "links": d3_links})
        modules_json = json.dumps(modules_list)
        stats_json = json.dumps(graph["stats"], indent=2)
        coverage_count = len([m for m in modules_list if m["entity"]])
        coverage_pct = int(100 * coverage_count / len(modules_list)) if modules_list else 0

        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{graph["project"]} - Codebase Visualization</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html, body {{
            width: 100%;
            height: 100%;
            background: #0A0A0F;
            color: #E5E7EB;
            font-family: 'Segoe UI', system-ui, sans-serif;
            overflow: hidden;
        }}
        #container {{
            display: flex;
            width: 100vw;
            height: 100vh;
        }}
        #graph {{
            flex: 1;
            position: relative;
            width: 100%;
            height: 100%;
        }}
        #sidebar {{
            width: 320px;
            min-width: 320px;
            background: #111827;
            padding: 20px;
            overflow-y: auto;
            border-left: 1px solid #374151;
        }}
        svg {{
            display: block;
            width: 100%;
            height: 100%;
        }}
        h1 {{
            font-size: 1.5rem;
            margin-bottom: 1rem;
            color: #A855F7;
        }}
        h2 {{
            font-size: 1rem;
            margin: 1.5rem 0 0.5rem 0;
            color: #9CA3AF;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .stat {{
            display: flex;
            justify-content: space-between;
            padding: 0.5rem 0;
            border-bottom: 1px solid #1F2937;
        }}
        .stat-label {{ color: #9CA3AF; }}
        .stat-value {{ color: #06B6D4; font-weight: 600; }}
        .legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 1rem;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.85rem;
        }}
        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
        #tooltip {{
            position: absolute;
            background: #1F2937;
            border: 1px solid #374151;
            border-radius: 8px;
            padding: 12px;
            font-size: 0.85rem;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.2s;
            max-width: 300px;
            z-index: 1000;
        }}
        #tooltip.visible {{ opacity: 1; }}
        #tooltip h3 {{
            color: #A855F7;
            margin-bottom: 8px;
        }}
        #tooltip p {{
            color: #9CA3AF;
            margin: 4px 0;
        }}
        #tooltip .highlight {{ color: #06B6D4; }}
        .links line {{
            stroke: #374151;
            stroke-opacity: 0.6;
        }}
        .nodes circle {{
            stroke: #1F2937;
            stroke-width: 2px;
            cursor: pointer;
        }}
        .nodes circle:hover {{
            stroke: #A855F7;
            stroke-width: 3px;
        }}
        #search {{
            width: 100%;
            padding: 8px 12px;
            background: #1F2937;
            border: 1px solid #374151;
            border-radius: 6px;
            color: #E5E7EB;
            font-size: 0.9rem;
            margin-bottom: 1rem;
        }}
        #search:focus {{
            outline: none;
            border-color: #A855F7;
        }}
        .coverage-bar {{
            width: 100%;
            height: 8px;
            background: #1F2937;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 0.5rem;
        }}
        .coverage-fill {{
            height: 100%;
            background: linear-gradient(90deg, #22C55E, #14B8A6);
            border-radius: 4px;
        }}
        .control-group {{
            padding: 0.5rem 0;
        }}
        .control-group label {{
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            font-size: 0.9rem;
        }}
        .control-group input[type="checkbox"] {{
            width: 16px;
            height: 16px;
            accent-color: #A855F7;
        }}
        .module-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 4px 0;
            font-size: 0.8rem;
            cursor: pointer;
        }}
        .module-item:hover {{
            color: #A855F7;
        }}
        .module-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
        }}
        .module-name {{
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .hull {{
            fill-opacity: 0.1;
            stroke-width: 1;
            stroke-opacity: 0.3;
        }}
        .hull-label {{
            font-size: 10px;
            fill: #9CA3AF;
            pointer-events: none;
        }}
    </style>
</head>
<body>
    <div id="container">
        <div id="graph">
            <div id="tooltip"></div>
        </div>
        <div id="sidebar">
            <h1>🏛️ {graph["project"]}</h1>
            <input type="text" id="search" placeholder="Search nodes...">

            <h2>Statistics</h2>
            <div class="stat">
                <span class="stat-label">Total Nodes</span>
                <span class="stat-value">{graph["stats"]["total_nodes"]}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Total Edges</span>
                <span class="stat-value">{graph["stats"]["total_edges"]}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Modules</span>
                <span class="stat-value">{graph["stats"]["total_modules"]}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Files</span>
                <span class="stat-value">{graph["stats"]["total_files"]}</span>
            </div>

            <h2>Entity Coverage</h2>
            <div class="stat">
                <span class="stat-label">Modules with Keepers</span>
                <span class="stat-value">{coverage_count}/{len(modules_list)} ({coverage_pct}%)</span>
            </div>
            <div class="coverage-bar">
                <div class="coverage-fill" style="width: {coverage_pct}%;"></div>
            </div>
            <div class="legend" style="margin-top: 0.5rem;">
                <div class="legend-item">
                    <div class="legend-dot" style="background: #22C55E;"></div>
                    <span>Has Keeper</span>
                </div>
                <div class="legend-item">
                    <div class="legend-dot" style="background: #EF4444; opacity: 0.5;"></div>
                    <span>Unmapped</span>
                </div>
            </div>

            <h2>Node Types</h2>
            <div class="legend">
                <div class="legend-item">
                    <div class="legend-dot" style="background: #9333EA;"></div>
                    <span>Class</span>
                </div>
                <div class="legend-item">
                    <div class="legend-dot" style="background: #06B6D4;"></div>
                    <span>Function</span>
                </div>
                <div class="legend-item">
                    <div class="legend-dot" style="background: #14B8A6;"></div>
                    <span>Method</span>
                </div>
            </div>

            <h2>Controls</h2>
            <div class="control-group">
                <label><input type="checkbox" id="show-hulls" checked> Show module groups</label>
            </div>
            <div class="control-group">
                <label><input type="checkbox" id="show-coverage" checked> Show coverage overlay</label>
            </div>
            <div class="control-group">
                <label><input type="checkbox" id="show-labels"> Show module labels</label>
            </div>

            <h2>Most Called</h2>
            <div id="most-called"></div>

            <h2>Most Complex</h2>
            <div id="most-complex"></div>

            <h2>Modules</h2>
            <div id="module-list" style="max-height: 200px; overflow-y: auto;"></div>
        </div>
    </div>

    <script>
        const data = {d3_data};
        const modules = {modules_json};
        const stats = {stats_json};

        // Generate consistent color from string
        function stringToColor(str) {{
            let hash = 0;
            for (let i = 0; i < str.length; i++) {{
                hash = str.charCodeAt(i) + ((hash << 5) - hash);
            }}
            const hue = Math.abs(hash % 360);
            return `hsl(${{hue}}, 70%, 50%)`;
        }}

        // Populate sidebar lists
        const mostCalled = document.getElementById('most-called');
        stats.most_called.slice(0, 5).forEach(item => {{
            const div = document.createElement('div');
            div.className = 'stat';
            div.innerHTML = `<span class="stat-label">${{item.id.split('.').pop()}}</span><span class="stat-value">${{item.callers}}</span>`;
            mostCalled.appendChild(div);
        }});

        const mostComplex = document.getElementById('most-complex');
        stats.most_complex.slice(0, 5).forEach(item => {{
            const div = document.createElement('div');
            div.className = 'stat';
            div.innerHTML = `<span class="stat-label">${{item.id.split('.').pop()}}</span><span class="stat-value">${{item.calls}}</span>`;
            mostComplex.appendChild(div);
        }});

        // Populate module list
        const moduleList = document.getElementById('module-list');
        modules.forEach(mod => {{
            const div = document.createElement('div');
            div.className = 'module-item';
            const color = mod.entity ? '#22C55E' : stringToColor(mod.name);
            const shortName = mod.name.split('.').pop();
            div.innerHTML = `<div class="module-dot" style="background: ${{color}};"></div><span class="module-name" title="${{mod.name}}">${{shortName}}</span>`;
            div.onclick = () => {{
                document.getElementById('search').value = mod.name;
                document.getElementById('search').dispatchEvent(new Event('input'));
            }};
            moduleList.appendChild(div);
        }});

        // D3 Visualization
        const container = document.getElementById('graph');
        let width = container.clientWidth;
        let height = container.clientHeight;

        const color = d3.scaleOrdinal()
            .domain(['class', 'function', 'method'])
            .range(['#9333EA', '#06B6D4', '#14B8A6']);

        const svg = d3.select('#graph')
            .append('svg')
            .attr('width', '100%')
            .attr('height', '100%')
            .attr('viewBox', `0 0 ${{width}} ${{height}}`)
            .attr('preserveAspectRatio', 'xMidYMid meet');

        // Handle window resize
        window.addEventListener('resize', () => {{
            width = container.clientWidth;
            height = container.clientHeight;
            svg.attr('viewBox', `0 0 ${{width}} ${{height}}`);
            simulation.force('center', d3.forceCenter(width / 2, height / 2));
            simulation.alpha(0.3).restart();
        }});

        // Add zoom behavior
        const g = svg.append('g');
        svg.call(d3.zoom()
            .extent([[0, 0], [width, height]])
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => g.attr('transform', event.transform)));

        // Create layers
        const hullLayer = g.append('g').attr('class', 'hulls');
        const labelLayer = g.append('g').attr('class', 'labels');

        // Group nodes by module for hulls
        const moduleNodes = {{}};
        data.nodes.forEach((n, i) => {{
            const mod = n.module.split('.')[0]; // Top-level module
            if (!moduleNodes[mod]) moduleNodes[mod] = [];
            moduleNodes[mod].push(i);
        }});

        // Get module info for coverage
        const moduleInfo = {{}};
        modules.forEach(m => {{
            const topMod = m.name.split('.')[0];
            if (!moduleInfo[topMod]) {{
                moduleInfo[topMod] = {{ entity: m.entity, name: topMod }};
            }} else if (m.entity && !moduleInfo[topMod].entity) {{
                moduleInfo[topMod].entity = m.entity;
            }}
        }});

        // Convex hull function
        function getHullPoints(nodeIndices) {{
            const points = nodeIndices.map(i => [data.nodes[i].x || 0, data.nodes[i].y || 0]);
            if (points.length < 3) return null;
            return d3.polygonHull(points);
        }}

        // Draw hulls
        function updateHulls() {{
            const showHulls = document.getElementById('show-hulls').checked;
            const showCoverage = document.getElementById('show-coverage').checked;
            const showLabels = document.getElementById('show-labels').checked;

            hullLayer.selectAll('path').remove();
            labelLayer.selectAll('text').remove();

            if (!showHulls) return;

            Object.entries(moduleNodes).forEach(([mod, indices]) => {{
                if (indices.length < 3) return;

                const hull = getHullPoints(indices);
                if (!hull) return;

                const info = moduleInfo[mod] || {{}};
                const hasEntity = showCoverage && info.entity;
                const baseColor = hasEntity ? '#22C55E' : stringToColor(mod);

                // Expand hull slightly for padding
                const centroid = d3.polygonCentroid(hull);
                const expandedHull = hull.map(p => [
                    centroid[0] + (p[0] - centroid[0]) * 1.2,
                    centroid[1] + (p[1] - centroid[1]) * 1.2
                ]);

                hullLayer.append('path')
                    .attr('class', 'hull')
                    .attr('d', 'M' + expandedHull.join('L') + 'Z')
                    .attr('fill', baseColor)
                    .attr('stroke', baseColor)
                    .attr('fill-opacity', hasEntity ? 0.15 : 0.08)
                    .attr('stroke-opacity', hasEntity ? 0.5 : 0.2);

                if (showLabels) {{
                    labelLayer.append('text')
                        .attr('class', 'hull-label')
                        .attr('x', centroid[0])
                        .attr('y', centroid[1])
                        .attr('text-anchor', 'middle')
                        .attr('fill', baseColor)
                        .text(mod + (info.entity ? ' ✓' : ''));
                }}
            }});
        }}

        // Toggle controls
        document.getElementById('show-hulls').addEventListener('change', updateHulls);
        document.getElementById('show-coverage').addEventListener('change', updateHulls);
        document.getElementById('show-labels').addEventListener('change', updateHulls);

        const simulation = d3.forceSimulation(data.nodes)
            .force('link', d3.forceLink(data.links).id((d, i) => i).distance(80))
            .force('charge', d3.forceManyBody().strength(-200))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(d => Math.sqrt(d.callers + 1) * 5 + 10));

        const link = g.append('g')
            .attr('class', 'links')
            .selectAll('line')
            .data(data.links)
            .enter().append('line');

        const node = g.append('g')
            .attr('class', 'nodes')
            .selectAll('circle')
            .data(data.nodes)
            .enter().append('circle')
            .attr('r', d => Math.sqrt(d.callers + 1) * 3 + 5)
            .attr('fill', d => color(d.type))
            .call(d3.drag()
                .on('start', dragstarted)
                .on('drag', dragged)
                .on('end', dragended));

        // Tooltip
        const tooltip = document.getElementById('tooltip');

        node.on('mouseover', (event, d) => {{
            const entityInfo = d.entity ? `<p>Keeper: <span class="highlight" style="color: #22C55E;">${{d.entity}}</span></p>` : `<p style="color: #EF4444; opacity: 0.7;">No entity coverage</p>`;
            tooltip.innerHTML = `
                <h3>${{d.name}}</h3>
                <p>Type: <span class="highlight">${{d.type}}</span></p>
                <p>Module: <span class="highlight">${{d.module}}</span></p>
                <p>File: <span class="highlight">${{d.file}}:${{d.line}}</span></p>
                <p>Called by: <span class="highlight">${{d.callers}} functions</span></p>
                <p>Calls: <span class="highlight">${{d.calls}} functions</span></p>
                ${{entityInfo}}
            `;
            tooltip.style.left = (event.pageX + 10) + 'px';
            tooltip.style.top = (event.pageY - 10) + 'px';
            tooltip.classList.add('visible');
        }});

        node.on('mouseout', () => {{
            tooltip.classList.remove('visible');
        }});

        // Search
        document.getElementById('search').addEventListener('input', (e) => {{
            const query = e.target.value.toLowerCase();
            node.attr('opacity', d =>
                query === '' || d.name.toLowerCase().includes(query) || d.module.toLowerCase().includes(query) ? 1 : 0.1
            );
            link.attr('opacity', d => {{
                const source = data.nodes[d.source.index || d.source];
                const target = data.nodes[d.target.index || d.target];
                if (query === '') return 0.6;
                return (source.name.toLowerCase().includes(query) || target.name.toLowerCase().includes(query)) ? 0.6 : 0.05;
            }});
        }});

        simulation.on('tick', () => {{
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            node
                .attr('cx', d => d.x)
                .attr('cy', d => d.y);

            // Update hulls on each tick
            updateHulls();
        }});

        function dragstarted(event) {{
            if (!event.active) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }}

        function dragged(event) {{
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }}

        function dragended(event) {{
            if (!event.active) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }}
    </script>
</body>
</html>'''

        if output_path:
            output_path = Path(output_path)
            output_path.write_text(html)
            logger.info(f"Exported HTML visualization to {output_path}")

        return html
