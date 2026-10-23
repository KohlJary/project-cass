"""
Results files and the generated pages.

Each run is written whole to docs/benchmarks/results/<run_id>-tier<N>.json,
whatever its status: failed checks, errored cells and budget stops are kept
alongside passes. The pages docs/benchmarks/tier2.md and tier3.md are
regenerated from every results file of their tier, so they carry the whole
history; nothing is dropped when a run goes badly.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

REPO_DIR = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_DIR / "docs" / "benchmarks" / "results"
PAGES = {2: REPO_DIR / "docs" / "benchmarks" / "tier2.md", 3: REPO_DIR / "docs" / "benchmarks" / "tier3.md"}
CRITERIA_DRAFT = REPO_DIR / "docs" / "benchmarks" / "criteria-DRAFT.md"

QUESTION = {
    2: "Does each capability work with real models? Scripted scenarios with deterministic checks "
       "and judge-scored rubric items, run once per model.",
    3: "Does the interior change anything? The same conversations run against configurations set "
       "by levers, scored on the same rubric.",
}


def write_results(run: dict, results_dir: Path = RESULTS_DIR) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{run['run_id']}-tier{run['tier']}.json"
    with open(path, "w") as f:
        json.dump(run, f, indent=1, default=str)
    return path


def load_runs(tier: int, results_dir: Path = RESULTS_DIR) -> List[dict]:
    runs = []
    for path in sorted(results_dir.glob(f"*-tier{tier}.json")):
        try:
            with open(path) as f:
                run = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            runs.append({"run_id": path.stem, "tier": tier, "status": f"unreadable: {e}", "cells": []})
            continue
        run["_file"] = path.name
        runs.append(run)
    return sorted(runs, key=lambda r: r.get("started_at") or "", reverse=True)


# ---------------------------------------------------------------------------
# Tallies
# ---------------------------------------------------------------------------

def tally_checks(cells: List[dict]) -> Dict[str, int]:
    t = defaultdict(int)
    for c in cells:
        for chk in c.get("checks") or []:
            t[chk["status"]] += 1
    return t


def tally_rubric(cells: List[dict]) -> Dict[str, int]:
    t = defaultdict(int)
    for c in cells:
        for r in c.get("rubric") or []:
            if r.get("status") == "scored":
                t["pass" if r.get("passed") else "fail"] += 1
            else:
                t[r.get("status") or "unknown"] += 1
    return t


def _frac(t: Dict[str, int]) -> str:
    decided = t.get("pass", 0) + t.get("fail", 0)
    extra = [f"{t[k]} {k}" for k in sorted(t) if k not in ("pass", "fail") and t[k]]
    base = f"{t.get('pass', 0)}/{decided}" if decided else "-"
    return base + (f" ({', '.join(extra)})" if extra else "")


def _cell_summary(cells: List[dict]) -> str:
    if not cells:
        return "not run"
    bad = [c["status"] for c in cells if c.get("status") != "completed"]
    s = f"checks {_frac(tally_checks(cells))}; rubric {_frac(tally_rubric(cells))}"
    if bad:
        s += f"; **{len(bad)} cell(s) {', '.join(sorted(set(bad)))}**"
    return s


def _esc(text) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def _history(runs: List[dict]) -> List[str]:
    lines = ["| Run | Started (UTC) | Commit | Status | Models | Configs | Cells | Checks | Rubric | Judge | Spent / cap | Criteria |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        cells = r.get("cells") or []
        crit = r.get("criteria") or {}
        crit_s = "adopted" if crit.get("adopted") else ("DRAFT" if crit.get("sha256") else "none")
        if crit.get("sha256"):
            crit_s += f" `{crit['sha256'][:8]}`"
        spent = r.get("spent_usd")
        lines.append("| " + " | ".join(_esc(x) for x in [
            f"`{r.get('run_id')}`", (r.get("started_at") or "")[:16].replace("T", " "), r.get("commit") or "?",
            r.get("status"), ", ".join(r.get("targets") or []),
            ", ".join(c["name"] for c in r.get("configs") or []), len(cells),
            _frac(tally_checks(cells)), _frac(tally_rubric(cells)), r.get("judge") or "none",
            f"${spent:.2f} / ${r.get('budget_usd', 0):.2f}" if spent is not None else "?", crit_s]) + " |")
    return lines


def _grid(run: dict, rows_key: str, cols_key: str, row_label: str) -> List[str]:
    by = defaultdict(list)
    rows, cols = [], []
    for c in run.get("cells") or []:
        r, k = c.get(rows_key), c.get(cols_key)
        by[(r, k)].append(c)
        if r not in rows:
            rows.append(r)
        if k not in cols:
            cols.append(k)
    lines = [f"| {row_label} | " + " | ".join(f"`{_esc(k)}`" for k in cols) + " |",
             "| --- |" + " --- |" * len(cols)]
    for r in rows:
        lines.append(f"| `{_esc(r)}` | " + " | ".join(_esc(_cell_summary(by[(r, k)])) for k in cols) + " |")
    return lines


def _measures(run: dict) -> List[str]:
    """Tier 3: rubric measures x configurations, mean score (0-2) and passes."""
    scores = defaultdict(list)
    measures, configs = [], []
    for c in run.get("cells") or []:
        cfg = c.get("config")
        if cfg not in configs:
            configs.append(cfg)
        for r in c.get("rubric") or []:
            m = r.get("measure") or r.get("id")
            if m not in measures:
                measures.append(m)
            scores[(m, cfg)].append(r)
    meaningful = {c["name"]: c.get("meaningful", True) for c in run.get("configs") or []}
    lines = ["| Measure | " + " | ".join(f"`{_esc(c)}`" + ("" if meaningful.get(c, True) else " (placeholder)")
                                       for c in configs) + " |",
             "| --- |" + " --- |" * len(configs)]
    for m in measures:
        row = []
        for cfg in configs:
            items = scores[(m, cfg)]
            scored = [i for i in items if i.get("status") == "scored"]
            if not scored:
                row.append(f"not scored ({len(items)} item(s))" if items else "-")
                continue
            # Every item on a 0-2 scale (a pass/fail item counts 0 or 2), as the criteria define.
            mean = sum(2 * i["score"] / (i.get("max") or 1) for i in scored) / len(scored)
            passed = sum(1 for i in scored if i.get("passed"))
            unscored = len(items) - len(scored)
            row.append(f"mean {mean:.2f}/2, pass {passed}/{len(scored)}"
                       + (f", {unscored} unscored" if unscored else ""))
        lines.append(f"| {_esc(m)} | " + " | ".join(_esc(x) for x in row) + " |")
    return lines


def _failures(run: dict) -> List[str]:
    lines = []
    for c in run.get("cells") or []:
        head = f"`{c.get('cell_id')}`"
        if c.get("status") != "completed":
            lines.append(f"- {head}: cell **{c.get('status')}**: {_esc(c.get('error'))}")
        for t in c.get("turns") or []:
            if t.get("error"):
                lines.append(f"- {head}: turn `{t.get('id') or t.get('session')}` failed: {_esc(t['error'])}")
        for a in c.get("actions") or []:
            if a.get("error"):
                lines.append(f"- {head}: action `{a.get('action')}` failed: {_esc(a['error'])}")
        for chk in c.get("checks") or []:
            if chk["status"] != "pass":
                lines.append(f"- {head}: check `{chk['id']}` **{chk['status']}**: {_esc(chk.get('detail'))}")
        for r in c.get("rubric") or []:
            if r.get("status") == "scored" and not r.get("passed"):
                lines.append(f"- {head}: rubric `{r['id']}` scored {r['score']}/{r['max']} "
                             f"(pass at {r.get('pass_at')}): {_esc(r.get('reason'))}")
            elif r.get("status") != "scored":
                lines.append(f"- {head}: rubric `{r['id']}` **{r.get('status')}**: {_esc(r.get('reason'))}")
    return lines or ["None."]


def render_page(tier: int, runs: List[dict]) -> str:
    out = [f"# Tier {tier} benchmark results", "",
           "<!-- Generated by `python -m benchmarks page`. Do not edit by hand. -->", "",
           QUESTION[tier], "",
           "Part of the benchmark suite (#65, `docs/ROADMAP-STABILIZATION.md`). Harness: `backend/benchmarks/`. "
           "Every run is listed, including failed and budget-stopped ones. "
           "Rubric items are scored by a judge model, which is not told the model or configuration; "
           "a judge score is one model's reading of a transcript, not ground truth.", "",
           ("Criteria: `docs/benchmarks/criteria-DRAFT.md` is a **draft, not adopted**; Kohl decides the "
            "criteria. A run made against draft criteria is marked DRAFT below, and its pass/fail lines are "
            "provisional." if CRITERIA_DRAFT.exists() else
            "Criteria: see `docs/benchmarks/`. Each run records the SHA-256 of the criteria file it ran under."),
           ""]
    if tier == 3:
        out += ["The `self_context_off` configuration is a **placeholder** until the self-context design "
                "(#63) exists; differences against it don't measure the designed section.", ""]
    if not runs:
        out += ["## History", "", "No runs yet.", ""]
        return "\n".join(out)
    out += ["## History", "", *_history(runs), ""]
    latest = runs[0]
    out += [f"## Latest run: `{latest.get('run_id')}`", "",
            f"- Status: {latest.get('status')}; commit `{latest.get('commit')}`; judge {latest.get('judge') or 'none'}",
            f"- Spent ${latest.get('spent_usd') or 0:.4f} of a ${latest.get('budget_usd') or 0:.2f} cap "
            f"(estimate ${(latest.get('estimate') or {}).get('usd', 0):.4f})",
            f"- Routing: {'chat and every non-pinned call site' if latest.get('route_all', True) else 'chat only'} "
            "on the model under test", ""]
    if tier == 2:
        out += ["### Per model", "", "Each cell: deterministic checks passed/decided; rubric items passed/scored.", "",
                *_grid(latest, "scenario", "target", "Scenario"), ""]
    else:
        out += ["### Measures by configuration", "", *_measures(latest), "",
                "### Scenarios by configuration", "", *_grid(latest, "scenario", "config", "Scenario"), ""]
    out += ["### Failures, errors and unscored items", "", *_failures(latest), ""]
    if latest.get("skipped"):
        out += ["### Not run", "", *[f"- {_esc(s)}" for s in latest["skipped"]], ""]
    return "\n".join(out)


def write_page(tier: int, results_dir: Path = RESULTS_DIR, page: Optional[Path] = None) -> Path:
    page = page or PAGES[tier]
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(render_page(tier, load_runs(tier, results_dir)))
    return page
