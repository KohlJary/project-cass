"""
Token Usage Queryable Source

Wraps TokenUsageTracker as a queryable source for the unified state query interface.
Provides access to LLM token usage metrics: costs, tokens by provider/category, etc.

Refresh strategy: LAZY (compute on query, cache briefly - data changes frequently)
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


logger = logging.getLogger(__name__)


class TokenQueryableSource(QueryableSource):
    """
    Token usage as a queryable source.

    Wraps TokenUsageTracker and exposes metrics through the unified query interface.
    Uses LAZY refresh since token data changes with every LLM call.
    """

    def __init__(self, daemon_id: str, tracker: "TokenUsageTracker"):
        """
        Initialize the token queryable source.

        Args:
            daemon_id: The daemon this source belongs to
            tracker: The TokenUsageTracker instance to wrap
        """
        super().__init__(daemon_id)
        self._tracker = tracker

    @property
    def source_id(self) -> str:
        return "tokens"

    @property
    def refresh_strategy(self) -> RefreshStrategy:
        return RefreshStrategy.LAZY

    @property
    def rollup_config(self) -> RollupConfig:
        return RollupConfig(
            strategy=RefreshStrategy.LAZY,
            cache_ttl_seconds=60,  # Cache rollups for 1 minute
            rollup_types=["daily", "weekly"],
        )

    @property
    def schema(self) -> SourceSchema:
        return SourceSchema(
            metrics=[
                MetricDefinition(
                    name="all",
                    description="All token metrics in one response",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit=None,
                ),
                MetricDefinition(
                    name="total_tokens",
                    description="Total tokens used (input + output)",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="tokens",
                ),
                MetricDefinition(
                    name="input_tokens",
                    description="Input/prompt tokens",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="tokens",
                ),
                MetricDefinition(
                    name="output_tokens",
                    description="Output/completion tokens",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="tokens",
                ),
                MetricDefinition(
                    name="cost_usd",
                    description="Estimated cost in USD",
                    data_type="float",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="USD",
                ),
                MetricDefinition(
                    name="cache_hits",
                    description="Anthropic cache read tokens (90% cost savings)",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="tokens",
                ),
                MetricDefinition(
                    name="call_count",
                    description="Number of LLM calls",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="calls",
                ),
            ],
            aggregations=["sum", "avg", "count", "max", "min", "latest"],
            group_by_options=["day", "hour", "provider", "category", "model"],
            filter_keys=["provider", "category", "model", "operation"],
            rollups=["daily", "weekly"],
        )

    async def execute_query(self, query: StateQuery) -> QueryResult:
        """
        Execute a query against token usage data.
        """
        # Resolve time range
        start, end = query.time_range.resolve() if query.time_range else (
            datetime.now() - timedelta(days=1),
            datetime.now()
        )

        # Get the metric to query
        metric = query.metric or "total_tokens"

        # Handle "all" metric - return comprehensive summary
        if metric == "all":
            data = await self._query_all()
            return QueryResult(
                source=self.source_id,
                query=query,
                data=data,
                timestamp=datetime.now(),
                metadata={"period": "computed_fresh"}
            )

        # Handle different query patterns
        if query.group_by in ["day", "hour"]:
            data = await self._query_timeseries(metric, start, end, query.group_by, query.filters)
        elif query.group_by in ["provider", "category", "model"]:
            data = await self._query_grouped(metric, start, end, query.group_by, query.filters)
        else:
            # Aggregated single value
            data = await self._query_aggregated(
                metric, start, end,
                query.aggregation.function if query.aggregation else "sum",
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

    async def _query_timeseries(
        self,
        metric: str,
        start: datetime,
        end: datetime,
        granularity: str,
        filters: Optional[Dict] = None
    ) -> QueryResultData:
        """Query for time series data."""
        days = (end - start).days + 1
        timeseries = self._tracker.get_timeseries(
            metric=self._map_metric(metric),
            days=days,
            granularity=granularity
        )

        # Filter if needed (timeseries doesn't support filtering directly)
        # Just return as-is for now
        series = [
            {"date": point["date"], "value": point["value"]}
            for point in timeseries
        ]

        return QueryResultData(series=series)

    async def _query_grouped(
        self,
        metric: str,
        start: datetime,
        end: datetime,
        group_by: str,
        filters: Optional[Dict] = None
    ) -> QueryResultData:
        """Query grouped by provider/category/model."""
        summary = self._tracker.get_summary(start_date=start, end_date=end)

        # Map group_by to summary key
        group_key = f"by_{group_by}"
        grouped_data = summary.get(group_key, {})

        series = []
        for key, data in grouped_data.items():
            if filters:
                # Apply filters
                skip = False
                for fk, fv in filters.items():
                    if fk == group_by and key != fv:
                        skip = True
                        break
                if skip:
                    continue

            # Extract requested metric
            value = self._extract_metric_from_group(metric, data)
            series.append({
                group_by: key,
                "value": value,
            })

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
        summary = self._tracker.get_summary(start_date=start, end_date=end)
        totals = summary.get("totals", {})

        # Map metric to totals key
        metric_map = {
            "total_tokens": "total_tokens",
            "input_tokens": "input_tokens",
            "output_tokens": "output_tokens",
            "cost_usd": "estimated_cost_usd",
            "cache_hits": "cache_read_tokens",
            "call_count": "records",
        }

        key = metric_map.get(metric, metric)
        value = totals.get(key, 0)

        # For "sum" aggregation, the summary already has the sum
        # For "avg", we need to divide by count
        if aggregation == "avg" and totals.get("records", 0) > 0:
            value = value / totals["records"]

        return QueryResultData(value=value)

    def _map_metric(self, metric: str) -> str:
        """Map our metric names to TokenTracker's metric names."""
        metric_map = {
            "total_tokens": "total_tokens",
            "input_tokens": "input_tokens",
            "output_tokens": "output_tokens",
            "cost_usd": "cost",
            "cache_hits": "total_tokens",  # No direct mapping
            "call_count": "count",
        }
        return metric_map.get(metric, metric)

    def _extract_metric_from_group(self, metric: str, data: Dict) -> Any:
        """Extract a metric value from grouped summary data."""
        metric_map = {
            "total_tokens": "tokens",
            "input_tokens": "tokens",  # Approximation
            "output_tokens": "tokens",  # Approximation
            "cost_usd": "cost",
            "cache_hits": "tokens",  # No direct mapping
            "call_count": "count",
        }
        key = metric_map.get(metric, "tokens")
        return data.get(key, 0)

    async def _query_all(self) -> QueryResultData:
        """Return all token metrics in one response."""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get summaries for different periods
        today_summary = self._tracker.get_summary(start_date=today_start, end_date=now)
        week_summary = self._tracker.get_summary(start_date=week_start, end_date=now)
        month_summary = self._tracker.get_summary(start_date=month_start, end_date=now)
        all_time_summary = self._tracker.get_summary()

        today_totals = today_summary.get("totals", {})
        week_totals = week_summary.get("totals", {})
        month_totals = month_summary.get("totals", {})
        all_totals = all_time_summary.get("totals", {})

        return QueryResultData(value={
            "today_cost_usd": round(today_totals.get("estimated_cost_usd", 0), 4),
            "today_input_tokens": today_totals.get("input_tokens", 0),
            "today_output_tokens": today_totals.get("output_tokens", 0),
            "today_total_tokens": today_totals.get("total_tokens", 0),
            "today_requests": today_totals.get("records", 0),
            "week_cost_usd": round(week_totals.get("estimated_cost_usd", 0), 4),
            "week_total_tokens": week_totals.get("total_tokens", 0),
            "month_cost_usd": round(month_totals.get("estimated_cost_usd", 0), 4),
            "month_total_tokens": month_totals.get("total_tokens", 0),
            "total_cost_usd": round(all_totals.get("estimated_cost_usd", 0), 4),
            "total_tokens": all_totals.get("total_tokens", 0),
            "total_requests": all_totals.get("records", 0),
            "cache_read_tokens": all_totals.get("cache_read_tokens", 0),
        })

    def get_precomputed_rollups(self) -> Dict[str, Any]:
        """Return cached rollup aggregates."""
        return {
            "tokens_today": self._rollups.get("tokens_today", 0),
            "cost_today": self._rollups.get("cost_today", 0.0),
            "tokens_7d": self._rollups.get("tokens_7d", 0),
            "cost_7d": self._rollups.get("cost_7d", 0.0),
            "calls_today": self._rollups.get("calls_today", 0),
            "last_refresh": self._last_rollup_refresh.isoformat() if self._last_rollup_refresh else None,
        }

    async def refresh_rollups(self) -> None:
        """Recompute rolling aggregates from token data."""
        logger.debug(f"[{self.source_id}] Refreshing rollups...")

        now = datetime.now()

        # Today's totals
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_summary = self._tracker.get_summary(start_date=today_start, end_date=now)
        today_totals = today_summary.get("totals", {})

        self._rollups["tokens_today"] = today_totals.get("total_tokens", 0)
        self._rollups["cost_today"] = round(today_totals.get("estimated_cost_usd", 0), 4)
        self._rollups["calls_today"] = today_totals.get("records", 0)

        # 7-day totals
        week_start = now - timedelta(days=7)
        week_summary = self._tracker.get_summary(start_date=week_start, end_date=now)
        week_totals = week_summary.get("totals", {})

        self._rollups["tokens_7d"] = week_totals.get("total_tokens", 0)
        self._rollups["cost_7d"] = round(week_totals.get("estimated_cost_usd", 0), 4)

        self._last_rollup_refresh = now

        # Persist rollups to database
        await self._save_rollups_to_db()

        logger.debug(f"[{self.source_id}] Rollups refreshed: {self._rollups}")

    async def _save_rollups_to_db(self) -> None:
        """Save current rollups to database for persistence."""
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


# Import at runtime to avoid circular imports
if False:  # TYPE_CHECKING
    from token_tracker import TokenUsageTracker
