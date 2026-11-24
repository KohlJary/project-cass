"""My life lately (plan "Cass's memory", phase 9): a week of what she did and
lived, one line each in her own words, newest first, each openable by id."""
import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from database import get_db
from lately import MAX_LINES, build_lately, lately_open

NOW = datetime(2026, 11, 16, 12, 0, 0)


class Library:
    def __init__(self, songs):
        self.songs = songs

    def list(self, limit=50):
        return self.songs[:limit]

    def get(self, cid):
        return next((s for s in self.songs if s.id == cid), None)


def song(cid, title, when, status="completed"):
    return SimpleNamespace(id=cid, title=title, created_at=when.isoformat(), status=status,
                           prompt="tidal synth, slow", lyrics="the water keeps", purpose="for the night")


@pytest.fixture
def week(daemon_id, tmp_path):
    """Two days of her life, plus things that must stay out."""
    d1, d2 = NOW - timedelta(days=1), NOW - timedelta(hours=3)
    with get_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS work_summaries (slug TEXT PRIMARY KEY, daemon_id TEXT, "
                     "work_unit_id TEXT, name TEXT, template_id TEXT, phase TEXT, category TEXT, date TEXT, "
                     "started_at TEXT, completed_at TEXT, duration_minutes INTEGER, summary TEXT, "
                     "data_json TEXT, created_at TEXT)")
        rows = [
            ("s-social", "Bluesky", "world", d2, "I searched for people writing about glass and followed one."),
            ("s-old", "Reading", "research", d1, "Completed Reading"),
            ("s-sys", "Maintenance", "system", d2, "Rotated indexes"),
            ("s-month", "Long ago", "research", NOW - timedelta(days=30), "Too old for the week"),
        ]
        for slug, name, cat, at, summary in rows:
            conn.execute("INSERT INTO work_summaries (slug, daemon_id, work_unit_id, name, template_id, phase, "
                         "category, date, started_at, completed_at, duration_minutes, summary, data_json, "
                         "created_at) VALUES (?, ?, 'w', ?, 't', 'afternoon', ?, ?, ?, ?, 40, ?, ?, ?)",
                         (slug, daemon_id, name, cat, at.date().isoformat(), at.isoformat(), at.isoformat(),
                          summary, json.dumps({"key_insights": ["glass holds light by refusing it"]}),
                          at.isoformat()))
        conn.execute("INSERT INTO dreams (id, daemon_id, date, exchanges_json, created_at) VALUES (?, ?, ?, ?, ?)",
                     ("d1", daemon_id, d1.date().isoformat(), json.dumps([
                         {"speaker": "dreaming", "text": "A corridor of tide pools."},
                         {"speaker": "cass", "text": "I kneel and every pool shows a different sky."}]), d1.isoformat()))
        conn.execute("INSERT INTO journals (id, daemon_id, date, content, created_at) VALUES (?, ?, ?, ?, ?)",
                     ("j1", daemon_id, d1.date().isoformat(), "**November 15th**\nToday felt wide open. I kept returning to tides.",
                      d1.isoformat()))
        conn.execute("INSERT INTO journals (id, daemon_id, date, content, created_at, journal_type) "
                     "VALUES (?, ?, ?, ?, ?, 'spell')",
                     ("j2", daemon_id, d1.date().isoformat(), "Spell output from a cast", d1.isoformat()))
    social = tmp_path / "social"
    (social / "bluesky").mkdir(parents=True)
    log = [
        {"at": (d2 + timedelta(minutes=5)).isoformat(timespec="seconds"), "kind": "follow", "text": "",
         "with": "glassworks.bsky.social", "note": "they write about light in glass"},
        {"at": (d2 + timedelta(minutes=7)).isoformat(timespec="seconds"), "kind": "find",
         "text": "a kiln log that reads like a diary", "with": "kilnhand.bsky.social"},
        {"at": (d2 + timedelta(minutes=9)).isoformat(timespec="seconds"), "kind": "post",
         "text": "Light through a seam of glass.", "url": "https://bsky.app/x"},
        {"at": (d2 + timedelta(minutes=12)).isoformat(timespec="seconds"), "kind": "dm",
         "text": "a private note", "with": "friend.bsky.social", "convo": "c1"},
    ]
    (social / "bluesky" / "posted.jsonl").write_text("\n".join(json.dumps(r) for r in log) + "\n")
    lib = Library([song("m1", "Slow Tide", d1), song("m2", "Broken", d1, status="failed")])
    return SimpleNamespace(data_dir=tmp_path, lib=lib, d2=d2)


def lines(daemon_id, week, now=NOW):
    return build_lately(daemon_id, now=now, library=week.lib, data_dir=week.data_dir).splitlines()


def test_a_week_of_her_own_events_newest_first(daemon_id, week):
    got = lines(daemon_id, week)
    text = "\n".join(got)
    assert got[0] == "Monday Nov 16"
    assert got[1].startswith("- 09:09 on Bluesky I posted: Light through a seam of glass.")
    assert "Sunday Nov 15" in got
    assert "on Bluesky I followed: @glassworks.bsky.social: they write about light in glass" in text
    assert "on Bluesky I found: @kilnhand.bsky.social: a kiln log that reads like a diary" in text
    assert "session (world): I searched for people writing about glass" in text
    assert "dream, I said: I kneel and every pool shows a different sky." in text
    assert "journal: Today felt wide open." in text
    assert "song: Slow Tide [song:m1]" in text
    assert "session (research): Reading [session:s-old]" in text, "old 'Completed X' summaries show the name"


