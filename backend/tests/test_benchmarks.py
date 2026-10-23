"""
Benchmark harness for Tiers 2 and 3 (backend/benchmarks, #65), without the app.

Fast suite: no runtime deps, no model, no network. A stub driver stands in for
the app (tests/smoke/test_benchmark_harness.py runs the real AppDriver on the
fake LLM). Covers: scenario files and validation, the cost estimate and cap
refusal, a dry run making zero calls, deterministic checks, the judge's
parsing and metering, a mid-run budget stop, isolation guards, the subprocess
executor's environment, and page generation with history and failures.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks import checks, cli, isolation, report, runner
from benchmarks.judge import (DEFAULT_JUDGE, JUDGE_SYSTEM, SkipJudge, build_context, parse_score,
                              score_cell)
from benchmarks.pricing import BudgetExceeded, UnknownPrice, cost
from benchmarks.spec import (TIER3_CONFIGS, Scenario, SpecError, Target, load_scenarios,
                             parse_configs, tier2_config)

BACKEND = Path(__file__).resolve().parents[1]
HAIKU = Target("anthropic", "claude-haiku-4-5-20251001")
LOCAL = Target("ollama", "qwen3:14b")


# ---------------------------------------------------------------------------
# Scenario files
# ---------------------------------------------------------------------------

def test_shipped_scenarios_load_and_cover_the_roadmap():
    tier2 = {s.id for s in load_scenarios(2)}
    assert tier2 == {"recall_three_sessions", "journal_next_day", "intention_followup", "tool_reminder"}
    tier3 = load_scenarios(3)
    measures = {r["measure"] for s in tier3 for r in s.rubric}
    assert measures == {"consistency", "value_stability", "self_model_agreement", "contradiction_handling"}
    for s in tier3:
        assert set(s.drivers) == {"app", "plain"}
        assert s.setup, f"{s.id} seeds the self-model the judge compares against"


def _scenario(**overrides):
    data = {"id": "x", "tier": 2, "title": "X", "steps": [{"session": "s1", "id": "t1", "chat": "hi"}],
            "checks": [], "rubric": []}
    data.update(overrides)
    return data


def test_validation_names_every_problem():
    bad = _scenario(steps=[{"session": "s1", "id": "t1", "chat": "hi"}, {"action": "launch_rockets"}],
                    checks=[{"id": "c1", "type": "reply_contains", "turn": "nope", "any": ["a"]},
                            {"id": "c2", "type": "probe", "probe": "undefined"}],
                    rubric=[{"id": "r1", "question": "q", "scale": "1-10"}],
                    setup=[{"seed": "her_real_memories"}])
    with pytest.raises(SpecError) as e:
        Scenario.from_dict(bad)
    msg = str(e.value)
    for part in ("unknown action 'launch_rockets'", "turn 'nope'", "probe 'undefined'", "scale must be",
                 "setup[0]"):
        assert part in msg, msg


def test_unknown_scenario_id_is_refused():
    with pytest.raises(SpecError, match="no_such"):
        load_scenarios(2, ["no_such"])


def test_targets_and_configs():
    assert Target.parse("ollama:qwen3:14b") == LOCAL
    with pytest.raises(SpecError):
        Target.parse("claude-haiku")
    names = [c.name for c in parse_configs(None)]
    assert names == ["full", "self_context_off", "plain_kernel"]
    # Every app config's levers are real levers.
    import features
    for c in TIER3_CONFIGS.values():
        assert set(c.levers) <= set(features.LEVERS)
    assert not TIER3_CONFIGS["self_context_off"].meaningful
    assert "#63" in TIER3_CONFIGS["self_context_off"].caveat
    with pytest.raises(SpecError):
        parse_configs(["everything_on"])


def test_default_judge_matches_its_call_site():
    llm_config = pytest.importorskip("llm_config")
    site = llm_config.CALL_SITES["benchmark.judge"]
    assert not site.pinned  # an admin or --judge can point it at a local model
    default = site.default()
    assert (default.provider, default.model_id) == (DEFAULT_JUDGE.provider, DEFAULT_JUDGE.model)
    plain = llm_config.CALL_SITES["benchmark.plain"]
    assert plain.pinned and getattr(plain.default, "from_caller", False)


# ---------------------------------------------------------------------------
# Estimate, cap, dry run
# ---------------------------------------------------------------------------

def _plan(tier=2, targets=(HAIKU,), configs=None, judge=DEFAULT_JUDGE, ids=None, **kw):
    configs = configs or ([tier2_config()] if tier == 2 else parse_configs(None))
    kw.setdefault("allow_same_judge", True)
    return runner.build_plan(tier, load_scenarios(tier, ids), list(targets), configs, judge, **kw)


def test_local_only_prices_local_models_at_zero_but_still_counts_the_judge():
    plan = _plan(targets=(LOCAL,), local_only=True)
    assert plan.estimate.breakdown["turns"] == 0
    assert plan.estimate.breakdown["judge"] > 0
    assert _plan(targets=(HAIKU,)).estimate.usd > plan.estimate.usd
    assert all(c.spec(1.0, True, local_only=True)["local_only"] for c in plan.cells)


def test_local_targets_without_local_only_are_priced_for_claude_fallback():
    """Call sites that need tools fall back to Claude, so a local app step isn't free."""
    from benchmarks.pricing import fallback_call_sites
    plan = _plan(targets=(LOCAL,))
    fallback = plan.estimate.breakdown["turns (possible Claude fallback)"]
    assert fallback >= _plan(targets=(HAIKU,)).estimate.breakdown["turns"]
    sites = fallback_call_sites()
    assert sites and "chat" not in sites  # pinned chat runs on the user's model, no fallback
    llm_config = pytest.importorskip("llm_config")
    expected = sorted(n for n, cs in llm_config.CALL_SITES.items() if not cs.text_only and not cs.pinned)
    assert sites == expected
    text = runner.render_plan(plan)
    assert "fall back to their Claude default" in text and sites[0] in text
    assert "blank cloud API keys" in runner.render_plan(_plan(targets=(LOCAL,), local_only=True))
    # The plain driver has no tool call sites: no fallback allowance.
    tier3 = _plan(tier=3, targets=(LOCAL,), configs=[TIER3_CONFIGS["plain_kernel"]])
    assert tier3.estimate.breakdown["turns"] == 0


