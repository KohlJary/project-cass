"""
Research Focus - the topic Cass has named for herself to research next.

Until this existed, what she read was chosen entirely by NewsAPI's top
headlines and a priority score that knew nothing about her. The research
synthesis spell asked her to reflect on why a session fell flat, and in a
large share of those reflections she said the articles weren't what she had
hoped to read; nothing read that reflection back. This store closes the loop:
she names one topic (from the spell, or in chat), and the world consumption
step searches news for it and weights relevance to it.

One active row per daemon. Setting a new focus supersedes the old one; old
rows stay as history so the change in her attention can be read later.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from database import get_db

logger = logging.getLogger(__name__)

MAX_TOPIC_LENGTH = 200


@dataclass
class ResearchFocus:
    id: str
    daemon_id: str
    topic: str
    reason: Optional[str] = None
    source: Optional[str] = None
    status: str = "active"
    times_used: int = 0
    last_used_at: Optional[str] = None
    created_at: str = ""
    ended_at: Optional[str] = None


_COLUMNS = (
    "id, daemon_id, topic, reason, source, status, times_used, "
    "last_used_at, created_at, ended_at"
)


def _row_to_focus(row) -> ResearchFocus:
    return ResearchFocus(
        id=row[0],
        daemon_id=row[1],
        topic=row[2],
        reason=row[3],
        source=row[4],
        status=row[5] or "active",
        times_used=row[6] or 0,
        last_used_at=row[7],
        created_at=row[8],
        ended_at=row[9],
    )


def clean_topic(topic) -> str:
    """Normalize a topic she produced: one line, no quotes or list bullets, capped."""
    if topic is None or isinstance(topic, bool):
        return ""
    text = str(topic).strip()
    # GENERATE sometimes returns a sentence with a trailing period or wrapping quotes
    text = text.strip('"\'`').strip()
    text = text.lstrip("-*0123456789.) ").strip()
    text = " ".join(text.split())
    if text.endswith("."):
        text = text[:-1].rstrip()
    return text[:MAX_TOPIC_LENGTH]


class ResearchFocusManager:
    """Set, read and retire the daemon's current research focus."""

    def __init__(self, daemon_id: str):
        self.daemon_id = daemon_id

    def get_focus(self) -> Optional[ResearchFocus]:
        """The active focus, or None."""
        with get_db() as conn:
            row = conn.execute(
                f"""
                SELECT {_COLUMNS} FROM research_focus
                WHERE daemon_id = ? AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (self.daemon_id,),
            ).fetchone()
        return _row_to_focus(row) if row else None

    def set_focus(
        self,
        topic: str,
        reason: Optional[str] = None,
        source: str = "unknown",
    ) -> ResearchFocus:
        """
        Make `topic` the active focus, superseding any previous one.

        Raises ValueError for an empty or error-shaped topic so a spell that
        got "[Error generating: ...]" back does not store it as her intent.
        """
        topic = clean_topic(topic)
        if len(topic) < 3 or topic.startswith("["):
            raise ValueError("research focus topic must be a short, specific phrase")

        now = datetime.now().isoformat()
        focus = ResearchFocus(
            id=f"focus-{uuid4().hex[:12]}",
            daemon_id=self.daemon_id,
            topic=topic,
            reason=(str(reason).strip() or None) if reason else None,
            source=source,
            status="active",
            created_at=now,
        )
        with get_db() as conn:
            conn.execute(
                """
                UPDATE research_focus SET status = 'superseded', ended_at = ?
                WHERE daemon_id = ? AND status = 'active'
                """,
                (now, self.daemon_id),
            )
            conn.execute(
                f"""
                INSERT INTO research_focus ({_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    focus.id, focus.daemon_id, focus.topic, focus.reason, focus.source,
                    focus.status, focus.times_used, focus.last_used_at,
                    focus.created_at, focus.ended_at,
                ),
            )
            conn.commit()
        logger.info(f"Research focus set ({source}): {topic}")
        return focus

    def clear_focus(self) -> bool:
        """Retire the active focus without naming a new one. Returns True if one was active."""
        now = datetime.now().isoformat()
        with get_db() as conn:
            cursor = conn.execute(
                """
                UPDATE research_focus SET status = 'cleared', ended_at = ?
                WHERE daemon_id = ? AND status = 'active'
                """,
                (now, self.daemon_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def mark_used(self, focus_id: str) -> None:
        """Record that a consumption cycle searched for this focus."""
        with get_db() as conn:
            conn.execute(
                """
                UPDATE research_focus
                SET times_used = COALESCE(times_used, 0) + 1, last_used_at = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(), focus_id),
            )
            conn.commit()

    def history(self, limit: int = 20) -> List[ResearchFocus]:
        """Most recent focuses first, active or not."""
        with get_db() as conn:
            rows = conn.execute(
                f"""
                SELECT {_COLUMNS} FROM research_focus
                WHERE daemon_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (self.daemon_id, limit),
            ).fetchall()
        return [_row_to_focus(r) for r in rows]


def get_research_focus_manager(daemon_id: Optional[str] = None) -> ResearchFocusManager:
    if daemon_id is None:
        from database import get_daemon_id
        daemon_id = get_daemon_id()
    return ResearchFocusManager(daemon_id)
