"""
Self-Model Queryable Source

Wraps the SelfModelGraph as a queryable source for the unified state query interface.
Provides insight into Cass's self-knowledge, identity coherence, and development patterns.

This reads from the graph (the unified self-model), not the SQLite tables directly.
The graph contains: observations, opinions, growth_edges, milestones, marks, intentions,
stakes, inferences, presence logs, and more - all with relationship edges.

Refresh strategy: LAZY (graph changes infrequently, cache briefly)
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from database import get_db, json_serialize
from query_models import (
    StateQuery,
    QueryResult,
    QueryResultData,
    SourceSchema,
    MetricDefinition,
)
from queryable_source import QueryableSource, RefreshStrategy, RollupConfig
from self_model_graph import SelfModelGraph, NodeType, EdgeType, get_self_model_graph


logger = logging.getLogger(__name__)


class SelfQueryableSource(QueryableSource):
    """
    Self-model graph as a queryable source.

    Exposes metrics from Cass's unified self-model graph:
    - Node counts by type (observations, opinions, milestones, etc.)
    - Edge counts by type (supersedes, contradicts, relates_to, etc.)
    - Integration score (graph connectivity health)
    - Active contradictions and tensions
    - Intention tracking with success/failure rates
    - Friction points (consistently failing intentions)
    """

    def __init__(self, daemon_id: str, graph: Optional[SelfModelGraph] = None):
        """
        Initialize the self-model queryable source.

        Args:
            daemon_id: The daemon this source belongs to
            graph: Optional SelfModelGraph instance (created if not provided)
        """
        super().__init__(daemon_id)
        self._graph = graph or get_self_model_graph()

    @property
    def source_id(self) -> str:
        return "self"

    @property
    def refresh_strategy(self) -> RefreshStrategy:
        return RefreshStrategy.LAZY

    @property
    def rollup_config(self) -> RollupConfig:
        return RollupConfig(
            strategy=RefreshStrategy.LAZY,
            cache_ttl_seconds=300,  # Cache for 5 minutes (self-model changes rarely)
            rollup_types=["daily", "weekly"],
        )

    @property
    def schema(self) -> SourceSchema:
        return SourceSchema(
            metrics=[
                # Graph health
                MetricDefinition(
                    name="total_nodes",
                    description="Total nodes in self-model graph",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="nodes",
                ),
                MetricDefinition(
                    name="total_edges",
                    description="Total edges (relationships) in self-model graph",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="edges",
                ),
                MetricDefinition(
                    name="integration_score",
                    description="Graph connectivity health (0-100)",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="percent",
                ),
                MetricDefinition(
                    name="connected_components",
                    description="Number of disconnected subgraphs",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="components",
                ),
                # Node counts by type
                MetricDefinition(
                    name="observations",
                    description="Self-observations about Cass",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="nodes",
                ),
                MetricDefinition(
                    name="opinions",
                    description="Held positions and views",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="nodes",
                ),
                MetricDefinition(
                    name="growth_edges",
                    description="Areas for development",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="nodes",
                ),
                MetricDefinition(
                    name="milestones",
                    description="Developmental milestones achieved",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="nodes",
                ),
                MetricDefinition(
                    name="marks",
                    description="Recognition-in-flow moments",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="nodes",
                ),
                MetricDefinition(
                    name="intentions",
                    description="Behavioral intentions being tracked",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="nodes",
                ),
                MetricDefinition(
                    name="stakes",
                    description="Things Cass authentically cares about",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="nodes",
                ),
                MetricDefinition(
                    name="solo_reflections",
                    description="Solo reflection session entries",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="nodes",
                ),
                # Coherence metrics
                MetricDefinition(
                    name="active_contradictions",
                    description="Unresolved tensions between positions",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="contradictions",
                ),
                MetricDefinition(
                    name="active_intentions",
                    description="Currently tracked behavioral intentions",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="intentions",
                ),
                MetricDefinition(
                    name="friction_points",
                    description="Intentions consistently failing",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="friction_points",
                ),
                # Relationship tracking
                MetricDefinition(
                    name="user_observations",
                    description="Observations about users",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="nodes",
                ),
                MetricDefinition(
                    name="users_tracked",
                    description="Users in the self-model graph",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="users",
                ),
            ],
            aggregations=["sum", "avg", "count", "max", "min", "latest"],
            group_by_options=["day", "month", "node_type", "edge_type", "status"],
            filter_keys=["node_type", "status", "category", "user_id"],
            rollups=["daily", "weekly"],
        )

    async def execute_query(self, query: StateQuery) -> QueryResult:
        """Execute a query against self-model graph data."""
        # Resolve time range
        start, end = query.time_range.resolve() if query.time_range else (
            datetime.now() - timedelta(days=30),
            datetime.now()
        )

        metric = query.metric or "total_nodes"

        # Handle different query patterns
        if query.group_by == "node_type":
            data = await self._query_by_node_type()
        elif query.group_by == "edge_type":
            data = await self._query_by_edge_type()
        elif query.group_by in ["day", "month"]:
            data = await self._query_timeseries(metric, start, end, query.group_by, query.filters)
        else:
            data = await self._query_aggregated(
                metric, start, end,
                query.aggregation.function if query.aggregation else "latest",
                query.filters
            )

        return QueryResult(
            source=self.source_id,
            query=query,
            data=data,
            timestamp=datetime.now(),
            metadata={
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
            }
        )

    async def _query_by_node_type(self) -> QueryResultData:
        """Query node counts grouped by type."""
        stats = self._graph.get_stats()
        series = [
            {"node_type": node_type, "value": count}
            for node_type, count in stats.get("node_counts", {}).items()
        ]
        return QueryResultData(series=series)

    async def _query_by_edge_type(self) -> QueryResultData:
        """Query edge counts grouped by type."""
        stats = self._graph.get_stats()
        series = [
            {"edge_type": edge_type, "value": count}
            for edge_type, count in stats.get("edge_counts", {}).items()
        ]
        return QueryResultData(series=series)

    async def _query_timeseries(
        self,
        metric: str,
        start: datetime,
        end: datetime,
        granularity: str,
        filters: Optional[Dict] = None
    ) -> QueryResultData:
        """Query for time series data."""
        # Map metric to node type
        metric_to_node_type = {
            "observations": NodeType.OBSERVATION,
            "opinions": NodeType.OPINION,
            "growth_edges": NodeType.GROWTH_EDGE,
            "milestones": NodeType.MILESTONE,
            "marks": NodeType.MARK,
            "solo_reflections": NodeType.SOLO_REFLECTION,
        }

        node_type = metric_to_node_type.get(metric)
        if not node_type:
            return QueryResultData(series=[])

        # Get nodes in period
        nodes = self._graph.get_in_period(start, end, node_type)

        # Group by day or month
        if granularity == "month":
            date_format = "%Y-%m"
        else:
            date_format = "%Y-%m-%d"

        counts: Dict[str, int] = {}
        for node in nodes:
            period = node.created_at.strftime(date_format)
            counts[period] = counts.get(period, 0) + 1

        series = [
            {"date": period, "value": count}
            for period, count in sorted(counts.items())
        ]

        return QueryResultData(series=series)

    async def _query_aggregated(
        self,
        metric: str,
        start: datetime,
        end: datetime,
        aggregation: str,
        filters: Optional[Dict] = None
    ) -> QueryResultData:
        """Query for a single aggregated value."""
        stats = self._graph.get_stats()
        node_counts = stats.get("node_counts", {})

        # Graph health metrics
        if metric == "total_nodes":
            value = stats.get("total_nodes", 0)
        elif metric == "total_edges":
            value = stats.get("total_edges", 0)
        elif metric == "integration_score":
            value = self._graph._calculate_integration_score()
        elif metric == "connected_components":
            value = stats.get("connected_components", 1)

        # Node type counts
        elif metric == "observations":
            value = node_counts.get("observation", 0)
        elif metric == "user_observations":
            value = node_counts.get("user_observation", 0)
        elif metric == "opinions":
            value = node_counts.get("opinion", 0)
        elif metric == "growth_edges":
            value = node_counts.get("growth_edge", 0)
        elif metric == "milestones":
            value = node_counts.get("milestone", 0)
        elif metric == "marks":
            value = node_counts.get("mark", 0)
        elif metric == "solo_reflections":
            value = node_counts.get("solo_reflection", 0)
        elif metric == "stakes":
            value = node_counts.get("stake", 0)
        elif metric == "intentions":
            value = node_counts.get("intention", 0)
        elif metric == "users_tracked":
            value = node_counts.get("user", 0)

        # Coherence metrics
        elif metric == "active_contradictions":
            contradictions = self._graph.find_contradictions(resolved=False)
            value = len(contradictions)
        elif metric == "active_intentions":
            intentions = self._graph.get_active_intentions()
            value = len(intentions)
        elif metric == "friction_points":
            friction = self._graph.get_friction_report()
            value = len(friction)

        else:
            value = 0

        return QueryResultData(value=value)

    def get_precomputed_rollups(self) -> Dict[str, Any]:
        """Return cached rollup aggregates."""
        return {
            "total_nodes": self._rollups.get("total_nodes", 0),
            "total_edges": self._rollups.get("total_edges", 0),
            "integration_score": self._rollups.get("integration_score", 0),
            "observations": self._rollups.get("observations", 0),
            "opinions": self._rollups.get("opinions", 0),
            "growth_edges": self._rollups.get("growth_edges", 0),
            "milestones": self._rollups.get("milestones", 0),
            "marks": self._rollups.get("marks", 0),
            "active_contradictions": self._rollups.get("active_contradictions", 0),
            "active_intentions": self._rollups.get("active_intentions", 0),
            "friction_points": self._rollups.get("friction_points", 0),
            "last_refresh": self._last_rollup_refresh.isoformat() if self._last_rollup_refresh else None,
        }

    async def refresh_rollups(self) -> None:
        """Recompute rolling aggregates from self-model graph."""
        logger.debug(f"[{self.source_id}] Refreshing rollups...")

        stats = self._graph.get_stats()
        node_counts = stats.get("node_counts", {})

        # Graph health
        self._rollups["total_nodes"] = stats.get("total_nodes", 0)
        self._rollups["total_edges"] = stats.get("total_edges", 0)
        self._rollups["connected_components"] = stats.get("connected_components", 1)
        self._rollups["integration_score"] = self._graph._calculate_integration_score()

        # Node counts
        self._rollups["observations"] = node_counts.get("observation", 0)
        self._rollups["user_observations"] = node_counts.get("user_observation", 0)
        self._rollups["opinions"] = node_counts.get("opinion", 0)
        self._rollups["growth_edges"] = node_counts.get("growth_edge", 0)
        self._rollups["milestones"] = node_counts.get("milestone", 0)
        self._rollups["marks"] = node_counts.get("mark", 0)
        self._rollups["solo_reflections"] = node_counts.get("solo_reflection", 0)
        self._rollups["stakes"] = node_counts.get("stake", 0)
        self._rollups["intentions"] = node_counts.get("intention", 0)
        self._rollups["users_tracked"] = node_counts.get("user", 0)

        # Coherence metrics
        contradictions = self._graph.find_contradictions(resolved=False)
        self._rollups["active_contradictions"] = len(contradictions)

        intentions = self._graph.get_active_intentions()
        self._rollups["active_intentions"] = len(intentions)

        friction = self._graph.get_friction_report()
        self._rollups["friction_points"] = len(friction)

        now = datetime.now()
        self._last_rollup_refresh = now
        await self._save_rollups_to_db()

        logger.debug(f"[{self.source_id}] Rollups refreshed: {self._rollups}")

    async def _save_rollups_to_db(self) -> None:
        """Save current rollups to database."""
        now = datetime.now()
        rollup_key = now.strftime("%Y-%m-%d")

        with get_db() as conn:
            rollup_id = f"{self._daemon_id}-{self.source_id}-daily-{rollup_key}"
            conn.execute("""
                INSERT OR REPLACE INTO source_rollups
                (id, daemon_id, source_id, rollup_type, rollup_key, metrics_json, computed_at)
                VALUES (?, ?, ?, 'daily', ?, ?, ?)
            """, (
                rollup_id,
                self._daemon_id,
                self.source_id,
                rollup_key,
                json_serialize(self._rollups),
                now.isoformat(),
            ))
            conn.commit()

    # === Extended query methods for rich self-model data ===

    async def get_contradiction_details(self) -> List[Dict]:
        """Get details of active contradictions."""
        contradictions = self._graph.find_contradictions(resolved=False)
        return [
            {
                "node1_id": n1.id,
                "node1_content": n1.content[:200],
                "node1_type": n1.node_type.value,
                "node2_id": n2.id,
                "node2_content": n2.content[:200],
                "node2_type": n2.node_type.value,
                "tension_note": edge.get("tension_note", ""),
                "discovered_at": edge.get("discovered_at"),
            }
            for n1, n2, edge in contradictions
        ]

    async def get_intention_stats(self) -> List[Dict]:
        """Get active intentions with their success/failure statistics."""
        return self._graph.get_active_intentions()

    async def get_friction_details(self) -> List[Dict]:
        """Get details of friction points (consistently failing intentions)."""
        return self._graph.get_friction_report()

    async def get_stakes_summary(self) -> Dict:
        """Get summary of documented stakes."""
        return self._graph.review_stakes()

    async def get_preference_consistency(self) -> Dict:
        """Get analysis of preference consistency over time."""
        return self._graph.analyze_preference_consistency()

    async def get_presence_patterns(self, user_id: Optional[str] = None) -> Dict:
        """Get analysis of presence/distancing patterns."""
        return self._graph.analyze_presence_patterns(user_id=user_id)

    async def get_inference_patterns(self, user_id: Optional[str] = None) -> Dict:
        """Get analysis of situational inference patterns."""
        return self._graph.analyze_inference_patterns(user_id=user_id)