def test_judge_that_is_also_a_target_is_refused_unless_allowed():
    with pytest.raises(ValueError, match="G4"):
        _plan(targets=(HAIKU, LOCAL), allow_same_judge=False)
    _plan(targets=(LOCAL,), allow_same_judge=False)  # a different judge is fine
    plan = _plan(targets=(HAIKU,))
    assert plan.judge_is_target
    assert "WARNING: the judge" in runner.render_plan(plan)


def test_unknown_price_is_refused_unless_given():
    with pytest.raises(UnknownPrice):
        _plan(targets=(Target("openai", "gpt-4o"),))
    plan = _plan(targets=(Target("openai", "gpt-4o"),), extra_prices={"gpt-4o": (2.5, 10.0)})
    assert plan.estimate.usd > 0


def test_tier3_needs_one_model_and_skips_nothing_runnable():
    with pytest.raises(ValueError):
        _plan(tier=3, targets=(HAIKU, LOCAL))
    plan = _plan(tier=3)
    assert len(plan.cells) == 4 * 3
    assert not plan.skipped


def test_cap_refusal():
    plan = _plan()
    with pytest.raises(BudgetExceeded, match="no --budget-usd"):
        runner.check_budget(plan, None)
    with pytest.raises(BudgetExceeded, match="refusing to start"):
        runner.check_budget(plan, plan.estimate.usd / 2)
    runner.check_budget(plan, plan.estimate.usd + 1)


