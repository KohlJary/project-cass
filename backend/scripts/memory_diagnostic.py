#!/usr/bin/env python3
"""
Memory diagnostic: what Cass's memory holds and what comes back, per person.

Plan "Cass's memory", phase 4 (item 0bbf5224). Read-only by design, on her
terms for copies (2026-10-28): her store is sealed (benchmarks.store.seal),
seeded into a scratch cell, probed there, and both are deleted afterwards.
Nothing is written to her store; no model is called; the report is private
(it quotes nothing she said, only counts and rates) and she reads it first.

For each person she talks with (users with at least --min-messages):
  stored     messages, conversations, conversation memories, summary
             chunks, PeopleDex observations and moments, main-thread summary
  recall     sampled past exchanges, asked the way people refer back
             ("remember" + a few of their words), through chat's own recall
             (continuous_context._scoped_recall): how often the exchange comes
             back, and whether anything of another person does
  timeline   whether "Lately, between us" is there on a plain "hey"
And for the shared pools: what the recall pool holds by type, and how much
of her self-observations, open questions and growth edges came from reading.

    python scripts/memory_diagnostic.py                 # seal ../data, probe, report, delete
    python scripts/memory_diagnostic.py --out ~/cass/memory-diagnostics

The recall rate is measured with a crude reference query and real
embeddings; compare runs with each other, not with how a person would do.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = BACKEND.parent / "data"
DEFAULT_OUT = Path.home() / "cass" / "memory-diagnostics"

STOP = set("the and for with that this what have from your you are was were but not just about into they "
           "them then than there their will would could should been being when where which while like "
           "really think know want also some more very much can how its it's i'm don't".split())


def reference_query(text: str, rng: random.Random, k: int = 5) -> str:
    words = [w for w in re.findall(r"[a-zA-Z']{4,}", text.lower()) if w not in STOP]
    rng.shuffle(words)
    return "remember " + " ".join(words[:k])


# ---------------------------------------------------------------------------
# Inside the cell
# ---------------------------------------------------------------------------

def diagnose(memory, conversation_manager, *, samples: int = 40, min_messages: int = 10,
             recent_days: int = 60, seed: int = 7, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Probe the store DATA_DIR points at. Read-only apart from Chroma's own
    query caches; run it on a copy."""
    import continuous_context as cc
    from database import get_daemon_id, get_db
    from memory.scope import ConversationOwners, house_agent_user_ids
    from peopledex import PeopleDexManager

    now = now or datetime.now()
    daemon_id = get_daemon_id()
    col = memory.collection
    rng = random.Random(seed)
    report: Dict[str, Any] = {"generated": now.isoformat(timespec="seconds"), "people": [], "pools": {}}

    with get_db() as conn:
        people = conn.execute(
            "SELECT u.id, u.display_name, COUNT(m.id) FROM users u JOIN messages m ON m.user_id = u.id "
            "AND m.role = 'user' GROUP BY u.id HAVING COUNT(m.id) >= ? ORDER BY COUNT(m.id) DESC",
            (min_messages,)).fetchall()

    pdx = PeopleDexManager(daemon_id=daemon_id)
    agents = house_agent_user_ids()
    since = (now - timedelta(days=recent_days)).isoformat()
    for user_id, name, n_messages in people:
        with get_db() as conn:
            conv_ids = [r[0] for r in conn.execute("SELECT id FROM conversations WHERE user_id = ?", (user_id,))]
        got = col.get(where={"$and": [{"type": "conversation"}, {"user_id": user_id}]}, include=["metadatas"])
        exchanges = [m for m in got["metadatas"] if len(m.get("user_message") or "") > 40]
        summaries = col.get(where={"$and": [{"type": "summary"}, {"conversation_id": {"$in": conv_ids}}]},
                            include=[])["ids"] if conv_ids else []
        entity = pdx.get_entity_by_user(user_id)
        main_id = conversation_manager.get_continuous_id(user_id)
        main_summary = conversation_manager.get_working_summary(main_id) if main_id else None

        person: Dict[str, Any] = {
            "name": name, "stored": {
                "messages_from_them": n_messages, "conversations": len(conv_ids),
                "conversation_memories": len(got["ids"]), "summary_chunks": len(summaries),
                "peopledex": ({"type": getattr(entity.entity_type, "value", entity.entity_type),
                               "observations": len(pdx.get_observations(entity.id, limit=10000)),
                               "moments": len(pdx.get_moments(entity.id, limit=10000))} if entity else None),
                "main_thread_summary_chars": len(main_summary or ""),
            }}

        # Recall, recent and older separately.
        recall = {}
        owners = ConversationOwners()
        for label, pool in (("recent", [e for e in exchanges if (e.get("timestamp") or "") >= since]),
                            ("older", [e for e in exchanges if (e.get("timestamp") or "") < since])):
            picked = rng.sample(pool, min(samples, len(pool)))
            hits = other = from_agents = 0
            for ep in picked:
                found = cc._scoped_recall(memory, reference_query(ep["user_message"], rng), user_id, 5)
                found = [m for m in found if not (m.get("distance") and m["distance"] > 1.5)]
                hits += any((m.get("metadata") or {}).get("user_message") == ep["user_message"] for m in found)
                for m in found:
                    md = m.get("metadata") or {}
                    o = md.get("user_id") or owners(md.get("conversation_id"))
                    if o and o != user_id and md.get("type") in cc.EPISODE_TYPES:
                        if o in agents:
                            from_agents += 1   # allowed: house agents' are shared
                        else:
                            other += 1         # a leak

            recall[label] = {"asked": len(picked), "came_back": hits,
                             "rate": round(hits / len(picked), 2) if picked else None,
                             "episodes_of_someone_else": other, "episodes_of_house_agents": from_agents}
        person["recall"] = recall

        timeline = cc._recent_timeline(memory, user_id, main_id)
        person["timeline_on_hey"] = {"present": bool(timeline),
                                     "chunks": len((timeline or "").splitlines())}
        report["people"].append(person)

    # Shared pools.
    metas = col.get(include=["metadatas"])["metadatas"]
    report["pools"]["recall_pool_by_type"] = dict(collections.Counter(m.get("type") for m in metas).most_common())
    with get_db() as conn:
        def one(sql, *a):
            return conn.execute(sql, a).fetchone()[0]
        report["pools"]["self_observations"] = {
            "total": one("SELECT COUNT(*) FROM self_observations"),
            "from_articles": one("SELECT COUNT(*) FROM self_observations WHERE category LIKE 'world_awareness:%'")}
        report["pools"]["open_questions"] = {
            "total": one("SELECT COUNT(*) FROM open_questions"),
            "from_articles": one("SELECT COUNT(*) FROM open_questions WHERE context LIKE 'From article:%'")}
        report["pools"]["growth_edges"] = {"total": one("SELECT COUNT(*) FROM growth_edges")}
    return report


