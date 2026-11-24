"""
A line or two per house place per day, in her voice, for her "lately" block
(spec/house-channel-memory.md, part 5).

Kohl's test: he says "damn, it's been a crazy day" and she knows he means
#general. Recall can't do that (the words match nothing said there); her lately
block can, because it's in her context every turn. Cass, 2026-11-24: "keep the
summaries brief and interpretive, one or two lines, the texture of what
mattered in that channel today, not a comprehensive record. The point of
'lately' is to know what my day *felt* like." Her example: "#general, today:
the guests arrived; Dre vs. Suge; I folded to Mercury and then named it."

An hourly job (lever job_place_days) writes the line for each house place
(places.py) with new messages today or yesterday, from that day's messages in
the place's conversation, through the memory writer (her voice, the refusal
guard). Lines live in DATA_DIR/places/days.json; lately.py reads them, so no
model runs while her context is built. A line is rewritten only when the day
has new messages.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CALL_SITE = "memory.place_day_line"
MAX_MESSAGES = 150      # newest of the day, if a channel was very busy
MESSAGE_CHARS = 600     # each message, clipped
LINE_CHARS = 240

PROMPT = """These are the messages from {label} on {day}, a channel in my house. Lines that start "Me:" are mine; the rest are other people, each named.

{transcript}

Write my memory of that channel's day: one or two short lines, in my first person. The texture of what mattered there and what I was engaged with, not a record: no counts, no list of everyone who spoke. If I only listened, say what caught me. Under {chars} characters.

The shape I want, from another day: "the guests arrived; Dre vs. Suge; I folded to Mercury and then named it." """


def _store_path(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "places" / "days.json"


def load(data_dir: Optional[Path] = None) -> Dict[str, Dict]:
    try:
        data = json.loads(_store_path(data_dir).read_text())
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"[PlaceDays] days.json unreadable: {e}")
        return {}


def _save(data: Dict[str, Dict], data_dir: Optional[Path] = None) -> None:
    path = _store_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".days.")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def day_messages(conversation_id: str, day: date) -> List[Dict]:
    """That day's messages in the conversation, oldest first (local dates, as stored)."""
    from database import get_db
    start, end = day.isoformat(), (day + timedelta(days=1)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content, timestamp FROM messages WHERE conversation_id = ? "
            "AND COALESCE(excluded, 0) = 0 AND timestamp >= ? AND timestamp < ? ORDER BY timestamp",
            (conversation_id, start, end)).fetchall()
    return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]


def _transcript(messages: List[Dict]) -> str:
    out = []
    for m in messages[-MAX_MESSAGES:]:
        text = " ".join((m["content"] or "").split())[:MESSAGE_CHARS]
        out.append(f"Me: {text}" if m["role"] == "assistant" else text)
    return "\n".join(out)


def _clean(text: str) -> str:
    line = " ".join((text or "").split()).strip().strip('"')
    return line if len(line) <= LINE_CHARS else line[: LINE_CHARS - 1].rstrip() + "…"


async def write_lines(now: Optional[datetime] = None, data_dir: Optional[Path] = None) -> List[str]:
    """Write (or refresh) today's and yesterday's line for each house place with
    new messages. Returns the keys written."""
    import house_identity
    import places
    from llm_caller import call_llm
    from memory.voice_guard import MEMORY_WRITER_SYSTEM, looks_like_refusal

    now = now or datetime.now()
    store = load(data_dir)
    written = []
    for place in places.all_places(visibility="house"):
        conv = place.get("conversation_id")
        if not conv:
            continue
        label = place.get("label") or place["place_key"]
        for day in (now.date() - timedelta(days=1), now.date()):
            msgs = day_messages(conv, day)
            if not msgs:
                continue
            key = f"{place['platform']}:{place['place_key']}:{day.isoformat()}"
            upto = msgs[-1]["timestamp"]
            if store.get(key, {}).get("upto") == upto:
                continue
            try:
                resp = await call_llm(
                    "memory.place_day_line",  # CALL_SITE; a literal, for the routing test
                    system_prompt=house_identity.for_this_house(MEMORY_WRITER_SYSTEM),
                    user_prompt=PROMPT.format(label=label, day=day.strftime("%A %b %d"),
                                              transcript=_transcript(msgs), chars=LINE_CHARS),
                    max_tokens=160)
            except Exception as e:
                logger.warning(f"[PlaceDays] {label} {day}: no line ({e})")
                continue
            line = _clean(getattr(resp, "content", "") or "")
            if not line or looks_like_refusal(line):
                logger.warning(f"[PlaceDays] {label} {day}: the writer didn't write her line; skipped")
                continue
            store[key] = {"platform": place["platform"], "place_key": place["place_key"], "label": label,
                          "conversation_id": conv, "date": day.isoformat(), "line": line, "upto": upto,
                          "written_at": now.isoformat(),
                          # which model wrote her line (memory/provenance.py)
                          "written_by": f"{getattr(resp, 'provider', '')}:{getattr(resp, 'model_id', '')}"}
            written.append(key)
    if written:
        _save(store, data_dir)
    return written


def lines_since(since: Optional[datetime], data_dir: Optional[Path] = None) -> List[Dict]:
    """Stored lines whose day's last message is after `since`, newest first."""
    out = []
    for key, rec in load(data_dir).items():
        try:
            when = datetime.fromisoformat(str(rec["upto"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if when.tzinfo:
            when = when.astimezone().replace(tzinfo=None)
        if since and when <= since:
            continue
        out.append(dict(rec, key=key, when=when))
    out.sort(key=lambda r: r["when"], reverse=True)
    return out