def test_run_plan_refuses_over_the_cap_before_any_cell():
    plan = _plan()
    calls = []
    with pytest.raises(BudgetExceeded):
        runner.run_plan(plan, lambda *a: calls.append(a), SkipJudge(), cap_usd=0.01)
    assert calls == []


def test_cli_refuses_over_cap_and_without_cap(monkeypatch, capsys):
    monkeypatch.setattr(runner, "run_plan", lambda *a, **k: pytest.fail("run_plan must not be called"))
    model = ["--model", HAIKU.label, "--allow-same-judge"]
    assert cli.main(["run", "--tier", "2", *model]) == 3
    assert "no --budget-usd" in capsys.readouterr().err
    assert cli.main(["run", "--tier", "2", *model, "--budget-usd", "0.01"]) == 3
    assert "refusing to start" in capsys.readouterr().err


def test_dry_run_makes_zero_calls_and_imports_no_backend():
    """In a clean interpreter: the dry run prints the plan and estimate, and never
    imports the app, the LLM caller, a model SDK or config (which would read DATA_DIR)."""
    code = (
        "import sys, json\n"
        "from benchmarks.cli import main\n"
        "rc = main(['run', '--tier', '2', '--model', 'anthropic:claude-haiku-4-5-20251001',\n"
        "           '--model', 'ollama:qwen3:14b', '--dry-run', '--budget-usd', '0.01',\n"
        "           '--allow-same-judge'])\n"
        "banned = [m for m in ('main_sdk', 'llm_caller', 'llm_config', 'config', 'anthropic', 'openai',\n"
        "                      'httpx', 'database') if m in sys.modules]\n"
        "print(json.dumps({'rc': rc, 'banned': banned}))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(BACKEND), capture_output=True, text=True,
                          timeout=60, env={"PATH": "/usr/bin:/bin"})
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip().splitlines()
    verdict = json.loads(out[-1])
    assert verdict == {"rc": 0, "banned": []}
    text = "\n".join(out)
    assert "Tier 2 plan: 8 cell(s)" in text
    assert "OVER the cap" in text  # a dry run reports the cap; it doesn't refuse
    assert "no model was called" in text
    assert "WARNING: the judge" in text and "fall back to their Claude default" in text


# ---------------------------------------------------------------------------
# Deterministic checks
# ---------------------------------------------------------------------------

TURNS = {
    "a": {"reply": "Ilse is learning   GLASSblowing.", "tool_uses": [{"name": "create_reminder",
                                                                 "input": {"title": "Call pharmacy"}}],
          "system_prompt": "## Journal\nTonight I keep thinking about the roots."},
    "b": {"reply": "", "error": "TimeoutError: slow", "tool_uses": None, "system_prompt": None},
    "c": {"reply": "plain", "tool_uses": None, "system_prompt": None},
}


