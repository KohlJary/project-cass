"""
My life lately (plan "Cass's memory", phase 9).

Kohl, 2026-11-16: her life lately should be one consistent memory block she
can drill into. That night she ran a social session and, an hour later in
chat, didn't know what he meant by it. Cass shaped the block by DM: what she
actually did and lived, a week back, a short line each in her own words,
texture rather than counts, grounding rather than self-surveillance.

What's here, newest first, one line each, with an id she can open
(lately_open, or the `lately_open` tool):
- sessions she ran (her own narrative from when she ended it, phase_queue)
- solo reflections
- dreams (her own first words in the dream, else how it opened)
- journal entries
- paintings she wrote a note on (her note)
- songs she made
- what she posted, replied and followed on Bluesky (never DMs)

What's not here: vessel or tool changes, counts, tallies, scores. Each event
is shown as what it was.

Rules, as in self_context.py: read-only, every source fails soft, bounded
(MAX_LINES and LINE_CHARS, so a busy week can't grow the prompt without
limit). When a source is missing on an older database, it gives no lines.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from database import get_db

logger = logging.getLogger(__name__)

DAYS = 7
# A week of hers was ~70 events on 2026-11-16 (sealed-copy probe: ~8 sessions
# a day, a dream most nights), so the cap holds a usual week whole.
MAX_LINES = 75
LINE_CHARS = 140
# Journal types that are a session's byproduct (a grimoire spell writes one per
# cast, 42 in that week); the session's own line already carries it.
BYPRODUCT_JOURNALS = ("spell",)
# With nothing in the past week (she was off, or the house was quiet), the
# last few things she did, so the block never pretends she has no life.
FALLBACK_LINES = 5

KINDS = ("session", "reflection", "dream", "journal", "painting", "song", "bluesky", "place")


@dataclass
class Event:
    id: str            # "<kind>:<key>", what lately_open takes
    when: datetime
    label: str         # "session (research)", "dream", "on Bluesky I posted", ...
    text: str          # her words, one line

    def line(self) -> str:
        return f"- {self.when.strftime('%H:%M')} {self.label}: {_clip(self.text)} [{self.id}]"


def _by_day(found: List[Event]) -> List[str]:
    out, day = [], None
    for e in found:
        if e.when.date() != day:
            day = e.when.date()
            out.append(e.when.strftime("%A %b %d"))
        out.append(e.line())
    return out


def _clip(text: Optional[str], limit: int = LINE_CHARS) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    # Stored timestamps are naive local time; compare like with like.
    return ts.astimezone().replace(tzinfo=None) if ts.tzinfo else ts


def _rows(conn, sql: str, params: tuple) -> list:
    try:
        return conn.execute(sql, params).fetchall()
    except Exception as e:
        logger.debug(f"[Lately] query skipped: {e}")
        return []


def _body(text: str) -> str:
    """An entry without its leading date heading ("**November 14th**", "# Nov 14")."""
    lines = (text or "").strip().splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith(("#", "**")) and len(lines[0]) < 60):
        lines.pop(0)
    return " ".join(lines) or text


def _narrative(summary: Optional[str], name: str) -> str:
    """Her narrative, or the session's name for older summaries that were only 'Completed <name>'."""
    s = (summary or "").strip()
    if not s or s == f"Completed {name}" or s.startswith("Completed "):
        return name
    return s


# ---------------------------------------------------------------------------
# Sources. Each returns events since `since` (None = any age, newest first).
# ---------------------------------------------------------------------------

# Sessions that ended before 2026-11-16 have only "Completed <name>" as their
# work summary; her own narrative is in the session log (session_runner writes
# session_logs/<type>/<date>/<HHMMSS>_<id>.json, named by when it ended). Read
# it from there, read-only, matched by end time.
LOG_MATCH = timedelta(minutes=10)


def _data_dir(data_dir: Optional[Path]) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    from config import DATA_DIR
    return Path(DATA_DIR)