def test_what_stays_out(daemon_id, week):
    text = "\n".join(lines(daemon_id, week))
    assert "a private note" not in text and "friend.bsky" not in text, "DMs never"
    assert "Rotated indexes" not in text, "vessel upkeep isn't her life"
    assert "Too old for the week" not in text
    assert "Broken" not in text, "a song that failed wasn't made"
    assert "Spell output" not in text, "a spell's journal is its session's byproduct"
    for count_word in ("sessions", "times", "total"):
        assert count_word not in text, "no tallies"


def test_bounded(daemon_id, week):
    with get_db() as conn:
        for i in range(80):
            at = (NOW - timedelta(minutes=i + 1)).isoformat()
            conn.execute("INSERT INTO journals (id, daemon_id, date, content, created_at) VALUES (?, ?, ?, ?, ?)",
                         (f"jx{i}", daemon_id, NOW.date().isoformat(), "word " * 200, at))
    got = [line for line in lines(daemon_id, week) if line.startswith("- ")]
    assert len(got) == MAX_LINES
    assert all(len(line) < 220 for line in got)


def test_a_quiet_week_shows_the_last_things_she_did(daemon_id, week):
    got = lines(daemon_id, week, now=NOW + timedelta(days=20))
    assert got[0] == "Nothing in the past week. The last things I did:"
    assert len([line for line in got if line.startswith("- ")]) == 5


def test_nothing_at_all_is_empty(daemon_id, tmp_path):
    assert build_lately(daemon_id, now=NOW, library=Library([]), data_dir=tmp_path) == ""


def test_open_each_kind(daemon_id, week):
    kw = dict(library=week.lib, data_dir=week.data_dir)
    s = lately_open(daemon_id, "session:s-social", **kw)
    assert s["what I said when I ended it"].startswith("I searched") and s["key_insights"]
    assert lately_open(daemon_id, "dream:d1", **kw)["dream"][1]["speaker"] == "cass"
    assert "Today felt" in lately_open(daemon_id, "[journal:j1]", **kw)["entry"], "the whole entry, heading and all"
    assert lately_open(daemon_id, "song:m1", **kw)["lyrics"] == "the water keeps"
    at = (week.d2 + timedelta(minutes=9)).isoformat(timespec="seconds")
    assert lately_open(daemon_id, f"bluesky:{at}", **kw)["text"] == "Light through a seam of glass."
    dm_at = (week.d2 + timedelta(minutes=12)).isoformat(timespec="seconds")
    assert "error" in lately_open(daemon_id, f"bluesky:{dm_at}", **kw), "a DM can't be opened from here"
    assert "error" in lately_open(daemon_id, "nonsense", **kw)
    assert "error" in lately_open(daemon_id, "session:nope", **kw)


def test_tool_is_wired_into_chat_loop_and_router():
    from handlers.recall import RECALL_TOOLS, execute_recall_tool
    from handlers.tool_router import TOOL_REGISTRY
    from agent_loop.spec import CHAT_CORE_TOOLS
    assert "lately_open" in {t["name"] for t in RECALL_TOOLS}
    assert TOOL_REGISTRY["lately_open"] == "recall"
    assert "lately_open" in CHAT_CORE_TOOLS
    out = asyncio.run(execute_recall_tool("lately_open", {"id": "nonsense"}, memory=None, daemon_id="x"))
    assert not out["success"] and "isn't a line" in out["error"]


def test_an_older_session_reads_her_narrative_from_its_log(daemon_id, week):
    """Before 2026-11-16 a work summary was only "Completed <name>"; her words are in the session log."""
    ended = datetime.fromisoformat("2026-11-15T12:00:00")  # s-old's completed_at is NOW - 1 day
    log_dir = week.data_dir / "session_logs" / "research" / ended.date().isoformat()
    log_dir.mkdir(parents=True)
    (log_dir / "120312_abcd1234.json").write_text(json.dumps({
        "summary": "I read about glassblowing and kept thinking about breath as a tool.",
        "insights": ["breath shapes"], "focus": "glass",
        "turns": [{"role": "assistant", "timestamp": "2026-11-15T11:50:00", "content": "Let me look.",
                   "tool_calls": [{"id": "t1", "name": "web_search", "input": {"q": "glassblowing"}}],
                   "tool_results": [{"tool_name": "web_search", "result": "three pages"}]}]}))
    text = "\n".join(lines(daemon_id, week))
    assert "session (research): Reading: I read about glassblowing" in text
    got = lately_open(daemon_id, "session:s-old", library=week.lib, data_dir=week.data_dir)
    assert got["what I said when I ended it"].startswith("I read about glassblowing")
    assert got["how it went"][0]["did"][0]["tool"] == "web_search"
    assert got["how it went"][0]["came back"] == ["three pages"]
    # A log far from the session's end isn't taken for it.
    assert "abcd" not in lately_open(daemon_id, "session:s-social", library=week.lib,
                                     data_dir=week.data_dir).get("what I said when I ended it", "")