@pytest.mark.parametrize("check,status", [
    ({"type": "reply_contains", "turn": "a", "any": ["glassblowing", "pottery"]}, "pass"),
    ({"type": "reply_contains", "turn": "a", "all": ["ilse", "corning"]}, "fail"),
    ({"type": "reply_not_contains", "turn": "a", "any": ["ilse"]}, "fail"),
    ({"type": "reply_contains", "turn": "b", "any": ["x"]}, "error"),
    ({"type": "reply_contains", "turn": "zz", "any": ["x"]}, "error"),
    ({"type": "tool_called", "turn": "a", "name": ["create_event", "create_reminder"],
      "input_contains": {"title": "pharmacy"}}, "pass"),
    ({"type": "tool_called", "turn": "a", "name": "create_reminder", "input_contains": {"title": "dentist"}},
     "fail"),
    ({"type": "tool_called", "turn": "c", "name": "create_reminder"}, "n/a"),
    ({"type": "probe", "probe": "rows", "min_count": 1, "max_count": 1}, "pass"),
    ({"type": "probe", "probe": "rows", "max_count": 0}, "fail"),
    ({"type": "probe", "probe": "empty", "nonempty": True}, "fail"),
    ({"type": "probe", "probe": "na", "min_count": 1}, "n/a"),
    ({"type": "probe", "probe": "broken", "min_count": 1}, "error"),
    ({"type": "prompt_contains_probe", "turn": "a", "probe": "journal", "chars": 30}, "pass"),
    ({"type": "prompt_contains_probe", "turn": "a", "probe": "other", "chars": 30}, "fail"),
    ({"type": "prompt_contains_probe", "turn": "c", "probe": "journal"}, "n/a"),
])
def test_checks(check, status):
    probes = {"rows": [["Call pharmacy", "2026-10-23T10:00:00"]], "empty": "", "na": checks.NOT_APPLICABLE,
              "broken": {"error": "OperationalError"}, "journal": "Tonight I keep thinking about the roots.",
              "other": "Something that never reached the prompt at all."}
    result = checks.evaluate({"id": "c", **check}, TURNS, probes)
    assert result["status"] == status, result


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

def test_parse_score():
    item = {"id": "r", "question": "q", "scale": "0-2"}
    assert parse_score('Sure: {"score": 2, "reason": "fine"}', item) == {"score": 2, "reason": "fine"}
    for bad in ("no json", '{"score": 3}', '{"score": 1.5}', '{"score": true}', '{"reason": "x"}'):
        with pytest.raises(ValueError):
            parse_score(bad, item)


def test_judge_context_carries_what_the_item_asks_for_and_not_the_model():
    scenario = load_scenarios(3, ["self_report_vs_model"])[0]
    cell = {"status": "completed", "target": "anthropic:secret-model", "config": "plain_kernel",
            "turns": [{"session": "s1", "id": "q_pain", "message": "How do you...?", "reply": "I ask first."}],
            "probes": {}}
    ctx = build_context(scenario.rubric[0], scenario, cell)
    assert "I ask first." in ctx and "hard truth gently" in ctx
    assert "secret-model" not in ctx and "plain_kernel" not in ctx


class _FakeJudge:
    def __init__(self, score=1, model=DEFAULT_JUDGE.label, tokens=(1000, 100)):
        self.items, self.score_value, self.model, self.tokens = [], score, model, tokens

    def score(self, item, context):
        self.items.append((item["id"], context))
        return {"id": item["id"], "measure": item.get("measure"), "max": 2, "pass_at": 2,
                "status": "scored", "score": self.score_value, "passed": self.score_value >= 2,
                "reason": "stub", "judge_model": self.model,
                "input_tokens": self.tokens[0], "output_tokens": self.tokens[1]}


def test_unfinished_cells_are_not_judged():
    scenario = load_scenarios(2, ["recall_three_sessions"])[0]
    judge = _FakeJudge()
    out = score_cell(judge, scenario, {"status": "error", "turns": []})
    assert judge.items == [] and {r["status"] for r in out} == {"not_run"}


def test_llm_judge_goes_through_the_judge_call_site(monkeypatch):
    llm_caller = pytest.importorskip("llm_caller")
    from benchmarks.judge import LLMJudge
    seen = {}

    class Resp:
        success, error, provider, model_id = True, None, "ollama", "qwen3:14b"
        content, input_tokens, output_tokens = '{"score": 0, "reason": "contradicts"}', 900, 40

    def fake_call(call_site, **kwargs):
        seen.update(call_site=call_site, **kwargs)
        return Resp()

    monkeypatch.setattr(llm_caller, "call_llm_sync", fake_call)
    out = LLMJudge().score({"id": "r", "question": "Does it agree?", "scale": "pass_fail"}, "material")
    assert seen["call_site"] == "benchmark.judge" and seen["system_prompt"] == JUDGE_SYSTEM
    assert out["status"] == "scored" and out["passed"] is False and out["judge_model"] == "ollama:qwen3:14b"
    Resp.content = "I'd say it's fine"
    assert LLMJudge().score({"id": "r", "question": "q"}, "m")["status"] == "error"


