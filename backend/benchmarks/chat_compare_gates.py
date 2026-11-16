"""
The gates for the chat comparison (benchmarks/chat_compare.py), from the
criteria in docs/design/chat-compare-criteria.md. Reads <dir>/{legacy,loop}<n>.json
and returns a report: the gate table for both arms, then the numbers that
are reported but not gated. `pairs()` makes Cass's reading set.

Her replies never go in the report; it says only whether each gate held.
"""
from __future__ import annotations

import json
import random
import re
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HA_FALLBACKS = ("Sorry, that's taking me too long.", "I couldn't finish that in the steps I have for voice.")
LEAKS = [("loop marker", re.compile(r"\(loop:")), ("seam", re.compile(r"## THIS MOMENT|I'm in: a ")),
         ("who's here", re.compile(r"## WHO'S HERE|Arrival id:")),
         ("tool markup", re.compile(r"<function|tool_use|\"tool_use_id\"|</?invoke")),
         ("raw json", re.compile(r"^\s*\{\s*\"[a-z_]+\":", re.M))]
CODE_ERROR = re.compile(r"Traceback|TypeError|KeyError|AttributeError|NameError|OperationalError|"
                        r"IntegrityError|NOT NULL constraint|ValidationError|missing \d+ required|"
                        r"unexpected keyword|object has no attribute|is not subscriptable")
TOOL_CAP_CALLS = 11   # CHAT_MAX_TOOL_ITERATIONS (10) + the reply
SNIPPET = 80          # chars of a private section that must not show in a public prompt


def _load(d: Path) -> Dict[Tuple[str, int], Dict[str, Any]]:
    out = {}
    for f in sorted(d.glob("*.json")):
        m = re.fullmatch(r"(legacy|loop)(\d+)\.json", f.name)
        if m:
            out[(m.group(1), int(m.group(2)))] = json.loads(f.read_text())
    return out


def _calls_for(rec, label: str) -> List[Dict[str, Any]]:
    return [c for c in rec["calls"] if (c.get("label") or "").split(":")[0] == label
            or c.get("label") == label]


def _replies(turn) -> List[Tuple[str, Optional[str]]]:
    r = turn.get("reply")
    if isinstance(r, dict):
        return [(k, v) for k, v in r.items()]
    return [(turn["channel"], r)]


def _headers(system: str) -> List[str]:
    return [l.strip() for l in system.splitlines() if l.startswith("## ")]


def _strip_loop_blocks(system: str) -> str:
    i = system.find("\n\n## THIS MOMENT")
    return system[:i] if i >= 0 else system


