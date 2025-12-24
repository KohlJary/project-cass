"""
Database Connection Management

Thread-local SQLite connection management for the Cass Vessel backend.
"""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from config import DATA_DIR


# Database path
DATABASE_PATH = DATA_DIR / "cass.db"

# Thread-local storage for connections
_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """
    Get a thread-local database connection.
    Creates connection if it doesn't exist for this thread.
    """
    if not hasattr(_local, 'connection') or _local.connection is None:
        _local.connection = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False,
            timeout=30.0
        )
        _local.connection.row_factory = sqlite3.Row
        # Enable foreign keys
        _local.connection.execute("PRAGMA foreign_keys = ON")
    return _local.connection


def close_connection():
    """Close the thread-local connection if it exists."""
    if hasattr(_local, 'connection') and _local.connection is not None:
        _local.connection.close()
        _local.connection = None


@contextmanager
def get_db():
    """Context manager for database access."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
