"""
Thymos Persistence

Database operations for storing and retrieving Thymos state.
"""

import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from database.connection import get_db
from .models import AffectState, NeedsState, FeltState, SuggestedGoal


# =============================================================================
# STATE PERSISTENCE
# =============================================================================

def save_thymos_state(
    daemon_id: str,
    affect_state: AffectState,
    needs_state: NeedsState,
    felt_state: Optional[FeltState] = None
) -> None:
    """
    Save current Thymos state to database.

    Upserts into thymos_state table.
    """
    with get_db() as conn:
        affect_json = json.dumps(affect_state.to_dict())
        needs_json = json.dumps(needs_state.to_dict())
        felt_state_text = felt_state.summary if felt_state else None
        now = datetime.now().isoformat()

        conn.execute("""
            INSERT INTO thymos_state (daemon_id, affect_json, needs_json, felt_state, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(daemon_id) DO UPDATE SET
                affect_json = excluded.affect_json,
                needs_json = excluded.needs_json,
                felt_state = excluded.felt_state,
                updated_at = excluded.updated_at
        """, (daemon_id, affect_json, needs_json, felt_state_text, now))


def load_thymos_state(daemon_id: str) -> Optional[tuple[AffectState, NeedsState, Optional[str]]]:
    """
    Load Thymos state from database.

    Returns (affect_state, needs_state, felt_state_text) or None if not found.
    """
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT affect_json, needs_json, felt_state
            FROM thymos_state
            WHERE daemon_id = ?
        """, (daemon_id,))
        row = cursor.fetchone()

    if not row:
        return None

    affect_state = AffectState.from_dict(json.loads(row[0]))
    needs_state = NeedsState.from_dict(json.loads(row[1]))
    felt_state_text = row[2]

    return affect_state, needs_state, felt_state_text


# =============================================================================
# SNAPSHOTS
# =============================================================================

def save_thymos_snapshot(
    daemon_id: str,
    affect_state: AffectState,
    needs_state: NeedsState,
    felt_state: Optional[FeltState] = None,
    trigger_event: Optional[str] = None
) -> str:
    """
    Save a snapshot of Thymos state (for history).

    Returns the snapshot ID.
    """
    snapshot_id = f"snapshot-{uuid4().hex[:12]}"
    now = datetime.now().isoformat()

    with get_db() as conn:
        conn.execute("""
            INSERT INTO thymos_snapshots
            (id, daemon_id, snapshot_at, affect_json, needs_json, felt_state, trigger_event)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_id,
            daemon_id,
            now,
            json.dumps(affect_state.to_dict()),
            json.dumps(needs_state.to_dict()),
            felt_state.summary if felt_state else None,
            trigger_event
        ))

    return snapshot_id


def get_thymos_snapshots(
    daemon_id: str,
    limit: int = 100,
    since: Optional[datetime] = None
) -> list[dict]:
    """
    Get recent Thymos snapshots.

    Returns list of snapshot dicts with parsed state.
    """
    with get_db() as conn:
        if since:
            cursor = conn.execute("""
                SELECT id, snapshot_at, affect_json, needs_json, felt_state, trigger_event
                FROM thymos_snapshots
                WHERE daemon_id = ? AND snapshot_at >= ?
                ORDER BY snapshot_at DESC
                LIMIT ?
            """, (daemon_id, since.isoformat(), limit))
        else:
            cursor = conn.execute("""
                SELECT id, snapshot_at, affect_json, needs_json, felt_state, trigger_event
                FROM thymos_snapshots
                WHERE daemon_id = ?
                ORDER BY snapshot_at DESC
                LIMIT ?
            """, (daemon_id, limit))

        rows = cursor.fetchall()

    snapshots = []
    for row in rows:
        snapshots.append({
            "id": row[0],
            "snapshot_at": row[1],
            "affect": json.loads(row[2]),
            "needs": json.loads(row[3]),
            "felt_state": row[4],
            "trigger_event": row[5],
        })

    return snapshots


# =============================================================================
# SUGGESTIONS (SHADOW MODE LOG)
# =============================================================================

