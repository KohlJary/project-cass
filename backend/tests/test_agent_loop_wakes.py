"""
Phase 4 of the agent loop: wake_me (she asks to be woken later, through
Heartbeat) and say (her own reach_out, under the loop's name).
"""
import asyncio
from datetime import datetime, timedelta

import pytest

from agent_loop import wakes as W
from agent_loop.spec import ACTIVITY_PACKS, session_spec

NOW = datetime(2026, 11, 13, 20, 0)


@pytest.fixture
def book(tmp_path):
    return W.WakeBook(tmp_path / "wakes.json")


def test_a_request_is_kept_and_comes_due(book):
    out = book.request({"in_minutes": 90, "why": "finish the tide notes"}, "s1", ACTIVITY_PACKS, now=NOW)
    assert "finish the tide notes" in out and "21:30" in out
    [w] = book.pending()
    assert w["activity"] == "reflection" and w["asked_in"] == "s1"
    assert book.take_due(NOW + timedelta(minutes=89)) == []
    [due] = book.take_due(NOW + timedelta(minutes=90))
    assert due["id"] == w["id"] and book.pending() == []
    assert book.take_due(NOW + timedelta(minutes=91)) == [], "never runs twice"
    book.finish(w["id"], W.DONE, "Reflection session completed")
    assert book.all()[0]["status"] == W.DONE


@pytest.mark.parametrize("tool_input,why", [
    ({"in_minutes": 5, "why": "x"}, "between 15"),
    ({"in_minutes": 20000, "why": "x"}, "between 15"),
    ({"in_minutes": "soon", "why": "x"}, "whole number"),
    ({"in_minutes": 60, "why": " "}, "why is needed"),
    ({"in_minutes": 60, "why": "x", "activity": "nap"}, "activity must be"),
])
def test_bad_requests_are_refused(book, tool_input, why):
    assert why in book.request(tool_input, "s1", ACTIVITY_PACKS, now=NOW)["error"]
    assert book.all() == []


def test_at_most_three_pending(book):
    for i in range(W.MAX_PENDING):
        book.request({"in_minutes": 60 + i, "why": f"t{i}"}, "s1", ACTIVITY_PACKS, now=NOW)
    result = book.request({"in_minutes": 60, "why": "one more"}, "s1", ACTIVITY_PACKS, now=NOW)
    assert "3 wakes pending" in result["error"] and len(book.pending()) == 3


def test_release_puts_a_wake_back(book):
    book.request({"in_minutes": 15, "why": "x"}, "s1", ACTIVITY_PACKS, now=NOW)
    [w] = book.take_due(NOW + timedelta(hours=1))
    book.release(w["id"])
    assert [p["id"] for p in book.pending()] == [w["id"]]


def test_check_wakes_submits_each_due_wake_to_heartbeat(book, levers, monkeypatch):
    from heartbeat import wiring
    submitted = []
    monkeypatch.setattr(wiring, "submit", lambda name, run, **kw: submitted.append((name, kw)) or True)
    book.request({"in_minutes": 15, "why": "x", "activity": "research"}, "s1", ACTIVITY_PACKS,
                 now=datetime.now() - timedelta(hours=1))
    with levers(agent_loop=True):
        assert asyncio.run(W.check_wakes(book)) == 1
    [(name, kw)] = submitted
    assert name == "agent_loop.wake.research" and kw["lever"] == ("agent_loop",)
    assert kw["budget_class"] is not None and kw["estimated_cost_usd"] > 0


def test_check_wakes_leaves_them_when_heartbeat_is_gone_or_the_lever_is_off(book, levers, monkeypatch):
    from heartbeat import wiring
    monkeypatch.setattr(wiring, "submit", lambda *a, **k: False)
    book.request({"in_minutes": 15, "why": "x"}, "s1", ACTIVITY_PACKS, now=datetime.now() - timedelta(hours=1))
    with levers(agent_loop=False):
        assert asyncio.run(W.check_wakes(book)) == 0
    with levers(agent_loop=True):
        asyncio.run(W.check_wakes(book))
    assert len(book.pending()) == 1


def test_say_and_wake_are_in_the_spec_only_when_on():
    names = session_spec("reflection").tool_names()
    assert "say" in names and "wake_me" in names
    off = session_spec("reflection", can_say=False, can_wake=False).tool_names()
    assert "say" not in off and "wake_me" not in off


def test_say_is_her_reach_out_and_reach_out_isnt_findable():
    pytest.importorskip("anthropic")
    from agent_loop import tools as T
    catalog = T.router_catalog()
    say = T.say_tool(catalog)
    assert say["input_schema"] == catalog["reach_out"]["input_schema"]
    assert "reach_out" not in T.findable(catalog, session_spec("reflection").tool_names())
