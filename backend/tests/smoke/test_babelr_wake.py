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
from tests.smoke.conftest import create_user


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


def test_a_linked_dm_is_their_chat_with_her(booted_app, fake_llm, levers, tmp_path):
    """Kohl's DM runs the shared chat turn in Kohl's continuous conversation,
    the same one the admin frontend uses, and the organ doesn't record it twice."""
    import main_sdk
    kohl_user = create_user("Kohl")
    babelr = FakeBabelr()
    with levers(babelr=True):
        organ = _organ(tmp_path, babelr)
        (organ.config.dir / "links.json").write_text(f'{{"kohl": "{kohl_user}"}}')
        asyncio.run(organ.poll_once())
        dm_id = babelr.dm_from(KOHL, "morning, it's me")
        fake_llm.queue(ScriptedResponse(text="<emote:happy>Morning."))
        asyncio.run(organ.poll_once())

    assert babelr.agents[-1].sent == [("dm", dm_id, "Morning.")]
    conv = main_sdk.conversation_manager.get_or_create_continuous(kohl_user)
    stored = [(m.role, m.content) for m in main_sdk.conversation_manager.load_conversation(conv.id).messages]
    assert stored[0] == ("user", "[Via: Babelr DM]\nmorning, it's me")
    assert stored[1][0] == "assistant" and "Morning." in stored[1][1]
    assert len(stored) == 2  # not also written by the organ
    titles = [c["title"] for c in main_sdk.conversation_manager.list_conversations(user_id=kohl_user)]
    assert not any(str(t).startswith("Babelr:") for t in titles)
    chat = [c for c in fake_llm.calls if c.tools]
    assert "## BABELR" in str(chat[0].system) and "same conversation" in str(chat[0].system)
    msg_id = babelr.dm_messages[dm_id][0]["id"]
    assert babelr.statuses[msg_id]["state"] == "done"


def test_a_channel_mention_runs_in_the_channels_conversation(booted_app, fake_llm, levers, tmp_path):
    """A channel turn carries the channel's own history and, for a linked
    person, their private context; the exchange is stored once, by the turn."""
    import main_sdk
    kohl_user = create_user("Kohl")
    babelr = FakeBabelr()
    with levers(babelr=True):
        organ = _organ(tmp_path, babelr)
        (organ.config.dir / "links.json").write_text(f'{{"kohl": "{kohl_user}"}}')
        asyncio.run(organ.poll_once())
        babelr.say("general", KOHL, "@cass first thing")
        fake_llm.queue(ScriptedResponse(text="First answer."))
        asyncio.run(organ.poll_once())
        babelr.say("general", KOHL, "@cass second thing")
        fake_llm.queue(ScriptedResponse(text="Second answer."))
        asyncio.run(organ.poll_once())

    conv_id = organ.state.conversation_for("channel:chan-general")
    stored = [(m.role, m.content) for m in main_sdk.conversation_manager.load_conversation(conv_id).messages]
    assert stored[0] == ("user", "[Babelr #general] @kohl: @cass first thing")
    assert [r for r, _ in stored] == ["user", "assistant", "user", "assistant"]  # not twice
    chat = [c for c in fake_llm.calls if c.tools]
    second = chat[-1]
    assert "First answer." in str(second.messages)  # her history in the channel


def test_her_thinking_never_reaches_babelr_and_a_thinking_only_reply_is_retried(
        booted_app, fake_llm, levers, tmp_path):
    """Her <gesture:think> blocks stay hers. A reply that is only thinking (or an
    unclosed block) gets one retry, visible in her own history; the channel gets
    only the final reply (Kohl, via RoboKohl, 2026-10-28)."""
    import main_sdk
    kohl_user = create_user("Kohl")
    babelr = FakeBabelr()
    replies = []  # her chat turns only (they carry tools); background calls get the default
    fake_llm.responder = lambda source, kw: ScriptedResponse(text=replies.pop(0)) if kw.get("tools") and replies else None
    with levers(babelr=True):
        organ = _organ(tmp_path, babelr)
        (organ.config.dir / "links.json").write_text(f'{{"kohl": "{kohl_user}"}}')
        asyncio.run(organ.poll_once())
        babelr.say("general", KOHL, "@cass one")
        replies[:] = ["<gesture:think>private weighing</gesture:think>\n\nThe answer."]
        asyncio.run(organ.poll_once())
        babelr.say("general", KOHL, "@cass two")
        replies[:] = ["<gesture:think>only weighing, never closed", "Second answer, on the retry."]
        asyncio.run(organ.poll_once())
        babelr.say("general", KOHL, "@cass three")
        replies[:] = ["<gesture:think>still only weighing", "<think>and again</think>"]
        asyncio.run(organ.poll_once())

    sent = [text for kind, _, text in babelr.agents[-1].sent if kind == "channel"]
    assert sent == ["The answer.", "Second answer, on the retry."]  # three: nothing posted
    assert not any("weighing" in t for t in sent)
    conv_id = organ.state.conversation_for("channel:chan-general")
    stored = [m.content for m in main_sdk.conversation_manager.load_conversation(conv_id).messages]
    assert main_sdk.BABELR_RETRY_NUDGE in stored  # the retry is in her history


def test_babelr_final():
    import main_sdk
    f = main_sdk._babelr_final
    assert f("<gesture:think:0.5>hm</gesture:think>Hi.") == "Hi."
    assert f("weighing it all </think>\n\nHi.") == "Hi."  # a stray close: before it was thinking
    assert f("<gesture:think>open") is None
    assert f("PASS") is None and f("") is None
    assert f("<emote:happy>Plain reply.") == "Plain reply."
