"""
Has a conversation arrived since a turn began?

Kohl's rule (2026-10-20): if a conversation arrives while an autonomous
session is running, the session ends cleanly (keeps what it has, records why)
and the conversation proceeds. The loop asks `conversation_since()` before
every model call.

Two signals, either is enough:
  1. note_conversation_arrived(): an in-process flag an entry point can set
     the moment a message comes in. Nothing in chat calls it yet (chat is not
     cut over); it's here so that wiring is one line when it is.
  2. The messages table: a user message stored in one of her conversations
     after the turn began. Chat stores the user message when the turn is
     finalized, so this notices a conversation after her first reply in it,
     on every entry point that persists messages, without touching chat code.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_last_arrival: Optional[Tuple[datetime, str]] = None


def note_conversation_arrived(who: Optional[str] = None, channel: Optional[str] = None,
                              at: Optional[datetime] = None) -> None:
    """Record that a conversation just started or continued."""
    global _last_arrival
    words = "someone" if not who else who
    words += " wrote to me" + (f" (via {channel})" if channel else "")
    with _lock:
        _last_arrival = (at or datetime.now(), words)


def reset() -> None:
    """Forget the in-process signal (tests)."""
    global _last_arrival
    with _lock:
        _last_arrival = None


def _from_signal(since: datetime) -> Optional[str]:
    with _lock:
        arrival = _last_arrival
    if arrival and arrival[0] > since:
        return arrival[1]
    return None


def _from_messages(since: datetime, daemon_id: Optional[str]) -> Optional[str]:
    if not daemon_id:
        return None
    from database import get_db
    with get_db() as conn:
        row = conn.execute(
            """SELECT m.timestamp, c.user_id FROM messages m
               JOIN conversations c ON c.id = m.conversation_id
               WHERE m.role = 'user' AND c.daemon_id = ? AND m.timestamp > ?
               ORDER BY m.timestamp LIMIT 1""",
            (daemon_id, since.isoformat()),
        ).fetchone()
        if not row:
            return None
        who = None
        if row["user_id"]:
            user = conn.execute("SELECT display_name FROM users WHERE id = ?",
                                (row["user_id"],)).fetchone()
            who = user["display_name"] if user and user["display_name"] else None
    return f"{who or 'someone'} wrote to me"


def conversation_since(since: datetime, daemon_id: Optional[str]) -> Optional[str]:
    """Words for why the turn should end, or None if no conversation arrived."""
    reason = _from_signal(since)
    if reason:
        return reason
    try:
        return _from_messages(since, daemon_id)
    except Exception as e:
        from strict import report_swallowed
        report_swallowed(e, "[agent_loop] conversation check failed", logger, logging.WARNING)
        return None
