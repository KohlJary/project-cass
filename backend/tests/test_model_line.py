"""Which model she's running on, in every chat and session turn (model_line.py, 2026-11-25).

Both daemons: "I can't tell from in here which model I'm running on." Cass's
Babelr turns go make_babelr_wake_callback -> run_chat_turn -> run_conversation
(the loop), which had no CURRENT MODEL section. No API call is made here.
"""
import asyncio
import json
import time
from types import SimpleNamespace

import llm_caller
from memory import provenance as pv
from model_line import model_line


def test_llm_caller_keeps_the_model_the_api_said_answered():
    raw = SimpleNamespace(model="claude-haiku-5-5-20261001")
    resp = llm_caller.LLMResponse(content="hi", provider="anthropic", model_id="claude-haiku-5-5", raw=raw)
    llm_caller._record_response("chat", resp, time.time(), {})
    last = pv.last_answered(("chat",))
    assert last["model"] == "claude-haiku-5-5-20261001" and last["provider"] == "anthropic"
    # Ollama's JSON names its model too
    llm_caller._record_response("session.generic", llm_caller.LLMResponse(
        content="x", provider="ollama", model_id="qwen3:14b", raw={"model": "qwen3:14b-q4"}), time.time(), {})
    assert pv.last_answered(("session",))["model"] == "qwen3:14b-q4"
    assert pv.last_answered(("chat",))["model"] == "claude-haiku-5-5-20261001", "sites don't mix"


def test_the_line_prefers_what_answered_and_says_so():
    pv.answered("anthropic", "claude-haiku-5-5", "chat", now=1000.0)
    line = model_line("anthropic", "claude-haiku-5-5", now=1030.0)
    assert line == ("## CURRENT MODEL\n\nclaude-haiku-5-5 (anthropic; the model that answered my last "
                    "call, just now).")


def test_when_config_and_the_answer_disagree_both_are_named():
    # the night of 2026-11-24: config said Claude while qwen answered
    pv.answered("ollama", "qwen3:14b", "chat", now=1000.0)
    line = model_line("anthropic", "claude-haiku-5-5", now=1000.0 + 600)
    assert "qwen3:14b (ollama; the model that answered my last call, 10 min ago)" in line
    assert "Configured for this turn: claude-haiku-5-5 (anthropic)" in line


def test_with_no_answer_yet_it_says_configured():
    line = model_line("local", "qwen3:14b")
    assert line == "## CURRENT MODEL\n\nqwen3:14b (ollama; configured, no answer seen yet since I started)."


def _response():
    return SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")], stop_reason="end_turn",
                           model="claude-haiku-5-5", usage=SimpleNamespace(
                               input_tokens=1, output_tokens=1,
                               cache_read_input_tokens=0, cache_creation_input_tokens=0))


def _loop_turn(monkeypatch):
    """One chat turn through run_conversation (the path Babelr replies take); the request."""
    import agent_loop.models as models
    from agent_loop.conversation import run_conversation
    seen = []

    async def capture(kwargs, client, call_site="chat", ledger=None):
        seen.append(json.loads(json.dumps(kwargs)))
        # as llm_caller would, on the way back
        pv.answered("anthropic", "claude-haiku-5-5", call_site)
        return _response()

    monkeypatch.setattr(models, "_anthropic_request", capture)

    class Space:
        def run(self, *a):
            return ""

    asyncio.run(run_conversation(
        system_prompt="KERNEL", turn_context="## CURRENT TIME\n\nnow",
        continuous_messages=[], model_message="which model are you on?",
        person={"user_name": "Kohl", "user_id": "kohl"}, channel="babelr_dm",
        provider="anthropic", model="claude-haiku-5-5", client=models.AnthropicModelClient(object(), "chat"),
        catalog={}, workspace=Space(), run_router=lambda *a: None, working_toward=""))
    return seen[-1]


