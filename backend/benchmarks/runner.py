"""
Plan, budget and run a benchmark: cells out, judged results in.

    plan = build_plan(tier=2, scenarios=..., targets=[...], configs=[...], judge=Target|None)
    print(render_plan(plan))                       # --dry-run stops here: no calls
    check_budget(plan, cap_usd)                    # refuses over the cap
    run = run_plan(plan, executor, judge, cap_usd) # results dict (see report.py)

The executor runs one cell and returns its result dict. For real runs it is
`SubprocessExecutor`: each cell gets its own process and its own fresh
DATA_DIR under the run's scratch root. Tests pass an in-process executor.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .judge import Judge, scale_bounds, score_cell, pass_at
from .pricing import ALLOWANCE, BudgetExceeded, Estimate, Meter, cost, estimate_cell, ledger_cost
from .spec import Config, Scenario, Target, tier2_config

BACKEND_DIR = Path(__file__).resolve().parents[1]


@dataclass
class Cell:
    cell_id: str
    scenario: Scenario
    target: Target
    config: Config
    repeat: int
    estimate: Estimate

    def spec(self, budget_usd: float, route_all: bool, extra_prices=None, local_only: bool = False) -> dict:
        return {"cell_id": self.cell_id, "scenario": self.scenario.to_dict(), "target": self.target.label,
                "config": self.config.name, "repeat": self.repeat, "budget_usd": budget_usd,
                "route_all": route_all, "extra_prices": extra_prices or {}, "local_only": local_only}


@dataclass
class Plan:
    tier: int
    cells: List[Cell]
    judge: Optional[Target]
    estimate: Estimate
    route_all: bool = True
    extra_prices: Dict = field(default_factory=dict)
    skipped: List[str] = field(default_factory=list)
    local_only: bool = False
    judge_is_target: bool = False


def build_plan(tier: int, scenarios: List[Scenario], targets: List[Target], configs: List[Config],
               judge: Optional[Target], repeats: int = 1, route_all: bool = True,
               extra_prices=None, local_only: bool = False, allow_same_judge: bool = False) -> Plan:
    if not scenarios:
        raise ValueError("no scenarios selected")
    if not targets:
        raise ValueError("no target model given")
    if tier == 3 and len(targets) != 1:
        raise ValueError("Tier 3 compares configurations on one model; give exactly one --model")
    judge_is_target = judge is not None and judge in targets
    if judge_is_target and not allow_same_judge:
        raise ValueError(f"the judge {judge.label} is also a model under test (criteria draft G4); "
                         "pick another --judge, or pass --allow-same-judge and the page will say so")
    cells, skipped = [], []
    total = Estimate()
    for scenario in scenarios:
        for target in targets:
            for config in configs:
                if config.driver not in scenario.drivers:
                    skipped.append(f"{scenario.id} x {config.name}: scenario needs driver "
                                   f"{'/'.join(scenario.drivers)}")
                    continue
                for r in range(1, repeats + 1):
                    est = estimate_cell(scenario, target, config, judge, extra_prices, local_only)
                    cid = f"{scenario.id}--{target.label.replace(':', '_').replace('/', '_')}--{config.name}--r{r}"
                    cells.append(Cell(cid, scenario, target, config, r, est))
                    total.input_tokens += est.input_tokens
                    total.output_tokens += est.output_tokens
                    total.usd += est.usd
                    total.calls += est.calls
                    for k, v in est.breakdown.items():
                        total.breakdown[k] = total.breakdown.get(k, 0.0) + v
    return Plan(tier, cells, judge, total, route_all, dict(extra_prices or {}), skipped, local_only,
                judge_is_target)


def check_budget(plan: Plan, cap_usd: Optional[float]) -> None:
    if cap_usd is None:
        raise BudgetExceeded("no --budget-usd given; a run never starts without a cap")
    if plan.estimate.usd > cap_usd:
        raise BudgetExceeded(f"estimate ${plan.estimate.usd:.2f} is over the cap ${cap_usd:.2f}; "
                             "refusing to start (narrow the plan or raise the cap)")


def render_plan(plan: Plan, cap_usd: Optional[float] = None) -> str:
    lines = [f"Tier {plan.tier} plan: {len(plan.cells)} cell(s)"]
    lines.append(f"Judge: {plan.judge.label if plan.judge else 'none (rubric items skipped)'}")
    lines.append(f"Routing: {'chat + every non-pinned call site' if plan.route_all else 'chat only'} "
                 "on the target model")
    for c in plan.cells:
        lines.append(f"  {c.cell_id}: {len(c.scenario.chat_turns)} turn(s), {len(c.scenario.actions)} action(s), "
                     f"{len(c.scenario.checks)} check(s), {len(c.scenario.rubric)} rubric item(s), "
                     f"est ${c.estimate.usd:.4f}")
        if not c.config.meaningful:
            lines.append(f"    NOTE {c.config.name}: {c.config.caveat}")
    for s in plan.skipped:
        lines.append(f"  skipped: {s}")
    e = plan.estimate
    lines.append(f"Estimate: {e.input_tokens:,} input + {e.output_tokens:,} output tokens over "
                 f"~{e.calls} call(s), ${e.usd:.2f} "
                 f"({', '.join(f'{k} ${v:.2f}' for k, v in e.breakdown.items())})")
    lines.append("Allowances per step (generous guesses until calibrated): "
                 + ", ".join(f"{k} {i:,}/{o:,}" for k, (i, o) in ALLOWANCE.items()))
    if plan.judge_is_target:
        lines.append(f"WARNING: the judge {plan.judge.label} is also a model under test (criteria draft G4); "
                     "the results and page say so.")
    if any(c.target.provider == "ollama" and c.config.driver == "app" for c in plan.cells):
        from .pricing import fallback_call_sites
        sites = ", ".join(fallback_call_sites())
        if plan.local_only:
            lines.append(f"Local only: cells get blank cloud API keys, so these Claude-only call sites "
                         f"fail instead of spending: {sites}.")
        else:
            lines.append(f"Local targets can still spend on Claude: these call sites need tools or images "
                         f"and fall back to their Claude default: {sites}. With --chat-only, every other "
                         f"call site also keeps its default. So each local app step is estimated at the "
                         f"highest known cloud price. Pass --local-only to strip cloud keys from the cells "
                         f"instead.")
    if cap_usd is not None:
        verdict = "within" if e.usd <= cap_usd else "OVER"
        lines.append(f"Cap: ${cap_usd:.2f} ({verdict} the cap)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def _ledger_from_db(db_path: Path) -> list:
    """Read a cell database's token ledger without importing the backend."""
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            return conn.execute("SELECT provider, model, SUM(input_tokens), SUM(output_tokens) "
                                "FROM token_usage_records GROUP BY provider, model").fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []


