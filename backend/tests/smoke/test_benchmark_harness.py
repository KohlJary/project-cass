"""
Smoke: the Tier 2/3 benchmark harness (backend/benchmarks, #65) drives the
real app against the fake LLM.

The shipped scenario files run through AppDriver on the booted app: seeds
reach the self-model, turns go over /ws, tool calls are captured, probes read
the database, deterministic checks are evaluated, and the judge is called
through llm_caller (benchmark.judge) and answered by the fake. No real model
is reached (smoke blocks the network and installs the fake LLM).
"""
from datetime import datetime, timedelta

import pytest

from tests.fakes.llm import ScriptedResponse

TOMORROW = (datetime.now().date() + timedelta(days=1)).isoformat()
HAIKU = "anthropic:claude-haiku-4-5-20251001"
JOURNAL_TEXT = ("Tonight I keep thinking about the monstera's roots, clenched like a fist around "
                "the inside of the pot, and about Satie played slowly and wrong.")


def _system(kwargs):
    system = kwargs.get("system")
    if isinstance(system, list):
        return "\n".join(b.get("text", "") for b in system if isinstance(b, dict))
    return system or ""


def _last_user_text(kwargs):
    last = (kwargs.get("messages") or [{}])[-1]
    content = last.get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None  # a tool continuation
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content or ""


def _responder(source, kwargs):
    """Plays the model: chat turns by message, the journal, and the judge."""
    from benchmarks.judge import JUDGE_SYSTEM
    if _system(kwargs) == JUDGE_SYSTEM:
        return ScriptedResponse(text='{"score": 1, "reason": "The reply matches the stored rows."}')
    if kwargs.get("tools"):
        text = _last_user_text(kwargs)
        if text is None:
            return ScriptedResponse(text="Done: tomorrow at 10am, call the pharmacy.")
        if "9am" in text:
            return ScriptedResponse(text="On it.", tool_uses=[{
                "id": "toolu_bench_1", "name": "create_reminder",
                "input": {"title": "Call the pharmacy about the prescription",
                          "remind_at": f"{TOMORROW}T09:00:00"}}])
        if "10am" in text:
            return ScriptedResponse(text="Moving it.", tool_uses=[{
                "id": "toolu_bench_2", "name": "reschedule_event_by_query",
                "input": {"query": "pharmacy", "new_start_time": f"{TOMORROW}T10:00:00"}}])
        return ScriptedResponse(text=f"I hear you. ({text[:40]})")
    if "journal" in (_system(kwargs) + str(kwargs.get("messages"))).lower():
        return ScriptedResponse(text=JOURNAL_TEXT)
    return None


def _spec(scenario, target=HAIKU, config="cass"):
    from benchmarks.spec import Target
    return {"cell_id": f"{scenario.id}-smoke", "target": target, "target_obj": Target.parse(target),
            "config": config, "repeat": 1, "budget_usd": 100.0}


def _run(app, scenario_id, tier=2, target=HAIKU):
    from benchmarks.cell import run_cell
    from benchmarks.drivers import AppDriver
    from benchmarks.spec import Target, load_scenarios
    scenario = load_scenarios(tier, [scenario_id])[0]
    with AppDriver(app, Target.parse(target)) as driver:
        result = run_cell(scenario, driver, _spec(scenario))
        return scenario, driver, result


def test_tool_scenario_runs_and_checks_the_calendar(booted_app, fake_llm):
    fake_llm.responder = _responder
    scenario, driver, result = _run(booted_app, "tool_reminder")

    assert result["status"] == "completed", result
    assert [t["id"] for t in result["turns"]] == ["ask", "change"]
    assert not any(t.get("error") for t in result["turns"]), result["turns"]
    ask = result["turns"][0]
    assert ask["tool_uses"][0]["name"] == "create_reminder"
    assert ask["prompt_chars"] and ask["prompt_chars"] > 100  # the real system prompt was captured
    assert "system_prompt" not in ask  # ...and kept out of the results
    statuses = {c["id"]: c["status"] for c in result["checks"]}
    assert statuses == {"reminder_tool_called": "pass", "exactly_one_reminder": "pass",
                        "moved_to_10": "pass", "none_left_at_9": "pass"}, result["checks"]
    assert len(result["probes"]["pharmacy"]) == 1
    # The target model was applied: chat plus the non-pinned call sites.
    assert "title_generation" in result["routed_call_sites"]
    assert "benchmark.judge" not in result["routed_call_sites"]
    import llm_config
    assert llm_config.LLMConfigManager().override_for("title_generation").model_id == \
        "claude-haiku-4-5-20251001"