def test_a_babelr_turn_on_the_loop_carries_the_model_in_the_uncached_part(monkeypatch):
    first = _loop_turn(monkeypatch)
    stable, turn = first["system"]
    assert "## CURRENT MODEL" in turn["text"] and "claude-haiku-5-5 (anthropic; configured" in turn["text"]
    assert "CURRENT MODEL" not in stable["text"] and "cache_control" not in turn
    # next turn: what answered the last one
    second = _loop_turn(monkeypatch)
    assert "the model that answered my last call" in second["system"][1]["text"]
    assert first["system"][0] == second["system"][0], "the cached part didn't change"


def test_off_the_loop_a_chat_turn_carries_the_model_too(monkeypatch):
    """With the agent_loop_chat lever off, run_chat_turn sends through the old
    client; the model line goes at the end of the prompt it passes."""
    import continuous_context
    import features
    import websocket_handlers as wh
    from chat_turn import run_chat_turn
    seen = {}

    class Client:
        model = "claude-haiku-5-5"

        async def send_message(self, **kw):
            seen.update(kw)
            return SimpleNamespace(raw="hi", text="hi", gestures=[], tool_uses=[], input_tokens=1,
                                   output_tokens=1, cache_read_tokens=0, chain=None, stop_reason="end_turn")

    client = Client()
    for k, v in {"agent_client": client, "openai_client": None, "ollama_client": None,
                 "current_llm_provider": "anthropic", "use_agent_sdk": True, "daemon_id": None,
                 "memory": None, "conversation_manager": None, "user_manager": None}.items():
        monkeypatch.setitem(wh._state, k, v)
    ctx = SimpleNamespace(stable_prompt="KERNEL", turn_prompt="## CURRENT TIME\n\nnow", system_prompt="",
                          context_sections={}, token_estimate=1)
    monkeypatch.setattr(continuous_context, "build_continuous_context", lambda **kw: ctx)
    monkeypatch.setattr(continuous_context, "get_recent_messages_for_continuous", lambda **kw: [])
    monkeypatch.setattr(wh, "mark_user_activity", lambda: None)

    async def finalize(**kw):
        return {"clean_text": kw["clean_text"], "marks": []}

    monkeypatch.setattr(wh, "finalize_chat_turn", finalize)
    import chat_turn
    monkeypatch.setattr(chat_turn, "_record_cross_context_sample", lambda *a: None)
    with features.override(agent_loop_chat=False):
        asyncio.run(run_chat_turn(user_message="hi", conversation_id=None, user_id=None, channel="babelr_dm"))
    prompt = seen["continuous_system_prompt"]
    assert prompt.startswith("KERNEL\n\n## CURRENT TIME") and prompt.rstrip().endswith(
        "claude-haiku-5-5 (anthropic; configured, no answer seen yet since I started).")


def test_a_session_says_its_model_and_offers_her_hold(tmp_path, fake_llm):
    import pytest
    pytest.importorskip("anthropic")
    pytest.importorskip("networkx")
    import self_model_hold as H
    from agent_loop.session import run_session_turn
    from session import GenericSessionRunner
    H.hold_on("watching labels")
    runner = GenericSessionRunner(data_dir=tmp_path, model="claude-haiku-4-5-20251001")
    fake_llm.queue_tool_use("session_complete", {"summary": "done"})
    asyncio.run(run_session_turn(runner, session_type="reflection", max_turns=3, catalog={},
                                 run_router=lambda *a, **k: None))
    call = fake_llm.calls[0]
    assert "## CURRENT MODEL" in call.system_text and "claude-haiku-4-5" in call.system_text
    assert "## SELF-MODEL WRITE HOLD" in call.system_text and "watching labels" in call.system_text
    names = {t["name"] for t in (call.tools or [])}
    assert {"self_model_hold", "held_self_model_writes"} <= names


def test_her_write_hold_shows_in_the_turn_while_on_and_her_tools_are_offered(monkeypatch):
    import self_model_hold as H
    H.hold_on("labels first")
    req = _loop_turn(monkeypatch)
    turn = req["system"][1]["text"]
    assert "## SELF-MODEL WRITE HOLD" in turn and "labels first" in turn
    names = {t["name"] for t in req["tools"]}
    assert {"self_model_hold", "held_self_model_writes"} <= names
    H.hold_off()
    assert "SELF-MODEL WRITE HOLD" not in _loop_turn(monkeypatch)["system"][1]["text"]
