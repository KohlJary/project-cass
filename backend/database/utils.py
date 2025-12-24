"""
Database Utilities

Serialization helpers and utility functions for database operations.
"""

import json
import sqlite3
from typing import Any, Optional

from .connection import get_db


def dict_from_row(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a dictionary."""
    if row is None:
        return None
    return dict(row)


def json_serialize(obj: Any) -> Optional[str]:
    """Serialize an object to JSON string, or None if obj is None."""
    if obj is None:
        return None
    return json.dumps(obj)


def json_deserialize(s: Optional[str]) -> Any:
    """Deserialize a JSON string, or return None if s is None."""
    if s is None:
        return None
    return json.loads(s)


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cursor.fetchone() is not None


def get_row_count(table_name: str) -> int:
    """Get the number of rows in a table."""
    with get_db() as conn:
        cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]
