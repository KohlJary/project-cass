"""
Schedule Queryable Source

Wraps ScheduleManager as a queryable source for the unified state query interface.
Provides access to Cass's schedule metrics: slots by status, upcoming slots, budget, etc.

Refresh strategy: LAZY (compute on query - data changes with schedule updates)
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
    ScheduleManager,
    SlotStatus,
)


logger = logging.getLogger(__name__)


class ScheduleQueryableSource(QueryableSource):
    """
    Schedule slots as a queryable source.

    Wraps ScheduleManager and exposes scheduling metrics through the unified query interface.
    Uses LAZY refresh since schedule data changes with operations.
    """

    def __init__(self, daemon_id: str, manager: Optional[ScheduleManager] = None):
        """
        Initialize the schedule queryable source.

        Args:
            daemon_id: The daemon this source belongs to
            manager: Optional ScheduleManager instance (created if not provided)
        """
        super().__init__(daemon_id)
        self._manager = manager or ScheduleManager(daemon_id)

    @property
    def source_id(self) -> str:
        return "schedule"

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
                    description="All schedule metrics in one response",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="total_slots",
                    description="Total number of schedule slots",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="slots",
                ),
                MetricDefinition(
                    name="by_status",
                    description="Slots grouped by status",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="today_count",
                    description="Slots scheduled for today",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="slots",
                ),
                MetricDefinition(
                    name="week_count",
                    description="Slots scheduled for this week",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="slots",
                ),
                MetricDefinition(
                    name="upcoming",
                    description="Upcoming scheduled slots (next 24 hours)",
                    data_type="list",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="next_slot",
                    description="The next scheduled slot",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="budget_scheduled",
                    description="Total budget allocated to scheduled slots",
                    data_type="float",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="usd",
                ),
                MetricDefinition(
                    name="flexible_slots",
                    description="Slots with no fixed time",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="slots",
                ),
                MetricDefinition(
                    name="idle_slots",
                    description="Slots requiring idle time",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="slots",
                ),
                MetricDefinition(
                    name="due_now",
                    description="Slots that should be executing now",
                    data_type="list",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
            ],
            aggregations=["sum", "count", "avg", "latest"],
            group_by_options=["status", "day", "week"],
            filter_keys=["status", "work_item_id", "requires_idle", "date_range", "hours", "window_minutes"],
            rollups=["daily", "weekly"],
        )

    async def execute_query(self, query: StateQuery) -> QueryResult:
        """
        Execute a query against schedule data.

        Args:
            query: The StateQuery to execute

        Returns:
            QueryResult with schedule metrics
        """
        metric = query.metric
        filters = query.filters or {}
        group_by = query.group_by

        # Get stats from manager
        stats = self._manager.get_stats()

        # Build result based on requested metric
        if metric == "total_slots":
            value = stats.get("total", 0)
        elif metric == "by_status":
            value = stats.get("by_status", {})
        elif metric == "today_count":
            value = stats.get("today_count", 0)
        elif metric == "week_count":
            value = stats.get("week_count", 0)
        elif metric == "upcoming":
            hours = filters.get("hours", 24)
            slots = self._manager.get_upcoming_slots(hours=hours)
            value = [s.to_dict() for s in slots]
        elif metric == "next_slot":
            slot = self._manager.get_next_slot()
            value = slot.to_dict() if slot else None
        elif metric == "budget_scheduled":
            value = stats.get("budget_scheduled_usd", 0.0)
        elif metric == "flexible_slots":
            value = stats.get("flexible_slots", 0)
        elif metric == "idle_slots":
            value = stats.get("idle_slots", 0)
        elif metric == "due_now":
            window = filters.get("window_minutes", 5)
            slots = self._manager.get_slots_due_now(window_minutes=window)
            value = [s.to_dict() for s in slots]
        elif metric == "all":
            value = stats
        else:
            # Unknown metric - return full stats
            value = stats

        # Handle group_by
        if group_by:
            if group_by == "status":
                grouped = stats.get("by_status", {})
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
                "total_slots": stats.get("total", 0),
                "by_status": stats.get("by_status", {}),
                "today_count": stats.get("today_count", 0),
                "week_count": stats.get("week_count", 0),
            },
            timestamp=datetime.now(),
        )

    async def compute_rollups(self, rollup_type: str) -> Dict[str, Any]:
        """
        Compute rollup aggregations for schedule.

        Args:
            rollup_type: "daily" or "weekly"

        Returns:
            Dict with rollup data
        """
        stats = self._manager.get_stats()

        now = datetime.now()
        if rollup_type == "daily":
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = period_start + timedelta(days=1)
        else:  # weekly
            days_since_monday = now.weekday()
            period_start = (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            period_end = period_start + timedelta(days=7)

        # Get slots for the period
        period_slots = self._manager.get_slots_for_range(period_start, period_end)

        scheduled = [s for s in period_slots if s.status == SlotStatus.SCHEDULED]
        completed = [s for s in period_slots if s.status == SlotStatus.COMPLETED]
        skipped = [s for s in period_slots if s.status == SlotStatus.SKIPPED]

        rollup = {
            "period_type": rollup_type,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "computed_at": now.isoformat(),
            "total_in_period": len(period_slots),
            "scheduled": len(scheduled),
            "completed": len(completed),
            "skipped": len(skipped),
            "completion_rate": (len(completed) / len(period_slots) * 100) if period_slots else 0.0,
            "budget_scheduled_usd": stats.get("budget_scheduled_usd", 0.0),
            "flexible_slots": stats.get("flexible_slots", 0),
            "idle_slots": stats.get("idle_slots", 0),
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
        """Get a human-readable summary of schedule."""
        stats = self._manager.get_stats()
        total = stats.get("total", 0)
        today = stats.get("today_count", 0)
        week = stats.get("week_count", 0)
        flexible = stats.get("flexible_slots", 0)

        parts = [f"{total} schedule slots"]

        if today > 0:
            parts.append(f"({today} today)")

        if week > 0:
            parts.append(f"({week} this week)")

        if flexible > 0:
            parts.append(f"- {flexible} flexible")

        return " ".join(parts)
