"""
Grimoire Persistence

Database operations for storing and retrieving Grimoire spell state.
"""

import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

from database.connection import get_db


# =============================================================================
# SPELL STATE PERSISTENCE
# =============================================================================

def save_spell_state(
    daemon_id: str,
    spell_name: str,
    last_executed_at: Optional[float] = None,
    timer_last_run_at: Optional[float] = None,
) -> None:
    """
    Save or update spell state (cooldowns and timer tracking).

    Upserts into grimoire_spell_state table.
    """
    now = datetime.now().isoformat()

    with get_db() as conn:
        # Check if row exists
        cursor = conn.execute(
            "SELECT execution_count FROM grimoire_spell_state WHERE daemon_id = ? AND spell_name = ?",
            (daemon_id, spell_name)
        )
        row = cursor.fetchone()

        if row:
            # Update existing row
            updates = ["updated_at = ?"]
            params = [now]

            if last_executed_at is not None:
                updates.append("last_executed_at = ?")
                params.append(datetime.fromtimestamp(last_executed_at).isoformat())
                updates.append("execution_count = execution_count + 1")

            if timer_last_run_at is not None:
                updates.append("timer_last_run_at = ?")
                params.append(datetime.fromtimestamp(timer_last_run_at).isoformat())

            params.extend([daemon_id, spell_name])
            conn.execute(
                f"UPDATE grimoire_spell_state SET {', '.join(updates)} WHERE daemon_id = ? AND spell_name = ?",
                params
            )
        else:
            # Insert new row
            conn.execute("""
                INSERT INTO grimoire_spell_state
                (daemon_id, spell_name, last_executed_at, timer_last_run_at, execution_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                daemon_id,
                spell_name,
                datetime.fromtimestamp(last_executed_at).isoformat() if last_executed_at else None,
                datetime.fromtimestamp(timer_last_run_at).isoformat() if timer_last_run_at else None,
                1 if last_executed_at else 0,
                now,
                now,
            ))


def load_spell_state(
    daemon_id: str,
    spell_name: str
) -> Optional[Dict[str, Any]]:
    """
    Load spell state from database.

    Returns dict with last_executed_at, timer_last_run_at, execution_count
    or None if not found.
    """
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT last_executed_at, timer_last_run_at, execution_count
            FROM grimoire_spell_state
            WHERE daemon_id = ? AND spell_name = ?
        """, (daemon_id, spell_name))
        row = cursor.fetchone()

    if not row:
        return None

    return {
        "last_executed_at": datetime.fromisoformat(row[0]).timestamp() if row[0] else None,
        "timer_last_run_at": datetime.fromisoformat(row[1]).timestamp() if row[1] else None,
        "execution_count": row[2],
    }


def load_all_spell_states(daemon_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Load all spell states for a daemon.

    Returns dict of spell_name -> state dict.
    """
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT spell_name, last_executed_at, timer_last_run_at, execution_count
            FROM grimoire_spell_state
            WHERE daemon_id = ?
        """, (daemon_id,))
        rows = cursor.fetchall()

    result = {}
    for row in rows:
        result[row[0]] = {
            "last_executed_at": datetime.fromisoformat(row[1]).timestamp() if row[1] else None,
            "timer_last_run_at": datetime.fromisoformat(row[2]).timestamp() if row[2] else None,
            "execution_count": row[3],
        }
    return result


# =============================================================================
# EXECUTION LOG
# =============================================================================

def log_execution(
    daemon_id: str,
    spell_name: str,
    trigger_type: str,
    status: str,
    reason: Optional[str] = None,
    execution_time_ms: Optional[float] = None,
    context: Optional[Dict[str, Any]] = None,
    trace: Optional[List[str]] = None,
) -> str:
    """
    Log a spell execution.

    Returns the execution ID.
    """
    exec_id = f"exec-{uuid4().hex[:12]}"
    now = datetime.now().isoformat()

    with get_db() as conn:
        conn.execute("""
            INSERT INTO grimoire_executions
            (id, daemon_id, spell_name, trigger_type, status, reason, execution_time_ms, context_json, trace_json, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            exec_id,
            daemon_id,
            spell_name,
            trigger_type,
            status,
            reason,
            execution_time_ms,
            json.dumps(context) if context else None,
            json.dumps(trace) if trace else None,
            now,
        ))

    return exec_id


def get_execution_log(
    daemon_id: str,
    limit: int = 50,
    spell_name: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get recent spell executions.

    Args:
        daemon_id: Daemon to get executions for
        limit: Max number of executions to return
        spell_name: Filter by specific spell
        status: Filter by status

    Returns:
        List of execution dicts, most recent first
    """
    query = """
        SELECT id, spell_name, trigger_type, status, reason, execution_time_ms, context_json, trace_json, executed_at
        FROM grimoire_executions
        WHERE daemon_id = ?
    """
    params: List[Any] = [daemon_id]

    if spell_name:
        query += " AND spell_name = ?"
        params.append(spell_name)

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY executed_at DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "spell_name": row[1],
            "trigger_type": row[2],
            "status": row[3],
            "reason": row[4],
            "execution_time_ms": row[5],
            "context": json.loads(row[6]) if row[6] else None,
            "trace": json.loads(row[7]) if row[7] else None,
            "executed_at": row[8],
        }
        for row in rows
    ]


def get_execution_stats(
    daemon_id: str,
    days: int = 7,
) -> Dict[str, Any]:
    """
    Get execution statistics for the past N days.

    Returns dict with counts by status, spell, and trigger type.
    """
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    with get_db() as conn:
        # Total count
        cursor = conn.execute("""
            SELECT COUNT(*) FROM grimoire_executions
            WHERE daemon_id = ? AND executed_at > ?
        """, (daemon_id, cutoff))
        total = cursor.fetchone()[0]

        # By status
        cursor = conn.execute("""
            SELECT status, COUNT(*) FROM grimoire_executions
            WHERE daemon_id = ? AND executed_at > ?
            GROUP BY status
        """, (daemon_id, cutoff))
        by_status = {row[0]: row[1] for row in cursor.fetchall()}

        # By spell
        cursor = conn.execute("""
            SELECT spell_name, COUNT(*) FROM grimoire_executions
            WHERE daemon_id = ? AND executed_at > ?
            GROUP BY spell_name
        """, (daemon_id, cutoff))
        by_spell = {row[0]: row[1] for row in cursor.fetchall()}

        # By trigger type
        cursor = conn.execute("""
            SELECT trigger_type, COUNT(*) FROM grimoire_executions
            WHERE daemon_id = ? AND executed_at > ?
            GROUP BY trigger_type
        """, (daemon_id, cutoff))
        by_trigger = {row[0]: row[1] for row in cursor.fetchall()}

    return {
        "total": total,
        "days": days,
        "by_status": by_status,
        "by_spell": by_spell,
        "by_trigger": by_trigger,
    }
