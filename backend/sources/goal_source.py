"""
Unified Goals Queryable Source

Wraps UnifiedGoalManager as a queryable source for the unified state query interface.
Provides access to goal metrics: counts by status, type, tier, completion rates, etc.

Refresh strategy: LAZY (compute on query - data changes with goal updates)
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from database import get_db, json_serialize, json_deserialize
from query_models import (
    StateQuery,
    QueryResult,
    QueryResultData,
    SourceSchema,
    MetricDefinition,
)
from queryable_source import QueryableSource, RefreshStrategy, RollupConfig
from unified_goals import (
    UnifiedGoalManager,
    GoalType,
    GoalStatus,
    AutonomyTier,
    GapType,
    GapStatus,
)


logger = logging.getLogger(__name__)


class GoalQueryableSource(QueryableSource):
    """
    Unified goals as a queryable source.

    Wraps UnifiedGoalManager and exposes metrics through the unified query interface.
    Uses LAZY refresh since goal data changes with operations.
    """

    def __init__(self, daemon_id: str, manager: Optional[UnifiedGoalManager] = None):
        """
        Initialize the goal queryable source.

        Args:
            daemon_id: The daemon this source belongs to
            manager: Optional UnifiedGoalManager instance (created if not provided)
        """
        super().__init__(daemon_id)
        self._manager = manager or UnifiedGoalManager(daemon_id)

    @property
    def source_id(self) -> str:
        return "goals"

    @property
    def refresh_strategy(self) -> RefreshStrategy:
        return RefreshStrategy.LAZY

    @property
    def rollup_config(self) -> RollupConfig:
        return RollupConfig(
            strategy=RefreshStrategy.LAZY,
            cache_ttl_seconds=30,  # Cache rollups for 30 seconds
            rollup_types=["daily", "weekly"],
        )

    @property
    def schema(self) -> SourceSchema:
        return SourceSchema(
            metrics=[
                MetricDefinition(
                    name="total_goals",
                    description="Total number of goals",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="goals",
                ),
                MetricDefinition(
                    name="active_goals",
                    description="Currently active goals",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="goals",
                ),
                MetricDefinition(
                    name="blocked_goals",
                    description="Goals that are blocked",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="goals",
                ),
                MetricDefinition(
                    name="pending_approval",
                    description="Goals awaiting approval",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="goals",
                ),
                MetricDefinition(
                    name="completed_goals",
                    description="Completed goals",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="goals",
                ),
                MetricDefinition(
                    name="open_capability_gaps",
                    description="Unresolved capability gaps",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="gaps",
                ),
                MetricDefinition(
                    name="blocking_gaps",
                    description="Capability gaps blocking progress",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="gaps",
                ),
                MetricDefinition(
                    name="average_alignment",
                    description="Average alignment score with user goals",
                    data_type="float",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="score",
                ),
                MetricDefinition(
                    name="completion_rate",
                    description="Percentage of goals completed vs total",
                    data_type="float",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="percentage",
                ),
                MetricDefinition(
                    name="abandoned_rate",
                    description="Percentage of goals abandoned vs total",
                    data_type="float",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="percentage",
                ),
            ],
            aggregations=["sum", "count", "avg", "latest"],
            group_by_options=["day", "week", "goal_type", "status", "autonomy_tier", "created_by"],
            filter_keys=["goal_type", "status", "autonomy_tier", "created_by", "assigned_to", "project_id"],
            rollups=["daily", "weekly"],
        )

    async def execute_query(self, query: StateQuery) -> QueryResult:
        """
        Execute a query against goal data.

        Args:
            query: The StateQuery to execute

        Returns:
            QueryResult with goal metrics
        """
        metric = query.metric
        filters = query.filters or {}
        group_by = query.group_by
        time_range = query.time_range

        # Get stats from manager
        stats = self._manager.get_stats()

        # Build result based on requested metric
        if metric == "total_goals":
            value = stats.get("total", 0)
        elif metric == "active_goals":
            value = stats.get("by_status", {}).get(GoalStatus.ACTIVE.value, 0)
        elif metric == "blocked_goals":
            value = stats.get("by_status", {}).get(GoalStatus.BLOCKED.value, 0)
        elif metric == "pending_approval":
            value = stats.get("by_status", {}).get(GoalStatus.PROPOSED.value, 0)
        elif metric == "completed_goals":
            value = stats.get("by_status", {}).get(GoalStatus.COMPLETED.value, 0)
        elif metric == "open_capability_gaps":
            value = stats.get("open_capability_gaps", 0)
        elif metric == "blocking_gaps":
            # Count gaps with blocking urgency
            gaps = self._manager.get_blocking_gaps()
            value = len([g for g in gaps if g.urgency == "blocking"])
        elif metric == "average_alignment":
            value = stats.get("average_alignment", 1.0)
        elif metric == "completion_rate":
            total = stats.get("total", 0)
            completed = stats.get("by_status", {}).get(GoalStatus.COMPLETED.value, 0)
            value = (completed / total * 100) if total > 0 else 0.0
        elif metric == "abandoned_rate":
            total = stats.get("total", 0)
            abandoned = stats.get("by_status", {}).get(GoalStatus.ABANDONED.value, 0)
            value = (abandoned / total * 100) if total > 0 else 0.0
        elif metric == "by_status":
            value = stats.get("by_status", {})
        elif metric == "by_type":
            value = stats.get("by_type", {})
        elif metric == "by_tier":
            value = stats.get("by_tier", {})
        elif metric == "all":
            value = stats
        else:
            # Unknown metric - return full stats
            value = stats

        # Handle group_by
        if group_by:
            if group_by == "status":
                grouped = stats.get("by_status", {})
            elif group_by == "goal_type":
                grouped = stats.get("by_type", {})
            elif group_by == "autonomy_tier":
                grouped = stats.get("by_tier", {})
            else:
                grouped = {"ungrouped": value}
            value = grouped

        # Build result
        data = QueryResultData(
            metric=metric or "all",
            value=value,
            unit="goals" if isinstance(value, (int, float)) else None,
            breakdown=stats.get("by_status", {}) if metric in ["total_goals", "all"] else None,
        )

        return QueryResult(
            source=self.source_id,
            query=query,
            data=data,
            metadata={
                "total_goals": stats.get("total", 0),
                "by_status": stats.get("by_status", {}),
                "by_type": stats.get("by_type", {}),
                "by_tier": stats.get("by_tier", {}),
            },
            timestamp=datetime.now(),
        )

    async def compute_rollups(self, rollup_type: str) -> Dict[str, Any]:
        """
        Compute rollup aggregations for goals.

        Args:
            rollup_type: "daily" or "weekly"

        Returns:
            Dict with rollup data
        """
        stats = self._manager.get_stats()

        now = datetime.now()
        if rollup_type == "daily":
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:  # weekly
            days_since_monday = now.weekday()
            period_start = (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        # Get goals for the period
        goals = self._manager.list_goals()
        period_goals = [
            g for g in goals
            if g.created_at and datetime.fromisoformat(g.created_at) >= period_start
        ]

        completed_in_period = [
            g for g in goals
            if g.completed_at and datetime.fromisoformat(g.completed_at) >= period_start
        ]

        rollup = {
            "period_type": rollup_type,
            "period_start": period_start.isoformat(),
            "computed_at": now.isoformat(),
            "created_this_period": len(period_goals),
            "completed_this_period": len(completed_in_period),
            "total_active": stats.get("by_status", {}).get(GoalStatus.ACTIVE.value, 0),
            "total_blocked": stats.get("by_status", {}).get(GoalStatus.BLOCKED.value, 0),
            "pending_approval": stats.get("by_status", {}).get(GoalStatus.PROPOSED.value, 0),
            "open_gaps": stats.get("open_capability_gaps", 0),
            "average_alignment": stats.get("average_alignment", 1.0),
        }

        return rollup

    async def ensure_rollups_fresh(self) -> None:
        """Ensure rollups are computed (for LAZY strategy)."""
        # For goals, we compute on-demand since data changes frequently
        # Check if rollups need refresh
        if self._rollups is None or self._last_rollup_refresh is None:
            await self.refresh_rollups()
        else:
            elapsed = (datetime.now() - self._last_rollup_refresh).total_seconds()
            if elapsed > self.rollup_config.cache_ttl_seconds:
                await self.refresh_rollups()

    def get_precomputed_rollups(self) -> Dict[str, Any]:
        """Return currently cached rollup aggregates."""
        if self._rollups is None:
            return {}
        return self._rollups

    async def refresh_rollups(self) -> None:
        """Recompute rolling aggregates."""
        stats = self._manager.get_stats()

        self._rollups = {
            "total_goals": stats.get("total", 0),
            "active_goals": stats.get("by_status", {}).get(GoalStatus.ACTIVE.value, 0),
            "blocked_goals": stats.get("by_status", {}).get(GoalStatus.BLOCKED.value, 0),
            "pending_approval": stats.get("by_status", {}).get(GoalStatus.PROPOSED.value, 0),
            "completed_goals": stats.get("by_status", {}).get(GoalStatus.COMPLETED.value, 0),
            "open_capability_gaps": stats.get("open_capability_gaps", 0),
            "average_alignment": stats.get("average_alignment", 1.0),
            "by_status": stats.get("by_status", {}),
            "by_type": stats.get("by_type", {}),
            "by_tier": stats.get("by_tier", {}),
        }
        self._last_rollup_refresh = datetime.now()

    def get_current_summary(self) -> str:
        """Get a human-readable summary of current goal state."""
        stats = self._manager.get_stats()

        parts = []

        total = stats.get("total", 0)
        if total > 0:
            active = stats.get("by_status", {}).get(GoalStatus.ACTIVE.value, 0)
            pending = stats.get("by_status", {}).get(GoalStatus.PROPOSED.value, 0)
            blocked = stats.get("by_status", {}).get(GoalStatus.BLOCKED.value, 0)

            if active > 0:
                parts.append(f"{active} active goals")
            if pending > 0:
                parts.append(f"{pending} awaiting approval")
            if blocked > 0:
                parts.append(f"{blocked} blocked")

        gaps = stats.get("open_capability_gaps", 0)
        if gaps > 0:
            parts.append(f"{gaps} open capability gaps")

        alignment = stats.get("average_alignment", 1.0)
        if alignment < 0.9:
            parts.append(f"alignment: {alignment:.0%}")

        return "; ".join(parts) if parts else "No active goals"