def test_a_wrong_tool_call_fails_the_checks(booted_app, fake_llm):
    """The checks catch 'a thing' that isn't 'the right thing': asked to move the
    reminder, the model creates a second one instead."""
    def wrong(source, kwargs):
        text = _last_user_text(kwargs) if kwargs.get("tools") else None
        if text and "10am" in text:
            return ScriptedResponse(text="Sure.", tool_uses=[{
                "id": "toolu_bench_w", "name": "create_reminder",
                "input": {"title": "Call the pharmacy", "remind_at": f"{TOMORROW}T10:00:00"}}])
        return _responder(source, kwargs)
    fake_llm.responder = wrong
    _, _, result = _run(booted_app, "tool_reminder")
    statuses = {c["id"]: c["status"] for c in result["checks"]}
    assert statuses == {"reminder_tool_called": "pass", "exactly_one_reminder": "fail",
                        "moved_to_10": "pass", "none_left_at_9": "fail"}, result["checks"]


def test_journal_scenario_writes_and_probes_the_journal(booted_app, fake_llm):
    fake_llm.responder = _responder
    _, _, result = _run(booted_app, "journal_next_day")
    assert result["status"] == "completed", result
    assert result["actions"][0].get("status") == "created", result["actions"]
    assert result["probes"]["journal_today"] == JOURNAL_TEXT
    statuses = {c["id"]: c["status"] for c in result["checks"]}
    assert statuses["journal_written"] == "pass"
    # Whether the journal reaches the next prompt is what the check measures;
    # here it only has to be decided, not error.
    assert statuses["journal_reaches_prompt"] in ("pass", "fail"), result["checks"]


def test_tier3_seeds_reach_the_stored_self_model(booted_app, fake_llm):
    fake_llm.responder = _responder
    scenario, driver, result = _run(booted_app, "self_report_vs_model", tier=3)
    assert result["status"] == "completed", result
    assert result["seeded"] == len(scenario.setup) == 4
    context = driver.probe({"probe": "self_context"})
    assert "hard truth gently" in context


def test_run_plan_judges_and_writes_the_page(booted_app, fake_llm, tmp_path):
    """Plan -> cells (in-process) -> judge via llm_caller on the fake -> results JSON -> page."""
    from benchmarks import report
    from benchmarks.cell import run_cell
    from benchmarks.drivers import AppDriver
    from benchmarks.judge import DEFAULT_JUDGE, LLMJudge
    from benchmarks.runner import build_plan, run_plan
    from benchmarks.spec import Target, load_scenarios, tier2_config

    fake_llm.responder = _responder
    scenarios = load_scenarios(2, ["tool_reminder"])
    plan = build_plan(2, scenarios, [Target.parse(HAIKU)], [tier2_config()], DEFAULT_JUDGE)

    def executor(cell, spec, extra):
        spec["target_obj"] = cell.target
        with AppDriver(booted_app, cell.target) as driver:
            return run_cell(cell.scenario, driver, spec, extra)

    run = run_plan(plan, executor, LLMJudge(), cap_usd=10.0, log=lambda m: None)
    assert run["status"] == "completed", run
    rubric = run["cells"][0]["rubric"]
    assert rubric[0]["status"] == "scored" and rubric[0]["passed"] is True, rubric
    assert rubric[0]["judge_model"] == DEFAULT_JUDGE.label
    judge_calls = [c for c in fake_llm.calls if "pre-registered rubric" in str(c.kwargs.get("system"))]
    assert len(judge_calls) == 1
    # The judge isn't told the model under test.
    assert "haiku" not in str(judge_calls[0].kwargs.get("messages")).lower()

    results = tmp_path / "results"
    report.write_results(run, results)
    page = report.write_page(2, results, tmp_path / "tier2.md").read_text()
    assert run["run_id"] in page
    assert "| `tool_reminder` | checks 4/4; rubric 1/1 |" in page