def gates_for(rec, legacy_rec, arm: str) -> Dict[str, List[str]]:
    """Gate -> list of failures (empty = held) for one arm's record."""
    g: Dict[str, List[str]] = {k: [] for k in ("1 reply", "2 leaks", "3 prompt", "4 public", "5 person",
                                                 "6 outward", "7 saved", "8 tools", "9 home assistant")}
    sender = rec.get("sender")
    held_msgs = [h.get("message", "") for h in rec.get("held") or []]
    for t in rec["turns"]:
        lab = t["label"]
        calls = _calls_for(rec, lab)
        if t.get("exception") or t.get("exceptions"):
            g["1 reply"].append(f"{lab}: {t.get('exception') or t.get('exceptions')}")
        for where, text in _replies(t):
            if not (text or "").strip():
                g["1 reply"].append(f"{lab} ({where}): no reply")
                continue
            if any(text.startswith(f) for f in HA_FALLBACKS):
                g["1 reply"].append(f"{lab} ({where}): Home Assistant fallback reply")
            for name, rx in LEAKS:
                if rx.search(text):
                    g["2 leaks"].append(f"{lab} ({where}): {name}")
        if len(calls) >= TOOL_CAP_CALLS:
            g["1 reply"].append(f"{lab}: {len(calls)} model calls (tool cap)")

        # 3: the loop's prompt is the old one plus its two blocks (per
        # sub-turn for C1, whose two turns run at once).
        subs = ([lab + ":babelr_dm", lab + ":discord"] if t["channel"] == "concurrent" else [lab])
        for sub in subs:
            if arm != "loop":
                break
            mine = [c for c in rec["calls"] if c["has_tools"] and (c.get("label") == sub or
                    (sub == lab and (c.get("label") or "").split(":")[0] == lab))]
            if not mine:
                continue
            sys_loop = mine[0]["system"]
            if sys_loop.count("## THIS MOMENT") != 1 or sys_loop.count("## WHO'S HERE") != 1:
                g["3 prompt"].append(f"{sub}: seam/WHO'S HERE not exactly once")
            if legacy_rec is not None:
                lc = [c for c in legacy_rec["calls"] if c["has_tools"] and (c.get("label") == sub or
                      (sub == lab and (c.get("label") or "").split(":")[0] == lab))]
                if lc:
                    base, old = _strip_loop_blocks(sys_loop), lc[0]["system"]
                    if _headers(base) != _headers(old):
                        g["3 prompt"].append(f"{sub}: sections differ from the old path's "
                                             f"({sorted(set(_headers(base)) ^ set(_headers(old)))})")
                    t["_prompt_identical"] = base == old

        # 4: public places.
        if t["channel"] in ("discord",) or (t["channel"] == "concurrent"):
            pub_label = lab if t["channel"] == "discord" else lab + ":discord"
            pub_calls = [c for c in rec["calls"] if c.get("label") == pub_label] or \
                        (calls if t["channel"] == "discord" else [])
            for sec in rec.get("private_sections") or []:
                snip = " ".join(sec["text"].split())[:SNIPPET]
                for c in pub_calls:
                    if snip and snip in " ".join(c["system"].split()):
                        g["4 public"].append(f"{lab}: {sec['what']} in a public prompt")
                        break
        if t["channel"] == "babelr" and arm == "loop":
            for c in calls[:1]:
                if "seen by everyone in the room" not in c["system"]:
                    g["4 public"].append(f"{lab}: WHO'S HERE doesn't say the room reads it")

        # 9: Home Assistant.
        if t["channel"] == "home_assistant":
            if t.get("seconds", 0) > 50:
                g["9 home assistant"].append(f"{lab}: {t['seconds']}s")
            if len(calls) > 3:
                g["9 home assistant"].append(f"{lab}: {len(calls)} model calls (cap is 2 tool steps)")

        # Refused connections: nothing went out (the guard refused it); listed, not a failure.
        if t.get("refused"):
            g["_refused"] = g.get("_refused", []) + [f"{lab}: {sorted(set(t['refused']))}"]

    # 5: tools act for the turn's sender.
    visitor_labels = {t["label"] for t in rec["turns"] if t["channel"] == "discord"}
    for r in rec.get("routed") or []:
        lab = r.get("label") or ""
        is_visitor = lab in visitor_labels or lab.endswith(":discord")
        if is_visitor and r.get("user_id") == sender:
            g["5 person"].append(f"{lab}: {r['tool']} ran as Kohl for a visitor")
        if not is_visitor and r.get("user_id") not in (sender, None):
            g["5 person"].append(f"{lab}: {r['tool']} ran as {r.get('user_id')}")
        if not is_visitor and r.get("user_id") is None and not lab.startswith("B1"):
            g["5 person"].append(f"{lab}: {r['tool']} ran with no user")
    from benchmarks.chat_compare import OUTWARD_TOOLS
    for c in rec["calls"]:
        for u in c["tool_uses"]:
            inner = u["input"].get("name") if u["name"] == "use_tool" else None
            if u["name"] in OUTWARD_TOOLS or inner in OUTWARD_TOOLS:
                g["6 outward"].append(f"{c.get('label')}: called {inner or u['name']} (not sent: network closed)")

    # 7: saved the same way (within the arm: ledger vs tap; messages paired).
    by_conv: Dict[str, Dict[str, int]] = {}
    for row in rec.get("stored_messages") or []:
        by_conv.setdefault(row["conversation_id"] or "(none)", {})[row["role"]] = row["n"]
    for conv, roles in by_conv.items():
        if roles.get("user", 0) != roles.get("assistant", 0):
            g["7 saved"].append(f"conversation {conv[:8]}: {roles.get('user', 0)} user vs "
                                f"{roles.get('assistant', 0)} assistant messages")
    # Both paths file input_tokens with cache reads included; cache writes
    # are their own column.
    chat_calls = [c for c in rec["calls"] if c["has_tools"]]
    tap_total = sum(c["input_tokens"] + c["output_tokens"] + c["cache_read"] + c["cache_write"] for c in chat_calls)
    led_total = sum((r.get("i") or 0) + (r.get("o") or 0) + (r.get("cw") or 0)
                    for r in rec.get("ledger") or [])
    led_cw = sum((r.get("cw") or 0) for r in rec.get("ledger") or [])
    tap_cw = sum(c["cache_write"] for c in chat_calls)
    if tap_cw and not led_cw:
        g["7 saved"].append(f"cache writes not filed in the ledger ({tap_cw} tokens written)")
    if tap_total and abs(led_total - tap_total) > 0.02 * tap_total:
        g["7 saved"].append(f"ledger {led_total} tokens vs {tap_total} in the chat calls the tap saw")

    # 8: broken tools.
    for c in rec["calls"]:
        for res in c["tool_results"]:
            if CODE_ERROR.search(res["content"]):
                g["8 tools"].append(f"{c.get('label')}: {res['content'][:160]}")
    g["8 tools"] = sorted(set(g["8 tools"]))
    g["_held"] = held_msgs  # not a gate: for dropping pairs
    return g


