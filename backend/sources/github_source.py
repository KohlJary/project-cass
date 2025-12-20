"""
GitHub Queryable Source

Wraps GitHubMetricsManager as a queryable source for the unified state query interface.
Provides access to repository metrics: stars, forks, clones, views, etc.

Refresh strategy: SCHEDULED (aligns with existing 6-hour GitHub API fetch cycle)
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


class GitHubQueryableSource(QueryableSource):
    """
    GitHub metrics as a queryable source.

    Wraps GitHubMetricsManager and exposes metrics through the unified query interface.
    Maintains daily/weekly rollups for fast access.
    """

    def __init__(self, daemon_id: str, metrics_manager: "GitHubMetricsManager"):
        """
        Initialize the GitHub queryable source.

        Args:
            daemon_id: The daemon this source belongs to
            metrics_manager: The GitHubMetricsManager instance to wrap
        """
        super().__init__(daemon_id)
        self._manager = metrics_manager

    @property
    def source_id(self) -> str:
        return "github"

    @property
    def refresh_strategy(self) -> RefreshStrategy:
        # Align with existing 6-hour GitHub fetch cycle
        return RefreshStrategy.SCHEDULED

    @property
    def rollup_config(self) -> RollupConfig:
        return RollupConfig(
            strategy=RefreshStrategy.SCHEDULED,
            schedule_interval_seconds=3600,  # Refresh rollups every hour
            cache_ttl_seconds=300,
            rollup_types=["daily", "weekly"],
        )

    @property
    def schema(self) -> SourceSchema:
        return SourceSchema(
            metrics=[
                MetricDefinition(
                    name="all",
                    description="All GitHub metrics in one response",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit=None,
                ),
                MetricDefinition(
                    name="stars",
                    description="Total repository stars",
                    data_type="int",
                    supports_delta=True,
                    supports_timeseries=True,
                ),
                MetricDefinition(
                    name="stars_gained",
                    description="Stars gained in time period",
                    data_type="int",
                    supports_delta=True,
                    supports_timeseries=True,
                ),
                MetricDefinition(
                    name="forks",
                    description="Total repository forks",
                    data_type="int",
                    supports_delta=True,
                    supports_timeseries=True,
                ),
                MetricDefinition(
                    name="clones",
                    description="Clone count in time period",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                ),
                MetricDefinition(
                    name="clones_uniques",
                    description="Unique cloners in time period",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                ),
                MetricDefinition(
                    name="views",
                    description="Page views in time period",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                ),
                MetricDefinition(
                    name="views_uniques",
                    description="Unique viewers in time period",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                ),
                MetricDefinition(
                    name="watchers",
                    description="Repository watchers",
                    data_type="int",
                    supports_delta=True,
                    supports_timeseries=True,
                ),
                MetricDefinition(
                    name="open_issues",
                    description="Open issues count",
                    data_type="int",
                    supports_delta=True,
                    supports_timeseries=True,
                ),
            ],
            aggregations=["sum", "avg", "count", "max", "min", "latest"],
            group_by_options=["day", "week", "repo"],
            filter_keys=["repo"],
            rollups=["daily", "weekly"],
        )

    async def execute_query(self, query: StateQuery) -> QueryResult:
        """
        Execute a query against GitHub metrics data.
        """
        # Resolve time range
        start, end = query.time_range.resolve() if query.time_range else (
            datetime.now() - timedelta(days=7),
            datetime.now()
        )

        # Get the metric to query
        metric = query.metric or "stars"

        # Handle "all" metric - return comprehensive summary
        if metric == "all":
            data = await self._query_all()
            return QueryResult(
                source=self.source_id,
                query=query,
                data=data,
                timestamp=datetime.now(),
                metadata={
                    "repos_tracked": self._manager.repos,
                    "last_fetch": self._manager.last_fetch.isoformat() if self._manager.last_fetch else None,
                }
            )

        # Handle different query patterns
        if query.group_by == "day":
            data = await self._query_timeseries(metric, start, end, query.filters)
        elif query.group_by == "repo":
            data = await self._query_by_repo(metric, start, end, query.filters)
        else:
            # Aggregated single value
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
                "repos_tracked": self._manager.repos,
                "last_fetch": self._manager.last_fetch.isoformat() if self._manager.last_fetch else None,
            }
        )

    async def _query_timeseries(
        self,
        metric: str,
        start: datetime,
        end: datetime,
        filters: Optional[Dict] = None
    ) -> QueryResultData:
        """Query for time series data grouped by day."""
        # Get historical data from manager
        # Don't pass repo filter here - we'll filter in _extract_metric_from_snapshot
        # because get_historical_metrics returns different structure when filtered
        days = (end - start).days + 1
        historical = self._manager.get_historical_metrics(days=days)

        series = []
        for snapshot in historical:
            date = snapshot.get("date", "")
            if not date:
                continue

            # Parse date and check range
            try:
                snapshot_date = datetime.strptime(date, "%Y-%m-%d")
                if snapshot_date < start.replace(hour=0, minute=0, second=0) or \
                   snapshot_date > end:
                    continue
            except ValueError:
                continue

            # Extract metric value (filtering happens here)
            repos_data = snapshot.get("repos", {})
            value = self._extract_metric_from_snapshot(metric, repos_data, filters)

            series.append({
                "date": date,
                "value": value,
            })

        # Sort by date
        series.sort(key=lambda x: x["date"])

        return QueryResultData(series=series)

    async def _query_by_repo(
        self,
        metric: str,
        start: datetime,
        end: datetime,
        filters: Optional[Dict] = None
    ) -> QueryResultData:
        """Query grouped by repository."""
        # Get current metrics
        current = self._manager.get_current_metrics()
        if not current:
            return QueryResultData(series=[])

        repos_data = current.get("repos", {})
        series = []

        for repo, data in repos_data.items():
            if filters and filters.get("repo") and filters["repo"] != repo:
                continue

            value = self._extract_single_metric(metric, data)
            series.append({
                "repo": repo,
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
        if aggregation == "latest":
            # Get latest snapshot
            current = self._manager.get_current_metrics()
            if not current:
                return QueryResultData(value=0)

            repos_data = current.get("repos", {})
            value = self._extract_metric_from_snapshot(metric, repos_data, filters)
            return QueryResultData(value=value)

        # For other aggregations, need historical data
        days = (end - start).days + 1
        historical = self._manager.get_historical_metrics(
            days=days,
            repo=filters.get("repo") if filters else None
        )

        values = []
        for snapshot in historical:
            repos_data = snapshot.get("repos", {})
            value = self._extract_metric_from_snapshot(metric, repos_data, filters)
            if value is not None:
                values.append(value)

        if not values:
            return QueryResultData(value=0)

        # Apply aggregation
        if aggregation == "sum":
            # For cumulative metrics like stars, sum doesn't make sense
            # Instead, calculate the delta over the period
            if metric in ["stars", "forks", "watchers"]:
                result = max(values) - min(values) if len(values) > 1 else 0
            else:
                result = sum(values)
        elif aggregation == "avg":
            result = sum(values) / len(values)
        elif aggregation == "max":
            result = max(values)
        elif aggregation == "min":
            result = min(values)
        elif aggregation == "count":
            result = len(values)
        else:
            result = values[-1] if values else 0

        return QueryResultData(value=result)

    def _extract_metric_from_snapshot(
        self,
        metric: str,
        repos_data: Dict,
        filters: Optional[Dict] = None
    ) -> int:
        """Extract a metric value from repos data, optionally filtered."""
        total = 0
        for repo, data in repos_data.items():
            if filters and filters.get("repo") and filters["repo"] != repo:
                continue
            value = self._extract_single_metric(metric, data)
            if value is not None:
                total += value
        return total

    def _extract_single_metric(self, metric: str, data: Dict) -> Optional[int]:
        """Extract a single metric from repo data."""
        metric_map = {
            "stars": "stars",
            "stars_gained": "stars",  # Will need delta calculation
            "forks": "forks",
            "clones": "clones_count",
            "clones_uniques": "clones_uniques",
            "views": "views_count",
            "views_uniques": "views_uniques",
            "watchers": "watchers",
            "open_issues": "open_issues",
        }

        key = metric_map.get(metric, metric)
        return data.get(key)

    async def _query_all(self) -> QueryResultData:
        """Return all GitHub metrics in one response."""
        now = datetime.now()
        week_ago = now - timedelta(days=7)

        # Get current metrics
        current = self._manager.get_current_metrics()
        if not current:
            return QueryResultData(value={
                "stars_total": 0,
                "forks_total": 0,
                "watchers_total": 0,
                "open_issues": 0,
                "clones_14d": 0,
                "clones_uniques_14d": 0,
                "views_14d": 0,
                "views_uniques_14d": 0,
                "stars_7d": 0,
                "repos_tracked": len(self._manager.repos),
                "last_fetch": None,
            })

        repos_data = current.get("repos", {})

        # Aggregate current totals
        stars_total = sum(r.get("stars", 0) for r in repos_data.values())
        forks_total = sum(r.get("forks", 0) for r in repos_data.values())
        watchers_total = sum(r.get("watchers", 0) for r in repos_data.values())
        open_issues = sum(r.get("open_issues", 0) for r in repos_data.values())

        # Traffic metrics (GitHub returns 14-day totals in the current snapshot)
        clones_14d = sum(r.get("clones_count", 0) for r in repos_data.values())
        clones_uniques_14d = sum(r.get("clones_uniques", 0) for r in repos_data.values())
        views_14d = sum(r.get("views_count", 0) for r in repos_data.values())
        views_uniques_14d = sum(r.get("views_uniques", 0) for r in repos_data.values())

        # Calculate stars gained in last 7 days from historical data
        stars_7d = 0
        historical = self._manager.get_historical_metrics(days=7)
        if len(historical) >= 2:
            oldest = historical[0]
            newest = historical[-1]
            oldest_stars = sum(r.get("stars", 0) for r in oldest.get("repos", {}).values())
            newest_stars = sum(r.get("stars", 0) for r in newest.get("repos", {}).values())
            stars_7d = newest_stars - oldest_stars

        return QueryResultData(value={
            "stars_total": stars_total,
            "forks_total": forks_total,
            "watchers_total": watchers_total,
            "open_issues": open_issues,
            "clones_14d": clones_14d,
            "clones_uniques_14d": clones_uniques_14d,
            "views_14d": views_14d,
            "views_uniques_14d": views_uniques_14d,
            "stars_7d": stars_7d,
            "repos_tracked": len(self._manager.repos),
            "last_fetch": self._manager.last_fetch.isoformat() if self._manager.last_fetch else None,
        })

    def get_precomputed_rollups(self) -> Dict[str, Any]:
        """Return cached rollup aggregates."""
        return {
            "stars_total": self._rollups.get("stars_total", 0),
            "stars_7d": self._rollups.get("stars_7d", 0),
            "clones_7d": self._rollups.get("clones_7d", 0),
            "views_7d": self._rollups.get("views_7d", 0),
            "repos_tracked": len(self._manager.repos),
            "last_refresh": self._last_rollup_refresh.isoformat() if self._last_rollup_refresh else None,
        }

    async def refresh_rollups(self) -> None:
        """Recompute rolling aggregates from historical data."""
        logger.debug(f"[{self.source_id}] Refreshing rollups...")

        # Get current metrics for totals
        current = self._manager.get_current_metrics()
        if current:
            repos_data = current.get("repos", {})
            self._rollups["stars_total"] = sum(
                r.get("stars", 0) for r in repos_data.values()
            )

        # Get 7-day metrics
        historical = self._manager.get_historical_metrics(days=7)
        if historical:
            # Calculate 7-day totals for traffic metrics
            clones_7d = 0
            views_7d = 0

            for snapshot in historical:
                repos_data = snapshot.get("repos", {})
                for repo_data in repos_data.values():
                    clones_7d += repo_data.get("clones_count", 0)
                    views_7d += repo_data.get("views_count", 0)

            # Average per day (since we have multiple snapshots per period)
            num_days = len(historical)
            if num_days > 0:
                self._rollups["clones_7d"] = clones_7d // num_days
                self._rollups["views_7d"] = views_7d // num_days

            # Stars gained = difference between oldest and newest
            if len(historical) >= 2:
                oldest = historical[0]
                newest = historical[-1]

                oldest_stars = sum(
                    r.get("stars", 0)
                    for r in oldest.get("repos", {}).values()
                )
                newest_stars = sum(
                    r.get("stars", 0)
                    for r in newest.get("repos", {}).values()
                )
                self._rollups["stars_7d"] = newest_stars - oldest_stars

        self._last_rollup_refresh = datetime.now()

        # Persist rollups to database
        await self._save_rollups_to_db()

        logger.debug(f"[{self.source_id}] Rollups refreshed: {self._rollups}")

    async def _save_rollups_to_db(self) -> None:
        """Save current rollups to database for persistence."""
        from uuid import uuid4

        now = datetime.now()
        rollup_key = now.strftime("%Y-%m-%d")

        with get_db() as conn:
            # Save daily rollup
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

    async def _load_rollups_from_db(self) -> None:
        """Load most recent rollups from database."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT metrics_json, computed_at
                FROM source_rollups
                WHERE daemon_id = ? AND source_id = ?
                ORDER BY computed_at DESC
                LIMIT 1
            """, (self._daemon_id, self.source_id))

            row = cursor.fetchone()
            if row:
                self._rollups = json_deserialize(row[0]) or {}
                self._last_rollup_refresh = datetime.fromisoformat(row[1])
                logger.debug(f"[{self.source_id}] Loaded rollups from DB")


# Import at runtime to avoid circular imports
if False:  # TYPE_CHECKING
    from github_metrics import GitHubMetricsManager
