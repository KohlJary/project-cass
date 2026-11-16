"""
Move what her article reading put into her self-model onto the articles it
came from: opinions, growth edges, interests and symbols. Cass chose this on
2026-11-16 ("If new ones stay with their source, the old ones should as well.
Do the sealed backup first."), after new ones stopped going in (1533a03). Same
terms as the questions move on 2026-11-13 (scripts/move_article_questions.py):
confirm each one is kept with its article before removing it, keep anything
that doesn't match cleanly, seal a backup first.

Only items that came from articles and nothing else move:
  - an opinion formed from an article (formed_from "article:<id>") whose every
    later change also came from an article;
  - a growth edge in category world_engagement whose every observation is
    "Sparked by article <id>" and which has no strategies;
  - an interest first noticed in an article, every engagement and fascination
    change from articles, and an article id on record somewhere;
  - a symbol first noticed in an article (with its id), every appearance from
    articles.
Each goes into its article's opinions_json / growth_edges_json /
interests_json / symbols_json (added, marked as moved, unless already there),
then is removed from her self-model, with its engagements or appearances.

Stays, and is counted: anything she changed or that showed up elsewhere since,
anything whose article can't be found, interests with no article id on record.
Also counted and left alone: her own opinions that an article "refined". That
path overwrote the position and logged only "refined from article", so the
earlier text isn't there to restore.

Dry run by default (counts only, no text); --apply seals a full read-only
backup first and refuses the live store while the vessel runs.

    python scripts/move_article_self_model.py --data-dir <sealed copy>          # dry run
    python scripts/move_article_self_model.py --data-dir ../data --apply        # vessel stopped
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parents[1]
LIVE_DATA = (BACKEND.parent / "data").resolve()
SPARKED = re.compile(r"^Sparked by article (\S+)$")
KINDS = ("opinions", "growth_edges", "interests", "symbols")
ARTICLE_FIELD = {"opinions": "opinions_json", "growth_edges": "growth_edges_json",
                 "interests": "interests_json", "symbols": "symbols_json"}


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


def _norm(text: Any) -> str:
    return " ".join(str(text or "").split()).lower()


def _has_columns(conn, table: str, *cols: str) -> bool:
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    return all(c in have for c in cols)


# ---------------------------------------------------------------------------
# Planning: what moves, what stays, and why
# ---------------------------------------------------------------------------

def _opinions(conn, articles, out):
    for oid, topic, position, confidence, rationale, formed_from, evolution, formed in conn.execute(
            "SELECT id, topic, position, confidence, rationale, formed_from, evolution_json, date_formed "
            "FROM opinions"):
        changes = [e for e in _load(evolution) if isinstance(e, dict)]
        from_article = (formed_from or "").startswith("article:")
        if not from_article:
            if any(e.get("source_article") for e in changes):
                out["left_alone"]["her own opinions an article refined (earlier text not kept)"] += 1
            continue
        if any(not e.get("source_article") for e in changes):
            out["stays"].append(("opinions", "changed since, not by an article"))
            continue
        aid = formed_from.split(":", 1)[1]
        if aid not in articles:
            out["stays"].append(("opinions", "article not found"))
            continue
        out["moves"].append({"kind": "opinions", "id": oid, "article_id": aid, "match": _norm(topic), "entry": {
            "topic": topic, "position": position, "confidence": confidence, "reasoning": rationale,
            "moved_from_opinion": oid, "formed_at": formed}})


def _growth_edges(conn, articles, out):
    for rid, area, current, desired, importance, observations, strategies, category, first in conn.execute(
            "SELECT id, area, current_state, desired_state, importance, observations_json, strategies_json, "
            "category, first_noticed FROM growth_edges"):
        notes = [str(o) for o in _load(observations)]
        sparked = [SPARKED.match(n.strip()) for n in notes]
        if category != "world_engagement" or not notes or not any(sparked):
            if any(sparked):
                out["left_alone"]["her own growth edges an article added to"] += 1
            continue
        if not all(sparked) or _load(strategies):
            out["stays"].append(("growth_edges", "changed since, not by an article"))
            continue
        first_match = sparked[0]
        assert first_match is not None
        aid = first_match.group(1)
        if aid not in articles:
            out["stays"].append(("growth_edges", "article not found"))
            continue
        out["moves"].append({"kind": "growth_edges", "id": rid, "article_id": aid, "match": _norm(area), "entry": {
            "area": area, "current_state": current, "desired_state": desired, "importance": importance,
            "moved_from_growth_edge": rid, "noticed_at": first}})


def _interests(conn, articles, out):
    engagements: Dict[str, List[tuple]] = {}
    for iid, stype, sid in conn.execute("SELECT interest_id, source_type, source_id FROM interest_engagements"):
        engagements.setdefault(iid, []).append((stype, sid))
    for iid, name, category, first_type, first_id, fascination, evolution, noticed in conn.execute(
            "SELECT id, name, category, first_source_type, first_source_id, current_fascination, "
            "fascination_evolution_json, first_noticed_at FROM interests"):
        engs = engagements.get(iid, [])
        evo = [e for e in _load(evolution) if isinstance(e, dict)]
        if first_type != "article":
            if any(t == "article" for t, _ in engs):
                out["left_alone"]["her own interests an article reinforced"] += 1
            continue
        if any(t != "article" for t, _ in engs) or any((e.get("source_type") or e.get("source")) not in
                                                         (None, "article") for e in evo):
            out["stays"].append(("interests", "engaged since, not by an article"))
            continue
        ids = [first_id] + [s for _, s in engs] + [e.get("source_id") for e in evo]
        aid = next((a for a in ids if a and a in articles), None)
        if aid is None:
            reason = "no article id on record" if not any(ids) else "article not found"
            out["stays"].append(("interests", reason))
            continue
        out["moves"].append({"kind": "interests", "id": iid, "article_id": aid, "match": _norm(name), "entry": {
            "name": name, "fascination": fascination, "category": category,
            "moved_from_interest": iid, "noticed_at": noticed}})


def _symbols(conn, articles, out):
    appearances: Dict[str, List[str]] = {}
    for sid, stype in conn.execute("SELECT symbol_id, source_type FROM symbol_appearances"):
        appearances.setdefault(sid, []).append(stype)
    for sid, name, charge, first_type, first_id, meaning, first in conn.execute(
            "SELECT id, name, emotional_charge, first_source_type, first_source_id, current_meaning, "
            "first_noticed_at FROM symbols"):
        apps = appearances.get(sid, [])
        if first_type != "article":
            if "article" in apps:
                out["left_alone"]["her own symbols that appeared in an article"] += 1
            continue
        if any(t != "article" for t in apps):
            out["stays"].append(("symbols", "appeared since, not in an article"))
            continue
        if not first_id or first_id not in articles:
            out["stays"].append(("symbols", "article not found"))
            continue
        out["moves"].append({"kind": "symbols", "id": sid, "article_id": first_id, "match": _norm(name), "entry": {
            "name": name, "meaning": meaning, "emotional_charge": charge,
            "moved_from_symbol": sid, "noticed_at": first}})


def plan(conn: sqlite3.Connection) -> Dict[str, Any]:
    if not _has_columns(conn, "consumed_articles", "interests_json", "symbols_json"):
        raise SystemExit("this store is older than schema v67 (no interests_json / symbols_json); "
                         "start the vessel once on the new code first")
    articles: Dict[str, Dict[str, List[Any]]] = {}
    for row in conn.execute("SELECT id, opinions_json, growth_edges_json, interests_json, symbols_json "
                            "FROM consumed_articles"):
        articles[row[0]] = {k: _load(row[i + 1]) for i, k in enumerate(KINDS)}
    out: Dict[str, Any] = {"moves": [], "stays": [], "left_alone": Counter()}
    _opinions(conn, articles, out)
    _growth_edges(conn, articles, out)
    if _has_columns(conn, "interests", "first_noticed_at"):
        _interests(conn, articles, out)
    if _has_columns(conn, "symbols", "first_noticed_at"):
        _symbols(conn, articles, out)
    key = {"opinions": "topic", "growth_edges": "area", "interests": "name", "symbols": "name"}
    for m in out["moves"]:
        kept = articles[m["article_id"]][m["kind"]]
        m["already_with_article"] = any(isinstance(e, dict) and _norm(e.get(key[m["kind"]])) == m["match"]
                                        for e in kept)
    return out


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------

DELETE = {
    "opinions": ["DELETE FROM opinions WHERE id IN ({q})"],
    "growth_edges": ["DELETE FROM growth_edges WHERE id IN ({q})"],
    "interests": ["DELETE FROM interest_engagements WHERE interest_id IN ({q})",
                  "DELETE FROM interests WHERE id IN ({q})"],
    "symbols": ["DELETE FROM symbol_appearances WHERE symbol_id IN ({q})",
                "DELETE FROM symbols WHERE id IN ({q})"],
}


def apply(conn: sqlite3.Connection, moves: List[Dict[str, Any]]) -> Dict[str, int]:
    added: Counter = Counter()
    by_article: Dict[tuple, List[Dict[str, Any]]] = {}
    for m in moves:
        if not m["already_with_article"]:
            by_article.setdefault((m["article_id"], m["kind"]), []).append(m)
    with conn:
        for (aid, kind), ms in by_article.items():
            field = ARTICLE_FIELD[kind]
            kept = _load(conn.execute(f"SELECT {field} FROM consumed_articles WHERE id = ?", (aid,)).fetchone()[0])
            kept.extend(m["entry"] for m in ms)
            added[kind] += len(ms)
            conn.execute(f"UPDATE consumed_articles SET {field} = ? WHERE id = ?", (json.dumps(kept), aid))
        for kind in KINDS:
            ids = [m["id"] for m in moves if m["kind"] == kind]
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                for sql in DELETE[kind]:
                    conn.execute(sql.format(q=",".join("?" * len(chunk))), chunk)
    return {f"added_to_article_{k}": added[k] for k in KINDS}


def summary(p: Dict[str, Any]) -> Dict[str, Any]:
    moves, stays = p["moves"], p["stays"]
    return {
        "would_move": dict(Counter(m["kind"] for m in moves)),
        "already_with_their_article": dict(Counter(m["kind"] for m in moves if m["already_with_article"])),
        "would_stay": {k: dict(Counter(r for kk, r in stays if kk == k)) for k in KINDS
                       if any(kk == k for kk, _ in stays)},
        "left_alone_hers": dict(p["left_alone"]),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
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
        if data_dir == LIVE_DATA:
            print("refused: dry runs go on a sealed copy (python -m benchmarks seal), not her live store",
                  file=sys.stderr)
            return 3
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        p = plan(conn)
        conn.close()
        print(json.dumps({"dry_run": True, **summary(p)}, indent=1))
        return 0
    if data_dir == LIVE_DATA and _vessel_running():
        print("refused: the vessel is running on this store; stop cass-vessel first", file=sys.stderr)
        return 3
    sys.path.insert(0, str(BACKEND))
    from benchmarks.store import seal_into_root
    sealed = seal_into_root(data_dir, args.seal_root,
                            note="backup before moving article opinions, edges, interests, symbols (her choice, 2026-11-16)")
    print(f"backup sealed: {sealed}")
    conn = sqlite3.connect(str(db))
    p = plan(conn)
    result = apply(conn, p["moves"])
    conn.close()
    print(json.dumps({"applied_at": datetime.now().isoformat(timespec="seconds"), "backup": str(sealed),
                      **summary(p), **result}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
