"""
Causal Slice Extraction for Mind Palace.

Extracts the minimal set of code paths causally related to a function or change.
This is the "program slice" computed via the call graph - everything that could
affect or be affected by a given function.

A causal slice contains:
- Backward slice: All transitive callers (what triggers this code)
- Forward slice: All transitive callees (what this code depends on)
- The focal point (the function being analyzed)

Usage:
    from mind_palace.causal_slice import CausalSlicer, SliceBundle

    slicer = CausalSlicer(project_root)

    # Extract slice for a function
    bundle = slicer.extract("backend.memory.add_message", depth=3)

    # Get slice as context for an Icarus worker
    context = bundle.to_context()

    # Get affected rooms for work package
    rooms = bundle.affected_rooms(palace)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import json

from .pathfinding import CallGraph, ImpactAnalysis, GraphNode, load_graph


@dataclass
class SliceNode:
    """A node in a causal slice with additional context."""
    id: str
    name: str
    type: str  # function, method, class
    file: str
    line: int
    signature: str
    docstring: Optional[str]
    depth: int  # Distance from focal point (0 = focal point)
    direction: str  # "caller", "callee", or "focal"

    # Relationships within the slice
    calls_in_slice: List[str] = field(default_factory=list)
    called_by_in_slice: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "file": self.file,
            "line": self.line,
            "signature": self.signature,
            "docstring": self.docstring,
            "depth": self.depth,
            "direction": self.direction,
            "calls_in_slice": self.calls_in_slice,
            "called_by_in_slice": self.called_by_in_slice,
        }


@dataclass
class SliceBundle:
    """
    A complete causal slice bundle ready for use as worker context.

    Contains all functions in the slice, organized by direction and depth,
    plus metadata about the affected files and modules.
    """
    focal_point: str
    backward_depth: int
    forward_depth: int

    # Nodes organized by direction
    callers: Dict[str, SliceNode] = field(default_factory=dict)
    callees: Dict[str, SliceNode] = field(default_factory=dict)
    focal: Optional[SliceNode] = None

    # Aggregate information
    affected_files: Set[str] = field(default_factory=set)
    affected_modules: Set[str] = field(default_factory=set)

    @property
    def total_nodes(self) -> int:
        return len(self.callers) + len(self.callees) + (1 if self.focal else 0)

    @property
    def all_nodes(self) -> Dict[str, SliceNode]:
        """All nodes in the slice."""
        nodes = {}
        nodes.update(self.callers)
        nodes.update(self.callees)
        if self.focal:
            nodes[self.focal.id] = self.focal
        return nodes

    def nodes_at_depth(self, depth: int, direction: str = "both") -> List[SliceNode]:
        """Get all nodes at a specific depth from the focal point."""
        result = []
        if direction in ("both", "caller"):
            result.extend(n for n in self.callers.values() if n.depth == depth)
        if direction in ("both", "callee"):
            result.extend(n for n in self.callees.values() if n.depth == depth)
        return result

    def affected_rooms(self, palace) -> List[str]:
        """
        Get the room slugs affected by this slice.

        Maps file paths to palace rooms.
        """
        rooms = []
        for file_path in self.affected_files:
            # Search for rooms that anchor to this file
            for room in palace.rooms.values():
                if room.anchor and room.anchor.file == file_path:
                    rooms.append(room.slug)
        return list(set(rooms))

    def to_context(
        self,
        include_source: bool = False,
        include_patterns: bool = False,
        project_root: Optional[Path] = None,
        source_lines: int = 30,
        pattern_files: Optional[List[str]] = None,
    ) -> str:
        """
        Generate context string for an Icarus worker.

        Args:
            include_source: Whether to include actual source code for slice nodes
            include_patterns: Whether to find and include similar patterns
            project_root: Project root for reading source files
            source_lines: Max lines to include per function
            pattern_files: Extra files to search for implementation patterns

        Returns:
            Formatted context string
        """
        lines = []
        lines.append(f"# Causal Slice: {self.focal_point}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append(f"- Focal point: `{self.focal_point}`")
        lines.append(f"- Callers (backward slice): {len(self.callers)} functions, depth {self.backward_depth}")
        lines.append(f"- Callees (forward slice): {len(self.callees)} functions, depth {self.forward_depth}")
        lines.append(f"- Affected files: {len(self.affected_files)}")
        lines.append("")

        # Focal point with source
        if self.focal:
            lines.append("## Focal Point")
            lines.append(f"**{self.focal.name}** ({self.focal.type})")
            lines.append(f"- File: `{self.focal.file}:{self.focal.line}`")
            lines.append(f"- Signature: `{self.focal.signature}`")
            if self.focal.docstring:
                lines.append(f"- Doc: {self.focal.docstring[:200]}...")

            if include_source and project_root:
                source = self._read_function_source(project_root, self.focal, source_lines)
                if source:
                    lines.append("")
                    lines.append("```python")
                    lines.append(source)
                    lines.append("```")
            lines.append("")

        # Callers with optional source (depth 1 only to keep it focused)
        if self.callers:
            lines.append("## Callers (what triggers this code)")
            for depth in range(1, self.backward_depth + 1):
                depth_nodes = self.nodes_at_depth(depth, "caller")
                if depth_nodes:
                    lines.append(f"\n### Depth {depth}")
                    for node in sorted(depth_nodes, key=lambda n: n.name):
                        lines.append(f"**`{node.name}`** ({node.file}:{node.line})")
                        if node.signature:
                            lines.append(f"- Signature: `{node.signature}`")
                        if include_source and project_root and depth == 1:
                            source = self._read_function_source(project_root, node, source_lines)
                            if source:
                                lines.append("```python")
                                lines.append(source)
                                lines.append("```")
                        lines.append("")
            lines.append("")

        # Callees with optional source
        if self.callees:
            lines.append("## Callees (what this code depends on)")
            for depth in range(1, self.forward_depth + 1):
                depth_nodes = self.nodes_at_depth(depth, "callee")
                if depth_nodes:
                    lines.append(f"\n### Depth {depth}")
                    for node in sorted(depth_nodes, key=lambda n: n.name):
                        lines.append(f"**`{node.name}`** ({node.file}:{node.line})")
                        if node.signature:
                            lines.append(f"- Signature: `{node.signature}`")
                        if include_source and project_root and depth == 1:
                            source = self._read_function_source(project_root, node, source_lines)
                            if source:
                                lines.append("```python")
                                lines.append(source)
                                lines.append("```")
                        lines.append("")
            lines.append("")

        # Pattern examples - find similar constructs to guide implementation
        if include_patterns and project_root:
            patterns = self._find_patterns(project_root, extra_files=pattern_files)
            if patterns:
                lines.append("## Pattern Examples")
                lines.append("Similar constructs in the codebase that may guide implementation:")
                lines.append("")
                for pattern in patterns:
                    lines.append(f"### {pattern['name']}")
                    lines.append(f"From `{pattern['file']}:{pattern['line']}`")
                    lines.append("")
                    lines.append("```python")
                    lines.append(pattern['source'])
                    lines.append("```")
                    lines.append("")

        # File list
        lines.append("## Affected Files")
        for f in sorted(self.affected_files):
            lines.append(f"- `{f}`")

        return "\n".join(lines)

    def _find_patterns(
        self,
        project_root: Path,
        max_patterns: int = 5,
        extra_files: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Find similar patterns in affected files that could guide implementation.

        Looks for:
        - Sibling methods/functions in the same class/module
        - Similar naming patterns (load_*, save_*, etc.)
        - Dataclass definitions if focal is a dataclass

        Args:
            project_root: Project root path
            max_patterns: Maximum patterns to return
            extra_files: Additional files to search for patterns
        """
        patterns = []

        # Combine affected files with extra files (like work package target files)
        files_to_search = set(self.affected_files)
        if extra_files:
            files_to_search.update(extra_files)

        for file_path in files_to_search:
            full_path = project_root / file_path
            if not full_path.exists():
                continue

            try:
                content = full_path.read_text()
                file_lines = content.splitlines()

                # Find dataclass patterns
                if "@dataclass" in content:
                    for i, line in enumerate(file_lines):
                        if "@dataclass" in line and i + 1 < len(file_lines):
                            # Get the dataclass definition (next 20 lines or until next class)
                            start = i
                            end = min(i + 25, len(file_lines))
                            for j in range(i + 2, len(file_lines)):
                                if file_lines[j].startswith("class ") or file_lines[j].startswith("@dataclass"):
                                    end = j
                                    break

                            source = "\n".join(file_lines[start:end])
                            class_name = file_lines[i + 1].split("class ")[-1].split("(")[0].split(":")[0]

                            patterns.append({
                                "name": f"Dataclass: {class_name}",
                                "file": file_path,
                                "line": i + 1,
                                "source": source.strip(),
                            })

                            if len(patterns) >= max_patterns:
                                return patterns

                # Find method patterns (load_*, save_*, get_*, etc.)
                focal_names = self.focal_point.split(",") if self.focal else []
                for focal_name in focal_names:
                    # Extract method prefix pattern
                    parts = focal_name.split(".")
                    if parts:
                        method_name = parts[-1]
                        prefix = method_name.split("_")[0] + "_" if "_" in method_name else None

                        if prefix and prefix in ["load_", "save_", "get_", "set_", "create_", "delete_", "update_"]:
                            for i, line in enumerate(file_lines):
                                if f"def {prefix}" in line and line.strip().startswith("def "):
                                    # Extract the method
                                    start = i
                                    indent = len(line) - len(line.lstrip())
                                    end = start + 1
                                    for j in range(i + 1, min(i + 40, len(file_lines))):
                                        curr_line = file_lines[j]
                                        if curr_line.strip() and not curr_line.startswith(" " * (indent + 1)) and not curr_line.strip().startswith("#"):
                                            if curr_line.strip().startswith("def ") or curr_line.strip().startswith("class "):
                                                end = j
                                                break
                                    else:
                                        end = min(i + 30, len(file_lines))

                                    source = "\n".join(file_lines[start:end])
                                    func_name = line.split("def ")[-1].split("(")[0]

                                    # Don't include if it's the focal point itself
                                    if func_name not in focal_name:
                                        patterns.append({
                                            "name": f"Pattern: {func_name}",
                                            "file": file_path,
                                            "line": i + 1,
                                            "source": source.strip(),
                                        })

                                        if len(patterns) >= max_patterns:
                                            return patterns

            except Exception:
                continue

        return patterns

    def _read_function_source(self, project_root: Path, node: SliceNode, context_lines: int = 20) -> Optional[str]:
        """Read source code for a function (limited lines)."""
        try:
            file_path = project_root / node.file
            if not file_path.exists():
                return None

            with open(file_path) as f:
                lines = f.readlines()

            start = max(0, node.line - 1)
            end = min(len(lines), start + context_lines)
            return "".join(lines[start:end]).strip()
        except Exception:
            return None

    def to_dict(self) -> Dict:
        return {
            "focal_point": self.focal_point,
            "backward_depth": self.backward_depth,
            "forward_depth": self.forward_depth,
            "callers": {k: v.to_dict() for k, v in self.callers.items()},
            "callees": {k: v.to_dict() for k, v in self.callees.items()},
            "focal": self.focal.to_dict() if self.focal else None,
            "affected_files": list(self.affected_files),
            "affected_modules": list(self.affected_modules),
            "total_nodes": self.total_nodes,
        }

    def save(self, path: Path):
        """Save bundle to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


class CausalSlicer:
    """
    Extracts causal slices from the call graph.

    A causal slice is the transitive closure of callers and callees
    for a given function - everything that could affect or be affected
    by changes to that function.
    """

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.graph: Optional[CallGraph] = None
        self.impact: Optional[ImpactAnalysis] = None

    def _ensure_loaded(self):
        """Load call graph if not already loaded."""
        if self.graph is None:
            self.graph = load_graph(self.project_root)
            self.impact = ImpactAnalysis(self.graph)

    def extract(
        self,
        focal_point: str,
        backward_depth: int = 3,
        forward_depth: int = 2,
    ) -> SliceBundle:
        """
        Extract a causal slice centered on a function.

        Args:
            focal_point: Function ID or name to analyze
            backward_depth: How far to trace callers
            forward_depth: How far to trace callees

        Returns:
            SliceBundle containing the complete slice
        """
        self._ensure_loaded()

        # Resolve focal point if needed
        focal_node = self.graph.get_node(focal_point)
        if not focal_node:
            focal_node = self.graph.find_node(focal_point)

        if not focal_node:
            # Return empty bundle if not found
            return SliceBundle(
                focal_point=focal_point,
                backward_depth=backward_depth,
                forward_depth=forward_depth,
            )

        bundle = SliceBundle(
            focal_point=focal_node.id,
            backward_depth=backward_depth,
            forward_depth=forward_depth,
        )

        # Create focal slice node
        bundle.focal = self._node_to_slice_node(focal_node, 0, "focal")
        bundle.affected_files.add(focal_node.file)
        bundle.affected_modules.add(focal_node.module)

        # Extract callers (backward slice)
        caller_result = self.impact.callers(focal_node.id, max_depth=backward_depth)
        for node_id in caller_result.affected:
            node = self.graph.get_node(node_id)
            if node:
                depth = caller_result.by_depth.get(node_id, 0)
                # Find actual depth
                for d, nodes in caller_result.by_depth.items():
                    if node_id in nodes:
                        depth = d
                        break

                slice_node = self._node_to_slice_node(node, depth, "caller")
                bundle.callers[node_id] = slice_node
                bundle.affected_files.add(node.file)
                bundle.affected_modules.add(node.module)

        # Extract callees (forward slice)
        callee_result = self.impact.callees(focal_node.id, max_depth=forward_depth)
        for node_id in callee_result.affected:
            node = self.graph.get_node(node_id)
            if node:
                depth = 0
                for d, nodes in callee_result.by_depth.items():
                    if node_id in nodes:
                        depth = d
                        break

                slice_node = self._node_to_slice_node(node, depth, "callee")
                bundle.callees[node_id] = slice_node
                bundle.affected_files.add(node.file)
                bundle.affected_modules.add(node.module)

        # Build in-slice relationships
        self._build_slice_relationships(bundle)

        return bundle

    def extract_multi(
        self,
        focal_points: List[str],
        backward_depth: int = 3,
        forward_depth: int = 2,
    ) -> SliceBundle:
        """
        Extract a unified slice for multiple focal points.

        Useful when a change affects multiple related functions.
        """
        self._ensure_loaded()

        # Extract individual slices
        bundles = [
            self.extract(fp, backward_depth, forward_depth)
            for fp in focal_points
        ]

        # Merge into unified bundle
        unified = SliceBundle(
            focal_point=",".join(focal_points),
            backward_depth=backward_depth,
            forward_depth=forward_depth,
        )

        for bundle in bundles:
            if bundle.focal:
                # Add as caller with depth 0 (focal points become pseudo-callers)
                unified.callers[bundle.focal.id] = bundle.focal
            unified.callers.update(bundle.callers)
            unified.callees.update(bundle.callees)
            unified.affected_files.update(bundle.affected_files)
            unified.affected_modules.update(bundle.affected_modules)

        self._build_slice_relationships(unified)
        return unified

    def _node_to_slice_node(
        self,
        node: GraphNode,
        depth: int,
        direction: str
    ) -> SliceNode:
        """Convert a GraphNode to a SliceNode."""
        return SliceNode(
            id=node.id,
            name=node.name,
            type=node.type,
            file=node.file,
            line=node.line,
            signature=node.signature,
            docstring=node.docstring,
            depth=depth,
            direction=direction,
        )

    def _build_slice_relationships(self, bundle: SliceBundle):
        """Build in-slice call relationships."""
        all_ids = set(bundle.all_nodes.keys())

        for node_id, slice_node in bundle.all_nodes.items():
            graph_node = self.graph.get_node(node_id)
            if not graph_node:
                continue

            # Filter calls/called_by to only in-slice nodes
            slice_node.calls_in_slice = [
                c for c in graph_node.calls if c in all_ids
            ]
            slice_node.called_by_in_slice = [
                c for c in graph_node.called_by if c in all_ids
            ]


def extract_slice_for_work_package(
    project_root: Path,
    focal_points: List[str],
    backward_depth: int = 3,
    forward_depth: int = 2,
) -> Tuple[SliceBundle, str]:
    """
    Convenience function to extract a slice and generate worker context.

    Args:
        project_root: Project root path
        focal_points: Functions to analyze
        backward_depth: Caller trace depth
        forward_depth: Callee trace depth

    Returns:
        Tuple of (SliceBundle, context_string)
    """
    slicer = CausalSlicer(project_root)

    if len(focal_points) == 1:
        bundle = slicer.extract(focal_points[0], backward_depth, forward_depth)
    else:
        bundle = slicer.extract_multi(focal_points, backward_depth, forward_depth)

    context = bundle.to_context(include_source=False, project_root=project_root)
    return bundle, context
