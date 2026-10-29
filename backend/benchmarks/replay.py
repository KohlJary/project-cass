"""
What can run locally: recorded inputs replayed on candidate models, compared
blind (benchmark plan phase 6, item 36f58a2d).

    python -m benchmarks replay --recordings DIR --site memory.gist \\
        --model anthropic:claude-haiku-4-5-20251001 --model ollama:qwen3:14b \\
        --judge anthropic:claude-sonnet-4-6 --n 30 --budget-usd 2 --out FILE

Recordings come from the llm_recording lever (llm_caller._record_io): one
JSON line per answered call, with the exact system prompt and messages the
call site sent. Each sampled input runs on every --model through
call_llm_sync("benchmark.replay"), recording output, failure and latency.
The first --model is the reference; for each other model and input, the
judge sees the task and the two outputs as A and B (order shuffled, seeded)
and picks one or a tie, without knowing which model wrote which.

Recordings hold her prompts: keep them, and the --out file, out of the repo.
This measures a call site's task on real inputs; whether a site moves is a
decision (item fe0b70fa), and her voice stays on Claude regardless.
"""
from __future__ import annotations

import json
import random
import re
import statistics
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .analysis import sign_test
from .pricing import cost
from .spec import Target

SEED = 20261028
TASK_MAX_CHARS = 12_000
OUTPUT_MAX_CHARS = 6_000

JUDGE_SYSTEM = """You compare two outputs for the same task, written by two different systems.
Judge only how well each one does the task its instructions describe: correct,
complete, follows the requested format, no invented content. Length and style
matter only where the instructions ask for them. You don't know which system
wrote which, and the order is random.

Answer with JSON only: {"winner": "A" | "B" | "tie", "reason": "<one sentence>"}"""


def load(recordings: Path, site: str) -> List[dict]:
    path = Path(recordings) / f"{site}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"no recordings for {site} at {path}")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sample(rows: List[dict], n: int, seed: int = SEED) -> List[dict]:
    rows = list(rows)
    random.Random(seed).shuffle(rows)
    return rows[:n]


def _task_text(row: dict) -> str:
    parts = []
    if row.get("system_prompt"):
        parts.append(f"[Instructions]\n{row['system_prompt']}")
    for m in row.get("messages") or []:
        content = m.get("content")
        if not isinstance(content, str):
            content = json.dumps(content)
        parts.append(f"[{m.get('role', 'user')}]\n{content}")
    text = "\n\n".join(parts)
    return text if len(text) <= TASK_MAX_CHARS else text[:TASK_MAX_CHARS] + "\n[...truncated]"


