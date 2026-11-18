"""start_session (Kohl, 2026-11-18): from a conversation she starts one of her sessions
now, as a wake due now: one at a time, a few a day, carrying where it came from."""
import asyncio
from datetime import datetime

from agent_loop import wakes as WK


def test_start_now_one_at_a_time_and_capped(tmp_path):
    book = WK.WakeBook(tmp_path / "wakes.json")
    now = datetime(2026, 11, 18, 9, 0)
    origin = WK.origin_of("babelr_dm", "a DM on Chapter House (Babelr)",
                          {"user_name": "Kohl", "user_id": "u1", "conversation_id": "c1", "partner": "kohl"})
    out = book.start_now({"activity": "listening", "why": "I want to hear One-X through", "focus": "One-X",
                          "minutes": 45}, "chat-1", ["listening", "workshop"], now=now, origin=origin)
    assert out["started"] == "listening" and out["minutes"] == 45
    w = book.pending()[0]
    assert w["at"] == now.isoformat(timespec="seconds") and w["origin"]["partner"] == "kohl"
    again = book.start_now({"activity": "workshop", "why": "x"}, "chat-2", ["listening", "workshop"], now=now)
    assert "one at a time" in again["error"]
    assert "activity must be" in book.start_now({"activity": "nope", "why": "x"}, "c", ["listening"], now=now)["error"]
    for i in range(WK.STARTS_PER_DAY):   # finish each so the next can start
        for x in book.pending():
            book.finish(x["id"], WK.DONE)
        r = book.start_now({"activity": "workshop", "why": f"go {i}"}, "c", ["workshop"], now=now)
    assert r.get("started")                       # the 6th counted start (the listening one didn't count)
    for x in book.pending():
        book.finish(x["id"], WK.DONE)
    r = book.start_now({"activity": "workshop", "why": "one more"}, "c", ["workshop"], now=now)
    assert "error" in r and "today" in r["error"]


def test_a_started_session_runs_with_its_focus_length_and_origin(tmp_path, monkeypatch):
    book = WK.WakeBook(tmp_path / "wakes.json")
    book.start_now({"activity": "listening", "why": "One-X", "focus": "One-X", "minutes": 20}, "chat-1",
                   ["listening"], origin={"channel": "babelr_dm", "who": "Kohl"})
    w = book.take_due()[0]
    seen = {}

    class Reg:
        async def execute(self, action, **kw):
            seen.update(kw, action=action)
            return type("R", (), {"success": True, "message": "ok"})()

    import scheduler.actions as acts
    monkeypatch.setattr(acts, "get_action_registry", lambda: Reg())
    asyncio.run(WK.run_wake(w, book))
    assert seen["action"] == "session.listening" and seen["focus"] == "One-X" and seen["duration_minutes"] == 20
    assert seen["reply_to"]["who"] == "Kohl" and seen["trigger_source"] == "conversation"
    assert seen["why"].startswith("I started this from a conversation")


def test_offered_in_chat_only_with_its_lever_and_available_kinds(monkeypatch, levers):
    monkeypatch.setattr(WK, "wakes_available", lambda: True)
    monkeypatch.setattr(WK, "startable", lambda: ["listening", "workshop"])
    with levers(agent_loop=True, start_sessions=False):
        assert WK.start_session_offer("chat-1") is None
    with levers(agent_loop=True, start_sessions=True):
        d, handler = WK.start_session_offer("chat-1")
        assert d["name"] == "start_session" and d["input_schema"]["properties"]["activity"]["enum"] == ["listening", "workshop"]


