"""benchmarks/pairwise.py: blind A/B between configs, tells stripped by regex, fidelity checked."""
import json

import pytest

import llm_caller
from benchmarks import pairwise
from benchmarks.spec import Target

JUDGE = Target("anthropic", "claude-sonnet-4-6")


@pytest.mark.unit
def test_strip_removes_tags_and_fidelity_holds():
    raw = "<gesture:wave> Hi Kohl. <emote:happy:0.7>I'm glad. <observe target=\"self\">I hedge</observe> Done."
    clean = pairwise.strip_tells(raw)
    assert clean == "Hi Kohl. I'm glad. Done."
    assert pairwise.fidelity(raw, clean)


@pytest.mark.unit
def test_fidelity_catches_a_change_beyond_tags():
    raw = "<gesture:wave> I think the tide is late tonight."
    assert not pairwise.fidelity(raw, "I think the moon is late tonight.")
    assert not pairwise.fidelity(raw, "I think the tide is late.")


def _cell(config, reply, scenario="s", repeat=1):
    return {"config": config, "scenario": scenario, "repeat": repeat, "status": "completed",
            "turns": [{"session": "a", "message": "How are you?", "reply": reply}]}


@pytest.mark.unit
def test_judge_is_blind_and_order_maps_back(monkeypatch):
    seen = []

    def call(site, **kw):
        seen.append(kw["user_prompt"])
        a_is_base = kw["user_prompt"].index("BASE") < kw["user_prompt"].index("OTHER")
        return type("R", (), {"content": json.dumps({"winner": "A" if a_is_base else "B"}),
                              "input_tokens": 10, "output_tokens": 5})()

    monkeypatch.setattr(llm_caller, "call_llm_sync", call)
    monkeypatch.setattr(pairwise, "question_for", lambda run, s: "Which is warmer?")
    run = {"tier": 3, "cells": [_cell("full", f"<emote:happy>BASE {i}", repeat=i) for i in range(8)]
           + [_cell("memories_off", f"OTHER {i}", repeat=i) for i in range(8)]}
    rep = pairwise.run_pairwise(run, JUDGE, budget_usd=5, log=lambda m: None)
    r = rep["configs"]["memories_off"]
    assert (r["other_wins"], r["baseline_wins"]) == (0, 8)  # the judge always picked BASE, wherever it sat
    assert {v["other_shown_first"] for v in r["verdicts"]} == {True, False}
    assert all("memories_off" not in p and "full" not in p and "emote" not in p for p in seen)
    assert "| `memories_off` | 0 | 0 | 8 |" in pairwise.render(rep)
