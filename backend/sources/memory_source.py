"""
Memory Queryable Source

Wraps memory subsystems (journals, threads, questions, embeddings) as a queryable source.
Provides insight into Cass's memory health, narrative coherence, and learning activity.

Refresh strategy: LAZY (data changes infrequently, cache briefly)
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from database import get_db, get_daemon_id, json_serialize, json_deserialize
from query_models import (
    StateQuery,
    QueryResult,
    QueryResultData,
    SourceSchema,
    MetricDefinition,
)
from queryable_source import QueryableSource, RefreshStrategy, RollupConfig


logger = logging.getLogger(__name__)


class MemoryQueryableSource(QueryableSource):
    """
    Memory subsystems as a queryable source.

    Exposes metrics from:
    - Journals (daily reflections)
    - Conversation threads (narrative arcs)
    - Open questions (unresolved curiosities)
    - ChromaDB embeddings (semantic memory)
    - Summaries (compressed conversation history)
    """

    def __init__(self, daemon_id: str, memory_core=None):
        """
        Initialize the memory queryable source.

        Args:
            daemon_id: The daemon this source belongs to
            memory_core: Optional MemoryCore instance for ChromaDB access
        """
        super().__init__(daemon_id)
        self._memory_core = memory_core

    @property
    def source_id(self) -> str:
        return "memory"

    @property
    def refresh_strategy(self) -> RefreshStrategy:
        return RefreshStrategy.LAZY

    @property
    def rollup_config(self) -> RollupConfig:
        return RollupConfig(
            strategy=RefreshStrategy.LAZY,
            cache_ttl_seconds=120,  # Cache for 2 minutes
            rollup_types=["daily", "weekly"],
        )

    @property
    def schema(self) -> SourceSchema:
        return SourceSchema(
            metrics=[
                MetricDefinition(
                    name="all",
                    description="All memory metrics in one response",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit=None,
                ),
                # Journals
                MetricDefinition(
                    name="total_journals",
                    description="Total journal entries",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="entries",
                ),
                MetricDefinition(
                    name="journals_created",
                    description="Journal entries created in time period",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="entries",
                ),
                # Threads (Narrative Coherence)
                MetricDefinition(
                    name="total_threads",
                    description="Total conversation threads",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="threads",
                ),
                MetricDefinition(
                    name="active_threads",
                    description="Active conversation threads",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="threads",
                ),
                MetricDefinition(
                    name="resolved_threads",
                    description="Resolved conversation threads",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="threads",
                ),
                # Open Questions
                MetricDefinition(
                    name="total_questions",
                    description="Total tracked questions",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="questions",
                ),
                MetricDefinition(
                    name="open_questions",
                    description="Currently open questions",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="questions",
                ),
                MetricDefinition(
                    name="resolved_questions",
                    description="Resolved questions",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="questions",
                ),
                # Embeddings
                MetricDefinition(
                    name="total_embeddings",
                    description="Total memory embeddings in ChromaDB",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="embeddings",
                ),
                # Summaries
                MetricDefinition(
                    name="summarized_conversations",
                    description="Conversations that have been summarized",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="conversations",
                ),
                MetricDefinition(
                    name="pending_summarization",
                    description="Messages awaiting summarization",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="messages",
                ),
            ],
            aggregations=["sum", "avg", "count", "max", "min", "latest"],
            group_by_options=["day", "month", "thread_type", "question_type", "status"],
            filter_keys=["status", "thread_type", "question_type", "user_id"],
            rollups=["daily", "weekly"],
        )

    async def execute_query(self, query: StateQuery) -> QueryResult:
        """Execute a query against memory data."""
        # Resolve time range
        start, end = query.time_range.resolve() if query.time_range else (
            datetime.now() - timedelta(days=30),
            datetime.now()
        )

        metric = query.metric or "total_journals"

        # Handle "all" metric
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
        if query.group_by in ["day", "month"]:
            data = await self._query_timeseries(metric, start, end, query.group_by, query.filters)
        elif query.group_by in ["thread_type", "question_type", "status"]:
            data = await self._query_grouped(metric, start, end, query.group_by, query.filters)
        else:
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
        with get_db() as conn:
            if granularity == "month":
                strftime_format = "%Y-%m"
            else:
                strftime_format = "%Y-%m-%d"

            if metric in ["total_journals", "journals_created"]:
                query_sql = f"""
                    SELECT strftime('{strftime_format}', created_at) as period,
                           COUNT(*) as value
                    FROM journals
                    WHERE daemon_id = ?
                      AND created_at >= ?
                      AND created_at <= ?
                    GROUP BY period
                    ORDER BY period
                """
                cursor = conn.execute(query_sql, (
                    self._daemon_id,
                    start.isoformat(),
                    end.isoformat()
                ))

            elif metric in ["total_threads"]:
                query_sql = f"""
                    SELECT strftime('{strftime_format}', created_at) as period,
                           COUNT(*) as value
                    FROM conversation_threads
                    WHERE daemon_id = ?
                      AND created_at >= ?
                      AND created_at <= ?
                    GROUP BY period
                    ORDER BY period
                """
                cursor = conn.execute(query_sql, (
                    self._daemon_id,
                    start.isoformat(),
                    end.isoformat()
                ))

            elif metric in ["total_questions"]:
                query_sql = f"""
                    SELECT strftime('{strftime_format}', created_at) as period,
                           COUNT(*) as value
                    FROM open_questions
                    WHERE daemon_id = ?
                      AND created_at >= ?
                      AND created_at <= ?
                    GROUP BY period
                    ORDER BY period
                """
                cursor = conn.execute(query_sql, (
                    self._daemon_id,
                    start.isoformat(),
                    end.isoformat()
                ))
            else:
                return QueryResultData(series=[])

            series = [
                {"date": row["period"], "value": row["value"]}
                for row in cursor.fetchall()
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
        """Query grouped by type/status."""
        with get_db() as conn:
            if group_by == "thread_type":
                cursor = conn.execute("""
                    SELECT thread_type, COUNT(*) as count
                    FROM conversation_threads
                    WHERE daemon_id = ?
                    GROUP BY thread_type
                """, (self._daemon_id,))
                series = [
                    {"thread_type": row["thread_type"], "value": row["count"]}
                    for row in cursor.fetchall()
                ]

            elif group_by == "question_type":
                cursor = conn.execute("""
                    SELECT question_type, COUNT(*) as count
                    FROM open_questions
                    WHERE daemon_id = ?
                    GROUP BY question_type
                """, (self._daemon_id,))
                series = [
                    {"question_type": row["question_type"], "value": row["count"]}
                    for row in cursor.fetchall()
                ]

            elif group_by == "status":
                # Combine thread and question status
                cursor = conn.execute("""
                    SELECT 'thread' as source, status, COUNT(*) as count
                    FROM conversation_threads
                    WHERE daemon_id = ?
                    GROUP BY status
                    UNION ALL
                    SELECT 'question' as source, status, COUNT(*) as count
                    FROM open_questions
                    WHERE daemon_id = ?
                    GROUP BY status
                """, (self._daemon_id, self._daemon_id))
                series = [
                    {"source": row["source"], "status": row["status"], "value": row["count"]}
                    for row in cursor.fetchall()
                ]
            else:
                series = []

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
        with get_db() as conn:
            if metric == "total_journals":
                cursor = conn.execute("""
                    SELECT COUNT(*) as value FROM journals WHERE daemon_id = ?
                """, (self._daemon_id,))
                value = cursor.fetchone()["value"]

            elif metric == "journals_created":
                cursor = conn.execute("""
                    SELECT COUNT(*) as value FROM journals
                    WHERE daemon_id = ? AND created_at >= ? AND created_at <= ?
                """, (self._daemon_id, start.isoformat(), end.isoformat()))
                value = cursor.fetchone()["value"]

            elif metric == "total_threads":
                cursor = conn.execute("""
                    SELECT COUNT(*) as value FROM conversation_threads WHERE daemon_id = ?
                """, (self._daemon_id,))
                value = cursor.fetchone()["value"]

            elif metric == "active_threads":
                cursor = conn.execute("""
                    SELECT COUNT(*) as value FROM conversation_threads
                    WHERE daemon_id = ? AND status = 'active'
                """, (self._daemon_id,))
                value = cursor.fetchone()["value"]

            elif metric == "resolved_threads":
                cursor = conn.execute("""
                    SELECT COUNT(*) as value FROM conversation_threads
                    WHERE daemon_id = ? AND status = 'resolved'
                """, (self._daemon_id,))
                value = cursor.fetchone()["value"]

            elif metric == "total_questions":
                cursor = conn.execute("""
                    SELECT COUNT(*) as value FROM open_questions WHERE daemon_id = ?
                """, (self._daemon_id,))
                value = cursor.fetchone()["value"]

            elif metric == "open_questions":
                cursor = conn.execute("""
                    SELECT COUNT(*) as value FROM open_questions
                    WHERE daemon_id = ? AND status = 'open'
                """, (self._daemon_id,))
                value = cursor.fetchone()["value"]

            elif metric == "resolved_questions":
                cursor = conn.execute("""
                    SELECT COUNT(*) as value FROM open_questions
                    WHERE daemon_id = ? AND status = 'resolved'
                """, (self._daemon_id,))
                value = cursor.fetchone()["value"]

            elif metric == "total_embeddings":
                # Query ChromaDB if available
                if self._memory_core:
                    value = self._memory_core.count()
                else:
                    value = 0

            elif metric == "summarized_conversations":
                cursor = conn.execute("""
                    SELECT COUNT(*) as value FROM conversations
                    WHERE daemon_id = ? AND last_summary_timestamp IS NOT NULL
                """, (self._daemon_id,))
                value = cursor.fetchone()["value"]

            elif metric == "pending_summarization":
                cursor = conn.execute("""
                    SELECT SUM(messages_since_last_summary) as value FROM conversations
                    WHERE daemon_id = ?
                """, (self._daemon_id,))
                row = cursor.fetchone()
                value = row["value"] or 0

            else:
                value = 0

        return QueryResultData(value=value)

    async def _query_all(self) -> QueryResultData:
        """Return all memory metrics in one response."""
        with get_db() as conn:
            # Journals
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM journals WHERE daemon_id = ?
            """, (self._daemon_id,))
            journals_total = cursor.fetchone()["count"]

            # Threads
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM conversation_threads WHERE daemon_id = ?
            """, (self._daemon_id,))
            threads_total = cursor.fetchone()["count"]

            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM conversation_threads
                WHERE daemon_id = ? AND status = 'active'
            """, (self._daemon_id,))
            threads_active = cursor.fetchone()["count"]

            # Questions
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM open_questions WHERE daemon_id = ?
            """, (self._daemon_id,))
            questions_total = cursor.fetchone()["count"]

            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM open_questions
                WHERE daemon_id = ? AND status = 'open'
            """, (self._daemon_id,))
            questions_open = cursor.fetchone()["count"]

        # Embeddings
        embeddings = self._memory_core.count() if self._memory_core else 0

        return QueryResultData(value={
            "total_journals": journals_total,
            "total_threads": threads_total,
            "threads_active": threads_active,
            "total_questions": questions_total,
            "questions_open": questions_open,
            "total_embeddings": embeddings,
        })

    def get_precomputed_rollups(self) -> Dict[str, Any]:
        """Return cached rollup aggregates."""
        return {
            "journals_total": self._rollups.get("journals_total", 0),
            "journals_this_month": self._rollups.get("journals_this_month", 0),
            "threads_total": self._rollups.get("threads_total", 0),
            "threads_active": self._rollups.get("threads_active", 0),
            "questions_total": self._rollups.get("questions_total", 0),
            "questions_open": self._rollups.get("questions_open", 0),
            "embeddings_total": self._rollups.get("embeddings_total", 0),
            "last_journal_date": self._rollups.get("last_journal_date"),
            "last_refresh": self._last_rollup_refresh.isoformat() if self._last_rollup_refresh else None,
        }

    async def refresh_rollups(self) -> None:
        """Recompute rolling aggregates."""
        logger.debug(f"[{self.source_id}] Refreshing rollups...")

        now = datetime.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        with get_db() as conn:
            # Journals
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM journals WHERE daemon_id = ?
            """, (self._daemon_id,))
            self._rollups["journals_total"] = cursor.fetchone()["count"]

            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM journals
                WHERE daemon_id = ? AND created_at >= ?
            """, (self._daemon_id, month_start.isoformat()))
            self._rollups["journals_this_month"] = cursor.fetchone()["count"]

            cursor = conn.execute("""
                SELECT MAX(date) as last_date FROM journals WHERE daemon_id = ?
            """, (self._daemon_id,))
            row = cursor.fetchone()
            self._rollups["last_journal_date"] = row["last_date"] if row else None

            # Threads
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM conversation_threads WHERE daemon_id = ?
            """, (self._daemon_id,))
            self._rollups["threads_total"] = cursor.fetchone()["count"]

            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM conversation_threads
                WHERE daemon_id = ? AND status = 'active'
            """, (self._daemon_id,))
            self._rollups["threads_active"] = cursor.fetchone()["count"]

            # Questions
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM open_questions WHERE daemon_id = ?
            """, (self._daemon_id,))
            self._rollups["questions_total"] = cursor.fetchone()["count"]

            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM open_questions
                WHERE daemon_id = ? AND status = 'open'
            """, (self._daemon_id,))
            self._rollups["questions_open"] = cursor.fetchone()["count"]

        # Embeddings (ChromaDB)
        if self._memory_core:
            self._rollups["embeddings_total"] = self._memory_core.count()
        else:
            self._rollups["embeddings_total"] = 0

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
