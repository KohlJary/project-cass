"""
Autonomous Schedule Queryable Source

Exposes Cass's autonomous scheduling state through the unified query interface.
Provides access to current work, work history, and daily summaries.

Refresh strategy: LAZY (compute on query - state changes with work execution)
"""

import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from query_models import (
    StateQuery,
    QueryResult,
    QueryResultData,
    SourceSchema,
    MetricDefinition,
)
from queryable_source import QueryableSource, RefreshStrategy, RollupConfig

logger = logging.getLogger(__name__)


class AutonomousScheduleSource(QueryableSource):
    """
    Cass's autonomous work as a queryable source.

    Exposes:
    - Current autonomous work (if any)
    - Recent work history
    - Daily summary of autonomous activity
    - Decision context (what informs her choices)

    Uses LAZY refresh since work state changes during execution.
    """

    def __init__(
        self,
        daemon_id: str,
        autonomous_scheduler=None,
    ):
        """
        Initialize the autonomous schedule source.

        Args:
            daemon_id: The daemon this source belongs to
            autonomous_scheduler: The AutonomousScheduler instance
        """
        super().__init__(daemon_id)
        self._scheduler = autonomous_scheduler

    def set_scheduler(self, scheduler) -> None:
        """Set the autonomous scheduler reference."""
        self._scheduler = scheduler

    @property
    def source_id(self) -> str:
        return "autonomous_schedule"

    @property
    def refresh_strategy(self) -> RefreshStrategy:
        return RefreshStrategy.LAZY

    @property
    def rollup_config(self) -> RollupConfig:
        return RollupConfig(
            strategy=RefreshStrategy.LAZY,
            cache_ttl_seconds=10,  # Short cache - state changes often
            rollup_types=["daily"],
        )

    @property
    def schema(self) -> SourceSchema:
        return SourceSchema(
            metrics=[
                MetricDefinition(
                    name="all",
                    description="All autonomous schedule metrics",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="current_work",
                    description="Currently executing autonomous work unit",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="is_working",
                    description="Whether Cass is currently doing autonomous work",
                    data_type="boolean",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="recent_history",
                    description="Recent autonomous work history",
                    data_type="list",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="daily_summary",
                    description="Summary of today's autonomous work",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="enabled",
                    description="Whether autonomous scheduling is enabled",
                    data_type="boolean",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="work_summary",
                    description="Detailed work summary by slug",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="work_by_date",
                    description="Work summaries for a specific date",
                    data_type="list",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="work_by_phase",
                    description="Work summaries for a specific date and phase",
                    data_type="list",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="work_stats",
                    description="Work statistics for a date range",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
            ],
            aggregations=[],  # No aggregations supported
            group_by_options=[],  # No grouping supported
        )

    async def execute_query(self, query: StateQuery) -> QueryResult:
        """Execute a query against autonomous schedule data."""
        if not self._scheduler:
            return QueryResult(
                source_id=self.source_id,
                metric=query.metric,
                data=QueryResultData(value=None),
                error="Autonomous scheduler not initialized",
            )

        try:
            metric = query.metric

            if metric == "all":
                value = self._get_all_metrics()
            elif metric == "current_work":
                value = self._get_current_work()
            elif metric == "is_working":
                value = self._scheduler.is_working
            elif metric == "recent_history":
                limit = query.params.get("limit", 20) if query.params else 20
                value = self._scheduler.get_work_history(limit=limit)
            elif metric == "daily_summary":
                value = self._scheduler.get_daily_summary()
            elif metric == "enabled":
                value = self._scheduler.is_enabled
            elif metric == "work_summary":
                slug = query.params.get("slug") if query.params else None
                if not slug:
                    # Return recent summaries
                    limit = query.params.get("limit", 5) if query.params else 5
                    summaries = self._scheduler.summary_store.get_recent(limit=limit)
                    value = [s.to_dict() for s in summaries]
                else:
                    summary = self._scheduler.summary_store.get_by_slug(slug)
                    value = summary.to_dict() if summary else None
            elif metric == "work_by_date":
                date_str = query.params.get("date") if query.params else None
                if date_str:
                    target_date = date.fromisoformat(date_str)
                else:
                    target_date = date.today()
                summaries = self._scheduler.summary_store.get_by_date(target_date)
                value = [s.to_dict() for s in summaries]
            elif metric == "work_by_phase":
                date_str = query.params.get("date") if query.params else None
                phase = query.params.get("phase", "morning") if query.params else "morning"
                if date_str:
                    target_date = date.fromisoformat(date_str)
                else:
                    target_date = date.today()
                summaries = self._scheduler.summary_store.get_by_phase(target_date, phase)
                value = [s.to_dict() for s in summaries]
            elif metric == "work_stats":
                start_str = query.params.get("start_date") if query.params else None
                end_str = query.params.get("end_date") if query.params else None
                end_date = date.today()
                start_date = end_date - timedelta(days=7)
                if start_str:
                    start_date = date.fromisoformat(start_str)
                if end_str:
                    end_date = date.fromisoformat(end_str)
                value = self._scheduler.summary_store.get_stats(start_date, end_date)
            else:
                return QueryResult(
                    source_id=self.source_id,
                    metric=metric,
                    data=QueryResultData(value=None),
                    error=f"Unknown metric: {metric}",
                )

            return QueryResult(
                source_id=self.source_id,
                metric=metric,
                data=QueryResultData(value=value),
                timestamp=datetime.now(),
            )

        except Exception as e:
            logger.error(f"Error querying autonomous schedule: {e}")
            return QueryResult(
                source_id=self.source_id,
                metric=query.metric,
                data=QueryResultData(value=None),
                error=str(e),
            )

    def _get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics in one response."""
        return {
            "current_work": self._get_current_work(),
            "is_working": self._scheduler.is_working,
            "enabled": self._scheduler.is_enabled,
            "daily_summary": self._scheduler.get_daily_summary(),
            "recent_history": self._scheduler.get_work_history(limit=10),
        }

    def _get_current_work(self) -> Optional[Dict[str, Any]]:
        """Get the current work unit as a dict."""
        work = self._scheduler.current_work
        if work:
            return work.to_dict()
        return None

    def describe_for_context(self) -> str:
        """
        Generate a natural language description for context injection.

        This helps Cass understand her own autonomous activity patterns.
        """
        if not self._scheduler:
            return "Autonomous scheduling not available."

        lines = ["## Autonomous Work"]

        if self._scheduler.is_working:
            work = self._scheduler.current_work
            if work:
                lines.append(f"Currently working on: **{work.name}**")
                if work.focus:
                    lines.append(f"Focus: {work.focus}")
                if work.motivation:
                    lines.append(f"Motivation: {work.motivation}")
        else:
            lines.append("Not currently doing autonomous work.")

        summary = self._scheduler.get_daily_summary()
        if summary.get("total_work_units", 0) > 0:
            lines.append(f"\nToday: {summary['total_work_units']} work units completed")
            for cat, info in summary.get("by_category", {}).items():
                lines.append(f"  - {cat}: {info['count']} ({info['total_minutes']}min)")

        return "\n".join(lines)

    def get_precomputed_rollups(self) -> Dict[str, Any]:
        """Return cached rollup aggregates."""
        if not self._scheduler:
            return {}

        # For LAZY sources, we compute on demand
        return {
            "daily_summary": self._scheduler.get_daily_summary(),
            "is_working": self._scheduler.is_working,
            "enabled": self._scheduler.is_enabled,
            "last_refresh": self._last_rollup_refresh,
        }

    async def refresh_rollups(self) -> None:
        """Refresh rollups - for LAZY source, this is a no-op as we compute on demand."""
        self._last_rollup_refresh = datetime.now()
        # LAZY strategy means we compute fresh data on each query
        # No persistent rollups needed for this source