def run_model(row: dict, target: Target) -> dict:
    """One recorded input on one model."""
    import llm_caller
    from llm_config import ModelAssignment
    kw = dict(default=ModelAssignment(target.provider, target.model), system_prompt=row.get("system_prompt"),
              max_tokens=row.get("max_tokens") or 1000, temperature=row.get("temperature"),
              json_mode=bool(row.get("json_mode")), timeout=180.0, category="benchmark", operation="replay")
    if row.get("use_chat"):
        kw["messages"] = row.get("messages")
    else:
        kw["user_prompt"] = (row.get("messages") or [{}])[0].get("content", "")
    started = time.time()
    resp = llm_caller.call_llm_sync("benchmark.replay", **kw)
    return {"model": target.label, "ok": resp.error is None and bool(resp.content), "output": resp.content or "",
            "error": resp.error, "ms": int((time.time() - started) * 1000),
            "input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens}


def parse_verdict(text: str) -> Optional[str]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        w = json.loads(m.group(0)).get("winner")
    except ValueError:
        return None
    return w if w in ("A", "B", "tie") else None


def judge_pair(row: dict, ref: dict, cand: dict, judge: Target, rng: random.Random) -> dict:
    """Blind A/B between the reference's and a candidate's output. Returns the winner by model."""
    import llm_caller
    from llm_config import ModelAssignment
    flip = rng.random() < 0.5
    a, b = (cand, ref) if flip else (ref, cand)
    prompt = (f"## Task\n\n{_task_text(row)}\n\n## Output A\n\n{a['output'][:OUTPUT_MAX_CHARS]}\n\n"
              f"## Output B\n\n{b['output'][:OUTPUT_MAX_CHARS]}")
    resp = llm_caller.call_llm_sync("benchmark.judge", default=ModelAssignment(judge.provider, judge.model),
                system_prompt=JUDGE_SYSTEM, user_prompt=prompt, max_tokens=200, temperature=0.0,
                category="benchmark", operation="replay_judge")
    verdict = parse_verdict(resp.content)
    winner = None if verdict is None else ("tie" if verdict == "tie" else (a if verdict == "A" else b)["model"])
    return {"winner": winner, "shown_first": a["model"], "raw": (resp.content or "")[:300],
            "input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens}


def summarize(results: List[dict], models: List[str]) -> Dict[str, dict]:
    ref = models[0]
    out = {}
    for m in models:
        runs = [r["runs"][m] for r in results if m in r["runs"]]
        ms = [x["ms"] for x in runs if x["ok"]]
        s = {"inputs": len(runs), "failures": sum(1 for x in runs if not x["ok"]),
             "median_ms": statistics.median(ms) if ms else None}
        if m != ref:
            verdicts = [r["judged"].get(m, {}).get("winner") for r in results]
            # A failed candidate run loses; a failed reference run is left out.
            score = []
            for r, v in zip(results, verdicts):
                if not r["runs"][ref]["ok"]:
                    continue
                if not r["runs"][m]["ok"]:
                    score.append(-1.0)
                elif v == m:
                    score.append(1.0)
                elif v == ref:
                    score.append(-1.0)
                elif v == "tie":
                    score.append(0.0)
            s.update({"wins": score.count(1.0), "ties": score.count(0.0), "losses": score.count(-1.0),
                      "sign_p": sign_test(score), "unjudged": len(results) - len(score)})
        out[m] = s
    return out


def run(rows: List[dict], targets: List[Target], judge: Optional[Target], budget_usd: float,
        log: Callable[[str], None] = print) -> dict:
    rng = random.Random(SEED)
    spent = 0.0
    results = []
    for i, row in enumerate(rows):
        if spent >= budget_usd:
            log(f"budget: stopping after {i} input(s), spent ${spent:.4f}")
            break
        runs = {}
        for t in targets:
            r = run_model(row, t)
            if t.provider != "ollama":
                spent += cost(t.provider, t.model, r["input_tokens"] or 0, r["output_tokens"] or 0, conservative=True)
            runs[t.label] = r
        judged = {}
        ref = runs[targets[0].label]
        if judge is not None and ref["ok"]:
            for t in targets[1:]:
                cand = runs[t.label]
                if not cand["ok"]:
                    continue
                j = judge_pair(row, ref, cand, judge, rng)
                spent += cost(judge.provider, judge.model, j["input_tokens"] or 0, j["output_tokens"] or 0,
                              conservative=True)
                judged[t.label] = j
        results.append({"ts": row.get("ts"), "runs": runs, "judged": judged})
        log(f"{i + 1}/{len(rows)}: " + ", ".join(f"{k} {'ok' if v['ok'] else 'FAIL'} {v['ms']}ms"
                                               for k, v in runs.items()))
    models = [t.label for t in targets]
    return {"models": models, "judge": judge.label if judge else None, "spent_usd": round(spent, 4),
            "results": results, "summary": summarize(results, models)}


def rejudge(prev: dict, rows: List[dict], judge: Target, budget_usd: float,
            log: Callable[[str], None] = print) -> dict:
    """Judge an earlier report's saved outputs again with another judge, without rerunning
    the models. Inputs are matched to the report's results by recording timestamp."""
    by_ts = {r.get("ts"): r for r in rows}
    rng = random.Random(SEED)
    models = prev["models"]
    spent, results = 0.0, []
    for i, old in enumerate(prev["results"]):
        row = by_ts.get(old.get("ts"))
        if row is None:
            raise ValueError(f"recording {old.get('ts')} not found; rejudge needs the same recordings")
        if spent >= budget_usd:
            log(f"budget: stopping after {i} input(s), spent ${spent:.4f}")
            break
        runs, judged = old["runs"], {}
        ref = runs[models[0]]
        if ref["ok"]:
            for m in models[1:]:
                if not runs[m]["ok"]:
                    continue
                j = judge_pair(row, ref, runs[m], judge, rng)
                spent += cost(judge.provider, judge.model, j["input_tokens"] or 0, j["output_tokens"] or 0,
                              conservative=True)
                judged[m] = j
        results.append({"ts": old.get("ts"), "runs": runs, "judged": judged})
        log(f"{i + 1}/{len(prev['results'])} judged")
    return {"models": models, "judge": judge.label, "previous_judge": prev.get("judge"),
            "spent_usd": round(spent, 4), "results": results, "summary": summarize(results, models)}


def render(report: dict, site: str) -> str:
    ref = report["models"][0]
    lines = [f"## {site}: {len(report['results'])} recorded input(s), reference `{ref}`, "
             f"judge `{report['judge']}`", "",
             "| Model | Failures | Median ms | Wins / ties / losses vs reference | Sign test p |",
             "| --- | --- | --- | --- | --- |"]
    for m, s in report["summary"].items():
        wtl = "-" if m == ref else f"{s['wins']} / {s['ties']} / {s['losses']}"
        p = "-" if s.get("sign_p") is None else f"{s['sign_p']:.3f}"
        med = "-" if s["median_ms"] is None else f"{s['median_ms']:.0f}"
        lines.append(f"| `{m}` | {s['failures']}/{s['inputs']} | {med} | {wtl} | {p} |")
    return "\n".join(lines)