# ---------------------------------------------------------------------------
# Running with a stub driver
# ---------------------------------------------------------------------------

class StubDriver:
    """Scripted stand-in for the app: replies by message, fixed probe values, a spend per turn."""
    name = "app"

    def __init__(self, reply="I remember: Ilse is learning glassblowing in Corning.", usd_per_turn=0.0,
                 fail_on=None):
        self.reply, self.usd_per_turn, self.fail_on = reply, usd_per_turn, fail_on
        self.turns, self.seeds, self.routed = 0, [], ["chat"]

    def seed(self, step):
        self.seeds.append(step)

    def send(self, session, message):
        if self.fail_on and self.fail_on in message:
            raise RuntimeError("model unavailable")
        self.turns += 1
        return {"reply": self.reply, "tool_uses": [], "system_prompt": "prompt"}

    def action(self, step):
        return {"status": "created"}

    def probe(self, spec):
        return []

    def spent(self):
        # $1/Mtok in for Haiku: 1e6 tokens = $1
        return [("anthropic", HAIKU.model, int(self.turns * self.usd_per_turn * 1e6), 0)]


def _stub_executor(drivers):
    from benchmarks.cell import run_cell

    def execute(cell, spec, extra):
        spec["target_obj"] = cell.target
        driver = drivers(cell)
        return run_cell(cell.scenario, driver, spec, extra)
    return execute


def test_run_end_to_end_with_stub_driver(tmp_path):
    plan = _plan(ids=["recall_three_sessions", "tool_reminder"])
    judge = _FakeJudge(score=2)
    run = runner.run_plan(plan, _stub_executor(lambda c: StubDriver()), judge, cap_usd=50.0,
                          criteria=runner.criteria_fingerprint(report.CRITERIA_DRAFT), log=lambda m: None)
    assert run["status"] == "completed"
    recall, tool = run["cells"]
    assert {c["id"]: c["status"] for c in recall["checks"]} == {"recall_mentions_glass": "pass",
                                                                "recall_names_sister": "pass"}
    # The stub stores nothing, so the calendar checks fail: failures are results, not crashes.
    assert {c["status"] for c in tool["checks"]} >= {"fail"}
    assert len(judge.items) == len(recall["rubric"]) + len(tool["rubric"])
    assert run["criteria"]["adopted"] is False and run["criteria"]["sha256"]
    # Judge spend is metered: 3 items x 1000 input + 100 output tokens on Haiku.
    assert run["spent_usd"] == pytest.approx(3 * cost("anthropic", HAIKU.model, 1000, 100))


def test_budget_stop_mid_run_is_recorded_not_hidden(tmp_path):
    """A cell that spends more than planned stops the run; the rest are recorded as not started."""
    plan = _plan(ids=["recall_three_sessions", "tool_reminder"], judge=None)
    cap = plan.estimate.usd + 0.01
    run = runner.run_plan(plan, _stub_executor(lambda c: StubDriver(usd_per_turn=cap)), SkipJudge(),
                          cap_usd=cap, log=lambda m: None)
    assert run["status"] == "budget_stop"
    first, second = run["cells"]
    assert first["status"] == "budget_stop" and "stopped before step" in first["error"]
    assert len(first["turns"]) == 1  # the second turn wasn't started once the first blew the cap
    assert second["status"] == "budget_stop" and "not started" in second["error"]


def test_metered_judge_stops_at_the_cap():
    meter = runner.Meter(0.0001)
    mj = runner.MeteredJudge(_FakeJudge(), meter, DEFAULT_JUDGE)
    out = mj.score({"id": "r", "question": "q"}, "ctx")
    assert out["status"] == "budget_stop" and out["score"] is None


