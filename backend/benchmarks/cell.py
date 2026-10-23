"""
One cell: one scenario, run once against one target model and one configuration.

`run_cell` is the in-process core (tests call it with a booted app). `main`
is the subprocess entry the runner uses for real runs:

    DATA_DIR=<fresh scratch dir> CASS_PROFILE=test \\
        python -m benchmarks cell --spec cell.json --out result.json

It checks isolation before importing any backend module, boots the driver,
runs the cell and writes the result JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any, Dict

from .checks import evaluate_all
from .pricing import Meter, cost, ledger_cost, step_allowance


def _turn_record(step: dict, turn: dict) -> dict:
    out = {"id": step.get("id"), "session": step["session"], "message": step["chat"]}
    out.update(turn)
    return out


def run_cell(scenario, driver, spec: Dict[str, Any], extra_prices=None) -> dict:
    """Run setup, steps, probes and deterministic checks. Never raises."""
    target = spec.get("target_obj")
    meter = Meter(spec.get("budget_usd", float("inf")))
    result: Dict[str, Any] = {
        "cell_id": spec["cell_id"], "scenario": scenario.id, "tier": scenario.tier,
        "target": spec.get("target"), "config": spec.get("config"), "repeat": spec.get("repeat", 1),
        "driver": driver.name, "status": "running", "error": None,
        "seeded": 0, "turns": [], "actions": [], "probes": {}, "checks": [],
        "routed_call_sites": list(getattr(driver, "routed", []) or []),
    }
    turns_by_id: Dict[str, dict] = {}

    def spent() -> float:
        return ledger_cost(driver.spent(), extra_prices)

    try:
        for seed in scenario.setup:
            driver.seed(seed)
            result["seeded"] += 1
        for i, step in enumerate(scenario.steps):
            if target is not None:
                i_tok, o_tok = step_allowance(driver.name, step)
                step_cost = cost(target.provider, target.model, i_tok, o_tok, extra_prices, conservative=True)
                meter.spent_usd = spent()
                if not meter.can_afford(step_cost):
                    result["status"] = "budget_stop"
                    result["error"] = (f"stopped before step {i}: allowance ${step_cost:.4f}, "
                                       f"spent ${meter.spent_usd:.4f} of ${meter.cap_usd:.4f}")
                    break
            if "chat" in step:
                try:
                    turn = driver.send(step["session"], step["chat"])
                except Exception as e:
                    turn = {"reply": "", "error": f"{type(e).__name__}: {e}", "tool_uses": None,
                            "system_prompt": None}
                record = _turn_record(step, turn)
                result["turns"].append(record)
                if step.get("id"):
                    turns_by_id[step["id"]] = record
            else:
                try:
                    outcome = driver.action(step)
                    result["actions"].append({"action": step["action"], **outcome})
                except Exception as e:
                    result["actions"].append({"action": step["action"], "error": f"{type(e).__name__}: {e}"})
        for name, probe in scenario.probes.items():
            try:
                result["probes"][name] = driver.probe(probe)
            except Exception as e:
                result["probes"][name] = {"error": f"{type(e).__name__}: {e}"}
        result["checks"] = evaluate_all(scenario.checks, turns_by_id, result["probes"])
        if result["status"] == "running":
            result["status"] = "completed"
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()[-4000:]
    try:
        result["usage"] = [list(r) for r in driver.spent()]
        result["spent_usd"] = round(spent(), 6)
    except Exception as e:
        result["usage"], result["spent_usd"] = [], None
        result["error"] = (result["error"] or "") + f" (ledger unreadable: {e})"
    # System prompts are only needed for the checks above; keep the results small.
    for t in result["turns"]:
        prompt = t.pop("system_prompt", None)
        t["prompt_chars"] = len(prompt) if prompt is not None else None
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="benchmarks cell")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    from .isolation import check_checkout, check_env_data_dir
    check_env_data_dir()   # before any backend import reads DATA_DIR
    check_checkout()

    with open(args.spec) as f:
        spec = json.load(f)
    from .spec import TIER3_CONFIGS, Scenario, Target, tier2_config
    scenario = Scenario.from_dict(spec["scenario"])
    target = Target.parse(spec["target"]) if spec.get("target") else None
    spec["target_obj"] = target
    config = TIER3_CONFIGS.get(spec["config"]) or tier2_config()
    extra = {k: tuple(v) for k, v in (spec.get("extra_prices") or {}).items()}

    from .drivers import AppDriver, PlainDriver
    try:
        if config.driver == "plain":
            from database import get_or_create_daemon
            from database.migrations import init_database
            init_database()
            get_or_create_daemon("cass")
            with PlainDriver(target) as driver:
                result = run_cell(scenario, driver, spec, extra)
        else:
            with AppDriver.boot(target, config, route_all=spec.get("route_all", True)) as driver:
                result = run_cell(scenario, driver, spec, extra)
    except Exception as e:
        result = {"cell_id": spec["cell_id"], "scenario": scenario.id, "tier": scenario.tier,
                  "target": spec.get("target"), "config": spec.get("config"),
                  "repeat": spec.get("repeat", 1), "status": "error",
                  "error": f"driver failed to start: {type(e).__name__}: {e}",
                  "traceback": traceback.format_exc()[-4000:], "turns": [], "checks": [], "probes": {},
                  "spent_usd": None}
    with open(args.out, "w") as f:
        json.dump(result, f, indent=1, default=str)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
