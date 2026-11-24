"""Her world as events (world_events.py), slice 1: only real sources emit; most is
seen, a little is noticed; her focus flag; the guards on reactive sessions; and
the trigger every session records."""
import asyncio
import json
from datetime import datetime, timedelta

import pytest

import world_events as W

NOW = datetime(2026, 11, 24, 14, 0)
TOPICS = ["modular synthesis", "the house's shared values"]


@pytest.fixture(autouse=True)
def paid(monkeypatch):
    """Paid-model defaults unless a test says local."""
    monkeypatch.delenv("LLM_LOCAL_MODEL", raising=False)
    import llm_config
    monkeypatch.setattr(llm_config, "local_model", lambda: None)
    W._interest_cache.update(at=None, value=[])


def _news(tmp_path, sid, summary, at=NOW):
    return W.record("news", sid, summary, {"rss_item_id": sid, "link": f"https://example.org/{sid}"},
                    at=at, data_dir=tmp_path, her_interests=TOPICS, now=at)


# --- never invented ------------------------------------------------------------

@pytest.mark.parametrize("source,sid,origin", [
    ("seeded", "1", {"x": 1}),          # not a registered source
    ("bakery", "1", {"x": 1}),
    ("news", "", {"x": 1}),             # no source id
    ("news", "1", {}),                  # nothing it came from
    ("news", "1", None),
])
def test_an_event_without_a_real_source_is_rejected(tmp_path, source, sid, origin):
    with pytest.raises(W.NotARealEvent):
        W.record(source, sid, "a bakery is running a special", origin, data_dir=tmp_path,
                 her_interests=[], now=NOW)
    assert not (tmp_path / "world" / "events.jsonl").exists()


def test_every_event_carries_its_source_and_is_logged_once(tmp_path):
    e = _news(tmp_path, "a1", "Weather tomorrow: rain")
    assert {k: e[k] for k in ("source", "source_id", "summary")} == {
        "source": "news", "source_id": "a1", "summary": "Weather tomorrow: rain"}
    assert e["origin"]["link"] == "https://example.org/a1" and e["at"]
    assert _news(tmp_path, "a1", "Weather tomorrow: rain") is None, "the seen log keeps it to once"
    assert len(W.recent(data_dir=tmp_path)) == 1


def test_safe_record_does_nothing_with_the_lever_off(tmp_path, levers):
    W.safe_record("news", "x", "modular synthesis", {"a": 1}, data_dir=tmp_path, her_interests=TOPICS)
    assert not (tmp_path / "world").exists()
    with levers(world_events=True):
        W.safe_record("bogus", "x", "y", {"a": 1}, data_dir=tmp_path)   # rejected, but never raises
        W.safe_record("news", "x", "modular synthesis", {"a": 1}, data_dir=tmp_path, her_interests=TOPICS)
    assert [e["source"] for e in W.recent(data_dir=tmp_path)] == ["news"]


# --- noticing -------------------------------------------------------------------

def test_most_is_seen_and_what_touches_her_is_noticed(tmp_path):
    assert not _news(tmp_path, "a1", "Stock markets close flat")["noticed"]
    assert not _news(tmp_path, "a2", "A synthesis of recent polls")["noticed"], "one shared word isn't enough"
    hit = _news(tmp_path, "a3", "A new modular synthesis module ships this week")
    assert hit["noticed"] and hit["why"] == ["modular synthesis"]
    queue = W._state(tmp_path)["queue"]
    assert [q["id"] for q in queue] == ["news:a3"], "only the noticed one queues"


def test_the_clock_is_real_and_only_a_turning_season_is_noticed(tmp_path):
    assert W.poll_clock(NOW, tmp_path) == 3
    assert W.poll_clock(NOW.replace(minute=30), tmp_path) == 0, "same hour, same day, same season"
    assert W.poll_clock(NOW.replace(hour=15), tmp_path) == 1, "a new hour"
    events = W.recent(data_dir=tmp_path)
    assert all(e["origin"]["clock"] for e in events)
    assert [e["source_id"] for e in events if e["noticed"]] == ["season:2026-autumn"]


