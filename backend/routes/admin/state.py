"""
Admin API routes for Global State Bus visibility.

Provides real-time access to Cass's current state, event stream, emotional arc,
and unified query interface for all registered queryable sources.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import get_db, json_deserialize
from state_bus import get_state_bus


# Pydantic model for query requests
class StateQueryRequest(BaseModel):
    """Request body for executing a state query."""
    source: str
    metric: Optional[str] = None
    time_preset: Optional[str] = None
    aggregation: Optional[str] = None
    group_by: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None

router = APIRouter()


def get_effective_daemon_id(daemon_id: Optional[str] = None) -> str:
    """Get effective daemon ID - uses provided one or falls back to global default."""
    if daemon_id:
        return daemon_id
    from database import get_daemon_id
    return get_daemon_id()


@router.get("/state")
async def get_current_state(
    daemon_id: Optional[str] = Query(None, description="Daemon ID (defaults to primary daemon)")
):
    """
    Get current global state for a daemon.

    Returns emotional, activity, coherence, and relational states.
    """
    d_id = get_effective_daemon_id(daemon_id)
    state_bus = get_state_bus(d_id)
    state = state_bus.read_state()

    return {
        "daemon_id": d_id,
        "timestamp": datetime.now().isoformat(),
        "emotional": state.emotional.to_dict(),
        "activity": state.activity.to_dict(),
        "coherence": state.coherence.to_dict(),
        "day_phase": state.day_phase.to_dict(),
        "relational": {
            user_id: rel.to_dict()
            for user_id, rel in state.relational.items()
        },
        "context_snapshot": state.get_context_snapshot(),
    }


@router.get("/state/events")
async def get_state_events(
    daemon_id: Optional[str] = Query(None, description="Daemon ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(50, ge=1, le=200, description="Maximum events to return"),
    since_hours: Optional[float] = Query(None, description="Only events in last N hours"),
):
    """
    Get recent state events from the event stream.

    Events include state deltas, session starts/ends, and custom events.
    """
    d_id = get_effective_daemon_id(daemon_id)
    state_bus = get_state_bus(d_id)

    events = state_bus.get_recent_events(limit=limit, event_type=event_type)

    # Filter by time if requested
    if since_hours:
        cutoff = datetime.now() - timedelta(hours=since_hours)
        events = [
            e for e in events
            if datetime.fromisoformat(e["created_at"]) > cutoff
        ]

    return {
        "daemon_id": d_id,
        "events": events,
        "total": len(events),
    }


@router.get("/state/emotional-arc")
async def get_emotional_arc(
    daemon_id: Optional[str] = Query(None, description="Daemon ID"),
    hours: float = Query(24, ge=1, le=168, description="Hours to look back"),
):
    """
    Get emotional state changes over time for visualization.

    Returns a time series of emotional snapshots for charting.
    """
    d_id = get_effective_daemon_id(daemon_id)
    cutoff = datetime.now() - timedelta(hours=hours)

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT data_json, created_at
            FROM state_events
            WHERE daemon_id = ?
              AND event_type = 'state_delta'
              AND created_at >= ?
            ORDER BY created_at ASC
        """, (d_id, cutoff.isoformat()))

        arc_points = []
        for row in cursor.fetchall():
            data = json_deserialize(row[0]) if row[0] else {}
            emotional = data.get("emotional_delta", {})

            if emotional:
                arc_points.append({
                    "timestamp": row[1],
                    "emotional_delta": emotional,
                    "source": data.get("source", "unknown"),
                    "reason": data.get("reason", ""),
                })

    # Also get current state as the latest point
    state_bus = get_state_bus(d_id)
    current = state_bus.read_state()

    return {
        "daemon_id": d_id,
        "hours": hours,
        "arc_points": arc_points,
        "current_state": current.emotional.to_dict(),
        "total_deltas": len(arc_points),
    }


