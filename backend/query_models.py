"""
Query Models for the Unified State Query Interface.

This module defines the structured query language for querying data
from registered subsystems through the Global State Bus.

The query language is designed to be:
- LLM-friendly: Simple enough for Cass to generate correct queries
- Type-safe: Structured dataclasses, not string interpolation
- Composable: Cross-source queries built from single-source primitives
- Time-centric: Temporal filtering is first-class
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import json


class TimePreset(Enum):
    """Common time range presets for easy querying."""
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_24H = "last_24h"
    LAST_7D = "last_7d"
    LAST_30D = "last_30d"
    THIS_WEEK = "this_week"
    THIS_MONTH = "this_month"
    ALL_TIME = "all_time"


class AggregationFunction(Enum):
    """Supported aggregation functions."""
    SUM = "sum"
    AVG = "avg"
    COUNT = "count"
    MAX = "max"
    MIN = "min"
    LATEST = "latest"
    FIRST = "first"


@dataclass
class TimeRange:
    """
    Time-based filtering for queries.

    Can use either a preset or explicit start/end times.
    Presets are resolved at query execution time.
    """
    preset: Optional[str] = None      # "today", "last_7d", etc.
    start: Optional[datetime] = None  # Explicit start time
    end: Optional[datetime] = None    # Explicit end time (defaults to now)

    def resolve(self) -> tuple[datetime, datetime]:
        """
        Resolve the time range to concrete start/end datetimes.

        Returns:
            Tuple of (start_datetime, end_datetime)
        """
        now = datetime.now()

        if self.start and self.end:
            return (self.start, self.end)

        if self.start and not self.end:
            return (self.start, now)

        if not self.preset:
            # Default to last 24 hours
            return (now - timedelta(hours=24), now)

        preset = self.preset.lower()

        if preset == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return (start, now)

        elif preset == "yesterday":
            yesterday = now - timedelta(days=1)
            start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
            return (start, end)

        elif preset == "last_24h":
            return (now - timedelta(hours=24), now)

        elif preset == "last_7d":
            return (now - timedelta(days=7), now)

        elif preset == "last_30d":
            return (now - timedelta(days=30), now)

        elif preset == "this_week":
            # Start of current week (Monday)
            days_since_monday = now.weekday()
            start = (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            return (start, now)

        elif preset == "this_month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return (start, now)

        elif preset == "all_time":
            # Use a very old date as start
            return (datetime(2020, 1, 1), now)

        else:
            # Unknown preset, default to last 24h
            return (now - timedelta(hours=24), now)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "preset": self.preset,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimeRange":
        """Deserialize from dictionary."""
        return cls(
            preset=data.get("preset"),
            start=datetime.fromisoformat(data["start"]) if data.get("start") else None,
            end=datetime.fromisoformat(data["end"]) if data.get("end") else None,
        )


@dataclass
class Aggregation:
    """
    How to aggregate values in query results.
    """
    function: str = "latest"  # sum, avg, count, max, min, latest, first
    over: str = "all"         # "all" (single value) or "time" (preserves time series)

    def to_dict(self) -> Dict[str, str]:
        return {"function": self.function, "over": self.over}

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Aggregation":
        return cls(
            function=data.get("function", "latest"),
            over=data.get("over", "all"),
        )


@dataclass
class StateQuery:
    """
    A query to one or more queryable sources.

    This is the primary interface for querying data from the unified
    state system. Queries are source-specific but use a common format.

    Examples:
        # Stars gained this week
        StateQuery(
            source="github",
            metric="stars_gained",
            time_range=TimeRange(preset="last_7d"),
            aggregation=Aggregation(function="sum")
        )

        # Daily token cost breakdown
        StateQuery(
            source="tokens",
            metric="cost_usd",
            time_range=TimeRange(preset="last_7d"),
            group_by="day"
        )

        # Current emotional state
        StateQuery(
            source="emotional",
            metric="curiosity",
            aggregation=Aggregation(function="latest")
        )
    """
    source: str                                    # "github", "tokens", "emotional"
    metric: Optional[str] = None                   # Specific metric to retrieve
    time_range: Optional[TimeRange] = None         # Time-based filtering
    aggregation: Optional[Aggregation] = None      # How to aggregate values
    group_by: Optional[str] = None                 # Group results by dimension
    filters: Optional[Dict[str, Any]] = None       # Source-specific filters
    correlate_with: Optional[str] = None           # For cross-source correlation

    def __post_init__(self):
        """Apply defaults."""
        if self.aggregation is None:
            self.aggregation = Aggregation(function="latest")
        if self.time_range is None:
            self.time_range = TimeRange(preset="last_24h")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for storage/transmission."""
        return {
            "source": self.source,
            "metric": self.metric,
            "time_range": self.time_range.to_dict() if self.time_range else None,
            "aggregation": self.aggregation.to_dict() if self.aggregation else None,
            "group_by": self.group_by,
            "filters": self.filters,
            "correlate_with": self.correlate_with,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateQuery":
        """Deserialize from dictionary."""
        return cls(
            source=data["source"],
            metric=data.get("metric"),
            time_range=TimeRange.from_dict(data["time_range"]) if data.get("time_range") else None,
            aggregation=Aggregation.from_dict(data["aggregation"]) if data.get("aggregation") else None,
            group_by=data.get("group_by"),
            filters=data.get("filters"),
            correlate_with=data.get("correlate_with"),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "StateQuery":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class QueryResultData:
    """
    The actual data portion of a query result.

    Can be a single value (for aggregated queries) or a list of
    data points (for time series / grouped queries).
    """
    value: Optional[Any] = None                    # Single aggregated value
    series: Optional[List[Dict[str, Any]]] = None  # Time series or grouped data

    @property
    def is_series(self) -> bool:
        """Whether this result contains series data."""
        return self.series is not None and len(self.series) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "value": self.value,
            "series": self.series,
            "is_series": self.is_series,
        }


@dataclass
class QueryResult:
    """
    Result of executing a StateQuery.

    Contains the data, metadata about the query, and staleness information.
    """
    source: str                           # Which source answered
    query: StateQuery                     # The query that was executed
    data: QueryResultData                 # The actual result data
    timestamp: datetime = field(default_factory=datetime.now)
    is_stale: bool = False                # True if data is from cache
    cache_age_seconds: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None  # Source-specific metadata

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source": self.source,
            "query": self.query.to_dict(),
            "data": {
                "value": self.data.value,
                "series": self.data.series,
            },
            "timestamp": self.timestamp.isoformat(),
            "is_stale": self.is_stale,
            "cache_age_seconds": self.cache_age_seconds,
            "metadata": self.metadata,
        }

    def format_for_llm(self) -> str:
        """
        Format the result in a human-readable way for LLM consumption.

        This is what Cass sees when she uses the query_state tool.
        """
        lines = []

        # Header
        metric_str = f" ({self.query.metric})" if self.query.metric else ""
        lines.append(f"Query result from {self.source}{metric_str}:")

        # Staleness warning
        if self.is_stale and self.cache_age_seconds:
            lines.append(f"  (Note: cached data, {int(self.cache_age_seconds)}s old)")

        # Data
        if self.data.is_series:
            lines.append(f"  Time series ({len(self.data.series)} points):")
            for point in self.data.series[:10]:  # Limit to 10 for readability
                if "date" in point:
                    lines.append(f"    {point['date']}: {point.get('value', point)}")
                else:
                    lines.append(f"    {point}")
            if len(self.data.series) > 10:
                lines.append(f"    ... and {len(self.data.series) - 10} more")
        else:
            value = self.data.value
            if isinstance(value, float):
                lines.append(f"  Value: {value:.2f}")
            else:
                lines.append(f"  Value: {value}")

        # Metadata
        if self.metadata:
            for key, val in self.metadata.items():
                lines.append(f"  {key}: {val}")

        return "\n".join(lines)


