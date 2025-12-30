"""
Push Token Management - Store and manage Expo push tokens for mobile devices.
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config import DATA_DIR

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(DATA_DIR) / "cass.db"


@dataclass
class PushToken:
    """A registered push token for a device."""
    id: str
    user_id: str
    token: str
    platform: str  # 'android' | 'ios'
    created_at: str
    last_seen: Optional[str] = None


class PushTokenManager:
    """Manages push token storage and retrieval."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the push tokens table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS push_device_tokens (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token TEXT NOT NULL UNIQUE,
                    platform TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_push_tokens_user
                ON push_device_tokens(user_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_push_tokens_token
                ON push_device_tokens(token)
            """)
            conn.commit()

    def register_token(
        self,
        user_id: str,
        token: str,
        platform: str,
    ) -> PushToken:
        """Register a push token for a user. Updates if token already exists."""
        now = datetime.utcnow().isoformat() + "Z"

        with sqlite3.connect(self.db_path) as conn:
            # Check if token already exists
            existing = conn.execute(
                "SELECT id FROM push_device_tokens WHERE token = ?",
                (token,)
            ).fetchone()

            if existing:
                # Update existing token
                token_id = existing[0]
                conn.execute("""
                    UPDATE push_device_tokens
                    SET user_id = ?, platform = ?, last_seen = ?
                    WHERE token = ?
                """, (user_id, platform, now, token))
            else:
                # Create new token
                token_id = str(uuid.uuid4())
                conn.execute("""
                    INSERT INTO push_device_tokens (id, user_id, token, platform, created_at, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (token_id, user_id, token, platform, now, now))

            conn.commit()

        logger.info(f"Registered push token for user {user_id}: {token_id}")
        return PushToken(
            id=token_id,
            user_id=user_id,
            token=token,
            platform=platform,
            created_at=now,
            last_seen=now,
        )

    def unregister_token(self, token: str) -> bool:
        """Unregister a push token."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM push_device_tokens WHERE token = ?",
                (token,)
            )
            conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info(f"Unregistered push token: {token[:20]}...")
        return deleted

    def get_tokens_for_user(self, user_id: str) -> List[PushToken]:
        """Get all push tokens for a user."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM push_device_tokens WHERE user_id = ?",
                (user_id,)
            ).fetchall()

        return [
            PushToken(
                id=row["id"],
                user_id=row["user_id"],
                token=row["token"],
                platform=row["platform"],
                created_at=row["created_at"],
                last_seen=row["last_seen"],
            )
            for row in rows
        ]

    def update_last_seen(self, token: str) -> None:
        """Update the last_seen timestamp for a token."""
        now = datetime.utcnow().isoformat() + "Z"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE push_device_tokens SET last_seen = ? WHERE token = ?",
                (now, token)
            )
            conn.commit()


# Global manager instance
_push_manager: Optional[PushTokenManager] = None


def get_push_manager() -> PushTokenManager:
    """Get the global push token manager."""
    global _push_manager
    if _push_manager is None:
        _push_manager = PushTokenManager()
    return _push_manager
