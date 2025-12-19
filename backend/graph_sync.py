"""
Graph sync engine for SelfModelGraph.
Handles syncing observations, milestones, and marks into the graph.
Extracted from SelfModelGraph for modularity.
"""
from datetime import datetime
from typing import Optional, List, Any, Protocol


class GraphInterface(Protocol):
    """Protocol defining the graph interface needed by SyncEngine."""
    def get_node(self, node_id: str) -> Any: ...
    def update_node(self, node_id: str, **updates) -> bool: ...
    def add_node(self, node_type: Any, content: str, **kwargs) -> str: ...
    def add_edge(self, source_id: str, target_id: str, edge_type: Any, **kwargs) -> bool: ...
    def suggest_edges_for_node(self, node_id: str, create_edges: bool = True, max_edges: int = 5) -> List: ...
    def save(self) -> None: ...
    @property
    def _nodes(self) -> dict: ...


class SyncEngine:
    """
    Handles syncing data into the self-model graph.

    Extracted from SelfModelGraph to separate sync concerns from
    graph structure and traversal.
    """

    def __init__(self, graph: GraphInterface, node_type_enum: Any, edge_type_enum: Any):
        """
        Args:
            graph: The graph instance to sync to
            node_type_enum: NodeType enum class
            edge_type_enum: EdgeType enum class
        """
        self._graph = graph
        self.NodeType = node_type_enum
        self.EdgeType = edge_type_enum

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
        Sync a self-observation into the graph.

        Called when observations are created/updated in SelfManager.

        Returns:
            Node ID of the created/updated node
        """
        # Parse timestamp
        try:
            created_at = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            created_at = datetime.now()

        # Check if node already exists
        existing = self._graph.get_node(observation_id[:8])

        if existing:
            # Update existing node
            self._graph.update_node(
                observation_id[:8],
                content=observation_text,
                category=category,
                confidence=confidence,
                **kwargs
            )
            node_id = observation_id[:8]
        else:
            # Create new node
            node_id = self._graph.add_node(
                node_type=self.NodeType.OBSERVATION,
                content=observation_text,
                node_id=observation_id[:8],
                created_at=created_at,
                category=category,
                confidence=confidence,
                original_id=observation_id,
                **kwargs
            )

        # Create edge to source conversation if available
        if source_conversation_id:
            conv_node_id = source_conversation_id[:8]
            if conv_node_id in self._graph._nodes:
                self._graph.add_edge(
                    node_id,
                    conv_node_id,
                    self.EdgeType.EMERGED_FROM,
                    extraction_type="observation"
                )

        # Create supersedes edge if applicable
        if supersedes:
            old_node_id = supersedes[:8]
            if old_node_id in self._graph._nodes:
                self._graph.add_edge(
                    node_id,
                    old_node_id,
                    self.EdgeType.SUPERSEDES,
                    reason="version_update"
                )

        # Auto-suggest semantic edges to related nodes
        self._graph.suggest_edges_for_node(node_id, create_edges=True, max_edges=3)

        self._graph.save()
        return node_id

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
        Sync a developmental milestone into the graph.

        Returns:
            Node ID of the created/updated node
        """
        try:
            created_at = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            created_at = datetime.now()

        content = f"{title}: {description}"

        existing = self._graph.get_node(milestone_id[:8])

        if existing:
            self._graph.update_node(
                milestone_id[:8],
                content=content,
                title=title,
                description=description,
                milestone_type=milestone_type,
                category=category,
                significance=significance,
                **kwargs
            )
            node_id = milestone_id[:8]
        else:
            node_id = self._graph.add_node(
                node_type=self.NodeType.MILESTONE,
                content=content,
                node_id=milestone_id[:8],
                created_at=created_at,
                title=title,
                milestone_type=milestone_type,
                category=category,
                significance=significance,
                original_id=milestone_id,
                **kwargs
            )

        # Create edges to evidence
        if evidence_ids:
            for eid in evidence_ids:
                evidence_node_id = eid[:8]
                if evidence_node_id in self._graph._nodes:
                    self._graph.add_edge(
                        node_id,
                        evidence_node_id,
                        self.EdgeType.EVIDENCED_BY
                    )

        # Auto-suggest semantic edges to related nodes
        self._graph.suggest_edges_for_node(node_id, create_edges=True, max_edges=3)

        self._graph.save()
        return node_id

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
        Sync a recognition-in-flow mark into the graph.

        Returns:
            Node ID of the created/updated node
        """
        try:
            created_at = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).replace(tzinfo=None) if timestamp else datetime.now()
        except ValueError:
            created_at = datetime.now()

        # Build content
        if description:
            content = f"[{category}] {description}"
        else:
            content = f"[{category}] {context_window[:100]}..."

        existing = self._graph.get_node(mark_id[:8])

        if existing:
            self._graph.update_node(
                mark_id[:8],
                content=content,
                category=category,
                description=description,
                **kwargs
            )
            node_id = mark_id[:8]
        else:
            node_id = self._graph.add_node(
                node_type=self.NodeType.MARK,
                content=content,
                node_id=mark_id[:8],
                created_at=created_at,
                category=category,
                description=description,
                context_window=context_window,
                conversation_id=conversation_id,
                original_id=mark_id,
                **kwargs
            )

        # Create edge to source conversation if available
        if conversation_id:
            conv_node_id = conversation_id[:8]
            if conv_node_id in self._graph._nodes:
                self._graph.add_edge(
                    node_id,
                    conv_node_id,
                    self.EdgeType.EMERGED_FROM,
                    extraction_type="recognition_in_flow"
                )

        # Auto-suggest semantic edges to related nodes
        self._graph.suggest_edges_for_node(node_id, create_edges=True, max_edges=3)

        self._graph.save()
        return node_id