@dataclass
class MetricDefinition:
    """
    Definition of a queryable metric within a source.

    This metadata helps the query system validate queries and
    provides documentation for LLMs constructing queries.

    Semantic fields enable natural language capability discovery:
    - semantic_summary: LLM-generated 1-2 sentence summary for embedding
    - example_queries: Natural language questions this metric answers
    - tags: Categorical tags for filtering (e.g., "engagement", "cost", "activity")
    """
    name: str                             # "stars", "total_tokens", "curiosity"
    description: str                      # Human-readable description
    data_type: str                        # "int", "float", "count", "percentage"
    supports_delta: bool = False          # Can compute change over time
    supports_timeseries: bool = True      # Can return time-indexed data
    unit: Optional[str] = None            # "USD", "tokens", etc.
    # Semantic discovery fields
    semantic_summary: Optional[str] = None  # LLM-generated, embedding-ready
    example_queries: List[str] = field(default_factory=list)  # Natural language examples
    tags: List[str] = field(default_factory=list)  # Categorical tags for filtering

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "data_type": self.data_type,
            "supports_delta": self.supports_delta,
            "supports_timeseries": self.supports_timeseries,
            "unit": self.unit,
            "semantic_summary": self.semantic_summary,
            "example_queries": self.example_queries,
            "tags": self.tags,
        }

    def get_embedding_text(self) -> str:
        """
        Generate text for embedding in semantic search.

        Uses semantic_summary if available, otherwise combines
        name, description, and example queries.
        """
        if self.semantic_summary:
            return self.semantic_summary

        # Fallback: construct from available metadata
        parts = [self.name, self.description]
        if self.example_queries:
            parts.extend(self.example_queries[:3])  # Limit for embedding size
        return " | ".join(parts)


@dataclass
class SourceSchema:
    """
    Schema describing what a queryable source can answer.

    Used for query validation and LLM documentation.
    """
    metrics: List[MetricDefinition]       # Available metrics
    aggregations: List[str]               # Supported aggregation functions
    group_by_options: List[str]           # Supported grouping dimensions
    filter_keys: List[str] = field(default_factory=list)  # Valid filter keys
    rollups: List[str] = field(default_factory=list)      # Precomputed rollup types

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metrics": [m.to_dict() for m in self.metrics],
            "aggregations": self.aggregations,
            "group_by_options": self.group_by_options,
            "filter_keys": self.filter_keys,
            "rollups": self.rollups,
        }

    def describe_for_llm(self, source_id: str) -> str:
        """
        Generate a description of this source for LLM context.
        """
        lines = [f"Source: {source_id}"]
        lines.append("Metrics:")
        for m in self.metrics:
            unit_str = f" ({m.unit})" if m.unit else ""
            lines.append(f"  - {m.name}: {m.description}{unit_str}")

        lines.append(f"Aggregations: {', '.join(self.aggregations)}")

        if self.group_by_options:
            lines.append(f"Group by: {', '.join(self.group_by_options)}")

        if self.filter_keys:
            lines.append(f"Filter by: {', '.join(self.filter_keys)}")

        return "\n".join(lines)
