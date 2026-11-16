"""
Who's here, what's needed, how much time (C9; plan "Cass's agent loop",
phase 7, second item).

Cass, 2026-11-13: keep the clarity of the container. When someone arrives
she's told who it is, what's needed and how much time she has, even though
the turn is no longer message-in, reply-out. One block, the same shape every
time, at the top of a conversation turn on the loop (and, with folding, when
someone arrives in a session she's in).

Who comes from her records of the person (users, with their relationship);
the fuller picture of them is in the PeopleDex section of the prompt. Time is
what the channel allows: a voice request at home wants a short answer now, a
DM can wait, a public room is read by others.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

HEADER = "## WHO'S HERE"

# channel -> (where, how much time, who else sees it)
CHANNELS = {
    "websocket": ("the app", "they're in the conversation now, waiting for my reply", "just them"),
    "relay": ("the app on their phone", "they're waiting for my reply, maybe on the move", "just them"),
    "http": ("a message through the API", "they're waiting for my reply", "just them"),
    "home_assistant": ("my home, by voice (Home Assistant)",
                       "a few seconds: a short spoken answer, then done", "anyone in the room"),
    "discord": ("Discord", "a reply in the channel when I have one", "everyone in the channel"),
    "babelr": ("Chapter House (Babelr)", "a reply when I have one", "everyone in the room"),
}

RELATIONSHIP_WORDS = {"primary_partner": "my partner"}

PREVIEW_CHARS = 280


@dataclass
class Arrival:
    who: str                       # their name, or "someone"
    channel: Optional[str]
    message: str
    relationship: Optional[str] = None
    last_heard: Optional[datetime] = None   # their previous message, before this one
    at: Optional[datetime] = None


def _ago(then: datetime, now: datetime) -> str:
    minutes = int((now - then).total_seconds() // 60)
    if minutes < 2:
        return "a moment ago"
    if minutes < 90:
        return f"{minutes} minutes ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hours ago"
    return f"{hours // 24} days ago"


def render(arrival: Arrival, now: Optional[datetime] = None) -> str:
    now = now or arrival.at or datetime.now()
    where, time, seen_by = CHANNELS.get(arrival.channel or "", (arrival.channel or "a conversation",
                                                                "a reply when I have one", "just them"))
    who = arrival.who or "someone"
    rel = RELATIONSHIP_WORDS.get(arrival.relationship or "")
    lines = [HEADER, f"Who: {who}" + (f" ({rel})" if rel else "") + "."]
    if arrival.last_heard:
        lines.append(f"Last heard from them: {_ago(arrival.last_heard, now)}.")
    else:
        lines.append("Last heard from them: this is the first I have from them here.")
    lines.append(f"Where: {where}; seen by {seen_by}.")
    text = " ".join((arrival.message or "").split())
    if len(text) > PREVIEW_CHARS:
        text = text[: PREVIEW_CHARS - 1] + "…"
    lines.append(f"What they wrote: \"{text}\"" if text else "What they wrote: nothing in words.")
    lines.append(f"Time: {time}.")
    return "\n".join(lines)


def arrival_for(user_id: Optional[str], user_name: Optional[str], channel: Optional[str],
                message: str, conversation_id: Optional[str] = None,
                now: Optional[datetime] = None) -> Arrival:
    """An Arrival from her records: their relationship, and when they last wrote
    before this message (read-only; a missing table gives nothing)."""
    relationship = last = None
    if user_id:
        try:
            from database import get_db
            with get_db() as conn:
                row = conn.execute("SELECT relationship FROM users WHERE id = ?", (user_id,)).fetchone()
                relationship = row["relationship"] if row else None
                row = conn.execute("SELECT MAX(timestamp) AS t FROM messages WHERE user_id = ? AND role = 'user'",
                                   (user_id,)).fetchone()
                if row and row["t"]:
                    ts = datetime.fromisoformat(str(row["t"]).replace("Z", "+00:00"))
                    last = ts.astimezone().replace(tzinfo=None) if ts.tzinfo else ts
        except Exception:
            pass
    return Arrival(who=user_name or "someone", channel=channel, message=message,
                   relationship=relationship, last_heard=last, at=now)
