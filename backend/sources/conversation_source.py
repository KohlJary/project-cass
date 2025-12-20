"""
Conversation Queryable Source

Wraps conversation/message data as a queryable source for the unified state query interface.
Provides access to conversation metrics: counts, activity, engagement patterns.

Refresh strategy: LAZY (data changes with user interaction, cache briefly)
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


class ConversationQueryableSource(QueryableSource):
    """
    Conversation and message data as a queryable source.

    Queries the conversations and messages tables directly for efficiency.
    Uses LAZY refresh since conversation activity is sporadic.
    """

    def __init__(self, daemon_id: str):
        """
        Initialize the conversation queryable source.

        Args:
            daemon_id: The daemon this source belongs to
        """
        super().__init__(daemon_id)

    @property
    def source_id(self) -> str:
        return "conversations"

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
                    name="total_conversations",
                    description="Total number of conversations",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="conversations",
                ),
                MetricDefinition(
                    name="conversations_created",
                    description="Conversations created in time period",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="conversations",
                ),
                MetricDefinition(
                    name="total_messages",
                    description="Total number of messages",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="messages",
                ),
                MetricDefinition(
                    name="messages_sent",
                    description="Messages sent in time period",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="messages",
                ),
                MetricDefinition(
                    name="user_messages",
                    description="User messages in time period",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="messages",
                ),
                MetricDefinition(
                    name="assistant_messages",
                    description="Assistant (Cass) messages in time period",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="messages",
                ),
                MetricDefinition(
                    name="avg_messages_per_conversation",
                    description="Average messages per conversation",
                    data_type="float",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="messages",
                ),
                MetricDefinition(
                    name="active_conversations",
                    description="Conversations with activity in time period",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=True,
                    unit="conversations",
                ),
                MetricDefinition(
                    name="avg_conversation_length",
                    description="Average character length of messages",
                    data_type="float",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="characters",
                ),
            ],
            aggregations=["sum", "avg", "count", "max", "min", "latest"],
            group_by_options=["day", "hour", "role", "user"],
            filter_keys=["role", "user_id", "project_id"],
            rollups=["daily", "weekly"],
        )

    async def execute_query(self, query: StateQuery) -> QueryResult:
        """
        Execute a query against conversation/message data.
        """
        # Resolve time range
        start, end = query.time_range.resolve() if query.time_range else (
            datetime.now() - timedelta(days=7),
            datetime.now()
        )

        # Get the metric to query
        metric = query.metric or "total_messages"

        # Handle different query patterns
        if query.group_by in ["day", "hour"]:
            data = await self._query_timeseries(metric, start, end, query.group_by, query.filters)
        elif query.group_by == "role":
            data = await self._query_by_role(metric, start, end, query.filters)
        elif query.group_by == "user":
            data = await self._query_by_user(metric, start, end, query.filters)
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
        """Query for time series data grouped by day or hour."""
        with get_db() as conn:
            # Format for grouping
            if granularity == "hour":
                date_format = "%Y-%m-%d %H:00"
                strftime_format = "%Y-%m-%d %H:00"
            else:  # day
                date_format = "%Y-%m-%d"
                strftime_format = "%Y-%m-%d"

            # Build query based on metric
            if metric in ["total_conversations", "conversations_created"]:
                # Query conversations table
                query_sql = f"""
                    SELECT strftime('{strftime_format}', created_at) as period,
                           COUNT(*) as value
                    FROM conversations
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
            elif metric == "active_conversations":
                # Conversations with messages in period
                query_sql = f"""
                    SELECT strftime('{strftime_format}', m.timestamp) as period,
                           COUNT(DISTINCT m.conversation_id) as value
                    FROM messages m
                    JOIN conversations c ON c.id = m.conversation_id
                    WHERE c.daemon_id = ?
                      AND m.timestamp >= ?
                      AND m.timestamp <= ?
                    GROUP BY period
                    ORDER BY period
                """
                cursor = conn.execute(query_sql, (
                    self._daemon_id,
                    start.isoformat(),
                    end.isoformat()
                ))
            else:
                # Query messages table
                role_filter = ""
                params = [self._daemon_id, start.isoformat(), end.isoformat()]

                if metric == "user_messages":
                    role_filter = "AND m.role = 'user'"
                elif metric == "assistant_messages":
                    role_filter = "AND m.role = 'assistant'"

                if filters:
                    if filters.get("role"):
                        role_filter = f"AND m.role = '{filters['role']}'"
                    if filters.get("user_id"):
                        role_filter += f" AND m.user_id = '{filters['user_id']}'"

                query_sql = f"""
                    SELECT strftime('{strftime_format}', m.timestamp) as period,
                           COUNT(*) as value
                    FROM messages m
                    JOIN conversations c ON c.id = m.conversation_id
                    WHERE c.daemon_id = ?
                      AND m.timestamp >= ?
                      AND m.timestamp <= ?
                      {role_filter}
                    GROUP BY period
                    ORDER BY period
                """
                cursor = conn.execute(query_sql, params)

            series = [
                {"date": row["period"], "value": row["value"]}
                for row in cursor.fetchall()
            ]

        return QueryResultData(series=series)

    async def _query_by_role(
        self,
        metric: str,
        start: datetime,
        end: datetime,
        filters: Optional[Dict] = None
    ) -> QueryResultData:
        """Query messages grouped by role (user/assistant)."""
        with get_db() as conn:
            query_sql = """
                SELECT m.role, COUNT(*) as count
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE c.daemon_id = ?
                  AND m.timestamp >= ?
                  AND m.timestamp <= ?
                GROUP BY m.role
            """
            cursor = conn.execute(query_sql, (
                self._daemon_id,
                start.isoformat(),
                end.isoformat()
            ))

            series = [
                {"role": row["role"], "value": row["count"]}
                for row in cursor.fetchall()
            ]

        return QueryResultData(series=series)

    async def _query_by_user(
        self,
        metric: str,
        start: datetime,
        end: datetime,
        filters: Optional[Dict] = None
    ) -> QueryResultData:
        """Query messages grouped by user."""
        with get_db() as conn:
            query_sql = """
                SELECT COALESCE(m.user_id, 'anonymous') as user_id, COUNT(*) as count
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE c.daemon_id = ?
                  AND m.timestamp >= ?
                  AND m.timestamp <= ?
                  AND m.role = 'user'
                GROUP BY m.user_id
                ORDER BY count DESC
            """
            cursor = conn.execute(query_sql, (
                self._daemon_id,
                start.isoformat(),
                end.isoformat()
            ))

            series = [
                {"user": row["user_id"], "value": row["count"]}
                for row in cursor.fetchall()
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
        with get_db() as conn:
            if metric == "total_conversations":
                cursor = conn.execute("""
                    SELECT COUNT(*) as value
                    FROM conversations
                    WHERE daemon_id = ?
                """, (self._daemon_id,))
                value = cursor.fetchone()["value"]

            elif metric == "conversations_created":
                cursor = conn.execute("""
                    SELECT COUNT(*) as value
                    FROM conversations
                    WHERE daemon_id = ?
                      AND created_at >= ?
                      AND created_at <= ?
                """, (self._daemon_id, start.isoformat(), end.isoformat()))
                value = cursor.fetchone()["value"]

            elif metric == "total_messages":
                cursor = conn.execute("""
                    SELECT COUNT(*) as value
                    FROM messages m
                    JOIN conversations c ON c.id = m.conversation_id
                    WHERE c.daemon_id = ?
                """, (self._daemon_id,))
                value = cursor.fetchone()["value"]

            elif metric in ["messages_sent", "user_messages", "assistant_messages"]:
                role_filter = ""
                if metric == "user_messages":
                    role_filter = "AND m.role = 'user'"
                elif metric == "assistant_messages":
                    role_filter = "AND m.role = 'assistant'"

                cursor = conn.execute(f"""
                    SELECT COUNT(*) as value
                    FROM messages m
                    JOIN conversations c ON c.id = m.conversation_id
                    WHERE c.daemon_id = ?
                      AND m.timestamp >= ?
                      AND m.timestamp <= ?
                      {role_filter}
                """, (self._daemon_id, start.isoformat(), end.isoformat()))
                value = cursor.fetchone()["value"]

            elif metric == "active_conversations":
                cursor = conn.execute("""
                    SELECT COUNT(DISTINCT m.conversation_id) as value
                    FROM messages m
                    JOIN conversations c ON c.id = m.conversation_id
                    WHERE c.daemon_id = ?
                      AND m.timestamp >= ?
                      AND m.timestamp <= ?
                """, (self._daemon_id, start.isoformat(), end.isoformat()))
                value = cursor.fetchone()["value"]

            elif metric == "avg_messages_per_conversation":
                cursor = conn.execute("""
                    SELECT AVG(msg_count) as value FROM (
                        SELECT COUNT(*) as msg_count
                        FROM messages m
                        JOIN conversations c ON c.id = m.conversation_id
                        WHERE c.daemon_id = ?
                        GROUP BY m.conversation_id
                    )
                """, (self._daemon_id,))
                row = cursor.fetchone()
                value = round(row["value"] or 0, 2)

            elif metric == "avg_conversation_length":
                cursor = conn.execute("""
                    SELECT AVG(LENGTH(content)) as value
                    FROM messages m
                    JOIN conversations c ON c.id = m.conversation_id
                    WHERE c.daemon_id = ?
                      AND m.timestamp >= ?
                      AND m.timestamp <= ?
                """, (self._daemon_id, start.isoformat(), end.isoformat()))
                row = cursor.fetchone()
                value = round(row["value"] or 0, 2)

            else:
                value = 0

        return QueryResultData(value=value)

    def get_precomputed_rollups(self) -> Dict[str, Any]:
        """Return cached rollup aggregates."""
        return {
            "conversations_total": self._rollups.get("conversations_total", 0),
            "conversations_today": self._rollups.get("conversations_today", 0),
            "conversations_7d": self._rollups.get("conversations_7d", 0),
            "messages_total": self._rollups.get("messages_total", 0),
            "messages_today": self._rollups.get("messages_today", 0),
            "messages_7d": self._rollups.get("messages_7d", 0),
            "last_activity": self._rollups.get("last_activity"),
            "last_refresh": self._last_rollup_refresh.isoformat() if self._last_rollup_refresh else None,
        }

    async def refresh_rollups(self) -> None:
        """Recompute rolling aggregates from conversation data."""
        logger.debug(f"[{self.source_id}] Refreshing rollups...")

        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)

        with get_db() as conn:
            # Total conversations
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM conversations WHERE daemon_id = ?
            """, (self._daemon_id,))
            self._rollups["conversations_total"] = cursor.fetchone()["count"]

            # Conversations today
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM conversations
                WHERE daemon_id = ? AND created_at >= ?
            """, (self._daemon_id, today_start.isoformat()))
            self._rollups["conversations_today"] = cursor.fetchone()["count"]

            # Conversations 7d
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM conversations
                WHERE daemon_id = ? AND created_at >= ?
            """, (self._daemon_id, week_start.isoformat()))
            self._rollups["conversations_7d"] = cursor.fetchone()["count"]

            # Total messages
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE c.daemon_id = ?
            """, (self._daemon_id,))
            self._rollups["messages_total"] = cursor.fetchone()["count"]

            # Messages today
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE c.daemon_id = ? AND m.timestamp >= ?
            """, (self._daemon_id, today_start.isoformat()))
            self._rollups["messages_today"] = cursor.fetchone()["count"]

            # Messages 7d
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE c.daemon_id = ? AND m.timestamp >= ?
            """, (self._daemon_id, week_start.isoformat()))
            self._rollups["messages_7d"] = cursor.fetchone()["count"]

            # Last activity
            cursor = conn.execute("""
                SELECT MAX(m.timestamp) as last_ts
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE c.daemon_id = ?
            """, (self._daemon_id,))
            row = cursor.fetchone()
            self._rollups["last_activity"] = row["last_ts"] if row else None

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
