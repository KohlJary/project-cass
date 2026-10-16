#!/usr/bin/env python3
"""
Attention report: how much of Cass's self-model is coming from the news.

Prints, for a DATA_DIR, the share of opinions, growth edges and open questions
that were created from consumed articles (overall and over the last N days),
how many research-synthesis reflections say the session didn't serve what she
intended, and what her research focus is. Run it before and after a change to
article selection (world/relevance.py, the integration gate, research focus)
to see whether her attention is moving.

Usage:
    python scripts/attention_report.py [DATA_DIR] [--days 30]

DATA_DIR defaults to $DATA_DIR, then backend/data. The database is opened
read-only; nothing is written.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# The low-value branch of research_synthesis.spell prompts "This research
# session didn't yield much value. Why might that be?" and her reflection
# echoes it, so these phrases mark a session she rated below 5/10 (for any
# reason: off-interest articles, no API credits, fatigue).
LOW_VALUE_PHRASES = [
    "didn't yield",
    "didn\u2019t yield",
    "did not yield",
    "not yield",
    "low-value",
    "low value",
]

# Phrases that say the material itself was not what she wanted to read. A
# heuristic, kept deliberately literal so the count is reproducible; the
# breakdown is printed so a change in one phrase's share is visible.
MISMATCH_PHRASES = [
    "rather than",
    "instead of",
    "had hoped",
    "unrelated",
    "irrelevant",
    "not relevant",
    "less relevant",
    "not directly relevant",
    "limited relevance",
    "low relevance",
    "mismatch",
    "off-topic",
    "not what i",
    "did not match",
    "didn't match",
    "intended",
    "not align",
    "didn't align",
    "did not align",
    "lack of alignment",
    "misalign",
    "less aligned",
    "tangential",
    "superficial",
    "not closely",
]

REFLECTION_CATEGORY = "spell:research_synthesis:reflection"


def _resolve_data_dir(arg: str) -> Path:
    if arg:
        return Path(arg)
    env = os.environ.get("DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "data"


def _open_readonly(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        sys.exit(f"No database at {db_path}")
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _count(conn, sql: str, params=()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def _share(part: int, whole: int) -> str:
    if not whole:
        return f"{part}/{whole}"
    return f"{part}/{whole} ({100.0 * part / whole:.0f}%)"


def article_shares(conn, since: str):
    """(label, from_articles_all, total_all, from_articles_recent, total_recent) per table."""
    rows = []

    # Opinions: formed_from = "article:<id>"
    rows.append((
        "opinions",
        _count(conn, "SELECT COUNT(*) FROM opinions WHERE formed_from LIKE 'article:%'"),
        _count(conn, "SELECT COUNT(*) FROM opinions"),
        _count(conn, "SELECT COUNT(*) FROM opinions WHERE formed_from LIKE 'article:%' AND date_formed >= ?", (since,)),
        _count(conn, "SELECT COUNT(*) FROM opinions WHERE date_formed >= ?", (since,)),
    ))

    # Growth edges: the integrator writes "Sparked by article <id>" into
    # observations_json (and category world_engagement).
    edge_from_article = "(observations_json LIKE '%Sparked by article%' OR category = 'world_engagement')"
    rows.append((
        "growth edges",
        _count(conn, f"SELECT COUNT(*) FROM growth_edges WHERE {edge_from_article}"),
        _count(conn, "SELECT COUNT(*) FROM growth_edges"),
        _count(conn, f"SELECT COUNT(*) FROM growth_edges WHERE {edge_from_article} AND first_noticed >= ?", (since,)),
        _count(conn, "SELECT COUNT(*) FROM growth_edges WHERE first_noticed >= ?", (since,)),
    ))

    # Open questions: context starts with "From article: <headline>"
    rows.append((
        "open questions",
        _count(conn, "SELECT COUNT(*) FROM open_questions WHERE context LIKE 'From article:%'"),
        _count(conn, "SELECT COUNT(*) FROM open_questions"),
        _count(conn, "SELECT COUNT(*) FROM open_questions WHERE context LIKE 'From article:%' AND created_at >= ?", (since,)),
        _count(conn, "SELECT COUNT(*) FROM open_questions WHERE created_at >= ?", (since,)),
    ))
    return rows


def _phrase_count(conn, phrases, since=None) -> int:
    clauses = " OR ".join("lower(observation) LIKE ?" for _ in phrases)
    params = [REFLECTION_CATEGORY]
    sql = f"SELECT COUNT(*) FROM self_observations WHERE category = ? AND ({clauses})"
    if since is not None:
        sql += " AND created_at >= ?"
    params.extend(f"%{p}%" for p in phrases)
    if since is not None:
        params.append(since)
    return _count(conn, sql, params)


def reflection_counts(conn, since: str):
    """
    Returns a dict:
      total / recent_total          all research-synthesis reflections
      low_value / recent_low_value  those from the low-value branch (rated < 5)
      mismatch / recent_mismatch    those saying the material was off-interest
      breakdown                     [(phrase, count)] for the mismatch phrases
    """
    total = _count(conn, "SELECT COUNT(*) FROM self_observations WHERE category = ?", (REFLECTION_CATEGORY,))
    recent_total = _count(
        conn, "SELECT COUNT(*) FROM self_observations WHERE category = ? AND created_at >= ?",
        (REFLECTION_CATEGORY, since),
    )
    return {
        "total": total,
        "recent_total": recent_total,
        "low_value": _phrase_count(conn, LOW_VALUE_PHRASES),
        "recent_low_value": _phrase_count(conn, LOW_VALUE_PHRASES, since),
        "mismatch": _phrase_count(conn, MISMATCH_PHRASES),
        "recent_mismatch": _phrase_count(conn, MISMATCH_PHRASES, since),
        "breakdown": [(p, _phrase_count(conn, [p])) for p in MISMATCH_PHRASES],
    }


def article_counts(conn, since: str):
    completed = _count(conn, "SELECT COUNT(*) FROM consumed_articles WHERE processing_status = 'completed'")
    recent = _count(
        conn, "SELECT COUNT(*) FROM consumed_articles WHERE processing_status = 'completed' AND consumed_at >= ?",
        (since,),
    )
    focused = _count(
        conn,
        "SELECT COUNT(*) FROM consumed_articles WHERE processing_status = 'completed' AND category = 'research_focus'",
    )
    recent_focused = _count(
        conn,
        "SELECT COUNT(*) FROM consumed_articles WHERE processing_status = 'completed' "
        "AND category = 'research_focus' AND consumed_at >= ?",
        (since,),
    )
    return completed, recent, focused, recent_focused


def focus_summary(conn):
    if not _table_exists(conn, "research_focus"):
        return None, 0
    current = conn.execute(
        "SELECT topic, source, created_at, times_used FROM research_focus "
        "WHERE status = 'active' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    total = _count(conn, "SELECT COUNT(*) FROM research_focus")
    return current, total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data_dir", nargs="?", help="DATA_DIR holding cass.db (default: $DATA_DIR or backend/data)")
    parser.add_argument("--days", type=int, default=30, help="recent window in days (default 30)")
    args = parser.parse_args(argv)

    data_dir = _resolve_data_dir(args.data_dir)
    db_path = data_dir / "cass.db"
    since = (datetime.now() - timedelta(days=args.days)).isoformat()

    conn = _open_readonly(db_path)
    try:
        print(f"Attention report for {db_path}")
        print(f"Recent window: last {args.days} days (since {since[:10]})\n")

        print("Self-model items created from consumed articles")
        print(f"  {'':16} {'overall':>22} {'last %d days' % args.days:>22}")
        for label, all_art, all_total, rec_art, rec_total in article_shares(conn, since):
            print(f"  {label:16} {_share(all_art, all_total):>22} {_share(rec_art, rec_total):>22}")

        r = reflection_counts(conn, since)
        print("\nResearch-synthesis reflections")
        print(f"  {'':44} {'overall':>16} {'last %d days' % args.days:>16}")
        print(f"  {'from a low-value session (rated < 5/10)':44} "
              f"{_share(r['low_value'], r['total']):>16} {_share(r['recent_low_value'], r['recent_total']):>16}")
        print(f"  {'saying the material was not what she wanted':44} "
              f"{_share(r['mismatch'], r['total']):>16} {_share(r['recent_mismatch'], r['recent_total']):>16}")
        print("  off-interest phrase breakdown (a reflection can match several):")
        for phrase, n in r["breakdown"]:
            if n:
                print(f"    {phrase!r:24} {n}")

        completed, recent, focused, recent_focused = article_counts(conn, since)
        print("\nArticles read (processing_status = completed)")
        print(f"  overall:        {completed} ({focused} found via research focus)")
        print(f"  last {args.days} days:   {recent} ({recent_focused} found via research focus)")

        current, history = focus_summary(conn)
        print("\nResearch focus")
        if current is None and history == 0 and not _table_exists(conn, "research_focus"):
            print("  (no research_focus table; database predates it)")
        elif current is None:
            print(f"  none set ({history} in history)")
        else:
            topic, source, created_at, times_used = current
            print(f"  {topic!r} set {created_at[:10]} via {source}, used {times_used or 0} time(s); {history} in history")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