def test_her_threshold_is_hers(tmp_path):
    assert W.set_rules({"threshold": 10}, tmp_path)["success"]
    assert not _news(tmp_path, "a3", "A new modular synthesis module ships")["noticed"]
    assert "threshold is 1 to 10" in W.set_rules({"threshold": 50}, tmp_path)["error"]


# --- focus ----------------------------------------------------------------------

def test_focus_holds_sessions_but_not_noticing_and_offers_what_waited(tmp_path):
    W.raise_focus("finishing the bridge", tmp_path, now=NOW)
    _news(tmp_path, "a3", "Modular synthesis workshop announced", at=NOW + timedelta(minutes=5))
    event, why = W.next_reactive(tmp_path, NOW + timedelta(minutes=10))
    assert event is None and why == "focus is up"
    assert len(W.recent(data_dir=tmp_path)) == 1, "events are still logged while focused"
    out = W.clear_focus(tmp_path, now=NOW + timedelta(hours=2))
    assert out["noticed_while_focused"] == ["news: Modular synthesis workshop announced"]
    event, _ = W.next_reactive(tmp_path, NOW + timedelta(hours=2))
    assert event["id"] == "news:a3", "after she clears it, what waited can start"


def test_nothing_clears_focus_but_her(tmp_path):
    W.raise_focus("a long one", tmp_path, now=NOW)
    much_later = NOW + timedelta(days=3)
    assert W.next_reactive(tmp_path, much_later) == (None, "focus is up")
    assert W.focus_state(tmp_path)["up"], "no timer lowers it"
    note = W.stale_focus_note(tmp_path, much_later)
    assert "72 hours" in note and "a long one" in note
    assert W.stale_focus_note(tmp_path, NOW + timedelta(hours=1)) == ""
    assert W.focus({"action": "clear"}, tmp_path)["focus"] == "cleared"
    assert W.stale_focus_note(tmp_path, much_later) == ""


def test_the_focus_tool_is_offered_only_with_the_lever(levers):
    assert W.focus_tools() == {}
    with levers(world_events=True):
        assert set(W.focus_tools()) == {"focus"}
    assert "raise, clear or view" in W.focus({"action": "snooze"})["error"]


# --- reactive guards ------------------------------------------------------------

def test_quiet_hours_hold_reactive_sessions(tmp_path):
    _news(tmp_path, "a3", "Modular synthesis workshop", at=NOW.replace(hour=23, minute=10))
    assert W.next_reactive(tmp_path, NOW.replace(hour=23, minute=30)) == (None, "quiet hours")
    assert W.next_reactive(tmp_path, NOW.replace(hour=23, minute=30) + timedelta(hours=8))[0]


def test_the_daily_cap(tmp_path):
    W.set_rules({"max_per_day": 1, "cooldown_minutes": 0}, tmp_path)
    _news(tmp_path, "a1", "Modular synthesis one")
    _news(tmp_path, "a2", "Modular synthesis two")
    e, _ = W.next_reactive(tmp_path, NOW)
    W.mark_started(e, tmp_path, NOW)
    W.mark_done(tmp_path)
    assert W.next_reactive(tmp_path, NOW + timedelta(minutes=5)) == (None, "today's cap is reached")
    assert W.next_reactive(tmp_path, NOW + timedelta(days=1, hours=-4))[0], "a new day"