def test_handlers_pass_reply_to_into_the_session(monkeypatch):
    """A conversation-started session knows where to reply (cass-vessel-68's reply_back)."""
    import asyncio
    from scheduler.actions import session_handlers as SH
    seen = {}

    async def fake_turn(runner, **kw):
        seen.update(kw)
        return type("R", (), {"status": "completed", "error": None, "estimated_cost_usd": 0.0,
                              "session_id": "s", "summary": "ok"})()

    import listening_turn
    monkeypatch.setattr(listening_turn, "run_listening_turn", fake_turn)
    monkeypatch.setattr(SH, "is_enabled", lambda name: True)
    runner = type("Runner", (), {"set_managers": lambda self, m: None,
                                 "register_tool_handlers": lambda self, h: None})()
    ctx = {"managers": {"session_runner": runner}, "focus": "One-X", "why": "w", "trigger_source": "conversation",
           "reply_to": {"channel": "babelr_dm", "who": "Kohl"}}
    out = asyncio.run(SH.listening_action(ctx))
    assert out.success and seen["reply_to"] == {"channel": "babelr_dm", "who": "Kohl"} and seen["focus"] == "One-X"


def test_listening_does_not_count_toward_the_day(tmp_path):
    book = WK.WakeBook(tmp_path / "wakes.json")
    now = datetime(2026, 11, 18, 9, 0)
    for i in range(WK.STARTS_PER_DAY):
        book.start_now({"activity": "workshop", "why": f"w{i}"}, "c", ["workshop", "listening"], now=now)
        for x in book.pending():
            book.finish(x["id"], WK.DONE)
    assert "today" in book.start_now({"activity": "workshop", "why": "one more"}, "c",
                                     ["workshop", "listening"], now=now)["error"]
    ok = book.start_now({"activity": "listening", "why": "One-X"}, "c", ["workshop", "listening"], now=now)
    assert ok["started"] == "listening" and "doesn't count" in ok["note"]


def test_a_refused_or_hung_wake_stops_blocking_new_starts(tmp_path):
    from datetime import timedelta
    book = WK.WakeBook(tmp_path / "wakes.json")
    t0 = datetime(2026, 11, 18, 9, 34)
    book.start_now({"activity": "listening", "why": "Hybrid Theory"}, "c", ["listening", "workshop"], now=t0)
    [w] = book.take_due(t0)            # handed to Heartbeat, which then refuses it: run_wake never runs
    soon = book.start_now({"activity": "workshop", "why": "x"}, "c", ["workshop"], now=t0 + timedelta(minutes=2))
    assert "one at a time" in soon["error"]
    later = book.start_now({"activity": "workshop", "why": "x"}, "c", ["workshop"], now=t0 + timedelta(minutes=6))
    assert later.get("started") == "workshop"
    old = next(x for x in book.all() if x["id"] == w["id"])
    assert old["status"] == WK.FAILED and "never started" in old["result"]
    # one that really ran and never finished closes after its minutes plus the margin
    [w2] = book.take_due(t0 + timedelta(minutes=6))
    book.mark_running(w2["id"])
    assert book.settle(datetime.now() + timedelta(minutes=10)) == 0
    assert book.settle(datetime.now() + timedelta(minutes=30 + 31)) == 1


def test_her_chat_sees_what_her_sessions_actually_did(tmp_path):
    from datetime import timedelta
    book = WK.WakeBook(tmp_path / "wakes.json")
    t0 = datetime(2026, 11, 18, 11, 40)
    book.start_now({"activity": "workshop", "why": "a song", "focus": "my-tone", "minutes": 60}, "c",
                   ["workshop"], now=t0)
    assert "about to start" in WK.sessions_block(book, now=t0)
    [w] = book.take_due(t0)
    book.mark_running(w["id"])
    assert "running since" in WK.sessions_block(book, now=t0 + timedelta(minutes=1))
    book.finish(w["id"], WK.DONE, "Workshop session complete", ended="max_turns")
    text = WK.sessions_block(book, now=datetime.now())
    assert "reached its step cap" in text and "of 60 min" in text
    assert "saying I'll start one doesn't" in text


def test_start_session_keeps_her_done_when(tmp_path):
    book = WK.WakeBook(tmp_path / "wakes.json")
    book.start_now({"activity": "workshop", "why": "a song", "done_when": "one full draft, ready to show"},
                   "c", ["workshop"], now=datetime(2026, 11, 18, 12, 0))
    assert book.pending()[0]["done_when"] == "one full draft, ready to show"