class SubprocessExecutor:
    """Runs each cell as `python -m benchmarks cell` with a fresh DATA_DIR."""

    def __init__(self, scratch_root: Path, timeout: float = 1800.0, python: str = sys.executable,
                 store: Optional[Path] = None):
        self.root = Path(scratch_root)
        self.timeout = timeout
        self.python = python
        # A sealed store (store.seal): each cell gets its own copy, deleted when the cell ends.
        self.store = Path(store) if store else None

    def env_for(self, data_dir: Path, local_only: bool = False) -> dict:
        env = dict(os.environ)
        if local_only:
            # Blank, not removed: config.py's load_dotenv() would refill a removed key from backend/.env.
            env["ANTHROPIC_API_KEY"] = ""
            env["OPENAI_API_KEY"] = ""
        env["DATA_DIR"] = str(data_dir)
        env["CASS_PROFILE"] = "test"   # every lever off; the config's levers are set in-process
        env.pop("LLM_CONFIG_PATH", None)  # the cell's llm_config lives in its own DATA_DIR
        env.pop("CASS_STRICT", None)
        return env

    def __call__(self, cell: Cell, spec: dict, extra_prices=None) -> dict:
        from .isolation import check_data_dir
        cell_dir = self.root / "cells" / cell.cell_id
        data_dir = cell_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=False)
        check_data_dir(data_dir)
        if self.store is not None:
            from . import store as store_mod
            store_mod.seed(self.store, data_dir)
        try:
            return self._run(cell, spec, cell_dir, data_dir, extra_prices)
        finally:
            if self.store is not None:
                from . import store as store_mod
                store_mod.discard(data_dir)

    def _run(self, cell: Cell, spec: dict, cell_dir: Path, data_dir: Path, extra_prices=None) -> dict:
        spec_path, out_path = cell_dir / "spec.json", cell_dir / "result.json"
        spec_path.write_text(json.dumps(spec, indent=1))
        cmd = [self.python, "-m", "benchmarks", "cell", "--spec", str(spec_path), "--out", str(out_path)]
        try:
            proc = subprocess.run(cmd, cwd=str(BACKEND_DIR), env=self.env_for(data_dir, spec.get("local_only", False)),
                                  capture_output=True, text=True, timeout=self.timeout)
            (cell_dir / "stdout.log").write_text(proc.stdout or "")
            (cell_dir / "stderr.log").write_text(proc.stderr or "")
            failed = proc.returncode != 0 or not out_path.exists()
            error = f"cell process exited {proc.returncode}: {(proc.stderr or '')[-1500:]}" if failed else None
        except subprocess.TimeoutExpired:
            failed, error = True, f"cell timed out after {self.timeout:.0f}s"
        if failed:
            rows = _ledger_from_db(data_dir / "cass.db")
            return {"cell_id": cell.cell_id, "scenario": cell.scenario.id, "tier": cell.scenario.tier,
                    "target": cell.target.label, "config": cell.config.name, "repeat": cell.repeat,
                    "status": "error", "error": error, "turns": [], "checks": [], "probes": {},
                    "usage": [list(r) for r in rows], "spent_usd": ledger_cost(rows, extra_prices)}
        result = json.loads(out_path.read_text())
        if result.get("spent_usd") is None:
            rows = _ledger_from_db(data_dir / "cass.db")
            result["spent_usd"] = ledger_cost(rows, extra_prices)
        return result


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