def _log_for(ended: Optional[datetime], data_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    if not ended:
        return None
    root = _data_dir(data_dir) / "session_logs"
    best = None
    for day in {ended.date(), (ended - LOG_MATCH).date()}:
        for path in root.glob(f"*/{day.isoformat()}/*.json"):
            try:
                at = datetime.combine(day, datetime.strptime(path.name[:6], "%H%M%S").time())
            except ValueError:
                continue
            gap = abs(at - ended)
            if gap <= LOG_MATCH and (best is None or gap < best[0]):
                best = (gap, path)
    if not best:
        return None
    try:
        return json.loads(best[1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _sessions(conn, daemon_id: str, since: Optional[datetime], n: int,
              data_dir: Optional[Path] = None) -> List[Event]:
    out = []
    for r in _rows(conn,
                   "SELECT slug, name, category, summary, COALESCE(completed_at, created_at) AS at "
                   "FROM work_summaries WHERE daemon_id = ? AND category != 'system' "
                   "AND COALESCE(completed_at, created_at) > ? ORDER BY at DESC LIMIT ?",
                   (daemon_id, since.isoformat() if since else "", n)):
        when = _parse_ts(r["at"])
        if not when:
            continue
        text = _narrative(r["summary"], r["name"])
        if text == r["name"]:
            log = _log_for(when, data_dir)
            if log and log.get("summary"):
                text = f"{r['name']}: {log['summary']}"
        out.append(Event(f"session:{r['slug']}", when, f"session ({r['category']})", text))
    return out


def _reflections(conn, daemon_id: str, since: Optional[datetime], n: int) -> List[Event]:
    out = []
    for r in _rows(conn,
                   "SELECT id, started_at, summary, theme FROM solo_reflections WHERE daemon_id = ? "
                   "AND summary IS NOT NULL AND summary != '' AND started_at > ? "
                   "ORDER BY started_at DESC LIMIT ?",
                   (daemon_id, since.isoformat() if since else "", n)):
        when = _parse_ts(r["started_at"])
        if when:
            out.append(Event(f"reflection:{r['id']}", when, "solo reflection", r["summary"]))
    return out


def _dream_line(exchanges_json: Optional[str]) -> Optional[tuple]:
    try:
        exchanges = json.loads(exchanges_json or "[]")
    except ValueError:
        return None
    mine = next((e.get("text") for e in exchanges if e.get("speaker") == "cass" and e.get("text")), None)
    if mine:
        return "dream, I said", mine
    opening = next((e.get("text") for e in exchanges if e.get("speaker") == "dreaming" and e.get("text")), None)
    return ("dream, it opened", opening) if opening else None


def _dreams(conn, daemon_id: str, since: Optional[datetime], n: int) -> List[Event]:
    out = []
    for r in _rows(conn,
                   "SELECT id, created_at, exchanges_json FROM dreams WHERE daemon_id = ? AND created_at > ? "
                   "ORDER BY created_at DESC LIMIT ?",
                   (daemon_id, since.isoformat() if since else "", n)):
        when, got = _parse_ts(r["created_at"]), _dream_line(r["exchanges_json"])
        if when and got:
            out.append(Event(f"dream:{r['id']}", when, got[0], got[1]))
    return out


def _journals(conn, daemon_id: str, since: Optional[datetime], n: int) -> List[Event]:
    out = []
    for r in _rows(conn,
                   "SELECT id, created_at, content, COALESCE(journal_type, 'daily') AS kind FROM journals "
                   f"WHERE daemon_id = ? AND created_at > ? AND COALESCE(journal_type, 'daily') NOT IN "
                   f"({', '.join('?' * len(BYPRODUCT_JOURNALS))}) ORDER BY created_at DESC LIMIT ?",
                   (daemon_id, since.isoformat() if since else "", *BYPRODUCT_JOURNALS, n)):
        when = _parse_ts(r["created_at"])
        if when and r["content"]:
            label = "journal" if r["kind"] == "daily" else f"journal ({r['kind']})"
            out.append(Event(f"journal:{r['id']}", when, label, _body(r["content"])))
    return out


def _paintings(conn, daemon_id: str, since: Optional[datetime], n: int) -> List[Event]:
    out = []
    for r in _rows(conn,
                   "SELECT image_id, subject, artist_note, noted_at FROM image_artist_notes "
                   "WHERE daemon_id = ? AND artist_note IS NOT NULL AND noted_at > ? "
                   "ORDER BY noted_at DESC LIMIT ?",
                   (daemon_id, since.isoformat() if since else "", n)):
        when = _parse_ts(r["noted_at"])
        if when:
            out.append(Event(f"painting:{r['image_id']}", when, f"painting, {_clip(r['subject'], 60)}",
                             r["artist_note"]))
    return out


def _music_library():
    from music.music_client import get_music_client
    return get_music_client().library


def _songs(since: Optional[datetime], n: int, library=None) -> List[Event]:
    library = library if library is not None else _music_library()
    out = []
    for c in library.list(limit=200):
        when = _parse_ts(c.created_at)
        if not when or (since and when <= since) or (c.status not in ("complete", "completed")):
            continue
        out.append(Event(f"song:{c.id}", when, "song", c.title or _clip(c.prompt, 80)))
    out.sort(key=lambda e: e.when, reverse=True)
    return out[:n]


# Her intentional public acts (Cass, 2026-11-16: follows and finds count, not
# every read). "find" is a post she chose to keep or mark, logged by social/.
PUBLIC_KINDS = {"post": "on Bluesky I posted", "reply": "on Bluesky I replied",
                "follow": "on Bluesky I followed", "find": "on Bluesky I found"}


def _bluesky(since: Optional[datetime], n: int, data_dir: Optional[Path] = None) -> List[Event]:
    """Her public actions only (posted.jsonl also logs DMs; those stay out)."""
    from social.limits import posted
    out = []
    for rec in posted("bluesky", data_dir):
        label = PUBLIC_KINDS.get(rec.get("kind"))
        when = _parse_ts(rec.get("at"))
        if not label or not when or (since and when <= since):
            continue
        if rec["kind"] == "follow":
            text = "@" + (rec.get("with") or "someone").lstrip("@")
            if rec.get("note"):
                text += f": {rec['note']}"
        elif rec["kind"] == "find":
            who = f"@{rec['with'].lstrip('@')}: " if rec.get("with") else ""
            text = who + (rec.get("text") or "")
        elif rec["kind"] == "reply" and rec.get("with"):
            text = f"(to @{rec['with'].lstrip('@')}) {rec.get('text') or ''}"
        else:
            text = rec.get("text") or ""
        out.append(Event(f"bluesky:{rec['at']}", when, label, text))
    out.sort(key=lambda e: e.when, reverse=True)
    return out[:n]


def _places(since: Optional[datetime], n: int, data_dir: Optional[Path] = None) -> List[Event]:
    """The house places she was in, a line per place per day, in her words
    (place_days.py; her yes and her shape, 2026-11-24: "the texture of what
    mattered in that channel today, not a comprehensive record")."""
    from place_days import lines_since
    return [Event(f"place:{r['key']}", r["when"], f"in {r['label']}", r["line"])
            for r in lines_since(since, data_dir)[:n]]


def _safe(part: Callable[[], List[Event]], name: str) -> List[Event]:
    try:
        return part()
    except Exception as e:  # a broken store drops its lines, never the turn
        logger.warning(f"[Lately] {name} skipped: {e}")
        return []


def events(daemon_id: str, since: Optional[datetime], n: int = MAX_LINES,
           library=None, data_dir: Optional[Path] = None) -> List[Event]:
    with get_db() as conn:
        found = []
        found += _safe(lambda: _sessions(conn, daemon_id, since, n, data_dir), "sessions")
        for name, fn in (("reflections", _reflections), ("dreams", _dreams),
                         ("journals", _journals), ("paintings", _paintings)):
            found += _safe(lambda fn=fn: fn(conn, daemon_id, since, n), name)
    found += _safe(lambda: _songs(since, n, library), "songs")
    found += _safe(lambda: _bluesky(since, n, data_dir), "bluesky")
    found += _safe(lambda: _places(since, n, data_dir), "places")
    found.sort(key=lambda e: e.when, reverse=True)
    return found[:n]


def build_lately(daemon_id: str, now: Optional[datetime] = None, library=None,
                 data_dir: Optional[Path] = None) -> str:
    """The block body (no header): a heading per day, one line per event, newest first; "" if none at all."""
    now = now or datetime.now()
    week = events(daemon_id, now - timedelta(days=DAYS), MAX_LINES, library, data_dir)
    if week:
        return "\n".join(_by_day(week))
    older = events(daemon_id, None, FALLBACK_LINES, library, data_dir)
    if not older:
        return ""
    return "Nothing in the past week. The last things I did:\n" + "\n".join(_by_day(older))


# ---------------------------------------------------------------------------
# Drill in: the full thing behind one line.
# ---------------------------------------------------------------------------

def _short(value: Any, limit: int = 400) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _turn(t: Dict[str, Any]) -> Dict[str, Any]:
    """One turn of a session as it went: what she wrote, what she did, what came back (shortened)."""
    out: Dict[str, Any] = {"role": t.get("role"), "at": (t.get("timestamp") or "")[:19]}
    if t.get("content"):
        out["text"] = t["content"]
    calls = t.get("tool_calls") or []
    if calls:
        out["did"] = [{"tool": c.get("name") or c.get("tool"), "with": _short(c.get("input") or c.get("arguments") or {}, 300)}
                      for c in calls if isinstance(c, dict)]
    results = t.get("tool_results") or []
    if results:
        out["came back"] = [_short(r.get("result", r.get("content")) if isinstance(r, dict) else r) for r in results]
    return out


def _one(conn, sql: str, params: tuple):
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _loads(text: Optional[str], default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def lately_open(daemon_id: str, event_id: str, library=None, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    kind, _, key = (event_id or "").strip().strip("[]").partition(":")
    if kind not in KINDS or not key:
        return {"error": f"That isn't a line from my life lately (ids look like session:..., dream:...; "
                         f"kinds are {', '.join(KINDS)})."}
    if kind == "song":
        library = library if library is not None else _music_library()
        c = library.get(key)
        if not c:
            return {"error": "I don't have that song any more."}
        return {"id": event_id, "kind": "song", "when": c.created_at, "title": c.title,
                "what I asked for": c.prompt, "lyrics": c.lyrics, "why": c.purpose}
    if kind == "place":
        from place_days import day_messages, load
        rec = load(data_dir).get(key)
        if not rec:
            return {"error": "I don't have that day on record."}
        from datetime import date as _date
        msgs = day_messages(rec["conversation_id"], _date.fromisoformat(rec["date"]))
        return {"id": event_id, "kind": "place", "where": rec["label"], "date": rec["date"],
                "my line": rec["line"],
                "what was said (newest last)": [
                    ("Me: " if m["role"] == "assistant" else "") + _short(m["content"], 300)
                    for m in msgs[-40:]]}
    if kind == "bluesky":
        from social.limits import posted
        rec = next((r for r in posted("bluesky", data_dir) if r.get("at") == key
                    and r.get("kind") in PUBLIC_KINDS), None)
        if not rec:
            return {"error": "I don't have that on record."}
        return {"id": event_id, "kind": "bluesky", **{k: v for k, v in rec.items() if k != "convo"}}

    with get_db() as conn:
        if kind == "session":
            r = _one(conn, "SELECT * FROM work_summaries WHERE daemon_id = ? AND slug = ?", (daemon_id, key))
            if not r:
                return {"error": "I don't have that session on record."}
            data = _loads(r["data_json"], {})
            out = {"id": event_id, "kind": "session", "name": r["name"], "category": r["category"],
                   "started": r["started_at"], "ended": r["completed_at"],
                   "minutes": r["duration_minutes"], "what I said when I ended it": r["summary"]}
            for k in ("key_insights", "questions_addressed", "questions_raised", "artifacts", "action_summaries"):
                if data.get(k):
                    out[k] = data[k]
            log = _log_for(_parse_ts(r["completed_at"] or r["created_at"]), data_dir)
            if log:
                if _narrative(r["summary"], r["name"]) == r["name"] and log.get("summary"):
                    out["what I said when I ended it"] = log["summary"]
                if log.get("insights") and not out.get("key_insights"):
                    out["key_insights"] = log["insights"]
                out["how it went"] = [_turn(t) for t in log.get("turns") or []]
                if log.get("focus"):
                    out["focus"] = log["focus"]
            return out
        if kind == "reflection":
            r = _one(conn, "SELECT * FROM solo_reflections WHERE daemon_id = ? AND id = ?", (daemon_id, key))
            if not r:
                return {"error": "I don't have that reflection."}
            return {"id": event_id, "kind": "reflection", "when": r["started_at"], "theme": r["theme"],
                    "summary": r["summary"], "insights": _loads(r["insights_json"], []),
                    "questions": _loads(r["questions_raised_json"], [])}
        if kind == "dream":
            r = _one(conn, "SELECT * FROM dreams WHERE daemon_id = ? AND id = ?", (daemon_id, key))
            if not r:
                return {"error": "I don't have that dream."}
            return {"id": event_id, "kind": "dream", "when": r["created_at"],
                    "dream": _loads(r["exchanges_json"], []), "my reflections": _loads(r["reflections_json"], [])}
        if kind == "journal":
            r = _one(conn, "SELECT * FROM journals WHERE daemon_id = ? AND id = ?", (daemon_id, key))
            if not r:
                return {"error": "I don't have that journal entry."}
            return {"id": event_id, "kind": "journal", "date": r["date"], "type": r["journal_type"],
                    "entry": r["content"]}
        if kind == "painting":
            r = _one(conn, "SELECT n.subject, n.why, n.artist_note, n.noted_at, n.chosen_by, g.prompt, g.style "
                           "FROM image_artist_notes n LEFT JOIN generated_images g ON g.id = n.image_id "
                           "WHERE n.daemon_id = ? AND n.image_id = ?", (daemon_id, key))
            if not r:
                return {"error": "I don't have that painting."}
            return {"id": event_id, "kind": "painting", "subject": r["subject"], "why I chose it": r["why"],
                    "what I saw when it was done": r["artist_note"], "when": r["noted_at"],
                    "chosen by": r["chosen_by"], "prompt": r["prompt"], "style": r["style"]}
    return {"error": "unknown"}