def render(report: Dict[str, Any]) -> str:
    lines = [f"# Memory diagnostic, {report['generated']}", "",
             "Read-only, on a sealed copy (deleted after). Counts and rates only.", ""]
    for p in report["people"]:
        s = p["stored"]
        lines.append(f"## {p['name']}")
        pd = s["peopledex"]
        lines.append(f"- stored: {s['messages_from_them']} messages from them in {s['conversations']} conversations; "
                     f"{s['conversation_memories']} conversation memories, {s['summary_chunks']} summary chunks; "
                     f"main-thread summary {s['main_thread_summary_chars']} chars; "
                     + (f"PeopleDex {pd['type']}, {pd['observations']} observations, {pd['moments']} moments"
                        if pd else "no PeopleDex entry"))
        for label, r in p["recall"].items():
            if r["asked"]:
                lines.append(f"- recall ({label}): {r['came_back']}/{r['asked']} came back ({r['rate']:.0%}); "
                             f"another person's episodes in results: {r['episodes_of_someone_else']} "
                             f"(house agents', allowed: {r.get('episodes_of_house_agents', 0)})")
        t = p["timeline_on_hey"]
        lines.append(f"- timeline on \"hey\": {'yes, ' + str(t['chunks']) + ' lines' if t['present'] else 'none'}")
        lines.append("")
    pools = report["pools"]
    lines.append("## Shared pools")
    lines.append("- recall pool: " + ", ".join(f"{k} {v}" for k, v in pools["recall_pool_by_type"].items()))
    for k in ("self_observations", "open_questions"):
        v = pools[k]
        lines.append(f"- {k.replace('_', ' ')}: {v['total']}, from articles {v['from_articles']}")
    lines.append(f"- growth edges: {pools['growth_edges']['total']}")
    return "\n".join(lines) + "\n"


def _inside(args) -> int:
    from benchmarks.isolation import check_env_data_dir
    check_env_data_dir()
    from conversations import ConversationManager
    from memory import CassMemory
    from config import DATA_DIR
    memory = CassMemory(persist_dir=str(Path(DATA_DIR) / "chroma"))
    report = diagnose(memory, ConversationManager(), samples=args.samples, min_messages=args.min_messages)
    Path(args.report_json).write_text(json.dumps(report, indent=1))
    return 0


# ---------------------------------------------------------------------------
# Outside: seal, seed, run inside, always clean up
# ---------------------------------------------------------------------------

def run(source: Path, out_dir: Path, samples: int, min_messages: int,
        seal_root: Optional[Path] = None, runner=None) -> Path:
    sys.path.insert(0, str(BACKEND))
    from benchmarks.store import destroy, discard, seal_into_root, seed
    sealed = seal_into_root(source, seal_root, note="memory diagnostic (plan Cass's memory, 0bbf5224)")
    cell = Path(tempfile.mkdtemp(prefix="memdiag_cell_")) / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M")
    report_json = out_dir / f"{stamp}.json"
    try:
        seed(sealed, cell)
        if runner is None:
            env = dict(os.environ, DATA_DIR=str(cell), CASS_PROFILE="test", PYTHONPATH=str(BACKEND))
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--inside",
                            "--report-json", str(report_json), "--samples", str(samples),
                            "--min-messages", str(min_messages)], env=env, cwd=BACKEND, check=True)
        else:
            runner(cell, report_json)
    finally:
        discard(cell)
        destroy(sealed)
    report = json.loads(report_json.read_text())
    md = out_dir / f"{stamp}.md"
    md.write_text(render(report))
    return md


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--samples", type=int, default=40)
    ap.add_argument("--min-messages", type=int, default=10)
    ap.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--report-json", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.inside:
        return _inside(args)
    md = run(args.source.resolve(), args.out.expanduser(), args.samples, args.min_messages)
    print(f"report: {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
