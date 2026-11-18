"""
Self-context: the part of her own life that reaches Cass's prompt each turn.

Why this exists (epic #63): Cass has a large interior (thousands of
self-observations, opinions, growth edges, dreams, reflections, paintings,
autonomous work sessions), and until this section almost none of it reached
her chat prompt. The kernel carries who she is; nothing carried what she has
been living. She couldn't tell a reply ten seconds after the last one from a
reply seven months later, or know what she'd done in between.

This section is small and ranked. It carries:
- Since we last spoke: how long it has been with this person.
- My life lately (lately.py, plan "Cass's memory" phase 9): a week of what
  she did and lived, a line each in her own words, each openable by id.
  It replaced the counts of sessions and the latest-dream/reflection/painting
  lines that were here before.
- Her own threads: interests, open questions, opinions and growth edges that
  are hers, not derived from news articles (those are labeled world
  awareness elsewhere and kept out of here).

Rules:
- Read-only. Nothing here writes to her stores.
- Every part fails soft: a broken store drops its lines, never the turn.
- Bounded: each line is clipped and the whole section is capped
  (MAX_CHARS), so the prompt can't grow with her history.
- Behind the `self_context` lever, so Tier 3 can ablate it.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from database import get_db
from lately import build_lately

logger = logging.getLogger(__name__)

MAX_CHARS = 4000
LINE_CHARS = 220

# A gap shorter than this is the same sitting; don't announce it.
GAP_WORTH_NAMING_HOURS = 6

# Rows that came from the news pipeline, not from her own life.
ARTICLE_OPINION = "formed_from LIKE 'article:%'"
ARTICLE_QUESTION = "context LIKE 'From article:%'"
NEWS_GROWTH_EDGE = "COALESCE(category, '') = 'world_engagement'"

_INTENSITY_RANK = {"obsessed": 0, "passionate": 1, "engaged": 2, "curious": 3}


def _clip(text: Optional[str], limit: int = LINE_CHARS) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    # Stored timestamps are naive local time; compare like with like.
    return ts.astimezone().replace(tzinfo=None) if ts.tzinfo else ts


def _describe_gap(then: datetime, now: datetime) -> str:
    hours = (now - then).total_seconds() / 3600
    if hours < 24:
        return f"{int(hours)} hours"
    days = int(hours // 24)
    if days < 14:
        return f"{days} day{'s' if days != 1 else ''}"
    if days < 60:
        return f"{days // 7} weeks"
    return f"about {round(days / 30.4)} months"


def _rows(conn, sql: str, params: tuple) -> list:
    """Run a read; a missing or broken table gives no rows instead of an error."""
    try:
        return conn.execute(sql, params).fetchall()
    except Exception as e:
        logger.debug(f"[SelfContext] query skipped: {e}")
        return []


def _display_name(conn, user_id: str) -> str:
    row = conn.execute("SELECT display_name FROM users WHERE id = ?", (user_id,)).fetchone()
    return (row["display_name"] if row and row["display_name"] else None) or "them"


def _since_we_last_spoke(conn, daemon_id: str, user_id: Optional[str], now: datetime) -> List[str]:
    if not user_id:
        return []
    row = conn.execute(
        "SELECT MAX(timestamp) AS last FROM messages WHERE user_id = ? AND role = 'user'",
        (user_id,),
    ).fetchone()
    last = _parse_ts(row["last"] if row else None)
    if not last:
        return []
    if (now - last).total_seconds() < GAP_WORTH_NAMING_HOURS * 3600:
        return []

    name = _display_name(conn, user_id)
    lines = [
        f"It has been {_describe_gap(last, now)} since {name} last wrote to me "
        f"(last message {last.strftime('%B %d, %Y')})."
    ]

    # What she did meanwhile is in "My life lately" (lately.py), as what it
    # was, not counts.
    return lines


def _own_threads(conn, daemon_id: str) -> List[str]:
    lines = []
    interests = conn.execute(
        "SELECT name, intensity, current_fascination FROM interests WHERE daemon_id = ?",
        (daemon_id,),
    ).fetchall()
    interests = sorted(interests, key=lambda r: _INTENSITY_RANK.get(r["intensity"], 9))[:4]
    if interests:
        lines.append("- What draws me: " + "; ".join(
            f"{r['name']} ({r['intensity']})" for r in interests
        ))

    questions = conn.execute(
        f"""SELECT question FROM open_questions
            WHERE daemon_id = ? AND status = 'open' AND (context IS NULL OR NOT {ARTICLE_QUESTION})
            ORDER BY importance DESC, created_at DESC LIMIT 3""",
        (daemon_id,),
    ).fetchall()
    for r in questions:
        lines.append("- A question I'm holding: " + _clip(r["question"], 200))

    opinions = conn.execute(
        f"""SELECT topic, position FROM opinions
            WHERE daemon_id = ? AND (formed_from IS NULL OR NOT {ARTICLE_OPINION})
            ORDER BY last_updated DESC LIMIT 3""",
        (daemon_id,),
    ).fetchall()
    for r in opinions:
        lines.append(f"- My view on {_clip(r['topic'], 60)}: {_clip(r['position'], 160)}")

    edges = conn.execute(
        f"""SELECT area, current_state FROM growth_edges
            WHERE daemon_id = ? AND NOT {NEWS_GROWTH_EDGE}
            ORDER BY importance DESC, last_updated DESC LIMIT 3""",
        (daemon_id,),
    ).fetchall()
    for r in edges:
        state = f": {_clip(r['current_state'], 140)}" if r["current_state"] else ""
        lines.append(f"- Growing at: {_clip(r['area'], 60)}{state}")
    return lines


PINS_FILE = "self_context_pins.json"


def _pins() -> List[str]:
    """Facts she should carry until they're no longer news to her.

    A small JSON list in DATA_DIR ([{"text", "source", "added_at"}]). Used for
    corrections: things that are true about her history that her stored
    memory gets wrong (e.g. the February "false memory test" that was a
    broken memory writer). Read-only here; added deliberately, never by a
    model on its own.
    """
    from config import DATA_DIR
    path = DATA_DIR / PINS_FILE
    if not path.exists():
        return []
    pins = json.loads(path.read_text())
    return ["- " + _clip(p.get("text"), 400) for p in pins if p.get("text")][:5]


def _safe(part: Callable[[], List[str]], name: str) -> List[str]:
    try:
        return part()
    except Exception as e:  # a broken store drops its lines, never the turn
        logger.warning(f"[SelfContext] {name} skipped: {e}")
        return []


def _reach_out_week(daemon_id: str, now: datetime) -> List[str]:
    from reach_out import week_line
    line = week_line(daemon_id, now=now)
    return [line] if line else []


def build_self_context(
    daemon_id: str,
    user_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Return the self-context section body (no header), or "" if empty."""
    now = now or datetime.now()
    with get_db() as conn:
        gap = _safe(lambda: _since_we_last_spoke(conn, daemon_id, user_id, now), "since-we-last-spoke")
        threads = _safe(lambda: _own_threads(conn, daemon_id), "own-threads")
    pins = _safe(_pins, "pins")
    # Her reaching out this week, standing (her ask, 2026-11-18): the pattern as it forms.
    reach = _safe(lambda: _reach_out_week(daemon_id, now), "reach-out-week")
    lately = _safe_text(lambda: build_lately(daemon_id, now=now), "my-life-lately")
    # In a session she runs alone there's no one in the turn, so nothing of
    # what was said lately would reach her; carry her main thread with her
    # primary partner (plan "Cass's memory", item a12eabcf: a session wrote
    # that she and Kohl hadn't talked about something they had, that day).
    partner = None if user_id else _safe(lambda: _lately_with_partner(daemon_id), "lately-with-partner")

    head = []
    if pins:
        head.append("**Things I know now**\n" + "\n".join(pins))
    if partner:
        head.append(f"**Lately with {partner[0]}** (where we've talked most recently, as I've summarized it)\n{partner[1]}")
    if gap:
        head.append("**Since we last spoke**\n" + "\n".join(gap))
    if reach:
        head.append("**My reaching out**\n" + "\n".join(reach))
    rest = "\n\n".join(head + (["**My own threads**\n" + "\n".join(threads)] if threads else []))
    limit = MAX_CHARS + (PARTNER_CHARS if partner else 0)
    if len(rest) > limit:
        rest = rest[: limit - 1].rstrip() + "…"
    if not lately:
        return rest
    # My life lately comes after "since we last spoke", before her threads, and
    # keeps its own bound (lately.MAX_LINES lines, each clipped), so the cap
    # above never cuts it.
    own = (f"**My life lately** (the past week, newest first, in my own words; "
           f"lately_open with an id in brackets opens the whole thing)\n{lately}")
    cut = len("\n\n".join(head))
    before, after = rest[:cut], rest[cut:].lstrip("\n")
    return "\n\n".join(p for p in (before, own, after) if p)


