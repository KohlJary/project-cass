"""
Work Item Queryable Source

Wraps WorkItemManager as a queryable source for the unified state query interface.
Provides access to Cass's work planning metrics: counts by status, category, pending approval, etc.

Refresh strategy: LAZY (compute on query - data changes with work updates)
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from query_models import (
    StateQuery,
    QueryResult,
    QueryResultData,
    SourceSchema,
    MetricDefinition,
)
from queryable_source import QueryableSource, RefreshStrategy, RollupConfig
from work_planning import (
    WorkItemManager,
    WorkStatus,
    WorkPriority,
    ApprovalStatus,
)


logger = logging.getLogger(__name__)


class WorkItemQueryableSource(QueryableSource):
    """
    Work items as a queryable source.

    Wraps WorkItemManager and exposes work planning metrics through the unified query interface.
    Uses LAZY refresh since work data changes with operations.
    """

    def __init__(self, daemon_id: str, manager: Optional[WorkItemManager] = None):
        """
        Initialize the work item queryable source.

        Args:
            daemon_id: The daemon this source belongs to
            manager: Optional WorkItemManager instance (created if not provided)
        """
        super().__init__(daemon_id)
        self._manager = manager or WorkItemManager(daemon_id)

    @property
    def source_id(self) -> str:
        return "work"

    @property
    def refresh_strategy(self) -> RefreshStrategy:
        return RefreshStrategy.LAZY

    @property
    def rollup_config(self) -> RollupConfig:
        return RollupConfig(
            strategy=RefreshStrategy.LAZY,
            cache_ttl_seconds=30,
            rollup_types=["daily", "weekly"],
        )

    @property
    def schema(self) -> SourceSchema:
        return SourceSchema(
            metrics=[
                MetricDefinition(
                    name="all",
                    description="All work item metrics in one response",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="total_items",
                    description="Total number of work items",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="items",
                ),
                MetricDefinition(
                    name="by_status",
                    description="Work items grouped by status",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="by_category",
                    description="Work items grouped by category",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="ready_items",
                    description="Work items ready for execution",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="items",
                ),
                MetricDefinition(
                    name="running_items",
                    description="Work items currently running",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="items",
                ),
                MetricDefinition(
                    name="pending_approval",
                    description="Work items awaiting approval",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="items",
                ),
                MetricDefinition(
                    name="completed_items",
                    description="Completed work items",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="items",
                ),
                MetricDefinition(
                    name="estimated_pending_cost",
                    description="Estimated cost of pending work",
                    data_type="float",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="usd",
                ),
                MetricDefinition(
                    name="actual_completed_cost",
                    description="Actual cost of completed work",
                    data_type="float",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="usd",
                ),
                MetricDefinition(
                    name="completion_rate",
                    description="Percentage of work items completed vs total",
                    data_type="float",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="percentage",
                ),
            ],
            aggregations=["sum", "count", "avg", "latest"],
            group_by_options=["status", "category", "priority", "goal_id"],
            filter_keys=["status", "category", "priority", "goal_id", "requires_approval"],
            rollups=["daily", "weekly"],
        )

    async def execute_query(self, query: StateQuery) -> QueryResult:
        """
        Execute a query against work item data.

        Args:
            query: The StateQuery to execute

        Returns:
            QueryResult with work item metrics
        """
        metric = query.metric
        filters = query.filters or {}
        group_by = query.group_by

        # Get stats from manager
        stats = self._manager.get_stats()

        # Build result based on requested metric
        if metric == "total_items":
            value = stats.get("total", 0)
        elif metric == "by_status":
            value = stats.get("by_status", {})
        elif metric == "by_category":
            value = stats.get("by_category", {})
        elif metric == "ready_items":
            ready_items = self._manager.list_ready()
            value = len(ready_items)
        elif metric == "running_items":
            value = stats.get("by_status", {}).get(WorkStatus.RUNNING.value, 0)
        elif metric == "pending_approval":
            value = stats.get("pending_approval", 0)
        elif metric == "completed_items":
            value = stats.get("by_status", {}).get(WorkStatus.COMPLETED.value, 0)
        elif metric == "estimated_pending_cost":
            value = stats.get("estimated_pending_cost_usd", 0.0)
        elif metric == "actual_completed_cost":
            value = stats.get("actual_completed_cost_usd", 0.0)
        elif metric == "completion_rate":
            total = stats.get("total", 0)
            completed = stats.get("by_status", {}).get(WorkStatus.COMPLETED.value, 0)
            value = (completed / total * 100) if total > 0 else 0.0
        elif metric == "all":
            value = stats
        else:
            # Unknown metric - return full stats
            value = stats

        # Handle group_by
        if group_by:
            if group_by == "status":
                grouped = stats.get("by_status", {})
            elif group_by == "category":
                grouped = stats.get("by_category", {})
            else:
                grouped = {"ungrouped": value}
            value = grouped

        # Build result
        data = QueryResultData(value=value)

        return QueryResult(
            source=self.source_id,
            query=query,
            data=data,
            metadata={
                "total_items": stats.get("total", 0),
                "by_status": stats.get("by_status", {}),
                "by_category": stats.get("by_category", {}),
                "pending_approval": stats.get("pending_approval", 0),
            },
            timestamp=datetime.now(),
        )

    async def compute_rollups(self, rollup_type: str) -> Dict[str, Any]:
        """
        Compute rollup aggregations for work items.

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

        # Get work items for the period
        all_items = self._manager.list_all(limit=1000)
        period_items = [
            w for w in all_items
            if w.created_at and w.created_at >= period_start
        ]

        completed_in_period = [
            w for w in all_items
            if w.completed_at and w.completed_at >= period_start
        ]

        rollup = {
            "period_type": rollup_type,
            "period_start": period_start.isoformat(),
            "computed_at": now.isoformat(),
            "created_this_period": len(period_items),
            "completed_this_period": len(completed_in_period),
            "total_planned": stats.get("by_status", {}).get(WorkStatus.PLANNED.value, 0),
            "total_ready": stats.get("by_status", {}).get(WorkStatus.READY.value, 0),
            "total_running": stats.get("by_status", {}).get(WorkStatus.RUNNING.value, 0),
            "pending_approval": stats.get("pending_approval", 0),
            "estimated_pending_cost_usd": stats.get("estimated_pending_cost_usd", 0.0),
            "actual_completed_cost_usd": stats.get("actual_completed_cost_usd", 0.0),
        }

        return rollup

    async def ensure_rollups_fresh(self) -> None:
        """Ensure rollups are computed (for LAZY strategy)."""
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
        rollups = {}
        for rollup_type in self.rollup_config.rollup_types:
            rollups[rollup_type] = await self.compute_rollups(rollup_type)

        self._rollups = rollups
        self._last_rollup_refresh = datetime.now()

    def get_current_summary(self) -> str:
        """Get a human-readable summary of work items."""
        stats = self._manager.get_stats()
        total = stats.get("total", 0)
        by_status = stats.get("by_status", {})
        pending = stats.get("pending_approval", 0)

        parts = [f"{total} work items"]

        if by_status:
            status_parts = []
            for status, count in by_status.items():
                if count > 0:
                    status_parts.append(f"{status}: {count}")
            if status_parts:
                parts.append(f"({', '.join(status_parts)})")

        if pending > 0:
            parts.append(f"- {pending} pending approval")

        return " ".join(parts)
