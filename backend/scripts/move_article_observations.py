"""
Move her article observations out of her self-observations, to the articles
they came from (plan "Cass's memory", item 8eb07bb8).

Cass chose this on 2026-11-13, option 1 of 3 (move; not compact, not prune):
keep them findable, but out of the memory her conversations are recalled from.

What it does, for each self-observation the world integrator wrote
(category world_awareness:*, context source "article"):
  1. finds its article in consumed_articles and makes sure the observation is
     in that article's observations_json (adds it, marked as moved, if not);
  2. removes the copy from self_observations and from the recall pool
     (Chroma cass_memory, id cass_self_observation_<id>).
An observation whose article can't be found stays where it is, and is
reported. Nothing is deleted that isn't kept with its article first.

Dry run by default: reports what it would do. --apply seals a full,
read-only backup of the store first (benchmarks.store.seal; that is the
undo) and refuses to touch the live store while the vessel is running.

    python scripts/move_article_observations.py --data-dir ../data            # dry run
    python scripts/move_article_observations.py --data-dir ../data --apply    # vessel stopped
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parents[1]
LIVE_DATA = (BACKEND.parent / "data").resolve()
PREFIX = "world_awareness:"


def _vessel_running() -> bool:
    try:
        out = subprocess.run(["systemctl", "is-active", "cass-vessel"], capture_output=True, text=True)
        return out.stdout.strip() == "active"
    except OSError:
        return False


def _context(raw: Optional[str]) -> Dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _texts(observations: List[Any]) -> set:
    out = set()
    for o in observations:
        text = o.get("text") if isinstance(o, dict) else o
        if isinstance(text, str):
            out.add(" ".join(text.split()))
    return out


def plan(conn: sqlite3.Connection) -> Dict[str, Any]:
    """What a move would do: per observation, keep-with-article or stay."""
    rows = conn.execute(
        "SELECT id, daemon_id, category, observation, confidence, context_json, created_at "
        "FROM self_observations WHERE category LIKE ?", (PREFIX + "%",)).fetchall()
    articles: Dict[str, Optional[List[Any]]] = {}
    moves, stays = [], []
    for obs_id, daemon_id, category, text, confidence, ctx_raw, created_at in rows:
        ctx = _context(ctx_raw)
        article_id = ctx.get("article_id")
        if ctx.get("source") != "article" or not article_id:
            stays.append({"id": obs_id, "why": "not marked as from an article"})
            continue
        if article_id not in articles:
            row = conn.execute("SELECT observations_json FROM consumed_articles WHERE id = ? AND daemon_id = ?",
                               (article_id, daemon_id)).fetchone()
            if row is None:
                articles[article_id] = None
            else:
                try:
                    articles[article_id] = json.loads(row[0] or "[]")
                except json.JSONDecodeError:
                    articles[article_id] = None
        kept = articles[article_id]
        if kept is None or not isinstance(kept, list):
            stays.append({"id": obs_id, "why": f"article {article_id} not found"})
            continue
        already = " ".join((text or "").split()) in _texts(kept)
        moves.append({"id": obs_id, "article_id": article_id, "already_with_article": already,
                      "text": text, "category": category[len(PREFIX):], "confidence": confidence,
                      "created_at": created_at})
    return {"moves": moves, "stays": stays}


def apply(conn: sqlite3.Connection, chroma_dir: Path, moves: List[Dict[str, Any]]) -> Dict[str, int]:
    """Keep each with its article, then remove the self-observation copy."""
    added = Counter()
    by_article: Dict[str, List[Dict[str, Any]]] = {}
    for m in moves:
        if not m["already_with_article"]:
            by_article.setdefault(m["article_id"], []).append(m)
    with conn:
        for article_id, ms in by_article.items():
            row = conn.execute("SELECT observations_json FROM consumed_articles WHERE id = ?", (article_id,)).fetchone()
            kept = json.loads(row[0] or "[]")
            for m in ms:
                kept.append({"text": m["text"], "category": m["category"], "confidence": m["confidence"],
                             "moved_from_self_observation": m["id"], "observed_at": m["created_at"]})
                added["added_to_article"] += 1
            conn.execute("UPDATE consumed_articles SET observations_json = ? WHERE id = ?",
                         (json.dumps(kept), article_id))
        ids = [m["id"] for m in moves]
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            conn.execute(f"DELETE FROM self_observations WHERE id IN ({','.join('?' * len(chunk))})", chunk)
        added["removed_from_self_observations"] = len(ids)

    import chromadb
    from chromadb.config import Settings
    client = chromadb.PersistentClient(path=str(chroma_dir), settings=Settings(anonymized_telemetry=False))
    col = client.get_collection("cass_memory")
    doc_ids = [f"cass_self_observation_{m['id']}" for m in moves]
    present = 0
    for i in range(0, len(doc_ids), 500):
        chunk = doc_ids[i:i + 500]
        got = col.get(ids=chunk, include=[])
        if got["ids"]:
            present += len(got["ids"])
            col.delete(ids=got["ids"])
    added["removed_from_recall_pool"] = present
    return dict(added)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--apply", action="store_true", help="seal a backup, then move (default: dry run)")
    ap.add_argument("--seal-root", type=Path, default=None, help="where the backup seal goes")
    args = ap.parse_args(argv)

    data_dir = args.data_dir.resolve()
    db = data_dir / "cass.db"
    if not db.exists():
        print(f"no cass.db in {data_dir}", file=sys.stderr)
        return 2

    if not args.apply:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        p = plan(conn)
        conn.close()
        print(json.dumps({
            "dry_run": True,
            "would_move": len(p["moves"]),
            "already_with_their_article": sum(m["already_with_article"] for m in p["moves"]),
            "would_add_to_their_article_first": sum(not m["already_with_article"] for m in p["moves"]),
            "would_stay": len(p["stays"]),
            "stay_reasons": Counter(s["why"].split(" ")[0] for s in p["stays"]),
        }, indent=1, default=str))
        return 0

    if data_dir == LIVE_DATA and _vessel_running():
        print("refused: the vessel is running on this store; stop cass-vessel first", file=sys.stderr)
        return 3

    sys.path.insert(0, str(BACKEND))
    from benchmarks.store import seal_into_root
    sealed = seal_into_root(data_dir, args.seal_root,
                            note="backup before moving article observations (plan item 8eb07bb8)")
    print(f"backup sealed: {sealed}")

    conn = sqlite3.connect(str(db))
    p = plan(conn)
    result = apply(conn, data_dir / "chroma", p["moves"])
    conn.close()
    report = {"applied_at": datetime.now().isoformat(timespec="seconds"), "backup": str(sealed),
              "moved": len(p["moves"]), "stayed": len(p["stays"]), **result}
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