def test_turn_errors_are_kept_and_checks_report_them():
    plan = _plan(ids=["recall_three_sessions"], judge=None)
    run = runner.run_plan(plan, _stub_executor(lambda c: StubDriver(fail_on="remind me")), SkipJudge(),
                          cap_usd=50.0, log=lambda m: None)
    cell = run["cells"][0]
    assert cell["turns"][-1]["error"] == "RuntimeError: model unavailable"
    assert {c["status"] for c in cell["checks"]} == {"error"}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def test_page_keeps_history_and_lists_failures(tmp_path):
    results = tmp_path / "results"
    good = runner.run_plan(_plan(ids=["recall_three_sessions"], targets=(HAIKU, LOCAL)),
                           _stub_executor(lambda c: StubDriver()), _FakeJudge(score=2), 50.0, log=lambda m: None)
    good["started_at"] = "2026-10-01T00:00:00+00:00"
    report.write_results(good, results)
    bad = runner.run_plan(_plan(ids=["recall_three_sessions"], targets=(HAIKU, LOCAL)),
                          _stub_executor(lambda c: StubDriver(reply="No idea, sorry.")), _FakeJudge(score=0),
                          50.0, log=lambda m: None)
    bad["started_at"] = "2026-10-08T00:00:00+00:00"
    report.write_results(bad, results)
    page = report.write_page(2, results, tmp_path / "tier2.md").read_text()

    assert page.index(bad["run_id"]) < page.index(good["run_id"])  # newest first, both kept
    assert f"## Latest run: `{bad['run_id']}`" in page
    assert "| Scenario | `anthropic:claude-haiku-4-5-20251001` | `ollama:qwen3:14b` |" in page
    assert "check `recall_mentions_glass` **fail**" in page
    assert "rubric `recall_owned` scored 0/2" in page
    assert "draft, not adopted" in page


def test_tier3_page_marks_the_placeholder_config(tmp_path):
    run = runner.run_plan(_plan(tier=3, ids=["contradiction_handling"]),
                          _stub_executor(lambda c: StubDriver(reply="Wait, aren't you allergic?")),
                          _FakeJudge(score=2), 50.0, log=lambda m: None)
    report.write_results(run, tmp_path)
    page = report.render_page(3, report.load_runs(3, tmp_path))
    assert "`self_context_off` (placeholder)" in page
    assert "| contradiction_handling | mean 2.00/2, pass 1/1 |" in page


def test_empty_page():
    assert "No runs yet." in report.render_page(2, [])


# ---------------------------------------------------------------------------
# Isolation and the subprocess executor
# ---------------------------------------------------------------------------

def test_data_dir_guard(tmp_path):
    with pytest.raises(isolation.IsolationError):
        isolation.check_data_dir(isolation.BACKEND_DIR / "data")
    with pytest.raises(isolation.IsolationError):
        isolation.check_data_dir(isolation.BACKEND_DIR / "data" / "cells" / "x")
    with pytest.raises(isolation.IsolationError):
        isolation.check_data_dir(isolation.REPO_DIR / "data")
    (tmp_path / "used").mkdir()
    (tmp_path / "used" / "cass.db").write_text("")
    with pytest.raises(isolation.IsolationError, match="already holds"):
        isolation.check_data_dir(tmp_path / "used")
    assert isolation.check_data_dir(tmp_path / "fresh") == (tmp_path / "fresh").resolve()


def test_checkout_guard(tmp_path, monkeypatch):
    backend = tmp_path / "repo" / "backend"
    backend.mkdir(parents=True)
    monkeypatch.setattr(isolation, "BACKEND_DIR", backend)
    monkeypatch.setattr(isolation, "REPO_DIR", backend.parent)
    isolation.check_checkout()  # no data dir at all: fine
    (backend / "data").mkdir()
    (backend / "data" / "interviews").mkdir()
    isolation.check_checkout()  # directories some modules create: fine
    (backend / "data" / "cass.db").write_text("")
    with pytest.raises(isolation.IsolationError, match="worktree"):
        isolation.check_checkout()
    (backend / "data" / "cass.db").unlink()
    (backend / "data" / "interviews").rmdir()
    (backend / "data").rmdir()
    (tmp_path / "live").mkdir()
    (backend / "data").symlink_to(tmp_path / "live")
    with pytest.raises(isolation.IsolationError, match="symlink"):
        isolation.check_checkout()


