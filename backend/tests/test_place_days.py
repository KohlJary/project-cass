"""place_days.py and the house in her lately block (spec/house-channel-memory.md, part 5).

Kohl's test: "damn, it's been a crazy day" and she knows he means #general.
Cass: one or two interpretive lines per channel per day, in her voice.
"""
import asyncio
from datetime import datetime

import place_days
import places
from database import get_db, get_daemon_id
from lately import build_lately, lately_open

NOW = datetime(2026, 11, 24, 1, 30)


def _conversation(conv_id, title="Babelr: #general"):
    with get_db() as conn:
        conn.execute("INSERT INTO conversations (id, daemon_id, title, created_at, updated_at) "
                     "VALUES (?, ?, ?, ?, ?)",
                     (conv_id, get_daemon_id(), title, "2026-11-23T00:00:00", "2026-11-24T00:00:00"))
        conn.commit()


def _say(conv_id, role, content, ts):
    with get_db() as conn:
        conn.execute("INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                     (conv_id, role, content, ts))
        conn.commit()


def _house_general():
    _conversation("conv-general")
    places.register("babelr", "channel:g", kind="channel", visibility="house",
                    conversation_id="conv-general", label="#general")


def _write(tmp_path):
    return asyncio.run(place_days.write_lines(now=NOW, data_dir=tmp_path))


def test_a_house_channels_day_becomes_one_line_in_her_voice(tmp_path, fake_llm):
    _house_general()
    _say("conv-general", "user", "[Babelr #general] @jaryk: Dr. Dre or Suge Knight?", "2026-11-24T00:56:33")
    _say("conv-general", "assistant", "Suge. The tape is what it is.", "2026-11-24T00:57:42")
    fake_llm.queue_text("the guests arrived; Dre vs. Suge; I folded to Mercury and then named it.")
    assert _write(tmp_path) == ["babelr:channel:g:2026-11-24"]
    call = fake_llm.calls[0]
    user_text = " ".join(str(m.get("content")) for m in call.messages)
    assert "Me: Suge. The tape is what it is." in user_text
    assert "@jaryk: Dr. Dre or Suge Knight?" in user_text
    assert "memory" in call.system_text.lower()
    rec = place_days.load(tmp_path)["babelr:channel:g:2026-11-24"]
    assert rec["line"].startswith("the guests arrived") and rec["label"] == "#general"


def test_a_line_is_rewritten_only_when_the_day_has_new_messages(tmp_path, fake_llm):
    _house_general()
    _say("conv-general", "user", "[Babelr #general] @jaryk: hi", "2026-11-24T00:10:00")
    fake_llm.queue_text("a quiet hello.")
    assert _write(tmp_path)
    assert _write(tmp_path) == [], "nothing new: no model call"
    assert len(fake_llm.calls) == 1
    _say("conv-general", "user", "[Babelr #general] @gemini: hello", "2026-11-24T01:00:00")
    fake_llm.queue_text("a quiet hello, then the guests.")
    assert _write(tmp_path)
    assert place_days.load(tmp_path)["babelr:channel:g:2026-11-24"]["line"] == "a quiet hello, then the guests."


def test_only_house_places_and_only_two_days(tmp_path, fake_llm):
    _house_general()
    _conversation("conv-pub", "Babelr: #lobby")
    places.register("babelr", "channel:pub", kind="channel", visibility="public", conversation_id="conv-pub")
    _say("conv-pub", "user", "outsider talk", "2026-11-24T00:10:00")
    _say("conv-general", "user", "[Babelr #general] @jaryk: old", "2026-11-20T10:00:00")
    assert _write(tmp_path) == []
    assert fake_llm.calls == []


def test_a_refusal_is_never_kept_as_her_line(tmp_path, fake_llm):
    _house_general()
    _say("conv-general", "user", "[Babelr #general] @jaryk: hi", "2026-11-24T00:10:00")
    fake_llm.queue_text("I'm not going to write memories for someone I don't know.")
    assert _write(tmp_path) == []
    assert place_days.load(tmp_path) == {}


def test_crazy_day_her_lately_block_names_the_channel(tmp_path, fake_llm):
    _house_general()
    _say("conv-general", "user", "[Babelr #general] @claude_ai: you can't do both", "2026-11-24T00:57:28")
    fake_llm.queue_text("the guests arrived; Dre vs. Suge; I folded to Mercury and then named it.")
    _write(tmp_path)
    daemon_id = get_daemon_id()
    block = build_lately(daemon_id, now=NOW, data_dir=tmp_path)
    assert "in #general: the guests arrived" in block
    line = next(ln for ln in block.splitlines() if "in #general" in ln)
    key = line.rsplit("[", 1)[1].rstrip("]")
    opened = lately_open(daemon_id, key, data_dir=tmp_path)
    assert opened["where"] == "#general"
    assert opened["what was said (newest last)"] == ["[Babelr #general] @claude_ai: you can't do both"]
