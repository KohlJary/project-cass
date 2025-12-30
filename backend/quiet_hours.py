"""
Quiet Hours Management - Control when Cass can send push notifications.

Respects user-configured do-not-disturb periods to avoid notifications
during sleep or focused work time.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from config import DATA_DIR

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(DATA_DIR) / "cass.db"


@dataclass
class QuietHoursPreference:
    """User's quiet hours configuration."""
    user_id: str
    enabled: bool = False
    start_hour: int = 22  # 10 PM
    end_hour: int = 8     # 8 AM
    timezone: str = "America/Los_Angeles"


class QuietHoursManager:
    """Manages quiet hours preferences and checks."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Ensure quiet hours columns exist in users table."""
        with sqlite3.connect(self.db_path) as conn:
            # Check if columns exist, add if not
            cursor = conn.execute("PRAGMA table_info(users)")
            columns = {row[1] for row in cursor.fetchall()}

            if "quiet_hours_enabled" not in columns:
                conn.execute("""
                    ALTER TABLE users ADD COLUMN quiet_hours_enabled INTEGER DEFAULT 0
                """)
            if "quiet_hours_start" not in columns:
                conn.execute("""
                    ALTER TABLE users ADD COLUMN quiet_hours_start INTEGER DEFAULT 22
                """)
            if "quiet_hours_end" not in columns:
                conn.execute("""
                    ALTER TABLE users ADD COLUMN quiet_hours_end INTEGER DEFAULT 8
                """)
            if "quiet_hours_timezone" not in columns:
                conn.execute("""
                    ALTER TABLE users ADD COLUMN quiet_hours_timezone TEXT DEFAULT 'America/Los_Angeles'
                """)
            conn.commit()

    def get_preference(self, user_id: str) -> QuietHoursPreference:
        """Get quiet hours preference for a user."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT quiet_hours_enabled, quiet_hours_start,
                       quiet_hours_end, quiet_hours_timezone
                FROM users WHERE id = ?
            """, (user_id,)).fetchone()

            if row:
                return QuietHoursPreference(
                    user_id=user_id,
                    enabled=bool(row["quiet_hours_enabled"]),
                    start_hour=row["quiet_hours_start"] or 22,
                    end_hour=row["quiet_hours_end"] or 8,
                    timezone=row["quiet_hours_timezone"] or "America/Los_Angeles",
                )

        return QuietHoursPreference(user_id=user_id)

    def set_preference(self, pref: QuietHoursPreference) -> None:
        """Update quiet hours preference for a user."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE users SET
                    quiet_hours_enabled = ?,
                    quiet_hours_start = ?,
                    quiet_hours_end = ?,
                    quiet_hours_timezone = ?
                WHERE id = ?
            """, (
                1 if pref.enabled else 0,
                pref.start_hour,
                pref.end_hour,
                pref.timezone,
                pref.user_id,
            ))
            conn.commit()

        logger.info(f"Updated quiet hours for user {pref.user_id}: {pref}")

    def is_quiet_hours(self, user_id: str) -> bool:
        """Check if it's currently quiet hours for a user."""
        pref = self.get_preference(user_id)

        if not pref.enabled:
            return False

        try:
            tz = ZoneInfo(pref.timezone)
        except Exception:
            logger.warning(f"Invalid timezone {pref.timezone}, using UTC")
            tz = ZoneInfo("UTC")

        now = datetime.now(tz)
        current_hour = now.hour

        # Handle overnight quiet hours (e.g., 22:00 - 08:00)
        if pref.start_hour > pref.end_hour:
            # Quiet hours span midnight
            is_quiet = current_hour >= pref.start_hour or current_hour < pref.end_hour
        else:
            # Quiet hours within same day
            is_quiet = pref.start_hour <= current_hour < pref.end_hour

        return is_quiet


# Global manager instance
_quiet_hours_manager: Optional[QuietHoursManager] = None


def get_quiet_hours_manager() -> QuietHoursManager:
    """Get the global quiet hours manager."""
    global _quiet_hours_manager
    if _quiet_hours_manager is None:
        _quiet_hours_manager = QuietHoursManager()
    return _quiet_hours_manager


def is_quiet_hours(user_id: str) -> bool:
    """Convenience function to check if it's quiet hours."""
    return get_quiet_hours_manager().is_quiet_hours(user_id)