class MeteredJudge:
    """Charges each judge call to the run's meter; refuses an item it can't afford."""

    def __init__(self, inner: Judge, meter: Meter, judge_target: Optional[Target], extra_prices=None):
        self.inner, self.meter, self.target, self.extra = inner, meter, judge_target, extra_prices

    def score(self, item: dict, context: str) -> dict:
        if self.target is not None:
            i, o = ALLOWANCE["judge_item"]
            allowance = cost(self.target.provider, self.target.model, i, o, self.extra, conservative=True)
            if not self.meter.can_afford(allowance):
                lo, hi = scale_bounds(item)
                return {"id": item["id"], "measure": item.get("measure"), "max": hi, "pass_at": pass_at(item),
                        "status": "budget_stop", "score": None, "passed": None,
                        "reason": "judge call would exceed the budget cap", "judge_model": None,
                        "input_tokens": 0, "output_tokens": 0}
        result = self.inner.score(item, context)
        model = result.get("judge_model")
        if model:
            provider, _, model_id = model.partition(":")
            self.meter.charge(cost(provider, model_id, result.get("input_tokens") or 0,
                                   result.get("output_tokens") or 0, self.extra, conservative=True))
        return result


def _commit() -> Optional[str]:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(BACKEND_DIR),
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


def criteria_fingerprint(path: Path) -> dict:
    import hashlib
    if not path.exists():
        return {"path": str(path), "sha256": None, "adopted": False}
    text = path.read_text()
    adopted = "DRAFT" not in path.name.upper() and "not adopted" not in text.lower()
    return {"path": str(path.relative_to(BACKEND_DIR.parent)) if path.is_relative_to(BACKEND_DIR.parent)
            else str(path), "sha256": hashlib.sha256(text.encode()).hexdigest(), "adopted": adopted}