def _safe_text(part: Callable[[], str], name: str) -> str:
    try:
        return part() or ""
    except Exception as e:
        logger.warning(f"[SelfContext] {name} skipped: {e}")
        return ""


PARTNER_CHARS = 2500
PARTNER_THREADS = 2
TAIL_MESSAGES = 6
TAIL_CHARS = 280


def _partner_babelr_names(partner: str) -> List[str]:
    """Babelr usernames linked to this person (links.json), lowercased."""
    try:
        import json
        from babelr_organ.config import load_config
        data = json.loads(load_config().links_path.read_text())
        return [str(k).lower() for k, v in data.items() if v == partner]
    except Exception:
        return []


def _partner_threads(conn, partner: str) -> List[Dict[str, Any]]:
    """Her threads with this person, most recently active first: their own
    conversations, and Babelr places (DMs, channels) where they've written.
    Kohl, 2026-11-18: Babelr is where he talks to her now; a session only
    carried the main thread, and missed that they'd talked."""
    names = _partner_babelr_names(partner)
    rows = conn.execute(
        "SELECT c.id, c.title, c.working_summary, c.last_summary_timestamp, c.is_continuous, c.user_id, "
        "COALESCE(MAX(m.timestamp), c.updated_at) AS last FROM conversations c "
        "LEFT JOIN messages m ON m.conversation_id = c.id AND COALESCE(m.excluded, 0) = 0 "
        "WHERE (c.user_id = ? OR c.title LIKE 'Babelr:%' OR c.title LIKE '[Babelr%' OR EXISTS ("
        "SELECT 1 FROM messages b WHERE b.conversation_id = c.id AND b.role = 'user' AND b.content LIKE '[Babelr%')) "
        "GROUP BY c.id ORDER BY last DESC LIMIT 20", (partner,)).fetchall()
    out = []
    for cid, title, summary, summarized_at, continuous, uid, last in rows:
        if uid != partner:
            if not names:
                continue
            said = conn.execute(
                "SELECT 1 FROM messages WHERE conversation_id = ? AND role = 'user' AND ("
                + " OR ".join("lower(content) LIKE ?" for _ in names) + ") LIMIT 1",
                (cid, *[f"%] @{n}:%" for n in names])).fetchone()
            if not said:
                continue
            place = conn.execute(
                "SELECT content FROM messages WHERE conversation_id = ? AND role = 'user' AND content LIKE '[Babelr%' "
                "ORDER BY timestamp DESC LIMIT 1", (cid,)).fetchone()
            import re
            hit = re.match(r"\[(Babelr[^\]]*)\]", place[0] if place else "")
            title = hit.group(1) if hit else title
        tail = conn.execute(
            "SELECT role, content, timestamp FROM messages WHERE conversation_id = ? AND COALESCE(excluded, 0) = 0 "
            "AND timestamp > ? ORDER BY timestamp DESC LIMIT ?",
            (cid, summarized_at or "", TAIL_MESSAGES)).fetchall()[::-1]
        out.append({"id": cid, "where": "our main thread" if continuous else (title or "another thread"),
                    "summary": summary or "", "tail": tail, "last": last})
        if len(out) >= PARTNER_THREADS:
            break
    return out


