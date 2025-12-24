"""
Daemon Management

Functions for managing daemon records in the database.
"""

import uuid
from datetime import datetime

from .connection import get_db


def get_or_create_daemon(label: str = "cass", kernel_version: str = "temple-codex-1.0", name: str = "Cass") -> str:
    """
    Get existing daemon by label or create if doesn't exist.
    Returns the daemon ID.

    Args:
        label: Display label for the daemon (e.g., "cass", "test-daemon")
        kernel_version: The cognitive kernel version
        name: Entity name used in prompts (e.g., "Cass", "Aria")
    """
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id FROM daemons WHERE label = ?",
            (label,)
        )
        row = cursor.fetchone()

        if row:
            return row['id']

        # Create new daemon
        daemon_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO daemons (id, label, name, created_at, kernel_version, status)
               VALUES (?, ?, ?, ?, ?, 'active')""",
            (daemon_id, label, name, datetime.now().isoformat(), kernel_version)
        )
        print(f"Created daemon '{label}' (entity: {name}) with ID {daemon_id}")
        return daemon_id


def get_daemon_id() -> str:
    """Get the default daemon ID (Cass)."""
    return get_or_create_daemon("cass")


def get_daemon_info(daemon_id: str) -> dict:
    """Get daemon info by ID."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, label, name, created_at, kernel_version, status FROM daemons WHERE id = ?",
            (daemon_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "label": row[1],
                "name": row[2],  # Entity name for prompts
                "created_at": row[3],
                "kernel_version": row[4],
                "status": row[5],
            }
        return None


def get_daemon_entity_name(daemon_id: str) -> str:
    """Get the entity name for a daemon (used in system prompts)."""
    info = get_daemon_info(daemon_id)
    return info["name"] if info else "Cass"
