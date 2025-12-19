"""
Queryable Source Interface for the Unified State Query System.

This module defines the abstract interface that subsystems implement
to register as queryable sources with the Global State Bus.

Each source:
- Has a unique identifier (e.g., "github", "tokens", "emotional")
- Declares a schema of what metrics it can answer
- Implements query execution
- Maintains precomputed rollups for fast access
- Chooses a refresh strategy for keeping rollups current
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from query_models import (
    StateQuery,
    QueryResult,
    QueryResultData,
    SourceSchema,
    MetricDefinition,
)


logger = logging.getLogger(__name__)


class RefreshStrategy(Enum):
    """
    How a source refreshes its precomputed rollups.

    Different sources have different update patterns:
    - SCHEDULED: Good for external APIs with rate limits (GitHub)
    - LAZY: Good for data that changes frequently but isn't always queried
    - EVENT_DRIVEN: Good for data where we control all writes
    """
    SCHEDULED = "scheduled"   # Background task recomputes periodically
    LAZY = "lazy"             # Compute on first query, cache with TTL
    EVENT_DRIVEN = "event"    # Recompute when source data changes


@dataclass
class RollupConfig:
    """
    Configuration for how a source manages its rollups.
    """
    strategy: RefreshStrategy = RefreshStrategy.LAZY
    schedule_interval_seconds: int = 3600       # For SCHEDULED: how often to refresh
    cache_ttl_seconds: int = 300                # For LAZY: how long to cache
    rollup_types: List[str] = field(default_factory=lambda: ["daily", "weekly"])


class QueryableSource(ABC):
    """
    Abstract base class for subsystems that register with the state bus
    as queryable data sources.

    Implementations must provide:
    - source_id: Unique identifier for this source
    - schema: Description of available metrics and capabilities
    - execute_query: Handle StateQuery and return QueryResult
    - get_precomputed_rollups: Return cached aggregates
    - refresh_rollups: Recompute rolling aggregates

    Optionally override:
    - refresh_strategy: How rollups are kept current (default: LAZY)
    - rollup_config: Fine-grained refresh configuration
    """

    def __init__(self, daemon_id: str):
        """
        Initialize the queryable source.

        Args:
            daemon_id: The daemon this source belongs to
        """
        self._daemon_id = daemon_id
        self._rollups: Dict[str, Any] = {}
        self._last_rollup_refresh: Optional[datetime] = None
        self._scheduled_refresh_task: Optional[asyncio.Task] = None
        self._is_registered: bool = False

    @property
    @abstractmethod
    def source_id(self) -> str:
        """
        Unique identifier for this source.

        Examples: "github", "tokens", "emotional", "narrative"
        """
        pass

    @property
    @abstractmethod
    def schema(self) -> SourceSchema:
        """
        Schema describing what this source can answer.

        This is used for query validation and LLM documentation.
        """
        pass

    @property
    def refresh_strategy(self) -> RefreshStrategy:
        """
        How this source refreshes its rollups.

        Override to change from the default (LAZY).
        """
        return RefreshStrategy.LAZY

    @property
    def rollup_config(self) -> RollupConfig:
        """
        Detailed rollup configuration.

        Override for fine-grained control over refresh behavior.
        """
        return RollupConfig(strategy=self.refresh_strategy)

    @abstractmethod
    async def execute_query(self, query: StateQuery) -> QueryResult:
        """
        Execute a structured query and return results.

        Implementations should:
        1. Validate the query against their schema
        2. Resolve time ranges
        3. Apply filters and aggregations
        4. Return properly formatted QueryResult

        Args:
            query: The StateQuery to execute

        Returns:
            QueryResult with data and metadata

        Raises:
            ValueError: If query is invalid for this source
        """
        pass

    @abstractmethod
    def get_precomputed_rollups(self) -> Dict[str, Any]:
        """
        Return currently cached rollup aggregates.

        These are precomputed values that can be returned immediately
        without querying the underlying data store.

        Returns:
            Dict with rollup values, e.g.:
            {
                "stars_7d": 15,
                "clones_7d": 142,
                "last_refresh": datetime(...),
            }
        """
        pass

    @abstractmethod
    async def refresh_rollups(self) -> None:
        """
        Recompute rolling aggregates.

        This is called:
        - Periodically for SCHEDULED sources
        - On first query (and cache expiry) for LAZY sources
        - On data change for EVENT_DRIVEN sources

        Implementations should:
        1. Query underlying data for rollup periods
        2. Update self._rollups dict
        3. Update self._last_rollup_refresh
        4. Optionally persist rollups to database
        """
        pass

    def on_data_changed(self) -> None:
        """
        Called when underlying data changes.

        For EVENT_DRIVEN sources, this triggers rollup refresh.
        Other sources may override for logging or cache invalidation.
        """
        if self.refresh_strategy == RefreshStrategy.EVENT_DRIVEN:
            logger.debug(f"[{self.source_id}] Data changed, refreshing rollups")
            asyncio.create_task(self.refresh_rollups())

    async def start_scheduled_refresh(self) -> None:
        """
        Start the background refresh task for SCHEDULED sources.

        Called by the state bus when registering a SCHEDULED source.
        """
        if self.refresh_strategy != RefreshStrategy.SCHEDULED:
            return

        async def refresh_loop():
            interval = self.rollup_config.schedule_interval_seconds
            logger.info(
                f"[{self.source_id}] Starting scheduled refresh "
                f"(interval: {interval}s)"
            )
            while True:
                try:
                    await self.refresh_rollups()
                    logger.debug(f"[{self.source_id}] Scheduled refresh complete")
                except Exception as e:
                    logger.error(f"[{self.source_id}] Scheduled refresh failed: {e}")
                await asyncio.sleep(interval)

        self._scheduled_refresh_task = asyncio.create_task(refresh_loop())

    def stop_scheduled_refresh(self) -> None:
        """Stop the background refresh task."""
        if self._scheduled_refresh_task:
            self._scheduled_refresh_task.cancel()
            self._scheduled_refresh_task = None

    async def ensure_rollups_fresh(self) -> bool:
        """
        Ensure rollups are fresh for LAZY sources.

        Returns True if rollups are fresh, False if refresh failed.
        Called by the state bus before returning cached rollups.
        """
        if self.refresh_strategy != RefreshStrategy.LAZY:
            return True

        config = self.rollup_config
        now = datetime.now()

        # Check if refresh needed
        if self._last_rollup_refresh is None:
            needs_refresh = True
        else:
            age = (now - self._last_rollup_refresh).total_seconds()
            needs_refresh = age > config.cache_ttl_seconds

        if needs_refresh:
            try:
                await self.refresh_rollups()
                return True
            except Exception as e:
                logger.error(f"[{self.source_id}] Lazy refresh failed: {e}")
                return False

        return True

    def validate_query(self, query: StateQuery) -> List[str]:
        """
        Validate a query against this source's schema.

        Returns a list of validation errors (empty if valid).
        """
        errors = []
        schema = self.schema

        # Check metric
        if query.metric:
            metric_names = [m.name for m in schema.metrics]
            if query.metric not in metric_names:
                errors.append(
                    f"Unknown metric '{query.metric}'. "
                    f"Available: {', '.join(metric_names)}"
                )

        # Check aggregation
        if query.aggregation and query.aggregation.function:
            if query.aggregation.function not in schema.aggregations:
                errors.append(
                    f"Unsupported aggregation '{query.aggregation.function}'. "
                    f"Available: {', '.join(schema.aggregations)}"
                )

        # Check group_by
        if query.group_by:
            if query.group_by not in schema.group_by_options:
                errors.append(
                    f"Unsupported group_by '{query.group_by}'. "
                    f"Available: {', '.join(schema.group_by_options)}"
                )

        # Check filters
        if query.filters:
            for key in query.filters.keys():
                if key not in schema.filter_keys:
                    errors.append(
                        f"Unknown filter key '{key}'. "
                        f"Available: {', '.join(schema.filter_keys)}"
                    )

        return errors

    def describe_for_llm(self) -> str:
        """
        Generate a description of this source for LLM context.

        Used when building tool documentation for Cass.
        """
        return self.schema.describe_for_llm(self.source_id)


class QueryExecutionError(Exception):
    """Raised when a query execution fails."""

    def __init__(self, source_id: str, query: StateQuery, message: str):
        self.source_id = source_id
        self.query = query
        self.message = message
        super().__init__(f"[{source_id}] Query failed: {message}")


class SourceNotFoundError(Exception):
    """Raised when a query references an unknown source."""

    def __init__(self, source_id: str, available: List[str]):
        self.source_id = source_id
        self.available = available
        super().__init__(
            f"Unknown source '{source_id}'. "
            f"Available: {', '.join(available)}"
        )


class QueryValidationError(Exception):
    """Raised when a query fails validation."""

    def __init__(self, source_id: str, errors: List[str]):
        self.source_id = source_id
        self.errors = errors
        super().__init__(
            f"[{source_id}] Query validation failed: {'; '.join(errors)}"
        )