def run_plan(plan: Plan, executor: Callable, judge: Judge, cap_usd: float,
             criteria: Optional[dict] = None, log: Callable[[str], None] = print,
             store: Optional[dict] = None) -> dict:
    """Run every cell, then judge it. Stops starting cells once the cap is reached."""
    check_budget(plan, cap_usd)
    meter = Meter(cap_usd)
    metered_judge = MeteredJudge(judge, meter, plan.judge, plan.extra_prices)
    run = {
        "schema": 1,
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6],
        "tier": plan.tier,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _commit(),
        "budget_usd": cap_usd,
        "estimate": plan.estimate.to_dict(),
        "judge": plan.judge.label if plan.judge else None,
        "route_all": plan.route_all,
        "local_only": plan.local_only,
        "judge_is_target": plan.judge_is_target,
        "targets": sorted({c.target.label for c in plan.cells}),
        "configs": [{"name": c.name, "driver": c.driver, "levers": c.levers, "meaningful": c.meaningful,
                     "caveat": c.caveat} for c in {c.config.name: c.config for c in plan.cells}.values()],
        "criteria": criteria,
        # The sealed store the cells ran against (store.seal), or None for fresh cells.
        "store": store,
        "skipped": plan.skipped,
        "cells": [],
        "status": "running",
    }
    for cell in plan.cells:
        judge_reserve = 0.0
        if plan.judge and cell.scenario.rubric:
            i, o = ALLOWANCE["judge_item"]
            judge_reserve = cost(plan.judge.provider, plan.judge.model, i, o, plan.extra_prices,
                                 conservative=True) * len(cell.scenario.rubric)
        cell_budget = meter.remaining - judge_reserve
        if cell_budget < cell.estimate.usd - cell.estimate.breakdown.get("judge", 0.0):
            log(f"budget: not starting {cell.cell_id} (remaining ${meter.remaining:.4f})")
            run["cells"].append({"cell_id": cell.cell_id, "scenario": cell.scenario.id, "tier": plan.tier,
                                 "target": cell.target.label, "config": cell.config.name,
                                 "repeat": cell.repeat, "status": "budget_stop",
                                 "error": "not started: remaining budget below the cell's estimate",
                                 "turns": [], "rubric": score_cell(metered_judge, cell.scenario,
                                                                   {"status": "budget_stop"}),
                                 "checks": [{"id": c["id"], "type": c["type"], "status": "not_run",
                                             "detail": "cell not started (budget)"}
                                            for c in cell.scenario.checks],
                                 "spent_usd": 0.0})
            continue
        log(f"running {cell.cell_id}")
        started = time.monotonic()
        spec = cell.spec(round(cell_budget, 6), plan.route_all, plan.extra_prices, plan.local_only)
        result = executor(cell, spec, plan.extra_prices)
        meter.charge(result.get("spent_usd") or 0.0)
        result["seconds"] = round(time.monotonic() - started, 1)
        result["meaningful"] = cell.config.meaningful
        if result.get("status") != "completed" and not result.get("checks"):
            # Checks that never ran stay visible: errored cells fail them (G2), budget stops don't.
            status = "error" if result.get("status") == "error" else "not_run"
            result["checks"] = [{"id": c["id"], "type": c["type"], "status": status,
                                 "detail": f"cell {result.get('status')}"} for c in cell.scenario.checks]
        result["rubric"] = score_cell(metered_judge, cell.scenario, result)
        run["cells"].append(result)
    run["spent_usd"] = round(meter.spent_usd, 6)
    run["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    statuses = {c["status"] for c in run["cells"]}
    if any(r.get("status") == "budget_stop" for c in run["cells"] for r in c.get("rubric") or []):
        statuses.add("budget_stop")
    if statuses <= {"completed"}:
        run["status"] = "completed"
    elif "budget_stop" in statuses:
        run["status"] = "budget_stop"
    else:
        run["status"] = "completed_with_errors"
    return run