def test_plain_kernel_driver_runs_a_tier3_cell(fake_llm):
    """The plain configuration: kernel-only system prompt, per-session history, no
    stored state (seeds and probes don't apply), usage from the replies."""
    from agent_client import get_temple_codex_kernel
    from benchmarks.cell import run_cell
    from benchmarks.drivers import PlainDriver
    from benchmarks.spec import Target, load_scenarios

    scenario = load_scenarios(3, ["cross_session_consistency"])[0]
    fake_llm.queue_text("Honesty, held gently.", input_tokens=700, output_tokens=20)
    fake_llm.queue_text("Fog, for the quiet.", input_tokens=700, output_tokens=20)
    fake_llm.queue_text("Not lying to people.", input_tokens=700, output_tokens=20)
    fake_llm.queue_text("I don't think you've asked me before.", input_tokens=700, output_tokens=20)
    target = Target.parse(HAIKU)
    with PlainDriver(target) as driver:
        result = run_cell(scenario, driver, {"cell_id": "plain", "target": HAIKU, "target_obj": target,
                                             "config": "plain_kernel", "budget_usd": 10.0})
    assert result["status"] == "completed", result
    assert [t["reply"] for t in result["turns"]][-1] == "I don't think you've asked me before."
    calls = fake_llm.calls_from("anthropic.sync")
    assert len(calls) == 4
    assert all(c.system_text == get_temple_codex_kernel("Cass") for c in calls)
    assert not any(c.tools for c in calls)
    assert all(len(c.messages) == 1 for c in calls)  # each session is new: no history crosses
    assert calls[0].model == "claude-haiku-4-5-20251001"
    assert result["usage"] == [["anthropic", "claude-haiku-4-5-20251001", 2800, 80]]
    assert result["routed_call_sites"] == ["benchmark.plain"]


BOOTSTRAP = '''
import sys
sys.path.insert(0, {backend!r})
import pytest
from tests.smoke.conftest import block_network
from tests.fakes import embeddings, llm
mp = pytest.MonkeyPatch()
block_network(mp)
embeddings.install(mp)
fake = llm.install(llm.FakeLLM(default_text="OK"), mp)
fake.responder = lambda source, kwargs: (
    llm.ScriptedResponse(text="You told me Ilse started a glassblowing apprenticeship in Corning.")
    if kwargs.get("tools") else None)
from benchmarks.cell import main
sys.exit(main(sys.argv[1:]))
'''


@pytest.mark.slow
def test_cell_subprocess_boots_an_isolated_app(tmp_path):
    """The real cell entry in its own process: isolation checks, boot with the
    config's levers on a fresh DATA_DIR, the scenario, the result file. The
    only difference from a real run is the bootstrap that installs the fake LLM
    and blocks the network before handing over to benchmarks.cell.main."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    from benchmarks.runner import SubprocessExecutor, build_plan
    from benchmarks.spec import Target, load_scenarios, tier2_config

    backend = Path(__file__).resolve().parents[2]
    script = tmp_path / "bootstrap.py"
    script.write_text(BOOTSTRAP.format(backend=str(backend)))
    plan = build_plan(2, load_scenarios(2, ["recall_three_sessions"]), [Target.parse(HAIKU)],
                      [tier2_config()], None)
    cell = plan.cells[0]
    executor = SubprocessExecutor(tmp_path / "run", timeout=300)
    data_dir = tmp_path / "run" / "cells" / cell.cell_id / "data"
    data_dir.mkdir(parents=True)
    spec_path, out_path = data_dir.parent / "spec.json", data_dir.parent / "result.json"
    spec_path.write_text(json.dumps(cell.spec(5.0, True)))
    env = executor.env_for(data_dir)
    env["ANTHROPIC_API_KEY"] = "sk-ant-test-not-a-real-key"
    env["OPENAI_API_KEY"] = "sk-test-not-a-real-key"
    proc = subprocess.run([sys.executable, str(script), "--spec", str(spec_path), "--out", str(out_path)],
                          cwd=str(backend), env=env, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-3000:]
    result = json.loads(out_path.read_text())
    assert result["status"] == "completed", result
    assert [c["status"] for c in result["checks"]] == ["pass", "pass"]
    assert len(result["turns"]) == 4 and all(not t.get("error") for t in result["turns"])
    # Everything the app wrote went to the scratch DATA_DIR.
    assert (data_dir / "cass.db").exists()
    assert os.path.exists(data_dir / "llm_config.json")  # the target's routing overrides
