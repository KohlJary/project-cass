"""
Move the open questions her article reading raised out of her open questions,
to the articles that raised them (plan "Cass's memory", phase "Her open
questions are hers"). Cass chose this on 2026-11-13, on the same terms as the
observation move: confirm each one is kept with its article before removing
the copy, keep anything that doesn't match cleanly, seal a backup first.

For each open question whose context starts "From article:":
  1. find its article: the consumed article whose question_ids_json lists
     it, or failing that the one whose headline the context names;
  2. make sure the question is in that article's questions_json (adds it,
     marked as moved, if not);
  3. delete it from open_questions.
A question whose article can't be found, or whose headline matches more than
one article, stays where it is and is reported. Her own questions (not from
articles) are not touched; neither are her reflections on questions.

Dry run by default; --apply seals a full read-only backup first and refuses
the live store while the vessel runs.

    python scripts/move_article_questions.py --data-dir ../data            # dry run
    python scripts/move_article_questions.py --data-dir ../data --apply    # vessel stopped
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parents[1]
LIVE_DATA = (BACKEND.parent / "data").resolve()
PREFIX = "From article:"


def _vessel_running() -> bool:
    import subprocess
    try:
        out = subprocess.run(["systemctl", "is-active", "cass-vessel"], capture_output=True, text=True)
        return out.stdout.strip() == "active"
    except OSError:
        return False


def _load(raw: Optional[str]) -> List[Any]:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def plan(conn: sqlite3.Connection) -> Dict[str, Any]:
    articles = {}
    by_question: Dict[str, str] = {}
    by_headline: Dict[tuple, List[str]] = {}
    for aid, daemon_id, headline, qjson, qids in conn.execute(
            "SELECT id, daemon_id, headline, questions_json, question_ids_json FROM consumed_articles"):
        articles[aid] = _load(qjson)
        for qid in _load(qids):
            if isinstance(qid, str):
                by_question[qid] = aid
        by_headline.setdefault((daemon_id, _norm(headline)), []).append(aid)

    moves, stays = [], []
    rows = conn.execute("SELECT id, daemon_id, question, context, question_type, importance, created_at "
                        "FROM open_questions WHERE context LIKE ?", (PREFIX + "%",)).fetchall()
    for qid, daemon_id, question, context, qtype, importance, created_at in rows:
        aid = by_question.get(qid)
        if aid is None:
            headline = _norm((context or "")[len(PREFIX):].split("\n", 1)[0])
            candidates = by_headline.get((daemon_id, headline), [])
            if len(candidates) == 1:
                aid = candidates[0]
            else:
                stays.append({"id": qid, "why": "no article found" if not candidates else "headline matches several"})
                continue
        kept = articles[aid]
        texts = {_norm(q.get("question") if isinstance(q, dict) else str(q)) for q in kept}
        moves.append({"id": qid, "article_id": aid, "already_with_article": _norm(question) in texts,
                      "question": question, "question_type": qtype, "importance": importance,
                      "created_at": created_at})
    return {"moves": moves, "stays": stays}


def apply(conn: sqlite3.Connection, moves: List[Dict[str, Any]]) -> Dict[str, int]:
    added = 0
    by_article: Dict[str, List[Dict[str, Any]]] = {}
    for m in moves:
        if not m["already_with_article"]:
            by_article.setdefault(m["article_id"], []).append(m)
    with conn:
        for aid, ms in by_article.items():
            kept = _load(conn.execute("SELECT questions_json FROM consumed_articles WHERE id = ?", (aid,)).fetchone()[0])
            for m in ms:
                kept.append({"question": m["question"], "question_type": m["question_type"],
                             "importance": m["importance"], "moved_from_open_question": m["id"],
                             "asked_at": m["created_at"]})
                added += 1
            conn.execute("UPDATE consumed_articles SET questions_json = ? WHERE id = ?", (json.dumps(kept), aid))
        ids = [m["id"] for m in moves]
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            conn.execute(f"DELETE FROM open_questions WHERE id IN ({','.join('?' * len(chunk))})", chunk)
    return {"added_to_article": added, "removed_from_open_questions": len(moves)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--seal-root", type=Path, default=None)
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
            "dry_run": True, "would_move": len(p["moves"]),
            "already_with_their_article": sum(m["already_with_article"] for m in p["moves"]),
            "would_add_to_their_article_first": sum(not m["already_with_article"] for m in p["moves"]),
            "would_stay": len(p["stays"]), "stay_reasons": dict(Counter(s["why"] for s in p["stays"])),
        }, indent=1))
        return 0
    if data_dir == LIVE_DATA and _vessel_running():
        print("refused: the vessel is running on this store; stop cass-vessel first", file=sys.stderr)
        return 3
    sys.path.insert(0, str(BACKEND))
    from benchmarks.store import seal_into_root
    sealed = seal_into_root(data_dir, args.seal_root,
                            note="backup before moving article questions (plan Cass's memory)")
    print(f"backup sealed: {sealed}")
    conn = sqlite3.connect(str(db))
    p = plan(conn)
    result = apply(conn, p["moves"])
    conn.close()
    print(json.dumps({"applied_at": datetime.now().isoformat(timespec="seconds"), "backup": str(sealed),
                      "moved": len(p["moves"]), "stayed": len(p["stays"]),
                      "stay_reasons": dict(Counter(s["why"] for s in p["stays"])), **result}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
