"""
Graph query utilities for self-model analysis.
Extracted from handlers/self_model.py for reusability and testability.
"""
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass


@dataclass
class NodeSearchResult:
    """Result of a node search."""
    node: Any  # GraphNode
    found_by: str  # "id" or "content"


@dataclass
class BeliefTraceResult:
    """Result of tracing a belief's sources."""
    target_node: Any
    sources: List[Any]
    evidence: List[Any]
    evolution: List[Any]


@dataclass
class ContradictionAnalysis:
    """Result of contradiction analysis."""
    explicit_contradictions: List[Tuple[Any, Any, Dict]]
    unsupported_growth_edges: List[Any]
    stats: Dict[str, Any]


class GraphQueryBuilder:
    """
    Builds and executes common graph queries.

    Extracted from handler functions to enable:
    - Independent testing
    - Reuse in other contexts
    - Cleaner handler code
    """

    # Priority order for node type matching
    PRIORITY_NODE_TYPES = [
        "observation", "mark", "opinion", "growth_edge", "milestone"
    ]

    def __init__(self, graph: Any):
        """
        Args:
            graph: SelfModelGraph instance
        """
        self._graph = graph

    def find_node_by_query(
        self,
        query: str,
        node_type_enum: Any
    ) -> Optional[NodeSearchResult]:
        """
        Find a node by ID or content search.

        Args:
            query: Node ID (8 chars) or text to search
            node_type_enum: NodeType enum for priority matching

        Returns:
            NodeSearchResult or None if not found
        """
        target_node = None
        found_by = "content"

        # Check if it's a node ID (8 chars hex)
        if len(query) == 8:
            target_node = self._graph.get_node(query)
            if target_node:
                found_by = "id"

        # If not found by ID, search by content
        if not target_node:
            matching = self._graph.find_nodes(content_contains=query)
            if matching:
                # Prefer specific node types over conversations
                for type_name in self.PRIORITY_NODE_TYPES:
                    try:
                        priority_type = node_type_enum(type_name)
                        for node in matching:
                            if node.node_type == priority_type:
                                target_node = node
                                break
                        if target_node:
                            break
                    except ValueError:
                        continue

                if not target_node:
                    target_node = matching[0]

        if target_node:
            return NodeSearchResult(node=target_node, found_by=found_by)
        return None

    def trace_belief_sources(
        self,
        node_id: str,
        max_depth: int = 3
    ) -> BeliefTraceResult:
        """
        Trace the sources, evidence, and evolution of a belief.

        Args:
            node_id: ID of the node to trace
            max_depth: Maximum depth for source chain

        Returns:
            BeliefTraceResult with sources, evidence, evolution
        """
        target_node = self._graph.get_node(node_id)
        if not target_node:
            return BeliefTraceResult(
                target_node=None,
                sources=[],
                evidence=[],
                evolution=[]
            )

        sources = self._graph.get_sources(node_id, max_depth=max_depth)
        evidence = self._graph.get_evidence(node_id)
        evolution = self._graph.get_evolution(node_id)

        return BeliefTraceResult(
            target_node=target_node,
            sources=sources,
            evidence=evidence,
            evolution=evolution
        )

    def analyze_contradictions(
        self,
        include_resolved: bool = False,
        check_growth_edges: bool = True,
        node_type_enum: Any = None,
        edge_type_enum: Any = None
    ) -> ContradictionAnalysis:
        """
        Analyze contradictions and unsupported growth edges.

        Args:
            include_resolved: Include resolved contradictions
            check_growth_edges: Check for unsupported growth edges
            node_type_enum: NodeType enum
            edge_type_enum: EdgeType enum

        Returns:
            ContradictionAnalysis with findings
        """
        # Find explicit contradictions
        contradictions = self._graph.find_contradictions(resolved=include_resolved)

        # Check growth edges for substance
        unsupported = []
        if check_growth_edges and node_type_enum and edge_type_enum:
            growth_edge_type = node_type_enum.GROWTH_EDGE
            emerged_from_type = edge_type_enum.EMERGED_FROM

            growth_edges = self._graph.find_nodes(node_type=growth_edge_type)
            for edge_node in growth_edges:
                evidence = self._graph.get_evidence(edge_node.id)
                outgoing = self._graph.get_edges(
                    edge_node.id,
                    direction="in",
                    edge_type=emerged_from_type
                )
                if not evidence and not outgoing:
                    unsupported.append(edge_node)

        stats = self._graph.get_stats()

        return ContradictionAnalysis(
            explicit_contradictions=contradictions,
            unsupported_growth_edges=unsupported,
            stats=stats
        )


def format_belief_trace(result: BeliefTraceResult) -> str:
    """Format belief trace result as markdown."""
    if not result.target_node:
        return "Node not found."

    node = result.target_node
    lines = [f"## Tracing: {node.content[:60]}...\n"]
    lines.append(f"**Node type:** {node.node_type.value.replace('_', ' ').title()}")
    lines.append(f"**Created:** {node.created_at.strftime('%Y-%m-%d')}\n")

    # Sources
    if result.sources:
        lines.append("### Source Chain")
        lines.append("*What this emerged from:*")
        for source in result.sources:
            type_label = source.node_type.value.replace("_", " ").title()
            lines.append(f"- [{type_label}] {source.content[:80]}...")
    else:
        lines.append("*No source chain found - this may be a root observation.*")

    # Evidence
    if result.evidence:
        lines.append("\n### Supporting Evidence")
        for ev in result.evidence:
            type_label = ev.node_type.value.replace("_", " ").title()
            lines.append(f"- [{type_label}] {ev.content[:80]}...")

    # Evolution
    if len(result.evolution) > 1:
        lines.append("\n### Evolution")
        lines.append("*How this understanding has changed:*")
        for i, ev_node in enumerate(result.evolution):
            marker = "→ " if i < len(result.evolution) - 1 else "✓ (current)"
            lines.append(f"{marker} {ev_node.content[:60]}...")

    return "\n".join(lines)


def format_contradiction_analysis(result: ContradictionAnalysis) -> str:
    """Format contradiction analysis as markdown."""
    lines = ["## Self-Model Tensions\n"]

    # Explicit contradictions
    if result.explicit_contradictions:
        lines.append("### Explicit Contradictions")
        lines.append("*Positions I hold that may be in tension:*\n")
        for node1, node2, edge_data in result.explicit_contradictions:
            lines.append(f"**{node1.content[:60]}...**")
            lines.append(f"  *vs*")
            lines.append(f"**{node2.content[:60]}...**")
            if edge_data.get("tension_note"):
                lines.append(f"  *Note: {edge_data['tension_note']}*")
            lines.append("")
    else:
        lines.append("*No explicit contradictions found in the graph.*\n")

    # Unsupported growth edges
    if result.unsupported_growth_edges:
        lines.append("### Growth Edges Without Evidence")
        lines.append("*Named edges that may be aspirational rather than grounded:*\n")
        for edge_node in result.unsupported_growth_edges[:5]:
            lines.append(f"- {edge_node.content[:80]}...")
            lines.append(f"  *No observations or marks support this edge yet.*")

    # Summary
    lines.append("\n### Summary")
    lines.append(f"- Active contradictions: {len(result.explicit_contradictions)}")
    lines.append(f"- Total nodes: {result.stats.get('total_nodes', 0)}")
    lines.append(f"- Connected components: {result.stats.get('connected_components', 0)}")

    return "\n".join(lines)
