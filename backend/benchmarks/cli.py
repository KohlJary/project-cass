"""
Command line for benchmark Tiers 2 and 3.

    cd backend
    # See what a run would do and cost. Makes no model calls, boots nothing.
    python -m benchmarks run --tier 2 --model anthropic:claude-haiku-4-5-20251001 \\
        --model ollama:qwen3:14b --dry-run
    # Run it (refuses without a cap, or when the estimate is over it).
    python -m benchmarks run --tier 2 --model ... --budget-usd 5
    # Tier 3: one model, the configurations side by side.
    python -m benchmarks run --tier 3 --model anthropic:claude-haiku-4-5-20251001 --budget-usd 5
    # Regenerate a page from the results files.
    python -m benchmarks page --tier 2

Not scheduled and not wired into CI: when and how often to run is Kohl's
call. Each cell gets a fresh scratch DATA_DIR.

Run from a git worktree or a clone, never the live checkout. Some modules
write under backend/data whatever DATA_DIR says, and the checkout guard
(isolation.check_checkout) only detects a symlinked backend/data or a cass.db
in backend/data or <repo>/data. Any other way of reaching her data is not
detected.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from .judge import DEFAULT_JUDGE
from .pricing import BudgetExceeded, UnknownPrice
from .spec import SpecError, Target, load_scenarios, parse_configs, tier2_config


def _prices(values):
    out = {}
    for v in values or []:
        model, sep, pair = v.partition("=")
        i, sep2, o = pair.partition("/")
        if not sep or not sep2:
            raise SpecError(f"--price {v!r}: expected MODEL=IN/OUT (USD per million tokens)")
        out[model] = (float(i), float(o))
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m benchmarks", description="Benchmark Tiers 2 and 3 (#65)")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="plan and (unless --dry-run) run a tier")
    run.add_argument("--tier", type=int, choices=(2, 3), required=True)
    run.add_argument("--model", action="append", default=[], metavar="PROVIDER:MODEL",
                     help="model under test (repeat for Tier 2; exactly one for Tier 3)")
    run.add_argument("--scenario", action="append", default=[], help="only these scenario ids")
    run.add_argument("--config", action="append", default=[],
                     help="Tier 3 configurations (default: all)")
    run.add_argument("--judge", metavar="PROVIDER:MODEL",
                     help=f"judge model, set as the benchmark.judge override (default {DEFAULT_JUDGE.label})")
    run.add_argument("--no-judge", action="store_true", help="leave rubric items unscored")
    run.add_argument("--budget-usd", type=float, help="hard cap for the whole run, judge included")
    run.add_argument("--repeats", type=int, default=1)
    run.add_argument("--chat-only", action="store_true",
                     help="route only chat to the model under test (default: every non-pinned call site too)")
    run.add_argument("--local-only", action="store_true",
                     help="blank cloud API keys in the cells, so Claude-only call sites fail instead of "
                          "spending (local targets are otherwise estimated at cloud prices)")
    run.add_argument("--allow-same-judge", action="store_true",
                     help="allow the judge to be a model under test (criteria draft G4; the page says so)")
    run.add_argument("--price", action="append", default=[], metavar="MODEL=IN/OUT",
                     help="price for a model the table doesn't know, USD per million tokens")
    run.add_argument("--dry-run", action="store_true", help="print the plan and estimate; make no calls")
    run.add_argument("--scratch", help="scratch root for cell data (default: a new temp dir)")
    run.add_argument("--results-dir", help="where results JSON goes (default docs/benchmarks/results)")
    run.add_argument("--no-page", action="store_true", help="don't regenerate the page")

    run.add_argument("--store", metavar="SEALED_DIR",
                     help="run every cell against its own copy of this sealed store (see `seal`); "
                          "each copy is deleted when its cell ends")

    seal = sub.add_parser("seal", help="seal a read-only copy of her store for test cells")
    seal.add_argument("--source", help="her data directory (default: <repo>/data)")
    seal.add_argument("--root", help="where sealed stores live (default ~/.local/share/cass-benchmarks/stores)")
    seal.add_argument("--note", default="")

    destroy = sub.add_parser("destroy", help="delete a sealed store")
    destroy.add_argument("sealed")

    page = sub.add_parser("page", help="regenerate a tier's page from its results files")
    page.add_argument("--tier", type=int, choices=(2, 3), required=True)
    page.add_argument("--results-dir")

    sub.add_parser("cell", help="(internal) run one cell in this process", add_help=False)
    return p


def plan_from_args(args):
    from .runner import build_plan
    targets = [Target.parse(m) for m in args.model]
    scenarios = load_scenarios(args.tier, args.scenario or None)
    configs = [tier2_config()] if args.tier == 2 else parse_configs(args.config or None)
    judge = None if args.no_judge else (Target.parse(args.judge) if args.judge else DEFAULT_JUDGE)
    return build_plan(args.tier, scenarios, targets, configs, judge, repeats=args.repeats,
                      route_all=not args.chat_only, extra_prices=_prices(args.price),
                      local_only=args.local_only, allow_same_judge=args.allow_same_judge)


def cmd_run(args) -> int:
    from .runner import check_budget, render_plan
    try:
        plan = plan_from_args(args)
    except (SpecError, UnknownPrice, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(render_plan(plan, args.budget_usd))
    if args.dry_run:
        print("Dry run: nothing was started and no model was called.")
        return 0
    try:
        check_budget(plan, args.budget_usd)
    except BudgetExceeded as e:
        print(f"refused: {e}", file=sys.stderr)
        return 3

    store_meta = None
    if args.store:
        from . import store as store_mod
        try:
            m = store_mod.manifest_of(args.store)
        except store_mod.StoreError as e:
            print(f"refused: {e}", file=sys.stderr)
            return 4
        store_meta = {"id": store_mod.store_id(m), "sealed_at": m["sealed_at"], "files": m["files"],
                      "bytes": m["bytes"], "databases": m["databases"]}
        print(store_mod.describe(args.store))
        # Results against her store carry her own prompts (memories, journals, threads):
        # they stay out of the repo, and Cass reads them before anything is reported.
        from .isolation import REPO_DIR
        results = Path(args.results_dir).resolve() if args.results_dir else None
        if results is None or results == REPO_DIR.resolve() or REPO_DIR.resolve() in results.parents:
            print("refused: a --store run needs --results-dir outside the repository "
                  "(its results hold her own prompts)", file=sys.stderr)
            return 4
        if not args.no_page:
            print("refused: a --store run takes --no-page (the page is committed)", file=sys.stderr)
            return 4

    from .isolation import IsolationError, check_checkout, check_data_dir
    scratch = Path(args.scratch) if args.scratch else Path(tempfile.mkdtemp(prefix="cass-bench-"))
    harness_dir = scratch / "harness"
    try:
        check_checkout()
        harness_dir.mkdir(parents=True, exist_ok=False)
        check_data_dir(harness_dir)
    except (IsolationError, FileExistsError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 4
    # Before any backend import: the harness's own DB (judge usage) and llm_config.
    os.environ["DATA_DIR"] = str(harness_dir)
    os.environ.pop("LLM_CONFIG_PATH", None)
    os.environ["CASS_PROFILE"] = "test"

    from database import get_or_create_daemon
    from database.migrations import init_database
    init_database()
    get_or_create_daemon("cass")

    from .judge import LLMJudge, SkipJudge
    if plan.judge is not None and args.judge:
        from llm_config import LLMConfigManager, ModelAssignment
        LLMConfigManager().set("benchmark.judge", ModelAssignment(plan.judge.provider, plan.judge.model))
    judge = SkipJudge() if plan.judge is None else LLMJudge()

    from . import report
    from .runner import SubprocessExecutor, criteria_fingerprint, run_plan
    results_dir = Path(args.results_dir) if args.results_dir else report.RESULTS_DIR
    print(f"Scratch: {scratch}")
    run = run_plan(plan, SubprocessExecutor(scratch, store=args.store), judge, args.budget_usd,
                   criteria=criteria_fingerprint(report.CRITERIA_DRAFT), store=store_meta)
    path = report.write_results(run, results_dir)
    print(f"Results: {path}")
    if not args.no_page:
        print(f"Page: {report.write_page(args.tier, results_dir)}")
    print(f"Status: {run['status']}; spent ${run['spent_usd']:.4f} of ${args.budget_usd:.2f}")
    return 0 if run["status"] == "completed" else 1


def cmd_seal(args) -> int:
    from . import store as store_mod
    from .isolation import REPO_DIR
    source = Path(args.source) if args.source else REPO_DIR / "data"
    try:
        dest = store_mod.seal_into_root(source, Path(args.root) if args.root else None, note=args.note)
    except store_mod.StoreError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 4
    print(f"Sealed: {dest}\n{store_mod.describe(dest)}")
    return 0


def cmd_destroy(args) -> int:
    from . import store as store_mod
    try:
        desc = store_mod.describe(args.sealed)
        store_mod.destroy(args.sealed)
    except store_mod.StoreError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 4
    print(f"Deleted {desc}")
    return 0


def cmd_page(args) -> int:
    from . import report
    results_dir = Path(args.results_dir) if args.results_dir else report.RESULTS_DIR
    print(report.write_page(args.tier, results_dir))
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["cell"]:
        from .cell import main as cell_main
        return cell_main(argv[1:])
    args = build_parser().parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "seal":
        return cmd_seal(args)
    if args.cmd == "destroy":
        return cmd_destroy(args)
    return cmd_page(args)
