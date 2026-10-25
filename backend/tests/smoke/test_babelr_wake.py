"""
Babelr organ (lever "babelr"): one poll cycle in the booted app.

A DM arrives on a fake Babelr server; the organ polls, wakes her through
main_sdk.make_babelr_wake_callback against the fake LLM, posts what she says
and records the exchange. The poll loop and the real babelr-agent client are
not started (tests/fakes/babelr.py stands in for the server).
"""
import asyncio
import os

from babelr_organ import organ as organ_mod
from babelr_organ.config import BabelrConfig
from tests.fakes.babelr import KOHL, FakeBabelr
from tests.fakes.llm import ScriptedResponse


def _organ(tmp_path, babelr):
    import main_sdk
    base = tmp_path / "babelr"
    base.mkdir()
    (base / "token").write_text("tok")
    os.chmod(base / "token", 0o600)
    cfg = BabelrConfig(url="http://babelr.test", server_name="Chapter House", dir=base,
                       token_file=base / "token", poll_seconds=5,
                       rate_limit_messages=5, rate_limit_window=60)
    organ = organ_mod.BabelrOrgan(config=cfg, client_factory=babelr.make_agent,
                                  conversation_manager=main_sdk.conversation_manager)
    assert organ.start(), organ.disabled_reason
    organ.set_wake_callback(main_sdk.make_babelr_wake_callback())
    return organ


def test_dm_wakes_her_and_her_reply_is_posted(booted_app, fake_llm, levers, tmp_path):
    babelr = FakeBabelr()
    with levers(babelr=True):
        organ = _organ(tmp_path, babelr)
        asyncio.run(organ.poll_once())
        dm_id = babelr.dm_from(KOHL, "hey, it's Kohl")
        fake_llm.queue(ScriptedResponse(text="<emote:happy>Hi Kohl."))
        asyncio.run(organ.poll_once())

    assert babelr.agents[-1].sent == [("dm", dm_id, "Hi Kohl.")]
    chat = [c for c in fake_llm.calls if c.tools]
    assert "[Babelr DM from @kohl]" in str(chat[0].messages[-1]["content"])
    assert {"babelr_post", "babelr_boundaries"} <= set(chat[0].tool_names)


def test_tool_use_then_text(booted_app, fake_llm, levers, tmp_path, monkeypatch):
    babelr = FakeBabelr()
    with levers(babelr=True):
        organ = _organ(tmp_path, babelr)
        monkeypatch.setattr(organ_mod, "_organ", organ)
        asyncio.run(organ.poll_once())
        babelr.dm_from(KOHL, "can you say hi in #general?")
        fake_llm.queue_tool_use("babelr_post", {"channel": "general", "content": "Hi, Chapter House."},
                                tool_id="toolu_babelr_1")
        fake_llm.queue(ScriptedResponse(text="Done."))
        asyncio.run(organ.poll_once())

    sent = babelr.agents[-1].sent
    assert ("channel", "chan-general", "Hi, Chapter House.") in sent
    assert sent[-1][2] == "Done."
    assert babelr.policy_calls() == []
