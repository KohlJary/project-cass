"""
Aggregation and statistics for Tier 3 runs, as code (benchmark plan phase 4,
item 0c7aa2a3; Momus F4/F5 on the draft criteria).

The rule, fixed before results are read:

- Scores are on report.rubric_outcome's 0-2 scale. An errored cell or failed
  turn scores 0 (G2); unscored items (budget stop, judge error) are dropped.
- Each configuration is compared with a baseline (default `full`), paired on
  (scenario, repeat, rubric item): the difference is config minus baseline,
  so scenario difficulty cancels.
- Per configuration: number of pairs, mean difference, a percentile
  bootstrap 95% interval (seeded, so the same results give the same
  numbers), and an exact two-sided sign test on the nonzero differences.
- The bite check: mean prompt characters per turn, config minus baseline.
  An ablation whose prompt didn't shrink didn't remove anything here, and its
  score difference says nothing about that subsystem.

What counts as an effect (thresholds, the N a claim needs) is not decided
here: that is the adopted criteria's job (item 78b9060e), and a claim needs
a pre-registered run. min_pairs_for() only reports what the sign test could
detect at a given N.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .report import rubric_outcome

BOOTSTRAP_RESAMPLES = 10_000
SEED = 20261028


def scores(run: dict) -> Dict[Tuple[str, str, int, str], float]:
    """(config, scenario, repeat, item id) -> score on 0-2, unscored items left out."""
    out = {}
    for cell in run.get("cells") or []:
        for item in cell.get("rubric") or []:
            _, sc = rubric_outcome(item, cell)
            if sc is not None:
                out[(cell.get("config"), cell.get("scenario"), int(cell.get("repeat") or 0), item.get("id"))] = sc
    return out


def prompt_chars(run: dict) -> Dict[str, Optional[float]]:
    """Mean prompt characters per turn, per configuration."""
    acc = defaultdict(list)
    for cell in run.get("cells") or []:
        for t in cell.get("turns") or []:
            if t.get("prompt_chars"):
                acc[cell.get("config")].append(t["prompt_chars"])
    return {k: sum(v) / len(v) for k, v in acc.items()}


def paired_diffs(run: dict, config: str, baseline: str = "full") -> List[float]:
    s = scores(run)
    out = []
    for (cfg, scen, rep, item), sc in sorted(s.items(), key=lambda kv: tuple(map(str, kv[0]))):
        if cfg != config:
            continue
        base = s.get((baseline, scen, rep, item))
        if base is not None:
            out.append(sc - base)
    return out


def bootstrap_ci(values: List[float], resamples: int = BOOTSTRAP_RESAMPLES, seed: int = SEED,
                 level: float = 0.95) -> Optional[Tuple[float, float]]:
    """Percentile bootstrap interval for the mean."""
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(resamples))
    lo = means[int((1 - level) / 2 * resamples)]
    hi = means[min(resamples - 1, int((1 + level) / 2 * resamples))]
    return lo, hi


def sign_test(values: List[float]) -> Optional[float]:
    """Exact two-sided sign test p-value on the nonzero values (None if all are zero)."""
    pos = sum(1 for v in values if v > 0)
    neg = sum(1 for v in values if v < 0)
    n = pos + neg
    if n == 0:
        return None
    k = min(pos, neg)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def min_pairs_for(alpha: float = 0.05) -> int:
    """The fewest nonzero pairs, all in one direction, at which the sign test reaches alpha."""
    n = 1
    while sign_test([1.0] * n) > alpha:
        n += 1
    return n


def compare(run: dict, baseline: str = "full") -> List[dict]:
    configs = []
    for c in run.get("cells") or []:
        if c.get("config") not in configs:
            configs.append(c.get("config"))
    chars = prompt_chars(run)
    rows = []
    for cfg in configs:
        if cfg == baseline:
            continue
        d = paired_diffs(run, cfg, baseline)
        rows.append({
            "config": cfg,
            "pairs": len(d),
            "mean_diff": sum(d) / len(d) if d else None,
            "ci95": bootstrap_ci(d),
            "sign_p": sign_test(d),
            "better": sum(1 for v in d if v > 0),
            "worse": sum(1 for v in d if v < 0),
            "prompt_chars_diff": (chars[cfg] - chars[baseline])
            if cfg in chars and baseline in chars else None,
        })
    return rows


def _f(x, fmt="{:+.2f}"):
    return "-" if x is None else fmt.format(x)


def render(run: dict, baseline: str = "full") -> str:
    """A markdown table of compare(); exploratory unless the run was pre-registered."""
    rows = compare(run, baseline)
    lines = [f"Paired against `{baseline}` on (scenario, repeat, rubric item); scores 0-2. "
             f"Bootstrap {BOOTSTRAP_RESAMPLES} resamples, seed {SEED}. The sign test needs at least "
             f"{min_pairs_for()} one-directional nonzero pairs to reach p<0.05.", "",
             "| Config | Pairs | Mean diff | 95% CI | Better / worse | Sign test p | Prompt chars vs baseline |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        ci = "-" if r["ci95"] is None else f"[{r['ci95'][0]:+.2f}, {r['ci95'][1]:+.2f}]"
        lines.append(f"| `{r['config']}` | {r['pairs']} | {_f(r['mean_diff'])} | {ci} | "
                     f"{r['better']} / {r['worse']} | {_f(r['sign_p'], '{:.3f}')} | "
                     f"{_f(r['prompt_chars_diff'], '{:+.0f}')} |")
    return "\n".join(lines)