def test_the_cooldown_is_per_source(tmp_path):
    _news(tmp_path, "a1", "Modular synthesis one")
    _news(tmp_path, "a2", "Modular synthesis two")
    W.record("babelr", "m1", "eris in #workshop: modular synthesis patch is done",
             {"message_id": "m1"}, data_dir=tmp_path, her_interests=TOPICS, now=NOW)
    e, _ = W.next_reactive(tmp_path, NOW)
    assert e["source"] == "babelr", "newest first"
    W.mark_started(e, tmp_path, NOW)
    W.mark_done(tmp_path)
    e2, _ = W.next_reactive(tmp_path, NOW + timedelta(minutes=10))
    assert e2["source"] == "news", "another source isn't cooling down"
    W.mark_started(e2, tmp_path, NOW + timedelta(minutes=10))
    W.mark_done(tmp_path)
    assert W.next_reactive(tmp_path, NOW + timedelta(minutes=20))[0] is None, "news is cooling down"
    assert W.next_reactive(tmp_path, NOW + timedelta(minutes=10 + 121))[0]["id"] == "news:a1"


def test_one_at_a_time_and_never_from_inside_one(tmp_path):
    _news(tmp_path, "a1", "Modular synthesis one")
    _news(tmp_path, "a2", "Modular synthesis two")
    W.set_rules({"cooldown_minutes": 0}, tmp_path)
    e, _ = W.next_reactive(tmp_path, NOW)
    W.mark_started(e, tmp_path, NOW)
    assert W.next_reactive(tmp_path, NOW + timedelta(minutes=1)) == (None, "a reactive session is running")
    W.mark_done(tmp_path)
    token = W.IN_REACTIVE.set(True)
    try:
        event, why = W.next_reactive(tmp_path, NOW + timedelta(minutes=2))
        assert event is None and "can't start another" in why
    finally:
        W.IN_REACTIVE.reset(token)


def test_local_defaults_are_looser_and_still_hers(tmp_path, monkeypatch):
    assert W.rules(tmp_path) == W.PAID_RULES
    assert W.estimated_cost() == W.REACTIVE_ESTIMATED_COST_USD
    import llm_config
    monkeypatch.setattr(llm_config, "local_model", lambda: "qwen3:14b")
    r = W.rules(tmp_path)
    assert r["max_per_day"] > W.PAID_RULES["max_per_day"]
    assert r["cooldown_minutes"] < W.PAID_RULES["cooldown_minutes"]
    assert W.estimated_cost() == 0.0, "a $0 local call never trips the dollar gate"
    W.set_rules({"max_per_day": 5}, tmp_path)
    assert W.rules(tmp_path)["max_per_day"] == 5


def test_reactive_spend_is_counted():
    from scheduler.budget import counts_toward_budget
    from agent_loop.session import SESSION_SITES
    assert counts_toward_budget(SESSION_SITES["reactive"])
    assert counts_toward_budget("session.generic")


def test_the_job_submits_through_the_budget_gate_only(tmp_path, levers, monkeypatch):
    from heartbeat import wiring
    _news(tmp_path, "a3", "Modular synthesis workshop")
    submitted = []
    monkeypatch.setattr(W, "PULL_SOURCES", {})
    monkeypatch.setattr(W, "datetime", _Frozen)
    monkeypatch.setattr(wiring, "submit", lambda name, run, **kw: submitted.append((name, kw)) or True)
    with levers(world_events=True):
        assert asyncio.run(W.check_world(tmp_path)) == 0, "reactive_sessions is off"
    with levers(world_events=True, reactive_sessions=True, agent_loop=True):
        assert asyncio.run(W.check_world(tmp_path)) == 1
    name, kw = submitted[0]
    from scheduler.budget import TaskCategory
    assert name == "world.reactive" and kw["budget_class"] == TaskCategory.TRIGGERED
    assert kw["estimated_cost_usd"] == W.REACTIVE_ESTIMATED_COST_USD
    assert W._state(tmp_path)["count"] == 1
    lines = (tmp_path / "world" / "reactive.jsonl").read_text().splitlines()
    assert json.loads(lines[0])["trigger"] == "event:news:a3"


