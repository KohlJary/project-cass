"""
Daily Activity Dashboard API

Aggregates all Cass activity for a given day into a unified view.
Uses a registry pattern for extensibility - add new sources by
registering them in ACTIVITY_SOURCES.
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Callable
from datetime import date, datetime
from dataclasses import dataclass
import sqlite3
import json
import logging

router = APIRouter(prefix="/daily-activity", tags=["admin-daily-activity"])


def _get_db():
    """Get database connection."""
    from database import get_db
    return get_db()
logger = logging.getLogger(__name__)

# Module-level daemon_id
_daemon_id: str = "cass"


def init_daily_activity_routes(daemon_id: str):
    """Initialize with daemon ID."""
    global _daemon_id
    _daemon_id = daemon_id


# =============================================================================
# ACTIVITY SOURCE REGISTRY
# =============================================================================

@dataclass
class ActivitySource:
    """
    Defines a source of daily activity data.

    To add a new source:
    1. Define the source with table, timestamp_field, etc.
    2. Add it to ACTIVITY_SOURCES dict
    3. Optionally add a custom formatter

    The system will automatically query and include it.
    """
    id: str                          # Unique identifier (e.g., "spells")
    name: str                        # Display name (e.g., "Spell Executions")
    category: str                    # Category for grouping (e.g., "autonomous")
    table: str                       # SQLite table name
    timestamp_field: str             # Field to filter by date
    daemon_id_field: str = "daemon_id"  # Field for daemon filtering
    select_fields: str = "*"         # Fields to SELECT
    order_by: str = None             # Optional ORDER BY (defaults to timestamp)
    join_clause: str = ""            # Optional JOIN
    where_extra: str = ""            # Additional WHERE conditions
    formatter: Callable = None       # Optional result formatter
    icon: str = ""                  # Icon for UI


def default_formatter(row: Dict[str, Any], source: ActivitySource) -> Dict[str, Any]:
    """Default formatter - returns row as-is with metadata."""
    result = dict(row)
    result["_source"] = source.id
    result["_category"] = source.category
    return result


# -----------------------------------------------------------------------------
# SOURCE DEFINITIONS
# Add new sources here to extend the dashboard
# -----------------------------------------------------------------------------

ACTIVITY_SOURCES: Dict[str, ActivitySource] = {
    # === AUTONOMOUS ACTIONS ===
    "spells": ActivitySource(
        id="spells",
        name="Spell Executions",
        category="autonomous",
        table="grimoire_executions",
        timestamp_field="executed_at",
        select_fields="id, spell_name, trigger_type, status, executed_at, execution_time_ms, reason",
        icon="wand",
    ),
    "research_sessions": ActivitySource(
        id="research_sessions",
        name="Research Sessions",
        category="autonomous",
        table="research_sessions",
        timestamp_field="started_at",
        select_fields="id, mode, status, topic, started_at, ended_at, findings_summary",
        icon="microscope",
    ),
    "solo_reflections": ActivitySource(
        id="solo_reflections",
        name="Solo Reflections",
        category="autonomous",
        table="solo_reflections",
        timestamp_field="started_at",
        select_fields="id, type, status, focus_area, started_at, ended_at, insights_json",
        icon="brain",
    ),
    "work_items": ActivitySource(
        id="work_items",
        name="Work Items",
        category="autonomous",
        table="work_items",
        timestamp_field="created_at",
        select_fields="id, title, status, priority, created_at, completed_at",
        icon="clipboard",
    ),

    # === CONVERSATIONS ===
    "messages": ActivitySource(
        id="messages",
        name="Messages",
        category="conversations",
        table="messages",
        timestamp_field="timestamp",
        daemon_id_field="c.daemon_id",
        select_fields="m.id, m.conversation_id, m.role, m.content, m.timestamp, m.input_tokens, m.output_tokens, m.provider, m.model",
        join_clause="AS m JOIN conversations c ON m.conversation_id = c.id",
        order_by="m.timestamp",
        icon="message-circle",
    ),

    # === SELF-MODEL ===
    "observations": ActivitySource(
        id="observations",
        name="Self Observations",
        category="self_model",
        table="self_observations",
        timestamp_field="created_at",
        select_fields="id, category, observation, confidence, created_at, source_conversation_id",
        icon="eye",
    ),
    "growth_edges": ActivitySource(
        id="growth_edges",
        name="Growth Edges",
        category="self_model",
        table="growth_edges",
        timestamp_field="last_updated",
        select_fields="id, area, current_state, desired_state, importance, last_updated",
        icon="trending-up",
    ),
    "opinions": ActivitySource(
        id="opinions",
        name="Opinions Formed",
        category="self_model",
        table="opinions",
        timestamp_field="date_formed",
        select_fields="id, topic, position, confidence, rationale, date_formed",
        icon="thumbs-up",
    ),
    "questions": ActivitySource(
        id="questions",
        name="Open Questions",
        category="self_model",
        table="open_questions",
        timestamp_field="created_at",
        select_fields="id, question, question_type, importance, context, created_at, resolved_at",
        icon="help-circle",
    ),
    "milestones": ActivitySource(
        id="milestones",
        name="Milestones",
        category="self_model",
        table="milestones",
        timestamp_field="triggered_at",
        select_fields="id, name, description, significance, triggered_at",
        icon="flag",
    ),

    # === WORLD CONSUMPTION ===
    "articles": ActivitySource(
        id="articles",
        name="Articles Consumed",
        category="world",
        table="consumed_articles",
        timestamp_field="consumed_at",
        select_fields="id, headline, source, url, summary, tokens_used, consumed_at, observations_json, questions_json",
        icon="newspaper",
    ),
    "rss_items": ActivitySource(
        id="rss_items",
        name="RSS Items Processed",
        category="world",
        table="rss_items",
        timestamp_field="processed_at",
        select_fields="id, feed_id, title, link, processed, processed_at, skip_reason",
        where_extra="AND processed = 1",
        icon="rss",
    ),
    "wiki_updates": ActivitySource(
        id="wiki_updates",
        name="Wiki Updates",
        category="world",
        table="wiki_pages",
        timestamp_field="updated_at",
        select_fields="id, title, category, updated_at",
        icon="book",
    ),

    # === JOURNALS & DREAMS ===
    "journals": ActivitySource(
        id="journals",
        name="Journal Entries",
        category="journals",
        table="journals",
        timestamp_field="created_at",
        select_fields="id, date, content, mood, themes_json, created_at",
        icon="book-open",
    ),
    "dreams": ActivitySource(
        id="dreams",
        name="Dreams",
        category="journals",
        table="dreams",
        timestamp_field="created_at",
        select_fields="id, date, narrative, themes_json, emotions_json, created_at",
        icon="moon",
    ),

    # === EMOTIONAL STATE ===
    "thymos_snapshots": ActivitySource(
        id="thymos_snapshots",
        name="Emotional Snapshots",
        category="emotional",
        table="thymos_snapshots",
        timestamp_field="snapshot_at",
        select_fields="id, affect_json, needs_json, felt_state, snapshot_at, trigger_event",
        icon="heart",
    ),
    "state_events": ActivitySource(
        id="state_events",
        name="State Events",
        category="emotional",
        table="state_events",
        timestamp_field="created_at",
        select_fields="id, event_type, data_json, created_at",
        icon="activity",
    ),

    # === CREATIVE ===
    "images": ActivitySource(
        id="images",
        name="Generated Images",
        category="creative",
        table="generated_images",
        timestamp_field="created_at",
        select_fields="id, prompt, style, purpose, image_path, created_at",
        icon="image",
    ),
    "art_studies": ActivitySource(
        id="art_studies",
        name="Art Studies",
        category="creative",
        table="artwork_studies",
        timestamp_field="studied_at",
        select_fields="id, artwork_id, observations_json, techniques_json, emotional_response, studied_at",
        icon="palette",
    ),

    # === SOCIAL ===
    "user_observations": ActivitySource(
        id="user_observations",
        name="User Observations",
        category="social",
        table="user_observations",
        timestamp_field="created_at",
        select_fields="id, user_id, category, observation, confidence, created_at",
        icon="users",
    ),

    # === RESOURCES ===
    "token_usage": ActivitySource(
        id="token_usage",
        name="Token Usage",
        category="resources",
        table="token_usage_records",
        timestamp_field="timestamp",
        select_fields="id, category, provider, model, input_tokens, output_tokens, estimated_cost_usd, timestamp",
        icon="cpu",
    ),

    # === OUTREACH ===
    "outreach": ActivitySource(
        id="outreach",
        name="Outreach Drafts",
        category="outreach",
        table="outreach_drafts",
        timestamp_field="created_at",
        select_fields="id, type, recipient, subject, status, created_at, sent_at",
        icon="send",
    ),
}


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class ActivityItem(BaseModel):
    """Single activity item."""
    source: str
    category: str
    timestamp: str
    data: Dict[str, Any]


class CategorySummary(BaseModel):
    """Summary for a category."""
    category: str
    count: int
    items: List[Dict[str, Any]]


class DailyActivityResponse(BaseModel):
    """Full daily activity response."""
    date: str
    daemon_id: str

    # Timeline (all items chronologically)
    timeline: List[ActivityItem]

    # By category
    categories: Dict[str, CategorySummary]

    # Aggregates
    totals: Dict[str, int]

    # Token/cost summary
    token_summary: Optional[Dict[str, Any]] = None

    # Emotional arc (if available)
    emotional_arc: Optional[List[Dict[str, Any]]] = None


class AvailableSourcesResponse(BaseModel):
    """List of available activity sources."""
    sources: List[Dict[str, str]]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def query_source(
    conn: sqlite3.Connection,
    source: ActivitySource,
    target_date: str,
    daemon_id: str,
) -> List[Dict[str, Any]]:
    """Query a single activity source for a given date."""

    # Build the query
    table_clause = f"{source.table} {source.join_clause}" if source.join_clause else source.table
    order_clause = source.order_by or source.timestamp_field

    query = f"""
        SELECT {source.select_fields}
        FROM {table_clause}
        WHERE {source.daemon_id_field} = ?
          AND date({source.timestamp_field}) = ?
          {source.where_extra}
        ORDER BY {order_clause}
    """

    try:
        cursor = conn.execute(query, (daemon_id, target_date))
        columns = [desc[0] for desc in cursor.description]
        rows = []
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            # Parse any JSON fields
            for key, value in row_dict.items():
                if key.endswith("_json") and value:
                    try:
                        row_dict[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        pass
            rows.append(row_dict)
        return rows
    except sqlite3.OperationalError as e:
        # Table might not exist or have different schema
        logger.debug(f"Query failed for {source.id}: {e}")
        return []


def get_token_summary(
    conn: sqlite3.Connection,
    target_date: str,
    daemon_id: str,
) -> Dict[str, Any]:
    """Get aggregated token usage for the day."""
    query = """
        SELECT
            category,
            provider,
            model,
            SUM(input_tokens) as input_tokens,
            SUM(output_tokens) as output_tokens,
            SUM(estimated_cost_usd) as cost_usd
        FROM token_usage_records
        WHERE daemon_id = ?
          AND date(timestamp) = ?
        GROUP BY category, provider, model
        ORDER BY cost_usd DESC
    """

    try:
        cursor = conn.execute(query, (daemon_id, target_date))
        rows = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]

        total_input = sum(r.get("input_tokens", 0) or 0 for r in rows)
        total_output = sum(r.get("output_tokens", 0) or 0 for r in rows)
        total_cost = sum(r.get("cost_usd", 0) or 0 for r in rows)

        return {
            "by_category": rows,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cost_usd": round(total_cost, 4),
        }
    except sqlite3.OperationalError:
        return {}


def get_emotional_arc(
    conn: sqlite3.Connection,
    target_date: str,
    daemon_id: str,
) -> List[Dict[str, Any]]:
    """Get emotional state progression throughout the day."""
    query = """
        SELECT snapshot_at, affect_json, needs_json, felt_state, trigger_event
        FROM thymos_snapshots
        WHERE daemon_id = ?
          AND date(snapshot_at) = ?
        ORDER BY snapshot_at
    """

    try:
        cursor = conn.execute(query, (daemon_id, target_date))
        arc = []
        for row in cursor.fetchall():
            snapshot = {
                "timestamp": row[0],
                "felt_state": row[3],
                "trigger": row[4],
            }
            if row[1]:
                try:
                    snapshot["affect"] = json.loads(row[1])
                except json.JSONDecodeError:
                    pass
            if row[2]:
                try:
                    snapshot["needs"] = json.loads(row[2])
                except json.JSONDecodeError:
                    pass
            arc.append(snapshot)
        return arc
    except sqlite3.OperationalError:
        return []


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/sources", response_model=AvailableSourcesResponse)
async def list_sources():
    """List all available activity sources."""
    sources = [
        {
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "icon": s.icon,
        }
        for s in ACTIVITY_SOURCES.values()
    ]
    return AvailableSourcesResponse(sources=sources)


@router.get("/{target_date}", response_model=DailyActivityResponse)
async def get_daily_activity(
    target_date: str,
    sources: Optional[str] = Query(None, description="Comma-separated source IDs to include (default: all)"),
    categories: Optional[str] = Query(None, description="Comma-separated categories to include"),
    include_content: bool = Query(True, description="Include full content (set false for summary)"),
):
    """
    Get all activity for a specific date.

    Args:
        target_date: Date in YYYY-MM-DD format
        sources: Optional filter for specific sources
        categories: Optional filter for specific categories
        include_content: Whether to include full message/article content
    """
    # Parse filters
    source_filter = set(sources.split(",")) if sources else None
    category_filter = set(categories.split(",")) if categories else None

    # Determine which sources to query
    sources_to_query = []
    for source_id, source in ACTIVITY_SOURCES.items():
        if source_filter and source_id not in source_filter:
            continue
        if category_filter and source.category not in category_filter:
            continue
        sources_to_query.append(source)

    # Query all sources
    with _get_db() as conn:
        all_items: List[ActivityItem] = []
        categories_data: Dict[str, List[Dict[str, Any]]] = {}
        totals: Dict[str, int] = {}

        for source in sources_to_query:
            rows = query_source(conn, source, target_date, _daemon_id)

            # Get timestamp field name (handle aliased fields)
            ts_field = source.timestamp_field.split(".")[-1]  # Handle m.timestamp -> timestamp

            for row in rows:
                # Optionally strip large content
                if not include_content:
                    for key in ["content", "full_content", "narrative", "summary"]:
                        if key in row and row[key] and len(str(row[key])) > 200:
                            row[key] = str(row[key])[:200] + "..."

                item = ActivityItem(
                    source=source.id,
                    category=source.category,
                    timestamp=row.get(ts_field, row.get("timestamp", "")),
                    data=row,
                )
                all_items.append(item)

                # Group by category
                if source.category not in categories_data:
                    categories_data[source.category] = []
                categories_data[source.category].append(row)

            # Track totals
            totals[source.id] = len(rows)

        # Sort timeline by timestamp
        all_items.sort(key=lambda x: x.timestamp or "")

        # Build category summaries
        category_summaries = {
            cat: CategorySummary(
                category=cat,
                count=len(items),
                items=items,
            )
            for cat, items in categories_data.items()
        }

        # Get additional aggregates
        token_summary = get_token_summary(conn, target_date, _daemon_id)
        emotional_arc = get_emotional_arc(conn, target_date, _daemon_id)

    return DailyActivityResponse(
        date=target_date,
        daemon_id=_daemon_id,
        timeline=all_items,
        categories=category_summaries,
        totals=totals,
        token_summary=token_summary if token_summary else None,
        emotional_arc=emotional_arc if emotional_arc else None,
    )


@router.get("/{target_date}/summary")
async def get_daily_summary(target_date: str):
    """
    Get a lightweight summary of daily activity (counts only).
    """
    with _get_db() as conn:
        summary = {
            "date": target_date,
            "daemon_id": _daemon_id,
            "counts": {},
            "categories": {},
        }

        for source_id, source in ACTIVITY_SOURCES.items():
            # Build count query
            table_clause = f"{source.table} {source.join_clause}" if source.join_clause else source.table

            query = f"""
                SELECT COUNT(*) FROM {table_clause}
                WHERE {source.daemon_id_field} = ?
                  AND date({source.timestamp_field}) = ?
                  {source.where_extra}
            """

            try:
                count = conn.execute(query, (_daemon_id, target_date)).fetchone()[0]
                summary["counts"][source_id] = count

                # Aggregate by category
                if source.category not in summary["categories"]:
                    summary["categories"][source.category] = 0
                summary["categories"][source.category] += count
            except sqlite3.OperationalError:
                summary["counts"][source_id] = 0

        # Add token summary
        summary["tokens"] = get_token_summary(conn, target_date, _daemon_id)

    return summary


@router.get("/range/{start_date}/{end_date}/summary")
async def get_date_range_summary(start_date: str, end_date: str):
    """
    Get activity summaries for a date range.
    Useful for calendar heatmaps.
    """
    with _get_db() as conn:
        # Query each major category for date range
        results = {}

        # Messages per day
        try:
            cursor = conn.execute("""
                SELECT date(m.timestamp) as day, COUNT(*) as count
                FROM messages m
                JOIN conversations c ON m.conversation_id = c.id
                WHERE c.daemon_id = ?
                  AND date(m.timestamp) BETWEEN ? AND ?
                GROUP BY day
            """, (_daemon_id, start_date, end_date))
            results["messages"] = {row[0]: row[1] for row in cursor.fetchall()}
        except:
            results["messages"] = {}

        # Spells per day
        try:
            cursor = conn.execute("""
                SELECT date(executed_at) as day, COUNT(*) as count
                FROM grimoire_executions
                WHERE daemon_id = ?
                  AND date(executed_at) BETWEEN ? AND ?
                GROUP BY day
            """, (_daemon_id, start_date, end_date))
            results["spells"] = {row[0]: row[1] for row in cursor.fetchall()}
        except:
            results["spells"] = {}

        # Articles per day
        try:
            cursor = conn.execute("""
                SELECT date(consumed_at) as day, COUNT(*) as count
                FROM consumed_articles
                WHERE daemon_id = ?
                  AND date(consumed_at) BETWEEN ? AND ?
                GROUP BY day
            """, (_daemon_id, start_date, end_date))
            results["articles"] = {row[0]: row[1] for row in cursor.fetchall()}
        except:
            results["articles"] = {}

        # Self-model changes per day (observations)
        try:
            cursor = conn.execute("""
                SELECT date(created_at) as day, COUNT(*) as count
                FROM self_observations
                WHERE daemon_id = ?
                  AND date(created_at) BETWEEN ? AND ?
                GROUP BY day
            """, (_daemon_id, start_date, end_date))
            results["observations"] = {row[0]: row[1] for row in cursor.fetchall()}
        except:
            results["observations"] = {}

    return {
        "start_date": start_date,
        "end_date": end_date,
        "daemon_id": _daemon_id,
        "activity": results,
    }
