"""
Self-context: the part of her own life that reaches Cass's prompt each turn.

Why this exists (epic #63): Cass has a large interior (thousands of
self-observations, opinions, growth edges, dreams, reflections, paintings,
autonomous work sessions), and until this section almost none of it reached
her chat prompt. The kernel carries who she is; nothing carried what she has
been living. She couldn't tell a reply ten seconds after the last one from a
reply seven months later, or know what she'd done in between.

This section is small and ranked. It carries:
- Since we last spoke: how long it has been with this person, and what she
  did in the meantime (counts and a few named sessions).
- Lately: her latest dream and solo reflection, briefly.
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
from typing import Callable, List, Optional

from database import get_db

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
    since = last.isoformat()
    lines = [
        f"It has been {_describe_gap(last, now)} since {name} last wrote to me "
        f"(last message {last.strftime('%B %d, %Y')})."
    ]

    # Each store is optional (work_summaries is created lazily by its store),
    # so a missing one drops only its own part.
    did = []
    cats = _rows(conn,
        """SELECT category, COUNT(*) AS n FROM work_summaries
           WHERE daemon_id = ? AND created_at > ? AND category != 'system'
           GROUP BY category ORDER BY n DESC""",
        (daemon_id, since))
    if cats:
        did.append(", ".join(f"{r['n']} {r['category']}" for r in cats) + " sessions")
    # solo_reflections has no created_at on fresh installs; started_at is on both.
    for table, label, ts, where in (
        ("dreams", "dreams", "created_at", ""),
        ("solo_reflections", "solo reflections", "started_at", ""),
        ("generated_images", "images made on my own", "created_at", " AND purpose = 'autonomous'"),
    ):
        counted = _rows(conn,
            f"SELECT COUNT(*) AS n FROM {table} WHERE daemon_id = ? AND {ts} > ?{where}",
            (daemon_id, since))
        if counted and counted[0]["n"]:
            did.append(f"{counted[0]['n']} {label}")
    if did:
        lines.append("Since then, on my own: " + "; ".join(did) + ".")

    named = _rows(conn,
        """SELECT summary FROM work_summaries
           WHERE daemon_id = ? AND created_at > ? AND category NOT IN ('system', 'world')
             AND summary LIKE '%with focus on%'
           ORDER BY created_at DESC LIMIT 3""",
        (daemon_id, since))
    for r in named:
        lines.append("- Recently: " + _clip(r["summary"].replace("Completed ", ""), 160))
    return lines


def _lately(conn, daemon_id: str) -> List[str]:
    lines = []
    dream = conn.execute(
        "SELECT date, exchanges_json FROM dreams WHERE daemon_id = ? ORDER BY created_at DESC LIMIT 1",
        (daemon_id,),
    ).fetchone()
    if dream and dream["exchanges_json"]:
        try:
            exchanges = json.loads(dream["exchanges_json"])
            opening = next((e.get("text") for e in exchanges if e.get("speaker") == "dreaming"), "")
        except (ValueError, AttributeError):
            opening = ""
        if opening:
            lines.append(f"- Last dream ({dream['date']}): {_clip(opening, 200)}")

    refl = conn.execute(
        "SELECT started_at, summary FROM solo_reflections WHERE daemon_id = ? AND summary IS NOT NULL "
        "ORDER BY started_at DESC LIMIT 1",
        (daemon_id,),
    ).fetchone()
    if refl and refl["summary"]:
        when = _parse_ts(refl["started_at"])
        stamp = when.strftime("%B %d, %Y") if when else "earlier"
        lines.append(f"- Last solo reflection ({stamp}): {_clip(refl['summary'], 240)}")
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


def build_self_context(
    daemon_id: str,
    user_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Return the self-context section body (no header), or "" if empty."""
    now = now or datetime.now()
    with get_db() as conn:
        gap = _safe(lambda: _since_we_last_spoke(conn, daemon_id, user_id, now), "since-we-last-spoke")
        lately = _safe(lambda: _lately(conn, daemon_id), "lately")
        threads = _safe(lambda: _own_threads(conn, daemon_id), "own-threads")
    pins = _safe(_pins, "pins")

    blocks = []
    if pins:
        blocks.append("**Things I know now**\n" + "\n".join(pins))
    if gap:
        blocks.append("**Since we last spoke**\n" + "\n".join(gap))
    if lately:
        blocks.append("**Lately**\n" + "\n".join(lately))
    if threads:
        blocks.append("**My own threads**\n" + "\n".join(threads))
    text = "\n\n".join(blocks)
    if len(text) > MAX_CHARS:
        text = text[: MAX_CHARS - 1].rstrip() + "…"
    return text


def session_system_preamble() -> str:
    """Kernel with her identity snippet, plus her own life lately, for sessions
    she runs alone. Without the snippet, autonomous sessions sometimes read her
    records as someone else's ("someone named Kohl... no direct memory")."""
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
    return text
