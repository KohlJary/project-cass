"""Holding a reply, or not giving one (C8): plan "Cass's agent loop", phase 7.
Her default lines live in her data, not here; these tests use stand-ins."""
from datetime import datetime

from agent_loop.container import Arrival, render
import json

from agent_loop.hold import NO_LINE, HeldBook, check, hold, line_for, load_lines

NOW = datetime(2026, 11, 16, 9, 0)
KOHL = {"user_id": "u-kohl", "user_name": "Kohl"}
LINES = {"hold": "HOLD.", "hold_back": "HOLD. Back in {time}.", "no_reply": "NO REPLY."}


class Wakes:
    def __init__(self):
        self.asked = []

    def request(self, tool_input, session_id, activities, now=None):
        self.asked.append(tool_input)
        return "ok"


def test_her_saved_lines_are_the_defaults_and_hers_win(tmp_path):
    path = tmp_path / "hold_lines.json"
    path.write_text(json.dumps(LINES))
    lines = load_lines(path)
    assert lines == LINES
    assert line_for({}, lines) == "HOLD."
    assert line_for({"back_in_minutes": 60}, lines) == "HOLD. Back in an hour."
    assert line_for({"back_in_minutes": 180}, lines) == "HOLD. Back in 3 hours."
    assert line_for({"no_reply": True}, lines) == "NO REPLY."
    assert line_for({"line": "my own words", "no_reply": True}, lines) == "my own words"


def test_without_saved_lines_she_writes_it(tmp_path):
    assert load_lines(tmp_path / "missing.json") == {}
    assert line_for({}, {}) is None
    assert check({"no_reply": True}, {}) == {"error": NO_LINE}
    assert check({"line": "later"}, {}) == {"holding": True, "they_see": "later"}


def test_a_hold_with_a_time_is_kept_and_wakes_her(tmp_path):
    book, wakes = HeldBook(tmp_path / "held.json"), Wakes()
    out = hold({"back_in_minutes": 60}, person=KOHL, channel="websocket",
               message="what do you make of the dream?", book=book, wakes=wakes, now=NOW, lines=LINES)
    assert out["line"] == "HOLD. Back in an hour." and out["held"]
    [item] = book.holding("u-kohl")
    assert item["back_at"] == "2026-11-16T10:00:00" and item["message"].startswith("what do you make")
    assert wakes.asked[0]["in_minutes"] == 60 and "Kohl" in wakes.asked[0]["why"]
    assert "What I'm holding" in book.section() and "Kohl" in book.section()


def test_not_replying_keeps_nothing(tmp_path):
    book, wakes = HeldBook(tmp_path / "held.json"), Wakes()
    out = hold({"no_reply": True}, person=KOHL, channel="websocket", message="goodnight",
               book=book, wakes=wakes, now=NOW, lines=LINES)
    assert out == {"line": "NO REPLY.", "held": False, "wake": None}
    assert book.holding() == [] and wakes.asked == []


def test_her_next_reply_lets_it_go(tmp_path):
    book = HeldBook(tmp_path / "held.json")
    hold({}, person=KOHL, channel="websocket", message="a", book=book, wakes=Wakes(), now=NOW)
    hold({}, person={"user_id": "u-ann", "user_name": "Ann"}, channel="relay", message="b",
         book=book, wakes=Wakes(), now=NOW)
    assert book.let_go("u-kohl") == 1
    assert [i["who"] for i in book.holding()] == ["Ann"]


def test_who_is_here_says_what_she_is_holding():
    text = render(Arrival(who="Kohl", channel="websocket", message="still there?",
                          holding=(("2026-11-16T09:00:00", "what do you make of the dream?"),)), NOW)
    assert "I'm holding something of theirs from 2026-11-16 09:00" in text