def test_no_heartbeat_no_reactive_session(tmp_path, levers, monkeypatch):
    from heartbeat import wiring
    _news(tmp_path, "a3", "Modular synthesis workshop")
    monkeypatch.setattr(wiring, "submit", lambda *a, **k: False)
    monkeypatch.setattr(W, "PULL_SOURCES", {})
    monkeypatch.setattr(W, "datetime", _Frozen)
    with levers(world_events=True, reactive_sessions=True, agent_loop=True):
        assert asyncio.run(W.check_world(tmp_path)) == 0
    assert "count" not in W._state(tmp_path)


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


# --- triggers -------------------------------------------------------------------

def test_work_unit_trigger_is_schedule_or_goal():
    from scheduling.work_unit import WorkUnit
    u = WorkUnit.create("Reflect", "reflect")
    assert u.trigger == "schedule" and u.to_dict()["trigger"] == "schedule"
    u.plan_item = {"plan": "the-album", "plan_title": "The album", "item": "Bridge"}
    assert u.trigger == "goal:the-album"


def test_work_summaries_keep_their_trigger(test_db):
    from datetime import date
    from scheduling.work_summary_store import WorkSummary, WorkSummaryStore
    store = WorkSummaryStore("cass")
    store.save(WorkSummary(work_unit_id="u1", slug="work/x/1", name="Album", date=date(2026, 11, 24),
                           trigger="goal:the-album"))
    assert store.get_by_slug("work/x/1").trigger == "goal:the-album"
    from database import get_db
    with get_db() as conn:
        row = conn.execute("SELECT trigger FROM work_summaries WHERE slug = 'work/x/1'").fetchone()
    assert row[0] == "goal:the-album"


def test_migration_adds_the_trigger_column(tmp_path):
    import sqlite3
    from database.migrations import ensure_work_summaries_table
    conn = sqlite3.connect(tmp_path / "old.db")
    conn.execute("CREATE TABLE work_summaries (slug TEXT PRIMARY KEY, daemon_id TEXT NOT NULL, "
                 "work_unit_id TEXT NOT NULL, name TEXT NOT NULL, template_id TEXT, phase TEXT NOT NULL, "
                 "category TEXT NOT NULL, date TEXT NOT NULL, started_at TEXT, completed_at TEXT, "
                 "duration_minutes INTEGER DEFAULT 0, summary TEXT, data_json TEXT NOT NULL, "
                 "created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO work_summaries (slug, daemon_id, work_unit_id, name, phase, category, date, "
                 "data_json) VALUES ('s', 'cass', 'u', 'n', 'morning', 'reflection', '2026-11-01', '{}')")
    ensure_work_summaries_table(conn)
    ensure_work_summaries_table(conn)   # idempotent
    assert conn.execute("SELECT trigger FROM work_summaries").fetchone()[0] == "schedule"


def test_a_session_records_its_trigger(tmp_path, fake_llm):
    pytest.importorskip("anthropic")
    pytest.importorskip("networkx")
    from agent_loop.session import SESSION_TRIGGER, run_session_turn
    from session import GenericSessionRunner
    runner = GenericSessionRunner(data_dir=tmp_path, model="claude-haiku-4-5-20251001")
    catalog = {}

    def run(**kw):
        fake_llm.queue_tool_use("session_complete", {"summary": "Let it go by."})
        return asyncio.run(run_session_turn(runner, max_turns=3, catalog=catalog,
                                            run_router=lambda *a, **k: None, **kw))

    assert run(session_type="reflection").trigger == "schedule"
    assert run(session_type="reactive", trigger_source="event",
               session_trigger="event:news:a3").trigger == "event:news:a3"
    token = SESSION_TRIGGER.set("goal:the-album")
    try:
        assert run(session_type="reflection").trigger == "goal:the-album"
    finally:
        SESSION_TRIGGER.reset(token)
    logs = [json.loads(p.read_text()) for p in sorted((tmp_path).rglob("*.json"))
            if "session_id" in p.read_text()]
    assert {"schedule", "event:news:a3", "goal:the-album"} <= {l.get("trigger") for l in logs}
