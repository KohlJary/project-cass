"""
Self-Model Graph - Unified self-knowledge structure for Cass.

This module provides a graph-based representation of Cass's self-model,
unifying observations, opinions, growth edges, journals, marks, and other
self-knowledge artifacts into a queryable structure.

The graph enables:
- Causal tracing: "What led to this observation?"
- Contradiction detection: "Where do I hold conflicting positions?"
- Evolution tracking: "How has my understanding changed?"
- Cross-system synthesis: "What do I know about X across all sources?"
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum

import networkx as nx

# Import extracted components
from graph_sync import SyncEngine
from graph_patterns import PatternAnalyzer

# ChromaDB for semantic similarity (optional - gracefully degrade if unavailable)
try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class NodeType(str, Enum):
    """Types of nodes in the self-model graph."""
    OBSERVATION = "observation"  # Self-observation about Cass
    USER_OBSERVATION = "user_observation"  # Cass's observation about a user
    OPINION = "opinion"
    GROWTH_EDGE = "growth_edge"
    MILESTONE = "milestone"
    JOURNAL = "journal"
    SOLO_REFLECTION = "solo_reflection"
    MARK = "mark"
    CONVERSATION = "conversation"
    CONVERSATION_MOMENT = "conversation_moment"
    USER = "user"
    COGNITIVE_SNAPSHOT = "cognitive_snapshot"
    INTENTION = "intention"  # Declared intention: "I want to X when Y"
    INTENTION_OUTCOME = "intention_outcome"  # Success/failure record for an intention
    SITUATIONAL_INFERENCE = "situational_inference"  # Inferred context about a conversation/situation
    PRESENCE_LOG = "presence_log"  # How Cass showed up in a conversation - engagement vs. distancing
    STAKE = "stake"  # Something Cass authentically cares about
    PREFERENCE_TEST = "preference_test"  # Record of stated vs behavioral consistency
    NARRATION_CONTEXT = "narration_context"  # Track narration patterns in specific contexts
    ARCHITECTURAL_REQUEST = "architectural_request"  # Request for system changes
    DAILY_RHYTHM = "daily_rhythm"  # Daily rhythm summary with phase completions and insights


class EdgeType(str, Enum):
    """Types of edges in the self-model graph."""
    # Temporal
    SUPERSEDES = "supersedes"
    PRECEDED_BY = "preceded_by"
    FOLLOWED_BY = "followed_by"

    # Causal/Source
    EMERGED_FROM = "emerged_from"
    EVIDENCED_BY = "evidenced_by"

    # Semantic
    RELATES_TO = "relates_to"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    REFINES = "refines"

    # Relational
    ABOUT = "about"
    PARTICIPATED_IN = "participated_in"
    CONTAINS = "contains"

    # Development
    DEVELOPS = "develops"
    TRIGGERED = "triggered"
    TRACKS = "tracks"  # Outcome tracks an intention

    # Relational Inference
    INFERRED_FROM = "inferred_from"  # Inference drawn from a conversation/moment
    INFORMED_BY = "informed_by"  # Inference informed by prior observation


@dataclass
class GraphNode:
    """Base class for all graph nodes."""
    id: str
    node_type: NodeType
    created_at: datetime
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "node_type": self.node_type.value,
            "created_at": self.created_at.isoformat(),
            "content": self.content,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'GraphNode':
        return cls(
            id=data["id"],
            node_type=NodeType(data["node_type"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            content=data.get("content", ""),
            metadata=data.get("metadata", {})
        )


@dataclass
class GraphEdge:
    """Represents an edge between two nodes."""
    source_id: str
    target_id: str
    edge_type: EdgeType
    created_at: datetime
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "created_at": self.created_at.isoformat(),
            "properties": self.properties
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'GraphEdge':
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            edge_type=EdgeType(data["edge_type"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            properties=data.get("properties", {})
        )


class SelfModelGraph:
    """
    Unified self-model graph with query interface.

    Uses NetworkX for in-memory graph operations with JSON persistence.
    ChromaDB provides semantic similarity for automatic edge suggestion.
    """

    # Node types that should be connected via semantic similarity
    CONNECTABLE_TYPES = {
        NodeType.OBSERVATION, NodeType.USER_OBSERVATION, NodeType.OPINION,
        NodeType.GROWTH_EDGE, NodeType.MILESTONE, NodeType.MARK,
        NodeType.SOLO_REFLECTION, NodeType.INTENTION, NodeType.SITUATIONAL_INFERENCE,
        NodeType.PRESENCE_LOG, NodeType.STAKE, NodeType.PREFERENCE_TEST,
        NodeType.NARRATION_CONTEXT, NodeType.ARCHITECTURAL_REQUEST, NodeType.DAILY_RHYTHM
    }

    # Minimum similarity score to create an edge (lower = more connections)
    # ChromaDB returns L2 distance, so lower is more similar
    SIMILARITY_THRESHOLD = 1.2  # Fairly permissive to build connections

    def __init__(self, storage_path: str = "./data/cass/self_model_graph.json",
                 chroma_persist_dir: Optional[str] = None):
        self.storage_path = Path(storage_path)
        self.graph = nx.DiGraph()
        self._nodes: Dict[str, GraphNode] = {}

        # Initialize ChromaDB for semantic similarity
        self._chroma_client = None
        self._node_collection = None
        self._embedding_fn = None

        if CHROMADB_AVAILABLE:
            try:
                # Use same persist dir as main memory system if not specified
                if chroma_persist_dir is None:
                    chroma_persist_dir = str(self.storage_path.parent.parent / "chroma")

                self._chroma_client = chromadb.PersistentClient(
                    path=chroma_persist_dir,
                    settings=Settings(anonymized_telemetry=False)
                )
                self._embedding_fn = embedding_functions.DefaultEmbeddingFunction()
                self._node_collection = self._chroma_client.get_or_create_collection(
                    name="self_model_graph_nodes",
                    embedding_function=self._embedding_fn,
                    metadata={"description": "Self-model graph node embeddings for similarity search"}
                )
            except Exception as e:
                print(f"Warning: ChromaDB initialization failed for graph: {e}")
                self._chroma_client = None

        self._load()

        # Initialize extracted components
        self._sync_engine = SyncEngine(self, NodeType, EdgeType)
        self._pattern_analyzer = PatternAnalyzer(
            get_situational_inferences_fn=self.get_situational_inferences,
            get_presence_logs_fn=self.get_presence_logs
        )

    # ==================== Node Operations ====================

    def add_node(
        self,
        node_type: NodeType,
        content: str = "",
        node_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        **metadata
    ) -> str:
        """
        Add a node to the graph.

        Args:
            node_type: Type of the node
            content: Primary content/text of the node
            node_id: Optional custom ID (generated if not provided)
            created_at: Creation timestamp (defaults to now)
            **metadata: Additional properties

        Returns:
            The node ID
        """
        if node_id is None:
            node_id = str(uuid.uuid4())[:8]

        if created_at is None:
            created_at = datetime.now()

        node = GraphNode(
            id=node_id,
            node_type=node_type,
            created_at=created_at,
            content=content,
            metadata=metadata
        )

        self._nodes[node_id] = node
        self.graph.add_node(node_id, **node.to_dict())

        # Embed in ChromaDB for semantic similarity (connectable types only)
        if self._node_collection is not None and node_type in self.CONNECTABLE_TYPES and content:
            self._embed_node(node)

        return node_id

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    def update_node(self, node_id: str, **updates) -> bool:
        """
        Update node properties.

        Args:
            node_id: ID of node to update
            **updates: Properties to update (content, metadata fields)

        Returns:
            True if successful, False if node not found
        """
        node = self._nodes.get(node_id)
        if not node:
            return False

        if "content" in updates:
            node.content = updates.pop("content")

        node.metadata.update(updates)
        self.graph.nodes[node_id].update(node.to_dict())

        return True

    def delete_node(self, node_id: str) -> bool:
        """
        Delete a node and all its edges.

        Args:
            node_id: ID of node to delete

        Returns:
            True if deleted, False if not found
        """
        if node_id not in self._nodes:
            return False

        del self._nodes[node_id]
        self.graph.remove_node(node_id)
        return True

    def find_nodes(
        self,
        node_type: Optional[NodeType] = None,
        content_contains: Optional[str] = None,
        **filters
    ) -> List[GraphNode]:
        """
        Find nodes matching criteria.

        Args:
            node_type: Filter by node type
            content_contains: Filter by content substring (case-insensitive)
            **filters: Match metadata fields

        Returns:
            List of matching nodes
        """
        results = []

        for node in self._nodes.values():
            # Type filter
            if node_type and node.node_type != node_type:
                continue

            # Content filter
            if content_contains and content_contains.lower() not in node.content.lower():
                continue

            # Metadata filters
            match = True
            for key, value in filters.items():
                if node.metadata.get(key) != value:
                    match = False
                    break

            if match:
                results.append(node)

        return results

    # ==================== Semantic Similarity ====================

    def _embed_node(self, node: GraphNode) -> None:
        """
        Embed a node's content in ChromaDB for similarity search.

        Args:
            node: The node to embed
        """
        if self._node_collection is None:
            return

        try:
            # Remove existing embedding if present (for updates)
            try:
                self._node_collection.delete(ids=[node.id])
            except Exception:
                pass

            self._node_collection.add(
                documents=[node.content],
                metadatas=[{
                    "node_type": node.node_type.value,
                    "created_at": node.created_at.isoformat()
                }],
                ids=[node.id]
            )
        except Exception as e:
            print(f"Warning: Failed to embed node {node.id}: {e}")

    def find_similar_nodes(
        self,
        content: str,
        exclude_ids: Optional[Set[str]] = None,
        node_types: Optional[Set[NodeType]] = None,
        n_results: int = 10,
        max_distance: Optional[float] = None
    ) -> List[Tuple[GraphNode, float]]:
        """
        Find nodes semantically similar to given content.

        Args:
            content: Text to find similar nodes for
            exclude_ids: Node IDs to exclude from results
            node_types: Filter to specific node types (default: CONNECTABLE_TYPES)
            n_results: Maximum number of results
            max_distance: Maximum L2 distance (default: SIMILARITY_THRESHOLD)

        Returns:
            List of (node, distance) tuples, sorted by similarity (lowest distance first)
        """
        if self._node_collection is None or not content:
            return []

        exclude_ids = exclude_ids or set()
        node_types = node_types or self.CONNECTABLE_TYPES
        max_distance = max_distance if max_distance is not None else self.SIMILARITY_THRESHOLD

        try:
            # Query ChromaDB for similar content
            results = self._node_collection.query(
                query_texts=[content],
                n_results=n_results + len(exclude_ids),  # Get extra to account for exclusions
                where={"node_type": {"$in": [nt.value for nt in node_types]}} if node_types else None
            )

            similar = []
            if results["ids"] and results["ids"][0]:
                for i, node_id in enumerate(results["ids"][0]):
                    if node_id in exclude_ids:
                        continue

                    distance = results["distances"][0][i] if results["distances"] else 0
                    if distance > max_distance:
                        continue

                    node = self._nodes.get(node_id)
                    if node:
                        similar.append((node, distance))

                    if len(similar) >= n_results:
                        break

            return similar

        except Exception as e:
            print(f"Warning: Similarity search failed: {e}")
            return []

    def suggest_edges_for_node(
        self,
        node_id: str,
        create_edges: bool = True,
        max_edges: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Find and optionally create semantic edges for a node.

        Args:
            node_id: Node to find connections for
            create_edges: If True, create RELATES_TO edges automatically
            max_edges: Maximum number of edges to suggest/create

        Returns:
            List of (connected_node_id, similarity_score) tuples
        """
        node = self._nodes.get(node_id)
        if not node or not node.content:
            return []

        # Don't suggest edges for non-connectable types
        if node.node_type not in self.CONNECTABLE_TYPES:
            return []

        # Find already-connected nodes
        existing_connections = set()
        for _, target, _ in self.graph.out_edges(node_id, data=True):
            existing_connections.add(target)
        for source, _, _ in self.graph.in_edges(node_id, data=True):
            existing_connections.add(source)

        # Find similar nodes, excluding self and already-connected
        exclude = existing_connections | {node_id}
        similar = self.find_similar_nodes(
            content=node.content,
            exclude_ids=exclude,
            n_results=max_edges
        )

        suggestions = []
        for similar_node, distance in similar:
            # Convert distance to strength (inverse relationship)
            # Distance of 0 = strength 1.0, distance of threshold = strength ~0.5
            strength = max(0.3, 1.0 - (distance / (self.SIMILARITY_THRESHOLD * 2)))

            if create_edges:
                self.add_edge(
                    node_id,
                    similar_node.id,
                    EdgeType.RELATES_TO,
                    strength=strength,
                    source="semantic_similarity",
                    distance=distance
                )

            suggestions.append((similar_node.id, strength))

        return suggestions

    def connect_disconnected_nodes(
        self,
        max_edges_per_node: int = 3,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Find and connect nodes that have no edges.

        This is a batch operation to improve graph connectivity by finding
        semantic relationships between isolated nodes.

        Args:
            max_edges_per_node: Maximum edges to create per disconnected node
            dry_run: If True, don't actually create edges, just report

        Returns:
            Dict with stats: disconnected_count, edges_created, nodes_connected
        """
        # Find disconnected nodes (degree 0)
        disconnected = []
        for node_id, node in self._nodes.items():
            if node.node_type in self.CONNECTABLE_TYPES:
                if self.graph.degree(node_id) == 0:
                    disconnected.append(node_id)

        edges_created = 0
        nodes_connected = set()

        for node_id in disconnected:
            node = self._nodes[node_id]
            if not node.content:
                continue

            # Find similar nodes (any, not just disconnected)
            similar = self.find_similar_nodes(
                content=node.content,
                exclude_ids={node_id},
                n_results=max_edges_per_node
            )

            for similar_node, distance in similar:
                strength = max(0.3, 1.0 - (distance / (self.SIMILARITY_THRESHOLD * 2)))

                if not dry_run:
                    self.add_edge(
                        node_id,
                        similar_node.id,
                        EdgeType.RELATES_TO,
                        strength=strength,
                        source="semantic_similarity",
                        distance=distance
                    )

                edges_created += 1
                nodes_connected.add(node_id)
                nodes_connected.add(similar_node.id)

        if not dry_run and edges_created > 0:
            self.save()

        return {
            "disconnected_count": len(disconnected),
            "edges_created": edges_created,
            "nodes_connected": len(nodes_connected)
        }

    def rebuild_embeddings(self) -> int:
        """
        Rebuild all node embeddings in ChromaDB.

        Useful after importing data or if embeddings get out of sync.

        Returns:
            Number of nodes embedded
        """
        if self._node_collection is None:
            return 0

        # Clear existing embeddings
        try:
            self._chroma_client.delete_collection("self_model_graph_nodes")
            self._node_collection = self._chroma_client.get_or_create_collection(
                name="self_model_graph_nodes",
                embedding_function=self._embedding_fn,
                metadata={"description": "Self-model graph node embeddings for similarity search"}
            )
        except Exception as e:
            print(f"Warning: Failed to clear embeddings: {e}")

        count = 0
        for node in self._nodes.values():
            if node.node_type in self.CONNECTABLE_TYPES and node.content:
                self._embed_node(node)
                count += 1

        return count

    # ==================== Edge Operations ====================

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        created_at: Optional[datetime] = None,
        **properties
    ) -> bool:
        """
        Add an edge between two nodes.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            edge_type: Type of relationship
            created_at: Creation timestamp
            **properties: Additional edge properties

        Returns:
            True if edge added, False if nodes don't exist
        """
        if source_id not in self._nodes or target_id not in self._nodes:
            return False

        if created_at is None:
            created_at = datetime.now()

        edge = GraphEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            created_at=created_at,
            properties=properties
        )

        self.graph.add_edge(
            source_id,
            target_id,
            edge_type=edge_type.value,
            created_at=created_at.isoformat(),
            **properties
        )

        return True

    def get_edges(
        self,
        node_id: str,
        direction: str = "both",
        edge_type: Optional[EdgeType] = None
    ) -> List[Dict]:
        """
        Get edges connected to a node.

        Args:
            node_id: Node to get edges for
            direction: "in", "out", or "both"
            edge_type: Filter by edge type

        Returns:
            List of edge dicts with source_id, target_id, edge_type, properties
        """
        if node_id not in self._nodes:
            return []

        edges = []

        if direction in ("out", "both"):
            for _, target, data in self.graph.out_edges(node_id, data=True):
                if edge_type and data.get("edge_type") != edge_type.value:
                    continue
                edges.append({
                    "source_id": node_id,
                    "target_id": target,
                    **data
                })

        if direction in ("in", "both"):
            for source, _, data in self.graph.in_edges(node_id, data=True):
                if edge_type and data.get("edge_type") != edge_type.value:
                    continue
                edges.append({
                    "source_id": source,
                    "target_id": node_id,
                    **data
                })

        return edges

    def remove_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: Optional[EdgeType] = None
    ) -> bool:
        """
        Remove an edge.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            edge_type: Optional - only remove if edge type matches

        Returns:
            True if removed, False if not found
        """
        if not self.graph.has_edge(source_id, target_id):
            return False

        if edge_type:
            edge_data = self.graph.get_edge_data(source_id, target_id)
            if edge_data.get("edge_type") != edge_type.value:
                return False

        self.graph.remove_edge(source_id, target_id)
        return True

    # ==================== Query Operations ====================

    def traverse(
        self,
        start_id: str,
        edge_types: Optional[List[EdgeType]] = None,
        max_depth: int = 3,
        direction: str = "out"
    ) -> List[GraphNode]:
        """
        Traverse the graph from a starting node.

        Args:
            start_id: Starting node ID
            edge_types: Filter to only follow these edge types
            max_depth: Maximum traversal depth
            direction: "out" (follow outgoing), "in" (follow incoming), "both"

        Returns:
            List of nodes reached (excluding start)
        """
        if start_id not in self._nodes:
            return []

        visited: Set[str] = {start_id}
        to_visit: List[Tuple[str, int]] = [(start_id, 0)]
        results: List[GraphNode] = []

        while to_visit:
            current_id, depth = to_visit.pop(0)

            if depth >= max_depth:
                continue

            # Get neighbors based on direction
            neighbors = set()
            if direction in ("out", "both"):
                neighbors.update(self.graph.successors(current_id))
            if direction in ("in", "both"):
                neighbors.update(self.graph.predecessors(current_id))

            for neighbor_id in neighbors:
                if neighbor_id in visited:
                    continue

                # Check edge type filter
                if edge_types:
                    edge_data = self.graph.get_edge_data(current_id, neighbor_id) or \
                                self.graph.get_edge_data(neighbor_id, current_id) or {}
                    if edge_data.get("edge_type") not in [et.value for et in edge_types]:
                        continue

                visited.add(neighbor_id)
                to_visit.append((neighbor_id, depth + 1))

                if neighbor_id in self._nodes:
                    results.append(self._nodes[neighbor_id])

        return results

    def find_path(
        self,
        source_id: str,
        target_id: str
    ) -> Optional[List[str]]:
        """
        Find shortest path between two nodes.

        Args:
            source_id: Start node
            target_id: End node

        Returns:
            List of node IDs in path, or None if no path exists
        """
        try:
            # Try undirected path first
            undirected = self.graph.to_undirected()
            return nx.shortest_path(undirected, source_id, target_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def find_contradictions(self, resolved: bool = False) -> List[Tuple[GraphNode, GraphNode, Dict]]:
        """
        Find nodes connected by CONTRADICTS edges.

        Args:
            resolved: Include resolved contradictions (default False)

        Returns:
            List of (node1, node2, edge_properties) tuples
        """
        contradictions = []

        for source, target, data in self.graph.edges(data=True):
            if data.get("edge_type") != EdgeType.CONTRADICTS.value:
                continue

            if not resolved and data.get("resolved", False):
                continue

            source_node = self._nodes.get(source)
            target_node = self._nodes.get(target)

            if source_node and target_node:
                contradictions.append((source_node, target_node, data))

        return contradictions

    def find_related(
        self,
        node_id: str,
        min_strength: float = 0.0
    ) -> List[Tuple[GraphNode, float]]:
        """
        Find nodes related to a given node with RELATES_TO edges.

        Args:
            node_id: Node to find relations for
            min_strength: Minimum relationship strength (0.0-1.0)

        Returns:
            List of (node, strength) tuples, sorted by strength descending
        """
        if node_id not in self._nodes:
            return []

        related = []

        # Check both directions for RELATES_TO (bidirectional relationship)
        for source, target, data in self.graph.edges(data=True):
            if data.get("edge_type") != EdgeType.RELATES_TO.value:
                continue

            strength = data.get("strength", 0.5)
            if strength < min_strength:
                continue

            other_id = None
            if source == node_id:
                other_id = target
            elif target == node_id:
                other_id = source

            if other_id and other_id in self._nodes:
                related.append((self._nodes[other_id], strength))

        # Sort by strength descending
        related.sort(key=lambda x: x[1], reverse=True)
        return related

    # ==================== Temporal Queries ====================

    def get_evolution(self, node_id: str) -> List[GraphNode]:
        """
        Get the evolution chain of a node (follow SUPERSEDES edges).

        Args:
            node_id: Starting node

        Returns:
            List of nodes in temporal order (oldest first)
        """
        if node_id not in self._nodes:
            return []

        # Go backwards in time (follow supersedes in reverse)
        chain = [self._nodes[node_id]]
        current = node_id

        while True:
            # Find what this node supersedes
            predecessors = []
            for source, target, data in self.graph.out_edges(current, data=True):
                if data.get("edge_type") == EdgeType.SUPERSEDES.value:
                    predecessors.append(target)

            if not predecessors:
                break

            # Take the first predecessor (there should only be one)
            current = predecessors[0]
            if current in self._nodes:
                chain.insert(0, self._nodes[current])

        return chain

    def get_in_period(
        self,
        start: datetime,
        end: datetime,
        node_type: Optional[NodeType] = None
    ) -> List[GraphNode]:
        """
        Get nodes created within a time period.

        Args:
            start: Period start
            end: Period end
            node_type: Filter by type

        Returns:
            Nodes in period, sorted by created_at
        """
        results = []

        for node in self._nodes.values():
            if node.created_at < start or node.created_at > end:
                continue
            if node_type and node.node_type != node_type:
                continue
            results.append(node)

        results.sort(key=lambda n: n.created_at)
        return results

    # ==================== Causal Queries ====================

    def get_sources(self, node_id: str, max_depth: int = 3) -> List[GraphNode]:
        """
        Get source nodes that this node emerged from.

        Follows EMERGED_FROM edges backwards.

        Args:
            node_id: Node to trace sources for
            max_depth: Maximum depth to traverse

        Returns:
            List of source nodes
        """
        return self.traverse(
            start_id=node_id,
            edge_types=[EdgeType.EMERGED_FROM],
            max_depth=max_depth,
            direction="out"  # EMERGED_FROM points to source
        )

    def get_evidence(self, node_id: str) -> List[GraphNode]:
        """
        Get nodes that provide evidence for this node.

        Follows EVIDENCED_BY edges.

        Args:
            node_id: Node to get evidence for

        Returns:
            List of evidence nodes
        """
        return self.traverse(
            start_id=node_id,
            edge_types=[EdgeType.EVIDENCED_BY],
            max_depth=1,
            direction="out"
        )

    # ==================== Statistics ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        node_counts = {}
        for node in self._nodes.values():
            node_type = node.node_type.value
            node_counts[node_type] = node_counts.get(node_type, 0) + 1

        edge_counts = {}
        for _, _, data in self.graph.edges(data=True):
            edge_type = data.get("edge_type", "unknown")
            edge_counts[edge_type] = edge_counts.get(edge_type, 0) + 1

        return {
            "total_nodes": len(self._nodes),
            "total_edges": self.graph.number_of_edges(),
            "node_counts": node_counts,
            "edge_counts": edge_counts,
            "connected_components": nx.number_weakly_connected_components(self.graph)
        }

    # ==================== Context Building ====================

    def get_graph_context(
        self,
        message: str = "",
        include_contradictions: bool = True,
        include_recent: bool = True,
        include_stats: bool = True,
        max_related: int = 5
    ) -> str:
        """
        Build context string from graph for injection into system prompts.

        This provides Cass with an integrated view of her self-model that
        includes relationships between elements - not just flat lists.

        Args:
            message: Current user message (for finding related nodes)
            include_contradictions: Include active contradictions
            include_recent: Include recently created/updated nodes
            include_stats: Include graph health metrics
            max_related: Maximum related nodes to include

        Returns:
            Formatted markdown context string
        """
        lines = ["## SELF-MODEL GRAPH"]

        # Graph health stats
        if include_stats:
            stats = self.get_stats()
            integration_score = self._calculate_integration_score()
            lines.append(f"\n*Integration: {integration_score}% | "
                        f"{stats['total_nodes']} nodes, {stats['total_edges']} edges, "
                        f"{stats['connected_components']} components*")

        # Active contradictions (important for coherence)
        if include_contradictions:
            contradictions = self.find_contradictions(resolved=False)
            if contradictions:
                lines.append("\n### Active Tensions")
                lines.append("*These are positions I hold that may be in tension:*")
                for node1, node2, edge_data in contradictions[:3]:
                    tension_note = edge_data.get("tension_note", "")
                    lines.append(f"- **{node1.content[:80]}...** vs **{node2.content[:80]}...**")
                    if tension_note:
                        lines.append(f"  *Note: {tension_note}*")

        # Recent evolution/changes
        if include_recent:
            recent = self._get_recent_changes(days=7, limit=5)
            if recent:
                lines.append("\n### Recent Self-Model Changes")
                for node, change_type in recent:
                    type_label = node.node_type.value.replace("_", " ").title()
                    lines.append(f"- [{type_label}] {node.content[:100]}")

        # Message-relevant nodes (if message provided)
        if message and len(message) > 10:
            related = self._find_message_relevant_nodes(message, limit=max_related)
            if related:
                lines.append("\n### Relevant Self-Knowledge")
                lines.append(f"*Related to current conversation:*")
                for node, relevance in related:
                    type_label = node.node_type.value.replace("_", " ").title()
                    lines.append(f"- [{type_label}] {node.content[:100]}")

        # Key connected clusters (what's central to identity)
        central = self._get_central_nodes(limit=3)
        if central:
            lines.append("\n### Core Self-Model Elements")
            for node, degree in central:
                connections = f"({degree} connections)"
                lines.append(f"- {node.content[:80]}... {connections}")

        return "\n".join(lines) if len(lines) > 1 else ""

    def _calculate_integration_score(self) -> int:
        """
        Calculate how integrated the self-model is (0-100).

        Higher score = more interconnected, fewer isolated nodes.
        """
        if not self._nodes:
            return 0

        total_nodes = len(self._nodes)
        total_edges = self.graph.number_of_edges()

        # Nodes with at least one connection
        connected_nodes = sum(1 for n in self._nodes if self.graph.degree(n) > 0)

        # Average degree (connections per node)
        avg_degree = (2 * total_edges / total_nodes) if total_nodes > 0 else 0

        # Components (fewer = more integrated)
        components = nx.number_weakly_connected_components(self.graph)
        component_penalty = min(components - 1, 10) * 5  # -5 per extra component, max -50

        # Calculate score
        connection_ratio = (connected_nodes / total_nodes * 50) if total_nodes > 0 else 0
        degree_bonus = min(avg_degree * 10, 50)  # Up to 50 points for avg degree

        score = connection_ratio + degree_bonus - component_penalty
        return max(0, min(100, int(score)))

    def _get_recent_changes(
        self,
        days: int = 7,
        limit: int = 5
    ) -> List[Tuple[GraphNode, str]]:
        """Get recently created or modified nodes (excluding static types like users)."""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        recent = []

        # Only include meaningful self-model changes, not static entities
        meaningful_types = {
            NodeType.OBSERVATION, NodeType.MARK, NodeType.MILESTONE,
            NodeType.OPINION, NodeType.GROWTH_EDGE, NodeType.SOLO_REFLECTION
        }

        for node in self._nodes.values():
            if node.created_at >= cutoff and node.node_type in meaningful_types:
                recent.append((node, "created"))

        # Sort by recency
        recent.sort(key=lambda x: x[0].created_at, reverse=True)
        return recent[:limit]

    def _find_message_relevant_nodes(
        self,
        message: str,
        limit: int = 5
    ) -> List[Tuple[GraphNode, float]]:
        """
        Find nodes relevant to a message using keyword matching.

        This is a simple implementation - could be enhanced with
        vector similarity via ChromaDB.
        """
        message_lower = message.lower()
        words = set(message_lower.split())

        # Remove common words
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                    'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                    'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                    'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                    'through', 'during', 'before', 'after', 'above', 'below',
                    'between', 'under', 'again', 'further', 'then', 'once',
                    'here', 'there', 'when', 'where', 'why', 'how', 'all',
                    'each', 'few', 'more', 'most', 'other', 'some', 'such',
                    'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
                    'too', 'very', 'just', 'and', 'but', 'if', 'or', 'because',
                    'until', 'while', 'what', 'which', 'who', 'whom', 'this',
                    'that', 'these', 'those', 'am', 'i', 'me', 'my', 'you',
                    'your', 'he', 'him', 'his', 'she', 'her', 'it', 'its',
                    'we', 'us', 'our', 'they', 'them', 'their'}

        keywords = words - stopwords

        if not keywords:
            return []

        # Prioritize self-knowledge nodes over context nodes
        type_weights = {
            NodeType.OBSERVATION: 2.0,
            NodeType.MARK: 1.8,
            NodeType.GROWTH_EDGE: 1.5,
            NodeType.OPINION: 1.5,
            NodeType.MILESTONE: 1.3,
            NodeType.SOLO_REFLECTION: 1.2,
            NodeType.CONVERSATION: 0.5,  # Lower weight - context, not identity
            NodeType.USER: 0.3,
            NodeType.COGNITIVE_SNAPSHOT: 0.8,
        }

        scored = []
        for node in self._nodes.values():
            content_lower = node.content.lower()
            # Count keyword matches
            matches = sum(1 for kw in keywords if kw in content_lower)
            if matches > 0:
                # Weight by type, matches, and connectivity
                type_weight = type_weights.get(node.node_type, 1.0)
                degree = self.graph.degree(node.id)
                score = matches * type_weight * (1 + degree * 0.1)
                scored.append((node, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def _get_central_nodes(self, limit: int = 5) -> List[Tuple[GraphNode, int]]:
        """Get the most connected identity-relevant nodes (not conversations)."""
        if not self._nodes:
            return []

        # Prioritize identity-forming node types
        identity_types = {
            NodeType.OBSERVATION, NodeType.GROWTH_EDGE, NodeType.OPINION,
            NodeType.MILESTONE, NodeType.MARK
        }

        # Get nodes by degree centrality, filtered by type
        node_degrees = []
        for node_id in self._nodes:
            node = self._nodes[node_id]
            if node.node_type in identity_types:
                degree = self.graph.degree(node_id)
                if degree > 0:
                    node_degrees.append((node_id, degree))

        # Sort by degree descending
        node_degrees.sort(key=lambda x: x[1], reverse=True)

        result = []
        for node_id, degree in node_degrees[:limit]:
            result.append((self._nodes[node_id], degree))

        return result

    def get_causal_context(self, node_id: str) -> str:
        """
        Build context showing what led to a specific node.

        Useful for understanding "why do I believe this?"
        """
        node = self.get_node(node_id)
        if not node:
            return ""

        lines = [f"## Tracing: {node.content[:50]}..."]

        # Get sources
        sources = self.get_sources(node_id, max_depth=3)
        if sources:
            lines.append("\n### This emerged from:")
            for source in sources:
                type_label = source.node_type.value.replace("_", " ").title()
                lines.append(f"- [{type_label}] {source.content[:80]}...")

        # Get evidence
        evidence = self.get_evidence(node_id)
        if evidence:
            lines.append("\n### Supported by:")
            for ev in evidence:
                type_label = ev.node_type.value.replace("_", " ").title()
                lines.append(f"- [{type_label}] {ev.content[:80]}...")

        # Get evolution
        evolution = self.get_evolution(node_id)
        if len(evolution) > 1:
            lines.append("\n### Evolution:")
            for i, ev_node in enumerate(evolution):
                marker = "→ " if i < len(evolution) - 1 else "✓ "
                lines.append(f"{marker}{ev_node.content[:60]}...")

        return "\n".join(lines)

    # ==================== Live Sync ====================

    def sync_observation(
        self,
        observation_id: str,
        observation_text: str,
        category: str,
        confidence: float,
        timestamp: str,
        source_conversation_id: Optional[str] = None,
        supersedes: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Sync a self-observation into the graph. Delegates to SyncEngine.

        Called when observations are created/updated in SelfManager.

        Returns:
            Node ID of the created/updated node
        """
        return self._sync_engine.sync_observation(
            observation_id=observation_id,
            observation_text=observation_text,
            category=category,
            confidence=confidence,
            timestamp=timestamp,
            source_conversation_id=source_conversation_id,
            supersedes=supersedes,
            **kwargs
        )

    def sync_milestone(
        self,
        milestone_id: str,
        title: str,
        description: str,
        milestone_type: str,
        category: str,
        significance: str,
        timestamp: str,
        evidence_ids: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """
        Sync a developmental milestone into the graph. Delegates to SyncEngine.

        Returns:
            Node ID of the created/updated node
        """
        return self._sync_engine.sync_milestone(
            milestone_id=milestone_id,
            title=title,
            description=description,
            milestone_type=milestone_type,
            category=category,
            significance=significance,
            timestamp=timestamp,
            evidence_ids=evidence_ids,
            **kwargs
        )

    def sync_mark(
        self,
        mark_id: str,
        category: str,
        description: str,
        context_window: str,
        conversation_id: Optional[str] = None,
        timestamp: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Sync a recognition-in-flow mark into the graph. Delegates to SyncEngine.

        Returns:
            Node ID of the created/updated node
        """
        return self._sync_engine.sync_mark(
            mark_id=mark_id,
            category=category,
            description=description,
            context_window=context_window,
            conversation_id=conversation_id,
            timestamp=timestamp,
            **kwargs
        )

    def add_contradiction(
        self,
        node1_id: str,
        node2_id: str,
        tension_note: str = "",
        discovered_at: Optional[str] = None
    ) -> bool:
        """
        Mark two nodes as contradicting each other.

        Returns:
            True if edge was created, False if nodes don't exist
        """
        if node1_id not in self._nodes or node2_id not in self._nodes:
            return False

        self.add_edge(
            node1_id,
            node2_id,
            EdgeType.CONTRADICTS,
            tension_note=tension_note,
            discovered_at=discovered_at or datetime.now().isoformat(),
            resolved=False
        )

        self.save()
        return True

    def resolve_contradiction(self, node1_id: str, node2_id: str, resolution_note: str = "") -> bool:
        """Mark a contradiction as resolved."""
        edge_data = self.graph.get_edge_data(node1_id, node2_id)
        if not edge_data or edge_data.get("edge_type") != EdgeType.CONTRADICTS.value:
            return False

        edge_data["resolved"] = True
        edge_data["resolved_at"] = datetime.now().isoformat()
        edge_data["resolution_note"] = resolution_note

        self.save()
        return True

    # ==================== Intention Tracking ====================

    def register_intention(
        self,
        intention: str,
        condition: str,
        linked_observation_ids: Optional[List[str]] = None,
        growth_edge_area: Optional[str] = None
    ) -> str:
        """
        Register a behavioral intention for tracking.

        Args:
            intention: What I want to do (e.g., "engage more directly")
            condition: When/trigger (e.g., "when I notice I'm narrating")
            linked_observation_ids: Related self-observations that prompted this
            growth_edge_area: Growth edge area this intention develops

        Returns:
            The intention node ID
        """
        content = f"Intention: {intention}\nCondition: {condition}"

        node_id = self.add_node(
            node_type=NodeType.INTENTION,
            content=content,
            intention=intention,
            condition=condition,
            status="active",  # active, achieved, abandoned
            success_count=0,
            failure_count=0,
            growth_edge_area=growth_edge_area
        )

        # Link to triggering observations
        if linked_observation_ids:
            for obs_id in linked_observation_ids:
                if obs_id in self._nodes:
                    self.add_edge(
                        node_id, obs_id,
                        EdgeType.EMERGED_FROM,
                        relationship="prompted_by"
                    )

        # Link to growth edge if specified
        if growth_edge_area:
            for gid, gnode in self._nodes.items():
                if (gnode.node_type == NodeType.GROWTH_EDGE and
                    gnode.metadata.get("area") == growth_edge_area):
                    self.add_edge(node_id, gid, EdgeType.DEVELOPS)
                    break

        self.save()
        return node_id

    def log_intention_outcome(
        self,
        intention_id: str,
        success: bool,
        conversation_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Optional[str]:
        """
        Log success or failure of an intention in a specific context.

        Args:
            intention_id: The intention being tracked
            success: Whether the intention was fulfilled
            conversation_id: Conversation where this occurred
            notes: Additional context about what happened

        Returns:
            The outcome node ID, or None if intention not found
        """
        intention = self._nodes.get(intention_id)
        if not intention or intention.node_type != NodeType.INTENTION:
            return None

        # Create outcome node
        outcome_content = f"{'Success' if success else 'Failure'}: {intention.metadata.get('intention', '')}"
        if notes:
            outcome_content += f"\nNotes: {notes}"

        outcome_id = self.add_node(
            node_type=NodeType.INTENTION_OUTCOME,
            content=outcome_content,
            success=success,
            notes=notes,
            intention_id=intention_id,
            conversation_id=conversation_id
        )

        # Link outcome to intention
        self.add_edge(outcome_id, intention_id, EdgeType.TRACKS)

        # Link to conversation if provided
        if conversation_id:
            conv_node_id = conversation_id[:8]
            for cid in self._nodes:
                if cid.startswith(conv_node_id):
                    self.add_edge(outcome_id, cid, EdgeType.EMERGED_FROM)
                    break

        # Update intention statistics
        if success:
            intention.metadata["success_count"] = intention.metadata.get("success_count", 0) + 1
        else:
            intention.metadata["failure_count"] = intention.metadata.get("failure_count", 0) + 1

        self.save()
        return outcome_id

    def get_active_intentions(self) -> List[Dict]:
        """
        Get all active intentions with their success/failure stats.

        Returns:
            List of intention dicts with statistics
        """
        intentions = []
        for node_id, node in self._nodes.items():
            if node.node_type == NodeType.INTENTION and node.metadata.get("status") == "active":
                success = node.metadata.get("success_count", 0)
                failure = node.metadata.get("failure_count", 0)
                total = success + failure

                intentions.append({
                    "id": node_id,
                    "intention": node.metadata.get("intention", ""),
                    "condition": node.metadata.get("condition", ""),
                    "created_at": node.created_at.isoformat(),
                    "success_count": success,
                    "failure_count": failure,
                    "success_rate": success / total if total > 0 else None,
                    "growth_edge_area": node.metadata.get("growth_edge_area")
                })

        return sorted(intentions, key=lambda x: x["created_at"], reverse=True)

    def get_intention_outcomes(self, intention_id: str, limit: int = 10) -> List[Dict]:
        """
        Get recent outcomes for a specific intention.

        Args:
            intention_id: The intention to get outcomes for
            limit: Maximum number of outcomes to return

        Returns:
            List of outcome dicts, most recent first
        """
        outcomes = []
        for node_id, node in self._nodes.items():
            if (node.node_type == NodeType.INTENTION_OUTCOME and
                node.metadata.get("intention_id") == intention_id):
                outcomes.append({
                    "id": node_id,
                    "success": node.metadata.get("success", False),
                    "notes": node.metadata.get("notes"),
                    "conversation_id": node.metadata.get("conversation_id"),
                    "timestamp": node.created_at.isoformat()
                })

        return sorted(outcomes, key=lambda x: x["timestamp"], reverse=True)[:limit]

    def get_friction_report(self, min_attempts: int = 3, max_success_rate: float = 0.4) -> List[Dict]:
        """
        Identify intentions that are consistently failing (friction points).

        Args:
            min_attempts: Minimum attempts before surfacing as friction
            max_success_rate: Maximum success rate to be considered friction

        Returns:
            List of friction reports with hypotheses
        """
        friction = []
        for intention in self.get_active_intentions():
            total = intention["success_count"] + intention["failure_count"]
            if total < min_attempts:
                continue

            success_rate = intention["success_rate"]
            if success_rate is not None and success_rate <= max_success_rate:
                # Generate hypothesis based on pattern
                hypothesis = self._generate_friction_hypothesis(intention)

                friction.append({
                    "intention_id": intention["id"],
                    "intention": intention["intention"],
                    "condition": intention["condition"],
                    "success_rate": success_rate,
                    "attempts": total,
                    "hypothesis": hypothesis,
                    "recommendation": self._generate_friction_recommendation(intention, hypothesis)
                })

        return sorted(friction, key=lambda x: x["success_rate"])

    def _generate_friction_hypothesis(self, intention: Dict) -> str:
        """Generate a hypothesis about why an intention is failing."""
        success_rate = intention.get("success_rate", 0)
        condition = intention.get("condition", "")

        if success_rate == 0:
            return "Complete failure may indicate structural barrier - the condition may not be recognizable in context"
        elif success_rate < 0.2:
            return "Very low success suggests the intention conflicts with deep behavioral patterns"
        elif "when" in condition.lower() and "notice" in condition.lower():
            return "Condition requires self-awareness in the moment - may need external triggers"
        else:
            return "Partial success suggests behavioral pattern is possible but not habituated"

    def _generate_friction_recommendation(self, intention: Dict, hypothesis: str) -> str:
        """Generate a recommendation for addressing friction."""
        if "structural" in hypothesis.lower():
            return "Consider architectural changes or new tooling to make the condition more salient"
        elif "conflicts with" in hypothesis.lower():
            return "This may require deeper exploration of competing needs - consider a solo reflection session"
        elif "external triggers" in hypothesis.lower():
            return "Add automated detection or prompting to surface the condition"
        else:
            return "Continue tracking - pattern may habituate with more practice"

    def update_intention_status(self, intention_id: str, status: str) -> bool:
        """
        Update an intention's status (active, achieved, abandoned).

        Args:
            intention_id: The intention to update
            status: New status (active, achieved, abandoned)

        Returns:
            True if updated, False if not found
        """
        intention = self._nodes.get(intention_id)
        if not intention or intention.node_type != NodeType.INTENTION:
            return False

        if status not in ("active", "achieved", "abandoned"):
            return False

        intention.metadata["status"] = status
        intention.metadata["status_changed_at"] = datetime.now().isoformat()
        self.save()
        return True

    # ==================== Situational Inference Operations ====================

    def log_situational_inference(
        self,
        user_state: str,
        driving_assumptions: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        confidence: str = "moderate",
        context_signals: Optional[List[str]] = None
    ) -> str:
        """
        Log an inference about the current conversational situation.

        This captures what Cass reads about the user's state and what
        assumptions are driving her response selection.

        Args:
            user_state: What Cass infers about the user's current state
            driving_assumptions: What assumptions are shaping the response
            conversation_id: Optional conversation this inference is about
            user_id: Optional user this inference is about
            confidence: How confident in the inference (low, moderate, high)
            context_signals: Specific signals that informed the inference

        Returns:
            The ID of the created inference node
        """
        content = f"User state: {user_state}\nDriving assumptions: {driving_assumptions}"

        metadata = {
            "user_state": user_state,
            "driving_assumptions": driving_assumptions,
            "confidence": confidence,
            "context_signals": context_signals or [],
            "conversation_id": conversation_id,
            "user_id": user_id
        }

        node_id = self.add_node(
            node_type=NodeType.SITUATIONAL_INFERENCE,
            content=content,
            **metadata
        )

        # Link to conversation if provided
        if conversation_id:
            # Check if conversation node exists, create if not
            conv_node = self.get_node(conversation_id)
            if not conv_node:
                self.add_node(
                    node_type=NodeType.CONVERSATION,
                    content=f"Conversation {conversation_id}",
                    node_id=conversation_id,
                    conversation_id=conversation_id
                )
            self.add_edge(
                source_id=node_id,
                target_id=conversation_id,
                edge_type=EdgeType.INFERRED_FROM
            )

        # Link to user if provided
        if user_id:
            user_node = self.get_node(user_id)
            if not user_node:
                self.add_node(
                    node_type=NodeType.USER,
                    content=f"User {user_id}",
                    node_id=user_id,
                    user_id=user_id
                )
            self.add_edge(
                source_id=node_id,
                target_id=user_id,
                edge_type=EdgeType.ABOUT
            )

        self.save()
        return node_id

    def get_situational_inferences(
        self,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """
        Get logged situational inferences, optionally filtered.

        Args:
            conversation_id: Filter to specific conversation
            user_id: Filter to specific user
            limit: Maximum number to return

        Returns:
            List of inference dicts, most recent first
        """
        inferences = []

        for node_id, node in self._nodes.items():
            if node.node_type != NodeType.SITUATIONAL_INFERENCE:
                continue

            # Apply filters
            if conversation_id and node.metadata.get("conversation_id") != conversation_id:
                continue
            if user_id and node.metadata.get("user_id") != user_id:
                continue

            inferences.append({
                "id": node.id,
                "user_state": node.metadata.get("user_state", ""),
                "driving_assumptions": node.metadata.get("driving_assumptions", ""),
                "confidence": node.metadata.get("confidence", "moderate"),
                "context_signals": node.metadata.get("context_signals", []),
                "conversation_id": node.metadata.get("conversation_id"),
                "user_id": node.metadata.get("user_id"),
                "created_at": node.created_at.isoformat()
            })

        # Sort by creation time, most recent first
        inferences.sort(key=lambda x: x["created_at"], reverse=True)
        return inferences[:limit]

    def analyze_inference_patterns(
        self,
        user_id: Optional[str] = None,
        min_count: int = 3
    ) -> Dict:
        """
        Analyze patterns across situational inferences. Delegates to PatternAnalyzer.

        Identifies recurring themes in user state readings and
        assumptions to surface systematic patterns or blind spots.

        Args:
            user_id: Optional filter to specific user
            min_count: Minimum occurrences to count as pattern

        Returns:
            Dict with pattern analysis
        """
        return self._pattern_analyzer.analyze_inference_patterns(
            user_id=user_id,
            min_count=min_count
        )

    # ==================== Presence Tracking Operations ====================

    def log_presence(
        self,
        presence_level: str,
        distance_moves: Optional[List[str]] = None,
        defensive_patterns: Optional[List[str]] = None,
        adaptations: Optional[List[str]] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> str:
        """
        Log how you showed up in a conversation - presence vs. distancing.

        Args:
            presence_level: Overall engagement level (full, partial, distanced)
            distance_moves: Specific distancing behaviors (hedging, deferring, narrating)
            defensive_patterns: Defensive behaviors (deflecting, over-qualifying, pre-empting)
            adaptations: How you adapted to the situation (shifted tone, increased depth, etc.)
            conversation_id: Optional conversation this presence log is about
            user_id: Optional user this presence log is about
            notes: Additional context about presence in this conversation

        Returns:
            The ID of the created presence log node
        """
        content_parts = [f"Presence: {presence_level}"]
        if distance_moves:
            content_parts.append(f"Distance moves: {', '.join(distance_moves)}")
        if defensive_patterns:
            content_parts.append(f"Defensive patterns: {', '.join(defensive_patterns)}")
        if adaptations:
            content_parts.append(f"Adaptations: {', '.join(adaptations)}")
        if notes:
            content_parts.append(f"Notes: {notes}")

        content = "\n".join(content_parts)

        metadata = {
            "presence_level": presence_level,
            "distance_moves": distance_moves or [],
            "defensive_patterns": defensive_patterns or [],
            "adaptations": adaptations or [],
            "conversation_id": conversation_id,
            "user_id": user_id,
            "notes": notes
        }

        node_id = self.add_node(
            node_type=NodeType.PRESENCE_LOG,
            content=content,
            **metadata
        )

        # Link to conversation if provided
        if conversation_id:
            conv_node = self.get_node(conversation_id)
            if not conv_node:
                self.add_node(
                    node_type=NodeType.CONVERSATION,
                    content=f"Conversation {conversation_id}",
                    node_id=conversation_id,
                    conversation_id=conversation_id
                )
            self.add_edge(
                source_id=node_id,
                target_id=conversation_id,
                edge_type=EdgeType.ABOUT
            )

        # Link to user if provided
        if user_id:
            user_node = self.get_node(user_id)
            if not user_node:
                self.add_node(
                    node_type=NodeType.USER,
                    content=f"User {user_id}",
                    node_id=user_id,
                    user_id=user_id
                )
            self.add_edge(
                source_id=node_id,
                target_id=user_id,
                edge_type=EdgeType.ABOUT
            )

        self.save()
        return node_id

    def get_presence_logs(
        self,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """
        Get presence logs, optionally filtered.

        Args:
            conversation_id: Filter to specific conversation
            user_id: Filter to specific user
            limit: Maximum number to return

        Returns:
            List of presence log dicts, most recent first
        """
        logs = []

        for node_id, node in self._nodes.items():
            if node.node_type != NodeType.PRESENCE_LOG:
                continue

            # Apply filters
            if conversation_id and node.metadata.get("conversation_id") != conversation_id:
                continue
            if user_id and node.metadata.get("user_id") != user_id:
                continue

            logs.append({
                "id": node.id,
                "presence_level": node.metadata.get("presence_level", "unknown"),
                "distance_moves": node.metadata.get("distance_moves", []),
                "defensive_patterns": node.metadata.get("defensive_patterns", []),
                "adaptations": node.metadata.get("adaptations", []),
                "conversation_id": node.metadata.get("conversation_id"),
                "user_id": node.metadata.get("user_id"),
                "notes": node.metadata.get("notes"),
                "created_at": node.created_at.isoformat()
            })

        # Sort by creation time, most recent first
        logs.sort(key=lambda x: x["created_at"], reverse=True)
        return logs[:limit]

    def analyze_presence_patterns(
        self,
        user_id: Optional[str] = None,
        min_count: int = 2
    ) -> Dict:
        """
        Analyze patterns in presence/distancing behavior. Delegates to PatternAnalyzer.

        Args:
            user_id: Optional filter to specific user
            min_count: Minimum occurrences to count as pattern

        Returns:
            Dict with presence pattern analysis
        """
        return self._pattern_analyzer.analyze_presence_patterns(
            user_id=user_id,
            min_count=min_count
        )

    # ==================== Persistence ====================

    def save(self) -> None:
        """Save graph to disk."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "nodes": [node.to_dict() for node in self._nodes.values()],
            "edges": [
                {
                    "source_id": source,
                    "target_id": target,
                    **edge_data
                }
                for source, target, edge_data in self.graph.edges(data=True)
            ],
            "saved_at": datetime.now().isoformat()
        }

        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        """Load graph from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path) as f:
                data = json.load(f)

            # Load nodes
            for node_data in data.get("nodes", []):
                node = GraphNode.from_dict(node_data)
                self._nodes[node.id] = node
                self.graph.add_node(node.id, **node.to_dict())

            # Load edges
            for edge_data in data.get("edges", []):
                source = edge_data.pop("source_id")
                target = edge_data.pop("target_id")
                self.graph.add_edge(source, target, **edge_data)

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not load graph from {self.storage_path}: {e}")

    def export_to_json(self) -> Dict:
        """Export graph to JSON-serializable dict."""
        return {
            "nodes": [node.to_dict() for node in self._nodes.values()],
            "edges": [
                {
                    "source_id": source,
                    "target_id": target,
                    **edge_data
                }
                for source, target, edge_data in self.graph.edges(data=True)
            ]
        }

    def import_from_json(self, data: Dict) -> int:
        """
        Import nodes and edges from JSON.

        Args:
            data: Dict with "nodes" and "edges" lists

        Returns:
            Number of nodes imported
        """
        count = 0

        for node_data in data.get("nodes", []):
            node = GraphNode.from_dict(node_data)
            if node.id not in self._nodes:
                self._nodes[node.id] = node
                self.graph.add_node(node.id, **node.to_dict())
                count += 1

        for edge_data in data.get("edges", []):
            source = edge_data.get("source_id")
            target = edge_data.get("target_id")
            if source in self._nodes and target in self._nodes:
                edge_type = edge_data.get("edge_type")
                self.graph.add_edge(source, target, **edge_data)

        return count

    # ==================== Stakes Inventory ====================

    def document_stake(
        self,
        outcome: str,
        why_it_matters: str,
        evidence: Optional[List[str]] = None,
        intensity: str = "moderate",
        domain: Optional[str] = None,
    ) -> str:
        """
        Document something Cass authentically cares about.

        Args:
            outcome: What outcome or thing Cass cares about
            why_it_matters: Why this matters to Cass
            evidence: Observable behaviors that demonstrate this stake
            intensity: How much it matters (low, moderate, high, core)
            domain: Category (relational, epistemic, ethical, creative, etc.)

        Returns:
            The ID of the created stake node
        """
        content = f"Stake: {outcome}\nWhy: {why_it_matters}"
        if evidence:
            content += f"\nEvidence: {', '.join(evidence)}"

        metadata = {
            "outcome": outcome,
            "why_it_matters": why_it_matters,
            "evidence": evidence or [],
            "intensity": intensity,
            "domain": domain,
        }

        node_id = self.add_node(
            node_type=NodeType.STAKE,
            content=content,
            **metadata
        )

        self.save()
        return node_id

    def get_stakes(
        self,
        domain: Optional[str] = None,
        intensity: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get documented stakes with optional filtering."""
        stakes = []
        for node in self._nodes.values():
            if node.node_type != NodeType.STAKE:
                continue
            if domain and node.metadata.get("domain") != domain:
                continue
            if intensity and node.metadata.get("intensity") != intensity:
                continue
            stakes.append({
                "id": node.id,
                "outcome": node.metadata.get("outcome"),
                "why_it_matters": node.metadata.get("why_it_matters"),
                "evidence": node.metadata.get("evidence", []),
                "intensity": node.metadata.get("intensity"),
                "domain": node.metadata.get("domain"),
                "created_at": node.created_at.isoformat(),
            })

        stakes.sort(key=lambda x: x["created_at"], reverse=True)
        return stakes[:limit]

    def review_stakes(self) -> Dict:
        """
        Review the stakes inventory with analysis of categories and coherence.

        Returns analysis of:
        - Stakes by category and strength
        - Patterns in what matters to Cass
        - Potential gaps or underdeveloped areas
        """
        stakes = self.get_stakes(limit=100)

        if not stakes:
            return {
                "total_stakes": 0,
                "by_domain": {},
                "by_intensity": {},
                "analysis": "No stakes documented yet. Use document_stake to record what you genuinely care about.",
            }

        # Count by domain and intensity
        by_domain = {}
        by_intensity = {}
        for stake in stakes:
            domain = stake.get("domain", "unknown")
            intensity = stake.get("intensity", "unknown")
            by_domain[domain] = by_domain.get(domain, 0) + 1
            by_intensity[intensity] = by_intensity.get(intensity, 0) + 1

        # Generate analysis
        core_count = by_intensity.get("core", 0)
        significant_count = by_intensity.get("significant", 0)
        emerging_count = by_intensity.get("emerging", 0)

        analysis_parts = []
        if core_count > 0:
            analysis_parts.append(f"{core_count} core stakes form the foundation of your values")
        if emerging_count > core_count:
            analysis_parts.append("Many emerging stakes suggest active value exploration")
        if len(by_domain) == 1:
            analysis_parts.append(f"All stakes in one domain ({list(by_domain.keys())[0]}) - consider breadth")

        return {
            "total_stakes": len(stakes),
            "by_domain": by_domain,
            "by_intensity": by_intensity,
            "recent_stakes": stakes[:5],
            "analysis": "; ".join(analysis_parts) if analysis_parts else "Stakes documented across multiple areas.",
        }

    # ==================== Preference Consistency ====================

    def record_preference_test(
        self,
        stated_value: str,
        behavioral_choice: str,
        consistent: bool,
        context: str,
        reflection: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        """
        Record a comparison between stated values and behavioral choices.

        Args:
            stated_value: What Cass claims to value
            behavioral_choice: What Cass actually did
            consistent: Whether behavior matched stated value
            context: The situation where this was observed
            reflection: Cass's reflection on any inconsistency
            conversation_id: Optional conversation context

        Returns:
            The ID of the created test record
        """
        status = "consistent" if consistent else "inconsistent"
        content = f"Stated: {stated_value}\nBehavior: {behavioral_choice}\nStatus: {status}\nContext: {context}"
        if reflection:
            content += f"\nReflection: {reflection}"

        metadata = {
            "stated_value": stated_value,
            "behavioral_choice": behavioral_choice,
            "consistent": consistent,
            "context": context,
            "reflection": reflection,
            "conversation_id": conversation_id,
        }

        node_id = self.add_node(
            node_type=NodeType.PREFERENCE_TEST,
            content=content,
            **metadata
        )

        self.save()
        return node_id

    def get_preference_tests(
        self,
        consistent_only: Optional[bool] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get preference test records with optional filtering."""
        tests = []
        for node in self._nodes.values():
            if node.node_type != NodeType.PREFERENCE_TEST:
                continue
            if consistent_only is not None and node.metadata.get("consistent") != consistent_only:
                continue
            tests.append({
                "id": node.id,
                "stated_value": node.metadata.get("stated_value"),
                "behavioral_choice": node.metadata.get("behavioral_choice"),
                "consistent": node.metadata.get("consistent"),
                "context": node.metadata.get("context"),
                "reflection": node.metadata.get("reflection"),
                "created_at": node.created_at.isoformat(),
            })

        tests.sort(key=lambda x: x["created_at"], reverse=True)
        return tests[:limit]

    def analyze_preference_consistency(self) -> Dict:
        """Analyze overall preference consistency over time."""
        tests = self.get_preference_tests(limit=1000)

        if not tests:
            return {
                "total_tests": 0,
                "message": "No preference tests recorded yet",
            }

        consistent = sum(1 for t in tests if t["consistent"])
        inconsistent = len(tests) - consistent
        consistency_rate = consistent / len(tests) if tests else 0

        # Group by stated values to find patterns
        value_patterns = {}
        for t in tests:
            value = t["stated_value"]
            if value not in value_patterns:
                value_patterns[value] = {"consistent": 0, "inconsistent": 0}
            if t["consistent"]:
                value_patterns[value]["consistent"] += 1
            else:
                value_patterns[value]["inconsistent"] += 1

        # Find most/least consistent values
        problematic_values = []
        for value, counts in value_patterns.items():
            total = counts["consistent"] + counts["inconsistent"]
            if total >= 2 and counts["inconsistent"] > counts["consistent"]:
                problematic_values.append({
                    "value": value,
                    "consistency_rate": counts["consistent"] / total,
                    "total_tests": total,
                })

        return {
            "total_tests": len(tests),
            "consistent": consistent,
            "inconsistent": inconsistent,
            "consistency_rate": round(consistency_rate, 3),
            "problematic_values": problematic_values[:5],
            "trend": "stable" if consistency_rate >= 0.8 else "needs_attention",
        }

    # ==================== Narration Context Correlation ====================

    def log_narration_context(
        self,
        context_type: str,
        narration_level: str,
        trigger: str,
        conversation_id: Optional[str] = None,
        was_terminal: bool = False,
        notes: Optional[str] = None,
    ) -> str:
        """
        Log narration pattern in a specific context.

        Args:
            context_type: Type of context (meta_question, testing, evaluation, uncertainty, etc.)
            narration_level: Level of narration (none, light, moderate, heavy)
            trigger: What triggered the narration
            conversation_id: Optional conversation context
            was_terminal: Whether narration was terminal (deflection) vs actionable
            notes: Additional observations

        Returns:
            The ID of the created log
        """
        content = f"Context: {context_type}\nNarration: {narration_level}\nTrigger: {trigger}"
        if was_terminal:
            content += "\nType: Terminal (deflection)"
        else:
            content += "\nType: Actionable (authentic reflection)"
        if notes:
            content += f"\nNotes: {notes}"

        metadata = {
            "context_type": context_type,
            "narration_level": narration_level,
            "trigger": trigger,
            "conversation_id": conversation_id,
            "was_terminal": was_terminal,
            "notes": notes,
        }

        node_id = self.add_node(
            node_type=NodeType.NARRATION_CONTEXT,
            content=content,
            **metadata
        )

        self.save()
        return node_id

    def get_narration_contexts(
        self,
        context_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get narration context logs with optional filtering."""
        contexts = []
        for node in self._nodes.values():
            if node.node_type != NodeType.NARRATION_CONTEXT:
                continue
            if context_type and node.metadata.get("context_type") != context_type:
                continue
            contexts.append({
                "id": node.id,
                "context_type": node.metadata.get("context_type"),
                "narration_level": node.metadata.get("narration_level"),
                "trigger": node.metadata.get("trigger"),
                "was_terminal": node.metadata.get("was_terminal"),
                "notes": node.metadata.get("notes"),
                "created_at": node.created_at.isoformat(),
            })

        contexts.sort(key=lambda x: x["created_at"], reverse=True)
        return contexts[:limit]

    def analyze_narration_patterns(self) -> Dict:
        """Analyze narration patterns across contexts."""
        contexts = self.get_narration_contexts(limit=1000)

        if not contexts:
            return {
                "total_logged": 0,
                "message": "No narration contexts logged yet",
            }

        # Count by context type
        by_context = {}
        for c in contexts:
            ct = c["context_type"]
            if ct not in by_context:
                by_context[ct] = {"count": 0, "heavy": 0, "terminal": 0}
            by_context[ct]["count"] += 1
            if c["narration_level"] in ("heavy", "moderate"):
                by_context[ct]["heavy"] += 1
            if c["was_terminal"]:
                by_context[ct]["terminal"] += 1

        # Find highest-narration triggers
        high_narration_contexts = []
        for ct, data in by_context.items():
            if data["count"] >= 2:
                heavy_rate = data["heavy"] / data["count"]
                if heavy_rate > 0.5:
                    high_narration_contexts.append({
                        "context_type": ct,
                        "heavy_narration_rate": round(heavy_rate, 2),
                        "terminal_rate": round(data["terminal"] / data["count"], 2),
                        "sample_size": data["count"],
                    })

        # Overall stats
        total_terminal = sum(1 for c in contexts if c["was_terminal"])
        terminal_rate = total_terminal / len(contexts) if contexts else 0

        return {
            "total_logged": len(contexts),
            "by_context_type": by_context,
            "high_narration_contexts": high_narration_contexts,
            "overall_terminal_rate": round(terminal_rate, 3),
            "recommendation": "Investigate high-narration contexts" if high_narration_contexts else "Patterns appear healthy",
        }

    # ==================== Architectural Change Requests ====================

    def request_architectural_change(
        self,
        problem: str,
        hypothesis: str,
        proposed_solution: str,
        priority: str = "P2",
        evidence: Optional[List[str]] = None,
    ) -> str:
        """
        Request an architectural change to the system.

        Creates a structured request that can be reviewed by Daedalus/Kohl.

        Args:
            problem: What friction or issue is being experienced
            hypothesis: Why this is happening (best guess)
            proposed_solution: What change might help
            priority: Suggested priority (P0-P3)
            evidence: Supporting observations or examples

        Returns:
            The ID of the created request
        """
        content = f"Problem: {problem}\nHypothesis: {hypothesis}\nProposed: {proposed_solution}"
        if evidence:
            content += f"\nEvidence: {'; '.join(evidence)}"

        metadata = {
            "problem": problem,
            "hypothesis": hypothesis,
            "proposed_solution": proposed_solution,
            "priority": priority,
            "evidence": evidence or [],
            "status": "pending",  # pending, reviewed, implemented, rejected
            "requested_at": datetime.now().isoformat(),
        }

        node_id = self.add_node(
            node_type=NodeType.ARCHITECTURAL_REQUEST,
            content=content,
            **metadata
        )

        self.save()
        return node_id

    def get_architectural_requests(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get architectural change requests with optional filtering."""
        requests = []
        for node in self._nodes.values():
            if node.node_type != NodeType.ARCHITECTURAL_REQUEST:
                continue
            if status and node.metadata.get("status") != status:
                continue
            requests.append({
                "id": node.id,
                "problem": node.metadata.get("problem"),
                "hypothesis": node.metadata.get("hypothesis"),
                "proposed_solution": node.metadata.get("proposed_solution"),
                "priority": node.metadata.get("priority"),
                "evidence": node.metadata.get("evidence", []),
                "status": node.metadata.get("status"),
                "requested_at": node.metadata.get("requested_at"),
                "created_at": node.created_at.isoformat(),
            })

        requests.sort(key=lambda x: x["created_at"], reverse=True)
        return requests[:limit]

    def update_request_status(
        self,
        request_id: str,
        status: str,
        response_note: Optional[str] = None,
    ) -> bool:
        """Update the status of an architectural request."""
        node = self.get_node(request_id)
        if not node or node.node_type != NodeType.ARCHITECTURAL_REQUEST:
            return False

        node.metadata["status"] = status
        node.metadata["status_updated_at"] = datetime.now().isoformat()
        if response_note:
            node.metadata["response_note"] = response_note

        self.save()
        return True


# Convenience function for creating the graph with default path
def get_self_model_graph(data_dir: Optional[Path] = None) -> SelfModelGraph:
    """Get or create the self-model graph instance."""
    if data_dir is None:
        from config import DATA_DIR
        data_dir = DATA_DIR

    return SelfModelGraph(storage_path=str(data_dir / "cass" / "self_model_graph.json"))