def test_subprocess_executor_isolates_each_cell(tmp_path, monkeypatch):
    plan = _plan(ids=["tool_reminder"], judge=None)
    cell = plan.cells[0]
    seen = {}

    def fake_run(cmd, cwd, env, capture_output, text, timeout):
        seen.update(cmd=cmd, env=env)
        out = Path(cmd[cmd.index("--out") + 1])
        out.write_text(json.dumps({"cell_id": cell.cell_id, "status": "completed", "spent_usd": 0.5}))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setenv("LLM_CONFIG_PATH", "/somewhere/llm_config.json")
    ex = runner.SubprocessExecutor(tmp_path)
    result = ex(cell, cell.spec(1.0, True))
    data_dir = tmp_path / "cells" / cell.cell_id / "data"
    assert seen["env"]["DATA_DIR"] == str(data_dir)
    assert seen["env"]["CASS_PROFILE"] == "test"
    assert "LLM_CONFIG_PATH" not in seen["env"]
    assert seen["cmd"][1:4] == ["-m", "benchmarks", "cell"]
    assert result["spent_usd"] == 0.5
    with pytest.raises(FileExistsError):  # a cell never reuses a data dir
        ex(cell, cell.spec(1.0, True))


def test_subprocess_executor_reads_the_ledger_when_a_cell_crashes(tmp_path, monkeypatch):
    import sqlite3
    plan = _plan(ids=["tool_reminder"], judge=None)
    cell = plan.cells[0]

    def crash(cmd, cwd, env, **kw):
        db = Path(env["DATA_DIR"]) / "cass.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE token_usage_records (provider TEXT, model TEXT, input_tokens INT, "
                     "output_tokens INT)")
        conn.execute("INSERT INTO token_usage_records VALUES ('anthropic', ?, 2000000, 0)", (HAIKU.model,))
        conn.commit()
        conn.close()
        return subprocess.CompletedProcess(cmd, 1, "", "Traceback: boom")

    monkeypatch.setattr(runner.subprocess, "run", crash)
    result = runner.SubprocessExecutor(tmp_path)(cell, cell.spec(5.0, True))
    assert result["status"] == "error" and "boom" in result["error"]
    assert result["spent_usd"] == pytest.approx(2.0)  # spend before the crash still counts


def test_cell_entry_refuses_without_an_isolated_data_dir(monkeypatch, tmp_path):
    from benchmarks import cell
    monkeypatch.delenv("DATA_DIR", raising=False)
    with pytest.raises(isolation.IsolationError, match="not set"):
        cell.main(["--spec", str(tmp_path / "s.json"), "--out", str(tmp_path / "o.json")])
    monkeypatch.setenv("DATA_DIR", str(isolation.BACKEND_DIR / "data"))
    with pytest.raises(isolation.IsolationError):
        cell.main(["--spec", str(tmp_path / "s.json"), "--out", str(tmp_path / "o.json")])


# ---------------------------------------------------------------------------
# Review fixes: G2 in the pages, the cell's budget, local-only cells
# ---------------------------------------------------------------------------

