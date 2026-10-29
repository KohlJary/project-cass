"""benchmarks/replay.py: recorded inputs on candidate models, judged blind (phase 6)."""
import json

import pytest

import llm_caller
from benchmarks import replay
from benchmarks.spec import Target

REF = Target("anthropic", "claude-haiku-4-5-20251001")
LOCAL = Target("ollama", "qwen3:14b")
JUDGE = Target("anthropic", "claude-sonnet-4-6")


class _Resp:
    def __init__(self, content, error=None):
        self.content, self.error, self.input_tokens, self.output_tokens = content, error, 100, 10


def _fake(monkeypatch, outputs, judge_says, seen):
    def call(site, **kw):
        seen.append((site, kw))
        if site == "benchmark.judge":
            a_is_ref = kw["user_prompt"].index("ref-out") < kw["user_prompt"].index("local-out")
            pick = judge_says  # "ref" | "local" | "tie"
            letter = "tie" if pick == "tie" else ("A" if (pick == "ref") == a_is_ref else "B")
            return _Resp(json.dumps({"winner": letter, "reason": "x"}))
        model = kw["default"].model_id
        out = outputs[model]
        return _Resp("", error="ReadTimeout: slow") if out is None else _Resp(out)
    monkeypatch.setattr(llm_caller, "call_llm_sync", call)


def _rows(n=6):
    return [{"ts": str(i), "system_prompt": "Title this.", "messages": [{"role": "user", "content": f"chat {i}"}],
             "use_chat": False, "max_tokens": 30} for i in range(n)]


@pytest.mark.unit
def test_replays_the_exact_input_and_judges_blind(monkeypatch):
    seen = []
    _fake(monkeypatch, {REF.model: "ref-out", LOCAL.model: "local-out"}, "local", seen)
    rep = replay.run(_rows(), [REF, LOCAL], JUDGE, budget_usd=5, log=lambda m: None)
    first = [kw for site, kw in seen if site == "benchmark.replay"][0]
    assert first["system_prompt"] == "Title this." and first["user_prompt"] == "chat 0"
    s = rep["summary"][LOCAL.label]
    assert (s["wins"], s["ties"], s["losses"]) == (6, 0, 0)
    shown = {r["judged"][LOCAL.label]["shown_first"] for r in rep["results"]}
    assert shown == {REF.label, LOCAL.label}  # order is shuffled
    judge_prompts = [kw["user_prompt"] for site, kw in seen if site == "benchmark.judge"]
    assert all("qwen" not in p and "haiku" not in p for p in judge_prompts)  # blind


@pytest.mark.unit
def test_a_failed_local_run_is_a_loss(monkeypatch):
    _fake(monkeypatch, {REF.model: "ref-out", LOCAL.model: None}, "tie", [])
    rep = replay.run(_rows(3), [REF, LOCAL], JUDGE, budget_usd=5, log=lambda m: None)
    s = rep["summary"][LOCAL.label]
    assert s["failures"] == 3 and s["losses"] == 3
    assert "3/3" in replay.render(rep, "title_generation")


@pytest.mark.unit
def test_budget_stops_it(monkeypatch):
    _fake(monkeypatch, {REF.model: "ref-out", LOCAL.model: "local-out"}, "tie", [])
    rep = replay.run(_rows(50), [REF, LOCAL], JUDGE, budget_usd=0.001, log=lambda m: None)
    assert len(rep["results"]) < 50


@pytest.mark.unit
def test_parse_verdict():
    assert replay.parse_verdict('ok {"winner": "B", "reason": "x"}') == "B"
    assert replay.parse_verdict("no json") is None
    assert replay.parse_verdict('{"winner": "C"}') is None


@pytest.mark.unit
def test_rejudge_reuses_saved_outputs_and_only_calls_the_judge(monkeypatch):
    seen = []
    _fake(monkeypatch, {REF.model: "ref-out", LOCAL.model: "local-out"}, "ref", seen)
    first = replay.run(_rows(4), [REF, LOCAL], JUDGE, budget_usd=5, log=lambda m: None)
    seen.clear()
    _fake(monkeypatch, {REF.model: None, LOCAL.model: None}, "local", seen)
    other = Target("openai", "gpt-4o")
    rep = replay.rejudge(first, _rows(4), other, budget_usd=5, log=lambda m: None)
    assert {site for site, _ in seen} == {"benchmark.judge"}
    assert all(kw["default"].model_id == "gpt-4o" for _, kw in seen)
    assert rep["summary"][LOCAL.label]["wins"] == 4
    assert rep["previous_judge"] == JUDGE.label


@pytest.mark.unit
def test_rejudge_refuses_recordings_that_do_not_match():
    prev = {"models": [REF.label, LOCAL.label], "results": [{"ts": "nope", "runs": {}, "judged": {}}]}
    with pytest.raises(ValueError):
        replay.rejudge(prev, _rows(2), JUDGE, budget_usd=5, log=lambda m: None)
