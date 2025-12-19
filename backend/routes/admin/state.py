"""
Admin API routes for Global State Bus visibility.

Provides real-time access to Cass's current state, event stream, and emotional arc.
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Query

from database import get_db, json_deserialize
from state_bus import get_state_bus

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