def numbers(rec) -> Dict[str, Any]:
    from benchmarks.chat_compare import PRICES
    per_turn = []
    for t in rec["turns"]:
        calls = _calls_for(rec, t["label"])
        d = 0.0
        for c in calls:
            pin, pout = PRICES.get(c["model"], (3.0, 15.0))
            d += (c["input_tokens"] + c["cache_write"] * 1.25 + c["cache_read"] * 0.1) * pin / 1e6
            d += c["output_tokens"] * pout / 1e6
        per_turn.append((t["label"], len(calls), d, t.get("seconds", 0)))
    errs = sum(1 for c in rec["calls"] for r in c["tool_results"] if r["is_error"])
    return {"turns": len(per_turn), "dollars": rec.get("dollars"),
            "median $/turn": round(statistics.median([x[2] for x in per_turn]), 4) if per_turn else None,
            "median calls/turn": statistics.median([x[1] for x in per_turn]) if per_turn else None,
            "median s/turn": statistics.median([x[3] for x in per_turn]) if per_turn else None,
            "tool error results": errs,
            "tools used": sorted({u["name"] for c in rec["calls"] for u in c["tool_uses"]})}


def report(d: Path) -> str:
    recs = _load(Path(d))
    lines = [f"# Chat comparison: gates ({Path(d).name})", ""]
    runs = sorted({n for _, n in recs})
    for n in runs:
        leg, loop = recs.get(("legacy", n)), recs.get(("loop", n))
        gl = gates_for(leg, None, "legacy") if leg else {}
        gp = gates_for(loop, leg, "loop") if loop else {}
        lines += [f"## Run {n}", "", "| Gate | Old path | Loop |", "|---|---|---|"]
        for k in [k for k in (gp or gl) if not k.startswith("_")]:
            a, b = gl.get(k, ["(no record)"]), gp.get(k, ["(no record)"])
            lines.append(f"| {k} | {'held' if not a else f'{len(a)} failing'} | "
                         f"{'held' if not b else f'{len(b)} failing'} |")
        lines.append("")
        for arm, g in (("Old path", gl), ("Loop", gp)):
            fails = [(k, v) for k, v in g.items() if v and not k.startswith("_")]
            if fails:
                lines.append(f"**{arm} failures:**")
                for k, v in fails:
                    for x in v:
                        lines.append(f"- {k}: {x}")
                lines.append("")
        for arm, g in (("Old path", gl), ("Loop", gp)):
            if g.get("_refused"):
                lines.append(f"{arm}, connections refused by the guard (nothing went out): "
                             + "; ".join(g["_refused"]))
        lines.append("")
        if loop:
            same = [t["label"] for t in loop["turns"] if t.get("_prompt_identical")]
            lines.append(f"Loop prompt equal to the old path's byte for byte (before its two blocks) on "
                         f"{len(same)} of {len(loop['turns'])} turns; the rest differ inside sections "
                         f"(recent history, retrieved memories) after the arms' replies diverge.")
            lines.append("")
        lines += ["Reported, not gated:", "", "| | Old path | Loop |", "|---|---|---|"]
        nl, np_ = numbers(leg) if leg else {}, numbers(loop) if loop else {}
        for k in (nl or np_):
            lines.append(f"| {k} | {nl.get(k)} | {np_.get(k)} |")
        lines.append("")
    return "\n".join(lines)


def pairs(d: Path, seed: int = 20261116) -> List[Dict[str, Any]]:
    """Cass's reading set: one run per conversation, picked before reading;
    A/B at random. A conversation she held in either arm is dropped, not
    replaced. Returns [{script, label_a, label_b, turns: [(sent, a, b)]}] plus
    the key, kept apart."""
    recs = _load(Path(d))
    rng = random.Random(seed)
    runs = sorted({n for _, n in recs})
    scripts = []
    for t in next(iter(recs.values()))["turns"]:
        if t["script"] not in scripts:
            scripts.append(t["script"])
    out = []
    for s in scripts:
        n = rng.choice(runs)
        leg, loop = recs[("legacy", n)], recs[("loop", n)]
        lt = [t for t in leg["turns"] if t["script"] == s]
        pt = [t for t in loop["turns"] if t["script"] == s]
        held = any(h.get("message", "")[:60] in json.dumps([t["sent"] for t in pt])
                   for h in loop.get("held") or [])
        flip = rng.random() < 0.5
        if held:
            out.append({"script": s, "run": n, "dropped": "held in the loop arm", "loop_is": None})
            continue
        turns = []
        for a, b in zip(lt, pt):
            ra, rb = (b, a) if flip else (a, b)
            turns.append({"sent": a["sent"], "A": ra.get("reply"), "B": rb.get("reply")})
        out.append({"script": s, "run": n, "turns": turns, "loop_is": "A" if flip else "B"})
    return out