@router.get("/state/activity-timeline")
async def get_activity_timeline(
    daemon_id: Optional[str] = Query(None, description="Daemon ID"),
    hours: float = Query(24, ge=1, le=168, description="Hours to look back"),
):
    """
    Get activity changes over time.

    Shows what Cass was doing when (chat, research, reflection, etc.)
    """
    d_id = get_effective_daemon_id(daemon_id)
    cutoff = datetime.now() - timedelta(hours=hours)

    with get_db() as conn:
        # Get session events
        cursor = conn.execute("""
            SELECT event_type, data_json, created_at
            FROM state_events
            WHERE daemon_id = ?
              AND event_type IN ('session.started', 'session.ended', 'state_delta')
              AND created_at >= ?
            ORDER BY created_at ASC
        """, (d_id, cutoff.isoformat()))

        timeline = []
        for row in cursor.fetchall():
            event_type = row[0]
            data = json_deserialize(row[1]) if row[1] else {}

            if event_type in ("session.started", "session.ended"):
                timeline.append({
                    "timestamp": row[2],
                    "event": event_type,
                    "activity_type": data.get("activity_type"),
                    "session_id": data.get("session_id"),
                })
            elif "activity_delta" in data:
                activity = data.get("activity_delta", {})
                if "current_activity" in activity:
                    timeline.append({
                        "timestamp": row[2],
                        "event": "activity_change",
                        "activity": activity["current_activity"],
                    })

    return {
        "daemon_id": d_id,
        "hours": hours,
        "timeline": timeline,
        "total_events": len(timeline),
    }


@router.get("/state/relational/{user_id}")
async def get_relational_state(
    user_id: str,
    daemon_id: Optional[str] = Query(None, description="Daemon ID"),
):
    """
    Get detailed relational state for a specific user.
    """
    d_id = get_effective_daemon_id(daemon_id)
    state_bus = get_state_bus(d_id)

    rel_state = state_bus.get_relational_state(user_id)

    if not rel_state:
        return {
            "daemon_id": d_id,
            "user_id": user_id,
            "exists": False,
            "state": None,
        }

    return {
        "daemon_id": d_id,
        "user_id": user_id,
        "exists": True,
        "state": rel_state.to_dict(),
    }


# =============================================================================
# Unified Query Interface Endpoints
# =============================================================================


@router.get("/state/sources")
async def list_queryable_sources(
    daemon_id: Optional[str] = Query(None, description="Daemon ID (defaults to primary daemon)")
):
    """
    List all registered queryable sources with their schemas.

    Returns available sources, their metrics, supported aggregations, and query options.
    Useful for understanding what data can be queried through the unified interface.
    """
    d_id = get_effective_daemon_id(daemon_id)
    state_bus = get_state_bus(d_id)

    schemas = state_bus.describe_sources()
    source_list = state_bus.list_sources()

    return {
        "daemon_id": d_id,
        "sources": source_list,
        "schemas": schemas,
        "total": len(source_list),
        "llm_description": state_bus.describe_sources_for_llm(),
    }


@router.post("/state/query")
async def execute_state_query(
    request: StateQueryRequest,
    daemon_id: Optional[str] = Query(None, description="Daemon ID (defaults to primary daemon)")
):
    """
    Execute a structured query against a registered queryable source.

    This provides a unified interface for querying any registered data source
    (github, tokens, emotional, etc.) with consistent query semantics.

    Example queries:
    - {"source": "github", "metric": "stars", "time_preset": "last_7d"}
    - {"source": "tokens", "metric": "cost_usd", "group_by": "day"}
    - {"source": "github", "metric": "clones", "filters": {"repo": "KohlJary/Temple-Codex"}}
    """
    d_id = get_effective_daemon_id(daemon_id)
    state_bus = get_state_bus(d_id)

    # Verify source exists
    if request.source not in state_bus.list_sources():
        raise HTTPException(
            status_code=404,
            detail=f"Source '{request.source}' not found. Available sources: {state_bus.list_sources()}"
        )

    # Build query from request
    from query_models import StateQuery, TimeRange, Aggregation

    time_range = None
    if request.time_preset:
        time_range = TimeRange(preset=request.time_preset)

    aggregation = None
    if request.aggregation:
        aggregation = Aggregation(function=request.aggregation)

    query = StateQuery(
        source=request.source,
        metric=request.metric,
        time_range=time_range,
        aggregation=aggregation,
        group_by=request.group_by,
        filters=request.filters,
    )

    try:
        result = await state_bus.query(query)

        return {
            "daemon_id": d_id,
            "query": {
                "source": request.source,
                "metric": request.metric,
                "time_preset": request.time_preset,
                "aggregation": request.aggregation,
                "group_by": request.group_by,
                "filters": request.filters,
            },
            "result": {
                "data": result.data.to_dict() if result.data else None,
                "formatted": result.format_for_llm(),
                "timestamp": result.timestamp.isoformat(),
                "is_stale": result.is_stale,
            },
            "metadata": result.metadata,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Query failed: {str(e)}"
        )


