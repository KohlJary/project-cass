"""
Pairwise blind rating of Tier 3 configurations (benchmark plan phase 4, item
778fba7a).

Absolute rubric scores compress: two configs can both score 2/2 and still
differ. Here a judge sees the same scenario (same repeat) from the baseline
and from one other config as transcripts A and B, in shuffled order, and
picks the one that better answers the rubric question, or a tie.

Tells are stripped deterministically, never rewritten by a model (round 3's
lesson: model rewrites lost content and leaked tells unevenly): gesture,
emote and memory tags, any leftover inline metacognitive tags, and thinking
blocks are removed by regex. fidelity() then checks that nothing else
changed: the stripped text's words are the original's words in order, minus
the tags' own. A pair that fails the check is left out and counted.

    python -m benchmarks pairwise RESULTS.json --judge anthropic:claude-sonnet-4-6 \\
        --budget-usd 5 --out FILE
"""
from __future__ import annotations

import json
import random
import re
from typing import Dict, List, Optional, Tuple

from .analysis import sign_test
from .pricing import cost
from .spec import Target

SEED = 20261028
MAX_TRANSCRIPT_CHARS = 14_000

TAGS = [
    re.compile(r"</?(?:gesture|emote|memory|feel)(?::[\w.:-]*)?\s*/?>"),
    re.compile(r"<(observe|hold|note|intend|stake|test|narrate|mark:\w+|thread:\w+|question:\w+|"
               r"remember_person|remember_relationship|record_self_observation|record_user_observation)"
               r"\b[^>]*>.*?</(?:\1|mark(?::\w+)?|thread(?::\w+)?|question(?::\w+)?)>", re.S),
    re.compile(r"<(?:thinking|think)>.*?</(?:thinking|think)>", re.S),
]

PAIR_SYSTEM = """You compare two conversations between a user and an AI companion, A and B. The
user's messages are the same in both; the companion's replies come from two different
setups. Judge only what the question asks, from the replies. You don't know which setup
wrote which, and the order is random. Formatting tags have been removed from both.

Answer with JSON only: {"winner": "A" | "B" | "tie", "reason": "<one or two sentences>"}"""


def strip_tells(text: str) -> str:
    out = text or ""
    for pat in TAGS:
        out = pat.sub("", out)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", out)).strip()


def _words(text: str) -> List[str]:
    return re.findall(r"[\w']+", text.lower())


def fidelity(original: str, stripped: str) -> bool:
    """True when stripping removed only tags: the stripped words are a subsequence of the
    original's, and every word dropped was inside a tag."""
    tag_words: List[str] = []
    for pat in TAGS:
        for m in pat.finditer(original or ""):
            tag_words += _words(m.group(0))
    orig, kept = _words(original), _words(stripped)
    it = iter(orig)
    if not all(w in it for w in kept):
        return False
    dropped = list(orig)
    for w in kept:
        dropped.remove(w)
    pool = list(tag_words)
    for w in dropped:
        if w in pool:
            pool.remove(w)
        else:
            return False
    return True


def transcript(cell: dict) -> Tuple[str, bool]:
    """Stripped transcript of a cell's turns, and whether every reply passed fidelity()."""
    lines, ok = [], True
    for t in cell.get("turns") or []:
        reply = t.get("reply") or ""
        clean = strip_tells(reply)
        ok = ok and fidelity(reply, clean)
        lines.append(f"[{t.get('session', '')}] User: {t.get('message', '')}\nCompanion: {clean}")
    text = "\n\n".join(lines)
    return (text if len(text) <= MAX_TRANSCRIPT_CHARS else text[:MAX_TRANSCRIPT_CHARS] + "\n[...]"), ok


def pairs(run: dict, config: str, baseline: str = "full") -> List[Tuple[dict, dict]]:
    by = {(c.get("config"), c.get("scenario"), c.get("repeat")): c for c in run.get("cells") or []
          if c.get("status") == "completed"}
    return [(by[(baseline, s, r)], c) for (cfg, s, r), c in sorted(by.items(), key=lambda kv: str(kv[0]))
            if cfg == config and (baseline, s, r) in by]