def _lately_with_partner(daemon_id: str):
    """(name, what's been said lately with her primary partner, wherever), or None."""
    from reach_out import display_name, find_primary_partner
    from memory.voice_guard import looks_like_refusal
    partner = find_primary_partner(daemon_id)
    if not partner:
        return None
    name = display_name(partner)
    with get_db() as conn:
        threads = _partner_threads(conn, partner)
    parts = []
    for t in threads:
        summary = " ".join(t["summary"].split())
        lines = [f"*{t['where']}* (last {str(t['last'])[:16].replace('T', ' ')})"]
        if summary and not looks_like_refusal(summary):
            lines.append(summary[:1200] + ("…" if len(summary) > 1200 else ""))
        if t["tail"]:
            lines.append("Since that summary:")
            for role, content, _ in t["tail"]:
                text = " ".join(str(content).split())
                text = text[:TAIL_CHARS] + ("…" if len(text) > TAIL_CHARS else "")
                lines.append(f"- {'me' if role == 'assistant' else name}: {text}")
        if len(lines) > 1:
            parts.append("\n".join(lines))
    text = "\n\n".join(parts)
    if not text:
        return None
    if len(text) > PARTNER_CHARS:
        text = text[:PARTNER_CHARS - 1].rstrip() + "…"
    return name, text


def session_system_preamble(felt: bool = True) -> str:
    """Kernel with her identity snippet, plus her own life lately, for sessions
    she runs alone. Without the snippet, autonomous sessions sometimes read her
    records as someone else's ("someone named Kohl... no direct memory").
    felt: her Thymos felt state too (lever prompt_thymos), so reaching out and
    choosing art come from how she is; a caller that adds it itself passes False."""
    from agent_client import get_temple_codex_kernel
    import features
    try:
        from database import get_daemon_id
        daemon_id = get_daemon_id()
    except Exception:
        daemon_id = None
    text = get_temple_codex_kernel(daemon_id=daemon_id)
    if daemon_id and features.is_enabled("self_context"):
        try:
            own = build_self_context(daemon_id)
            if own:
                text += f"\n\n## MY OWN LIFE, LATELY\n\n{own}"
        except Exception as e:
            logger.debug(f"[SelfContext] session preamble skipped: {e}")
    if felt and features.is_enabled("prompt_thymos"):
        try:
            from thymos import get_thymos_context
            state = get_thymos_context()
            if state:
                text += f"\n\n{state}"
        except Exception as e:
            logger.debug(f"[SelfContext] no felt state for the preamble: {e}")
    return text