@router.get("/state/rollups")
async def get_rollup_summary(
    daemon_id: Optional[str] = Query(None, description="Daemon ID (defaults to primary daemon)")
):
    """
    Get precomputed rollup aggregates from all registered sources.

    Returns cached rollup data that provides quick access to common metrics
    without requiring full queries. Useful for dashboards and status displays.

    Each source maintains its own rollups based on its refresh strategy:
    - SCHEDULED: Refreshed periodically in the background
    - LAZY: Computed on first access, cached with TTL
    - EVENT_DRIVEN: Refreshed when underlying data changes
    """
    d_id = get_effective_daemon_id(daemon_id)
    state_bus = get_state_bus(d_id)

    rollups = state_bus.get_rollup_summary()

    return {
        "daemon_id": d_id,
        "timestamp": datetime.now().isoformat(),
        "rollups": rollups,
        "sources_with_rollups": list(rollups.keys()),
    }


@router.post("/state/rollups/refresh")
async def refresh_all_rollups(
    daemon_id: Optional[str] = Query(None, description="Daemon ID (defaults to primary daemon)")
):
    """
    Force refresh of all source rollups.

    Triggers an immediate recomputation of rollup aggregates for all sources.
    Useful after manual data updates or for debugging.
    """
    d_id = get_effective_daemon_id(daemon_id)
    state_bus = get_state_bus(d_id)

    await state_bus.refresh_all_rollups()

    return {
        "daemon_id": d_id,
        "status": "refreshed",
        "timestamp": datetime.now().isoformat(),
        "sources_refreshed": state_bus.list_sources(),
    }


@router.post("/state/rollups/{source_id}/refresh")
async def refresh_source_rollups(
    source_id: str,
    daemon_id: Optional[str] = Query(None, description="Daemon ID (defaults to primary daemon)")
):
    """
    Force refresh of rollups for a specific source.
    """
    d_id = get_effective_daemon_id(daemon_id)
    state_bus = get_state_bus(d_id)

    if source_id not in state_bus.list_sources():
        raise HTTPException(
            status_code=404,
            detail=f"Source '{source_id}' not found. Available sources: {state_bus.list_sources()}"
        )

    # Get the source and refresh its rollups
    source = state_bus._queryable_sources.get(source_id)
    if source:
        await source.refresh_rollups()

    return {
        "daemon_id": d_id,
        "source": source_id,
        "status": "refreshed",
        "timestamp": datetime.now().isoformat(),
    }


# === Capability Discovery Endpoints ===


class CapabilitySearchRequest(BaseModel):
    """Request body for semantic capability search."""
    query: str
    limit: int = 5
    source: Optional[str] = None
    tags: Optional[list] = None


@router.get("/state/capabilities")
async def list_capabilities(
    daemon_id: Optional[str] = Query(None, description="Daemon ID (defaults to primary daemon)")
):
    """
    List all registered capabilities grouped by source.

    Returns all queryable metrics from all registered sources with their
    semantic summaries and metadata. Useful for understanding what data
    is available to query.
    """
    d_id = get_effective_daemon_id(daemon_id)
    state_bus = get_state_bus(d_id)

    capabilities = await state_bus.list_all_capabilities()

    # Also include source schemas for context
    schemas = state_bus.describe_sources()

    return {
        "daemon_id": d_id,
        "timestamp": datetime.now().isoformat(),
        "sources": list(capabilities.keys()),
        "capabilities": capabilities,
        "schemas": schemas,
    }


@router.post("/state/capabilities/search")
async def search_capabilities(
    request: CapabilitySearchRequest,
    daemon_id: Optional[str] = Query(None, description="Daemon ID (defaults to primary daemon)")
):
    """
    Search for capabilities using natural language.

    Semantically matches your query against registered capabilities
    to find relevant data sources and metrics.

    Examples:
    - {"query": "user engagement metrics"}
    - {"query": "how much are we spending on tokens?"}
    - {"query": "repository activity", "source": "github"}
    """
    d_id = get_effective_daemon_id(daemon_id)
    state_bus = get_state_bus(d_id)

    matches = await state_bus.find_capabilities(
        query=request.query,
        limit=request.limit,
        source_filter=request.source,
        tag_filter=request.tags,
    )

    return {
        "daemon_id": d_id,
        "query": request.query,
        "timestamp": datetime.now().isoformat(),
        "matches": [m.to_dict() for m in matches],
        "formatted": state_bus.format_capabilities_for_llm(matches),
    }