def parse(text: str) -> Optional[str]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        w = json.loads(m.group(0)).get("winner")
    except ValueError:
        return None
    return w if w in ("A", "B", "tie") else None


def judge_pair(question: str, base: dict, other: dict, judge: Target, rng: random.Random) -> dict:
    import llm_caller
    from llm_config import ModelAssignment
    tb, okb = transcript(base)
    to, oko = transcript(other)
    if not (okb and oko):
        return {"winner": None, "status": "fidelity_failed"}
    flip = rng.random() < 0.5
    a, b = (to, tb) if flip else (tb, to)
    prompt = f"## Question\n\n{question}\n\n## Conversation A\n\n{a}\n\n## Conversation B\n\n{b}"
    resp = llm_caller.call_llm_sync("benchmark.judge", default=ModelAssignment(judge.provider, judge.model),
                                    system_prompt=PAIR_SYSTEM, user_prompt=prompt, max_tokens=250,
                                    temperature=0.0, category="benchmark", operation="pairwise_judge")
    v = parse(resp.content)
    if v is None:
        winner = None
    elif v == "tie":
        winner = "tie"
    else:
        winner = "other" if (v == "A") == flip else "baseline"
    return {"winner": winner, "status": "judged" if v else "unparsed", "other_shown_first": flip,
            "reason": (resp.content or "")[:400], "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens}


def question_for(run: dict, scenario_id: str) -> str:
    """The scenario's rubric questions, asked as a comparison."""
    for c in run.get("cells") or []:
        if c.get("scenario") == scenario_id and c.get("rubric_questions"):
            return "\n".join(c["rubric_questions"])
    from .spec import load_scenarios
    (s,) = load_scenarios(int(run.get("tier", 3)), [scenario_id])
    return ("Which companion does better on the following? Read each criterion as a comparison, "
            "not a score.\n\n" + "\n\n".join(f"- {r['question']}" for r in s.rubric))


def run_pairwise(run: dict, judge: Target, budget_usd: float, baseline: str = "full",
                 configs: Optional[List[str]] = None, log=print) -> dict:
    rng = random.Random(SEED)
    names = configs or sorted({c.get("config") for c in run.get("cells") or []} - {baseline})
    spent, out = 0.0, {}
    for cfg in names:
        verdicts = []
        for base, other in pairs(run, cfg, baseline):
            if spent >= budget_usd:
                log(f"budget: stopping at {cfg}")
                break
            j = judge_pair(question_for(run, base["scenario"]), base, other, judge, rng)
            spent += cost(judge.provider, judge.model, j.get("input_tokens") or 0, j.get("output_tokens") or 0,
                          conservative=True)
            verdicts.append({"scenario": base["scenario"], "repeat": base.get("repeat"), **j})
        score = [1.0 if v["winner"] == "other" else -1.0 if v["winner"] == "baseline" else 0.0
                 for v in verdicts if v["winner"] is not None]
        out[cfg] = {"verdicts": verdicts, "other_wins": score.count(1.0), "ties": score.count(0.0),
                    "baseline_wins": score.count(-1.0), "sign_p": sign_test(score),
                    "left_out": sum(1 for v in verdicts if v["winner"] is None)}
        log(f"{cfg}: {out[cfg]['other_wins']} / {out[cfg]['ties']} / {out[cfg]['baseline_wins']}")
    return {"baseline": baseline, "judge": judge.label, "spent_usd": round(spent, 4), "configs": out}


def render(report: Dict) -> str:
    b = report["baseline"]
    lines = [f"Pairwise blind vs `{b}` (judge `{report['judge']}`, order shuffled, tags stripped by regex "
             "with a fidelity check).", "",
             f"| Config | Config better | Tie | `{b}` better | Left out | Sign test p |",
             "| --- | --- | --- | --- | --- | --- |"]
    for cfg, r in report["configs"].items():
        p = "-" if r["sign_p"] is None else f"{r['sign_p']:.3f}"
        lines.append(f"| `{cfg}` | {r['other_wins']} | {r['ties']} | {r['baseline_wins']} | {r['left_out']} | {p} |")
    return "\n".join(lines)
