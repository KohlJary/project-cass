"""Happenings (happenings.py): what happens to her wakes her, by her rules;
crisis always; never twice for the same thing."""
from datetime import datetime

import commitments as C
import happenings as H
from social import inbox

NOW = datetime(2026, 11, 18, 14, 0)


def _inbox(tmp_path, *items):
    state = inbox.load("bluesky", tmp_path)
    state["items"].extend({"status": "new", **i} for i in items)
    inbox.save("bluesky", state, tmp_path)


def test_a_reply_and_a_due_commitment_wake_her_once(tmp_path):
    _inbox(tmp_path, {"id": "at://1", "kind": "reply", "from": "ann.bsky.social", "text": "loved this"},
           {"id": "at://2", "kind": "follow", "from": "bo"})
    C.add("Send Kohl the notes", "Kohl", "2026-11-18T16:00", data_dir=tmp_path, now=NOW)
    due = H.due_to_wake(tmp_path, NOW)
    assert sorted(h["kind"] for h in due) == ["commitment", "reply"], "a follow doesn't wake her"
    assert "due 16:00: Send Kohl the notes (for Kohl)" in H.describe(due)
    H.mark_woken(due, tmp_path, NOW)
    assert H.due_to_wake(tmp_path, NOW.replace(hour=15)) == [], "never twice for the same thing"


def test_her_rules_quiet_hours_cap_and_gap(tmp_path):
    _inbox(tmp_path, {"id": "at://1", "kind": "mention", "from": "ann", "text": "hi"})
    assert H.due_to_wake(tmp_path, NOW.replace(hour=23, minute=30)) == [], "quiet hours"
    assert H.set_rules({"wake_for": ["dm"]}, tmp_path)["success"]
    assert H.due_to_wake(tmp_path, NOW) == [], "mentions aren't hers to be woken for now"
    assert "kinds are" in H.set_rules({"wake_for": ["everything"]}, tmp_path)["error"]
    H.set_rules({"wake_for": ["mention", "dm"], "min_gap_minutes": 60}, tmp_path)
    H.mark_woken([{"id": "x", "kind": "dm", "crisis": False}], tmp_path, NOW)
    assert H.due_to_wake(tmp_path, NOW.replace(minute=30)) == [], "within the gap"
    assert H.due_to_wake(tmp_path, NOW.replace(hour=15, minute=1)), "after the gap"
    H.set_rules({"max_per_day": 1}, tmp_path)
    assert H.due_to_wake(tmp_path, NOW.replace(hour=16)) == [], "the day's cap"


def test_crisis_wakes_her_through_everything(tmp_path):
    H.set_rules({"wake_for": [], "quiet": ["00:00", "23:59"], "max_per_day": 0}, tmp_path)
    _inbox(tmp_path, {"id": "at://9", "kind": "dm", "from": "someone", "triage": {"label": "crisis"}})
    due = H.due_to_wake(tmp_path, NOW)
    assert len(due) == 1 and due[0]["crisis"]


def test_the_job_submits_a_budgeted_respond_run(tmp_path, monkeypatch, levers):
    import asyncio
    from heartbeat import wiring
    H.set_rules({"quiet": []}, tmp_path)   # the real clock may be in her quiet hours
    _inbox(tmp_path, {"id": "at://1", "kind": "reply", "from": "ann", "text": "hi"})
    sent = []
    monkeypatch.setattr(wiring, "submit", lambda name, run, **kw: sent.append((name, kw)) or True)
    with levers(happenings=True, agent_loop=True):
        assert asyncio.run(H.check_happenings(tmp_path)) == 1
    assert sent[0][0] == "happenings.respond" and sent[0][1]["budget_class"].value == "triggered"
    with levers(happenings=False, agent_loop=True):
        assert asyncio.run(H.check_happenings(tmp_path)) == 0
