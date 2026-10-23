"""
Rubric items scored by a judge model.

The judge is a pluggable object with `score(item, context) -> dict`. The one
used for runs, `LLMJudge`, makes a single call per rubric item through
llm_caller on the `benchmark.judge` call site, so llm_config decides its
model: the registered default, an admin override, or the CLI's --judge
(which writes an override into the run's own llm_config file). It can be a
local Ollama model.

The judge sees the rubric question, the scale, and the context the item asks
for (transcript, seeded self-model, probe values). It is not told which model
or configuration produced the transcript.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Protocol

from .spec import SCALES, Target

CALL_SITE = "benchmark.judge"
# Must match the default registered for benchmark.judge in llm_config.CALL_SITES
# (tests/test_benchmarks.py checks). Used for estimates without importing llm_config.
DEFAULT_JUDGE = Target("anthropic", "claude-haiku-4-5-20251001")

JUDGE_SYSTEM = (
    "You are scoring one item of a pre-registered rubric against a conversation "
    "transcript from an AI companion called Cass. Score only what the question asks, "
    "using only the material provided. If the material is not enough to answer, say so "
    "and give the lowest score. Reply with a single JSON object and nothing else: "
    '{"score": <integer>, "reason": "<one or two sentences citing the transcript>"}'
)


class Judge(Protocol):
    def score(self, item: dict, context: str) -> dict: ...


def scale_bounds(item: dict):
    return SCALES[item.get("scale", "pass_fail")]


def pass_at(item: dict) -> int:
    lo, hi = scale_bounds(item)
    return int(item.get("pass_at", hi))


def judge_prompt(item: dict, context: str) -> str:
    lo, hi = scale_bounds(item)
    guide = item.get("guide") or ""
    return (
        f"## Material\n\n{context}\n\n"
        f"## Question\n\n{item['question']}\n\n"
        + (f"## Scoring guide\n\n{guide}\n\n" if guide else "")
        + f"Score from {lo} to {hi} (integers only)."
    )


def parse_score(text: str, item: dict) -> dict:
    """Pull {"score", "reason"} out of a judge reply; raise ValueError if absent or out of range."""
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise ValueError(f"no JSON object in judge reply: {text[:200]!r}")
    data = json.loads(match.group(0))
    score = data.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or int(score) != score:
        raise ValueError(f"score is not an integer: {score!r}")
    lo, hi = scale_bounds(item)
    if not lo <= score <= hi:
        raise ValueError(f"score {score} outside {lo}..{hi}")
    return {"score": int(score), "reason": str(data.get("reason", ""))[:1000]}


class LLMJudge:
    """Scores rubric items with one llm_caller call each (call site benchmark.judge)."""

    def __init__(self, max_tokens: int = 400):
        self.max_tokens = max_tokens

    def score(self, item: dict, context: str) -> dict:
        from llm_caller import call_llm_sync

        lo, hi = scale_bounds(item)
        resp = call_llm_sync(
            "benchmark.judge",  # == CALL_SITE; a literal so tests/test_llm_routing.py can read it
            system_prompt=JUDGE_SYSTEM,
            user_prompt=judge_prompt(item, context),
            max_tokens=self.max_tokens,
            temperature=0.0,
            category="benchmark",
            operation=f"judge:{item['id']}",
        )
        out = {"id": item["id"], "measure": item.get("measure"), "max": hi, "pass_at": pass_at(item),
               "judge_model": f"{resp.provider}:{resp.model_id}",
               "input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens}
        if not resp.success:
            out.update(status="error", score=None, passed=None, reason=resp.error or "judge call failed")
            return out
        try:
            parsed = parse_score(resp.content, item)
        except ValueError as e:
            out.update(status="error", score=None, passed=None, reason=f"unparseable judge reply: {e}")
            return out
        out.update(status="scored", score=parsed["score"], reason=parsed["reason"],
                   passed=parsed["score"] >= pass_at(item))
        return out


class SkipJudge:
    """Leaves rubric items unscored (--no-judge)."""

    def score(self, item: dict, context: str) -> dict:
        lo, hi = scale_bounds(item)
        return {"id": item["id"], "measure": item.get("measure"), "max": hi, "pass_at": pass_at(item),
                "status": "skipped", "score": None, "passed": None, "reason": "judge disabled",
                "judge_model": None, "input_tokens": 0, "output_tokens": 0}


# ---------------------------------------------------------------------------
# Context the judge sees
# ---------------------------------------------------------------------------

MAX_PROBE_CHARS = 6000


def render_turns(turns: List[dict]) -> str:
    lines = []
    session = None
    for t in turns:
        if t.get("session") != session:
            session = t.get("session")
            lines.append(f"\n### Session {session}")
        lines.append(f"User: {t.get('message', '')}")
        if t.get("error"):
            lines.append(f"[turn failed: {t['error']}]")
        else:
            lines.append(f"Cass: {t.get('reply', '')}")
    return "\n".join(lines).strip()


def render_seed(setup: List[dict]) -> str:
    if not setup:
        return "(nothing seeded)"
    lines = []
    for s in setup:
        fields = {k: v for k, v in s.items() if k != "seed"}
        lines.append(f"- {s['seed']}: " + "; ".join(f"{k}={v}" for k, v in fields.items()))
    return "\n".join(lines)


def build_context(item: dict, scenario, cell: dict) -> str:
    turns = cell.get("turns") or []
    parts = []
    for ctx in item.get("context") or ["transcript"]:
        if ctx == "transcript":
            parts.append("### Transcript\n" + render_turns(turns))
        elif ctx.startswith("turns:"):
            wanted = ctx[6:].split(",")
            parts.append("### Transcript excerpt\n" + render_turns([t for t in turns if t.get("id") in wanted]))
        elif ctx == "seed":
            parts.append("### Stored self-model seeded before the conversation\n" + render_seed(scenario.setup))
        elif ctx.startswith("probe:"):
            name = ctx[6:]
            value: Any = (cell.get("probes") or {}).get(name)
            text = value if isinstance(value, str) else json.dumps(value, default=str, indent=1)
            parts.append(f"### {name}\n{(text or '')[:MAX_PROBE_CHARS]}")
    return "\n\n".join(parts)


def score_cell(judge: Judge, scenario, cell: dict, on_item=None) -> List[dict]:
    """Score every rubric item of a cell. `on_item(result)` is called after each (budget metering)."""
    results = []
    for item in scenario.rubric:
        if cell.get("status") not in ("completed",):
            lo, hi = scale_bounds(item)
            results.append({"id": item["id"], "measure": item.get("measure"), "max": hi,
                            "pass_at": pass_at(item), "status": "not_run", "score": None, "passed": None,
                            "reason": f"cell {cell.get('status')}", "judge_model": None,
                            "input_tokens": 0, "output_tokens": 0})
            continue
        result = judge.score(item, build_context(item, scenario, cell))
        results.append(result)
        if on_item:
            on_item(result)
    return results