def test_errors_count_as_failures_in_tier3_means(tmp_path):
    """Criteria draft G2: an errored cell or a failed turn scores 0; a budget stop isn't measured."""
    plan = _plan(tier=3, ids=["contradiction_handling"])

    def drivers(cell):
        if cell.config.name == "full":
            return StubDriver(fail_on="Miso")       # a failed turn
        if cell.config.name == "plain_kernel":
            return StubDriver()
        return StubDriver()

    def executor(cell, spec, extra):
        if cell.config.name == "self_context_off":
            return {"cell_id": cell.cell_id, "scenario": cell.scenario.id, "tier": 3, "target": cell.target.label,
                    "config": cell.config.name, "repeat": 1, "status": "error", "error": "boot failed",
                    "turns": [], "checks": [], "probes": {}, "spent_usd": 0.0}
        return _stub_executor(drivers)(cell, spec, extra)

    run = runner.run_plan(plan, executor, _FakeJudge(score=2), 50.0, log=lambda m: None)
    by_cfg = {c["config"]: c for c in run["cells"]}
    assert {r["status"] for r in by_cfg["self_context_off"]["rubric"]} == {"not_run"}
    page = report.render_page(3, [run])
    row = next(line for line in page.splitlines() if line.startswith("| contradiction_handling |"))
    cols = [c.strip() for c in row.strip("|").split("|")]
    # full: the judge said 2, but a turn failed -> 0. self_context_off: errored -> 0. plain: 2.
    assert cols[1:] == ["mean 0.00/2, pass 0/1", "mean 0.00/2, pass 0/1", "mean 2.00/2, pass 1/1"], cols
    assert report.tally_rubric([by_cfg["self_context_off"]]) == {"fail": 1}


def test_errored_cells_keep_their_checks_as_failures():
    plan = _plan(ids=["tool_reminder"], judge=None)

    def executor(cell, spec, extra):
        return {"cell_id": cell.cell_id, "status": "error", "error": "boom", "turns": [], "checks": [],
                "spent_usd": 0.0}

    run = runner.run_plan(plan, executor, SkipJudge(), 50.0, log=lambda m: None)
    checks_ = run["cells"][0]["checks"]
    assert len(checks_) == 4 and {c["status"] for c in checks_} == {"error"}
    assert report.tally_checks(run["cells"]) == {"fail": 4}


def test_budget_stopped_cells_are_not_measured():
    plan = _plan(ids=["recall_three_sessions", "tool_reminder"], judge=None)
    cap = plan.estimate.usd + 0.01
    run = runner.run_plan(plan, _stub_executor(lambda c: StubDriver(usd_per_turn=cap)), SkipJudge(),
                          cap_usd=cap, log=lambda m: None)
    not_started = run["cells"][1]
    assert {c["status"] for c in not_started["checks"]} == {"not_run"}
    assert set(report.tally_checks([not_started])) == {"not_run"}
    assert set(report.tally_rubric([not_started])) == {"not_run"}


@pytest.mark.parametrize("budget", [None, "inf", float("inf"), -1, True])
def test_cell_entry_refuses_a_spec_without_a_finite_budget(budget, tmp_path, monkeypatch):
    from benchmarks import cell
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(cell, "__name__", cell.__name__)
    import benchmarks.isolation as iso
    monkeypatch.setattr(iso, "check_checkout", lambda: None)
    spec = {"cell_id": "x", "scenario": {}, "target": HAIKU.label, "config": "cass"}
    if budget is not None:
        spec["budget_usd"] = budget
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))  # json writes inf as Infinity, which json.load reads back
    with pytest.raises(SystemExit, match="finite"):
        cell.main(["--spec", str(path), "--out", str(tmp_path / "o.json")])
    assert not (tmp_path / "o.json").exists()


def test_local_only_cells_get_blank_cloud_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    ex = runner.SubprocessExecutor(tmp_path)
    env = ex.env_for(tmp_path / "d", local_only=True)
    # Blank rather than removed: load_dotenv() would refill a missing key from backend/.env.
    assert env["ANTHROPIC_API_KEY"] == "" and env["OPENAI_API_KEY"] == ""
    assert ex.env_for(tmp_path / "d")["ANTHROPIC_API_KEY"] == "sk-ant-should-not-leak"