def save_suggestion(daemon_id: str, suggestion: SuggestedGoal) -> None:
    """Save a goal suggestion to the shadow log."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO thymos_suggestions
            (id, daemon_id, suggested_at, need_name, need_current, need_threshold,
             urgency, suggested_action, is_urgent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            suggestion.id,
            daemon_id,
            suggestion.suggested_at.isoformat(),
            suggestion.need_name,
            suggestion.need_current,
            suggestion.need_threshold,
            suggestion.urgency,
            suggestion.suggested_action,
            1 if suggestion.is_urgent else 0
        ))


def get_suggestions(
    daemon_id: str,
    limit: int = 50,
    since: Optional[datetime] = None
) -> list[dict]:
    """Get recent goal suggestions from shadow log."""
    with get_db() as conn:
        if since:
            cursor = conn.execute("""
                SELECT id, suggested_at, need_name, need_current, need_threshold,
                       urgency, suggested_action, is_urgent, feedback, feedback_at
                FROM thymos_suggestions
                WHERE daemon_id = ? AND suggested_at >= ?
                ORDER BY suggested_at DESC
                LIMIT ?
            """, (daemon_id, since.isoformat(), limit))
        else:
            cursor = conn.execute("""
                SELECT id, suggested_at, need_name, need_current, need_threshold,
                       urgency, suggested_action, is_urgent, feedback, feedback_at
                FROM thymos_suggestions
                WHERE daemon_id = ?
                ORDER BY suggested_at DESC
                LIMIT ?
            """, (daemon_id, limit))

        rows = cursor.fetchall()

    suggestions = []
    for row in rows:
        suggestions.append({
            "id": row[0],
            "suggested_at": row[1],
            "need_name": row[2],
            "need_current": row[3],
            "need_threshold": row[4],
            "urgency": row[5],
            "suggested_action": row[6],
            "is_urgent": bool(row[7]),
            "feedback": row[8],
            "feedback_at": row[9],
        })

    return suggestions


def add_suggestion_feedback(suggestion_id: str, feedback: str) -> bool:
    """
    Add feedback to a suggestion.

    Used for calibration - track whether suggestions were good/bad.
    Returns True if suggestion was found and updated.
    """
    now = datetime.now().isoformat()

    with get_db() as conn:
        cursor = conn.execute("""
            UPDATE thymos_suggestions
            SET feedback = ?, feedback_at = ?
            WHERE id = ?
        """, (feedback, now, suggestion_id))

        return cursor.rowcount > 0


# =============================================================================
# ANALYTICS
# =============================================================================

def get_need_trends(
    daemon_id: str,
    need_name: str,
    hours: int = 24  # TODO: Filter by time window
) -> list[tuple[str, float]]:
    """
    Get trend data for a specific need.

    Returns list of (timestamp, value) tuples.
    """
    # hours parameter reserved for future time-based filtering
    _ = hours  # Suppress unused warning

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT snapshot_at, needs_json
            FROM thymos_snapshots
            WHERE daemon_id = ?
            ORDER BY snapshot_at DESC
            LIMIT 100
        """, (daemon_id,))

        rows = cursor.fetchall()

    trends = []
    for row in rows:
        needs = json.loads(row[1])
        if need_name in needs:
            trends.append((row[0], needs[need_name].get("current", 0.5)))

    return trends


def get_affect_trends(
    daemon_id: str,
    dimension: str,
    hours: int = 24  # TODO: Filter by time window
) -> list[tuple[str, float]]:
    """
    Get trend data for a specific affect dimension.

    Returns list of (timestamp, value) tuples.
    """
    # hours parameter reserved for future time-based filtering
    _ = hours  # Suppress unused warning
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT snapshot_at, affect_json
            FROM thymos_snapshots
            WHERE daemon_id = ?
            ORDER BY snapshot_at DESC
            LIMIT 100
        """, (daemon_id,))

        rows = cursor.fetchall()

    trends = []
    for row in rows:
        affect = json.loads(row[1])
        if dimension in affect:
            trends.append((row[0], affect[dimension]))

    return trends
