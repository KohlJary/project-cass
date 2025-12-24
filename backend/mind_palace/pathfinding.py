"""
Pathfinding algorithms for the Mind Palace call graph.

Provides BFS/DFS traversal, impact radius analysis, and path finding
between functions in the codebase.

Usage:
    from mind_palace.pathfinding import CallGraph, ImpactAnalysis

    graph = CallGraph.load(Path(".mind-palace/codebase-graph.json"))

    # Find all paths between two functions
    paths = graph.find_paths("backend.memory.add_message", "backend.api.send_response")

    # Get impact radius (all transitive callers)
    impact = ImpactAnalysis(graph)
    affected = impact.callers("backend.memory.add_message", max_depth=5)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Callable
from collections import deque
import json


@dataclass
class GraphNode:
    """A node in the call graph."""
    id: str
    name: str
    simple_name: str
    type: str  # function, method, class
    module: str
    file: str
    line: int
    signature: str
    docstring: Optional[str] = None
    calls: List[str] = field(default_factory=list)
    called_by: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> "GraphNode":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            simple_name=data.get("simple_name", ""),
            type=data.get("type", "function"),
            module=data.get("module", ""),
            file=data.get("file", ""),
            line=data.get("line", 0),
            signature=data.get("signature", ""),
            docstring=data.get("docstring"),
            calls=data.get("calls", []),
            called_by=data.get("called_by", []),
        )


@dataclass
class PathResult:
    """Result of a path search."""
    source: str
    target: str
    paths: List[List[str]]  # List of paths, each path is list of node IDs
    shortest_length: int
    total_paths: int

    def __str__(self) -> str:
        if not self.paths:
            return f"No path from {self.source} to {self.target}"
        return f"{self.total_paths} paths found, shortest: {self.shortest_length} hops"


@dataclass
class ImpactResult:
    """Result of impact analysis."""
    source: str
    direction: str  # "callers" or "callees"
    affected: Set[str]
    by_depth: Dict[int, Set[str]]  # Nodes at each depth level
    max_depth_reached: int

    @property
    def total(self) -> int:
        return len(self.affected)

    def summary(self) -> str:
        lines = [f"Impact analysis for {self.source} ({self.direction}):"]
        lines.append(f"  Total affected: {self.total}")
        for depth in sorted(self.by_depth.keys()):
            lines.append(f"  Depth {depth}: {len(self.by_depth[depth])} nodes")
        return "\n".join(lines)


class CallGraph:
    """
    Call graph with pathfinding capabilities.

    Wraps the codebase-graph.json data and provides graph traversal algorithms.
    """

    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.modules: Dict[str, List[str]] = {}  # module -> node IDs
        self.stats: Dict[str, int] = {}
        self.project: str = ""

    @classmethod
    def load(cls, path: Path) -> "CallGraph":
        """Load a call graph from JSON file."""
        graph = cls()

        with open(path) as f:
            data = json.load(f)

        # Load nodes
        for node_id, node_data in data.get("nodes", {}).items():
            graph.nodes[node_id] = GraphNode.from_dict(node_data)

        # Build module index
        for node_id, node in graph.nodes.items():
            if node.module not in graph.modules:
                graph.modules[node.module] = []
            graph.modules[node.module].append(node_id)

        graph.stats = data.get("stats", {})
        graph.project = data.get("project", "")

        return graph

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def find_node(self, name: str) -> Optional[GraphNode]:
        """Find a node by simple name or partial match."""
        # Exact match first
        if name in self.nodes:
            return self.nodes[name]

        # Search by simple_name
        for node in self.nodes.values():
            if node.simple_name == name:
                return node

        # Search by suffix
        for node_id, node in self.nodes.items():
            if node_id.endswith(f".{name}"):
                return node

        return None

    def callers(self, node_id: str) -> List[str]:
        """Get direct callers of a node."""
        node = self.nodes.get(node_id)
        return node.called_by if node else []

    def callees(self, node_id: str) -> List[str]:
        """Get direct callees of a node."""
        node = self.nodes.get(node_id)
        return node.calls if node else []

    def find_paths(
        self,
        source: str,
        target: str,
        max_depth: int = 10,
        max_paths: int = 100,
        direction: str = "forward"  # "forward" (calls) or "backward" (called_by)
    ) -> PathResult:
        """
        Find all paths between two nodes using BFS.

        Args:
            source: Source node ID
            target: Target node ID
            max_depth: Maximum path length
            max_paths: Maximum number of paths to return
            direction: "forward" follows calls, "backward" follows called_by

        Returns:
            PathResult with all found paths
        """
        if source not in self.nodes:
            return PathResult(source, target, [], 0, 0)
        if target not in self.nodes:
            return PathResult(source, target, [], 0, 0)

        paths = []
        queue = deque([(source, [source])])
        visited_at_depth: Dict[str, int] = {source: 0}

        get_neighbors = self.callees if direction == "forward" else self.callers

        while queue and len(paths) < max_paths:
            current, path = queue.popleft()

            if len(path) > max_depth:
                continue

            if current == target and len(path) > 1:
                paths.append(path)
                continue

            for neighbor in get_neighbors(current):
                if neighbor not in self.nodes:
                    continue

                new_depth = len(path)
                # Allow revisiting if we found a shorter path
                if neighbor not in visited_at_depth or visited_at_depth[neighbor] >= new_depth:
                    visited_at_depth[neighbor] = new_depth
                    if neighbor not in path:  # Avoid cycles in current path
                        queue.append((neighbor, path + [neighbor]))

        shortest = min(len(p) for p in paths) if paths else 0
        return PathResult(source, target, paths, shortest, len(paths))

    def bfs(
        self,
        start: str,
        direction: str = "forward",
        max_depth: int = 10,
        filter_fn: Optional[Callable[[GraphNode], bool]] = None
    ) -> Dict[str, int]:
        """
        Breadth-first search from a starting node.

        Args:
            start: Starting node ID
            direction: "forward" follows calls, "backward" follows called_by
            max_depth: Maximum search depth
            filter_fn: Optional filter function for nodes

        Returns:
            Dict mapping node ID to distance from start
        """
        if start not in self.nodes:
            return {}

        get_neighbors = self.callees if direction == "forward" else self.callers

        visited: Dict[str, int] = {start: 0}
        queue = deque([(start, 0)])

        while queue:
            current, depth = queue.popleft()

            if depth >= max_depth:
                continue

            for neighbor in get_neighbors(current):
                if neighbor not in self.nodes:
                    continue
                if neighbor in visited:
                    continue

                node = self.nodes[neighbor]
                if filter_fn and not filter_fn(node):
                    continue

                visited[neighbor] = depth + 1
                queue.append((neighbor, depth + 1))

        return visited

    def dfs(
        self,
        start: str,
        direction: str = "forward",
        max_depth: int = 10,
        filter_fn: Optional[Callable[[GraphNode], bool]] = None
    ) -> List[str]:
        """
        Depth-first search from a starting node.

        Args:
            start: Starting node ID
            direction: "forward" follows calls, "backward" follows called_by
            max_depth: Maximum search depth
            filter_fn: Optional filter function for nodes

        Returns:
            List of visited node IDs in DFS order
        """
        if start not in self.nodes:
            return []

        get_neighbors = self.callees if direction == "forward" else self.callers

        visited: List[str] = []
        visited_set: Set[str] = set()

        def _dfs(node_id: str, depth: int):
            if depth > max_depth:
                return
            if node_id in visited_set:
                return
            if node_id not in self.nodes:
                return

            node = self.nodes[node_id]
            if filter_fn and not filter_fn(node):
                return

            visited_set.add(node_id)
            visited.append(node_id)

            for neighbor in get_neighbors(node_id):
                _dfs(neighbor, depth + 1)

        _dfs(start, 0)
        return visited


class ImpactAnalysis:
    """
    Analyze the impact radius of changes to a function.

    Given a function, find all functions that would be affected by changes to it.
    """

    def __init__(self, graph: CallGraph):
        self.graph = graph

    def callers(
        self,
        node_id: str,
        max_depth: int = 10,
        include_self: bool = False
    ) -> ImpactResult:
        """
        Find all transitive callers of a function.

        These are the functions that would be affected if node_id changes its behavior.

        Args:
            node_id: The function to analyze
            max_depth: Maximum call chain depth
            include_self: Whether to include the source node

        Returns:
            ImpactResult with all affected callers
        """
        distances = self.graph.bfs(node_id, direction="backward", max_depth=max_depth)

        if not include_self and node_id in distances:
            del distances[node_id]

        # Group by depth
        by_depth: Dict[int, Set[str]] = {}
        for node, depth in distances.items():
            if depth not in by_depth:
                by_depth[depth] = set()
            by_depth[depth].add(node)

        max_reached = max(distances.values()) if distances else 0

        return ImpactResult(
            source=node_id,
            direction="callers",
            affected=set(distances.keys()),
            by_depth=by_depth,
            max_depth_reached=max_reached,
        )

    def callees(
        self,
        node_id: str,
        max_depth: int = 10,
        include_self: bool = False
    ) -> ImpactResult:
        """
        Find all transitive callees of a function.

        These are the functions that node_id depends on.

        Args:
            node_id: The function to analyze
            max_depth: Maximum call chain depth
            include_self: Whether to include the source node

        Returns:
            ImpactResult with all dependencies
        """
        distances = self.graph.bfs(node_id, direction="forward", max_depth=max_depth)

        if not include_self and node_id in distances:
            del distances[node_id]

        # Group by depth
        by_depth: Dict[int, Set[str]] = {}
        for node, depth in distances.items():
            if depth not in by_depth:
                by_depth[depth] = set()
            by_depth[depth].add(node)

        max_reached = max(distances.values()) if distances else 0

        return ImpactResult(
            source=node_id,
            direction="callees",
            affected=set(distances.keys()),
            by_depth=by_depth,
            max_depth_reached=max_reached,
        )

    def blast_radius(
        self,
        node_id: str,
        max_depth: int = 5
    ) -> Tuple[ImpactResult, ImpactResult]:
        """
        Get the full blast radius of a function - both callers and callees.

        Returns:
            Tuple of (callers_result, callees_result)
        """
        return (
            self.callers(node_id, max_depth),
            self.callees(node_id, max_depth),
        )

    def affected_files(self, impact: ImpactResult) -> Set[str]:
        """Get the set of files affected by an impact result."""
        files = set()
        for node_id in impact.affected:
            node = self.graph.get_node(node_id)
            if node:
                files.add(node.file)
        return files

    def affected_modules(self, impact: ImpactResult) -> Set[str]:
        """Get the set of modules affected by an impact result."""
        modules = set()
        for node_id in impact.affected:
            node = self.graph.get_node(node_id)
            if node:
                modules.add(node.module)
        return modules


def load_graph(project_root: Path) -> CallGraph:
    """
    Load the call graph for a project.

    Looks in .mind-palace/codebase-graph.json by default.
    """
    graph_path = project_root / ".mind-palace" / "codebase-graph.json"
    if not graph_path.exists():
        raise FileNotFoundError(f"No call graph found at {graph_path}")
    return CallGraph.load(graph_path)
