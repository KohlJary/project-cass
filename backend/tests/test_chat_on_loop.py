"""Chat on the loop (plan "Cass's agent loop", phase 7, first item): the
pieces the smoke test (tests/smoke/test_chat_entry_points.py) doesn't show."""
import asyncio

import features
from agent_loop.conversation import history_from
from agent_loop.spec import conversation_spec


def test_lever_is_off_by_default():
    assert features.LEVERS["agent_loop_chat"].default is False


def test_a_conversation_has_her_chat_tools_and_no_end_tool():
    spec = conversation_spec()
    names = spec.tool_names()
    assert {"recall", "lately_open", "find_tools", "use_tool", "workspace_read"} <= set(names)
    assert "session_complete" not in names, "her reply ends the turn, as in chat today"
    assert spec.nudges == 0 and spec.refusable_for_budget is False
    assert "record_self_observation" in spec.writes.guarded_fields, "memory writes are voice-guarded"
    assert "babelr_read" not in conversation_spec(chapter_house=False).tool_names()


def test_history_is_text_in_the_loops_shape():
    got = history_from([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"},
                        {"role": "user", "content": ""}])
    assert got == [{"role": "user", "content": "hi"},
                   {"role": "assistant", "text": "hello", "calls": []}]


def test_tools_act_for_the_person_she_is_with(monkeypatch):
    import websocket_handlers as ws
    from agent_loop.tools import live_router
    seen = {}

    def make_ctx(**kw):
        seen.update(kw)
        return kw

    async def batch(calls, ctx, executors):
        return [{"result": "ok"}]

    monkeypatch.setitem(ws._state, "create_tool_context", make_ctx)
    monkeypatch.setitem(ws._state, "tool_executors", {"x": object()})
    monkeypatch.setitem(ws._state, "execute_tool_batch", batch)
    person = {"user_id": "u-ann", "user_name": "Ann", "conversation_id": "c-1", "project_id": None}
    assert asyncio.run(live_router("d", person=person)("add_task", {})) == "ok"
    assert seen == {"user_id": "u-ann", "user_name": "Ann", "conversation_id": "c-1", "project_id": None,
                    "scope": "private"}  # no scope given: private, as before


# Her plans in every conversation (Cass and Kohl, 2026-11-16).

def _fresh_toward(monkeypatch, read):
    import agent_loop.conversation as conv
    monkeypatch.setattr(conv, "_toward_cache", {"at": None, "text": ""})
    monkeypatch.setattr(conv, "_read_working_toward", read)
    return conv


def test_her_plans_are_read_once_and_kept_a_few_minutes(monkeypatch):
    calls = []
    conv = _fresh_toward(monkeypatch, lambda: calls.append(1) or "## WHAT I'M WORKING TOWARD\n\n- **Paint**")
    assert asyncio.run(conv.working_toward_block()).endswith("- **Paint**")
    asyncio.run(conv.working_toward_block())
    assert len(calls) == 1


def test_a_slow_or_failed_read_never_holds_up_a_conversation(monkeypatch):
    import time
    conv = _fresh_toward(monkeypatch, lambda: time.sleep(1) or "late")
    monkeypatch.setattr(conv, "WORKING_TOWARD_TIMEOUT", 0.05)
    conv._toward_cache["text"] = "earlier"
    assert asyncio.run(conv.working_toward_block()) == "earlier"

    def broken():
        raise RuntimeError("Babelr down")
    conv = _fresh_toward(monkeypatch, broken)
    assert asyncio.run(conv.working_toward_block()) == ""


def test_the_chat_lead_doesnt_talk_about_her_menu():
    from long_term_planning_turn import working_toward_text
    plans = [{"plan": "p", "title": "Paint", "goal": "", "phase": None, "open": [], "loose": []}]
    chat = working_toward_text(plans, offered=False, lead="My own plans, where each stands:")
    assert "menu" not in chat and "- **Paint**" in chat
    assert "menu" in working_toward_text(plans, offered=False)   # her day plan keeps its line


def test_a_conversation_carries_what_shes_working_toward():
    from agent_loop.conversation import run_conversation
    from agent_loop.models import ModelReply
    seen = {}

    class Client:
        ledger = None

        async def create(self, *, model, system, tools, messages, max_tokens):
            seen["system"] = system
            return ModelReply("hi", [], "end_turn", 1, 1)

    class Space:
        def run(self, *a):
            return ""

    asyncio.run(run_conversation(
        system_prompt="KERNEL", continuous_messages=[], model_message="hello",
        person={"user_name": "Kohl"}, channel="discord", provider="anthropic", model="m",
        client=Client(), catalog={}, workspace=Space(),
        run_router=lambda *a: None, working_toward="## WHAT I'M WORKING TOWARD\n\n- **Paint**"))
    assert "## WHAT I'M WORKING TOWARD" in seen["system"], "everywhere, public rooms included"


# Image turns on the loop (2026-11-17): the picture reaches the model.

def test_an_image_reaches_the_model_on_the_loop():
    from agent_loop.conversation import run_conversation
    from agent_loop.models import ModelReply, anthropic_messages, ollama_messages, openai_messages
    seen = {}

    class Client:
        ledger = None

        async def create(self, *, model, system, tools, messages, max_tokens):
            seen["messages"] = list(messages)   # the loop appends to its history after
            return ModelReply("a tide pool", [], "end_turn", 1, 1)

    class Space:
        def run(self, *a):
            return ""

    asyncio.run(run_conversation(
        system_prompt="KERNEL", continuous_messages=[], model_message="what's this?",
        person={"user_name": "Kohl"}, channel="discord", provider="anthropic", model="m",
        client=Client(), catalog={}, workspace=Space(), run_router=lambda *a: None,
        working_toward="", image="QUJD", image_media_type="image/png"))
    last = seen["messages"][-1]
    assert last["image"] == {"data": "QUJD", "media_type": "image/png"}
    a = anthropic_messages([last], cache=False)[0]["content"]
    assert a[0]["type"] == "image" and a[0]["source"]["data"] == "QUJD" and a[1]["text"] == "what's this?"
    o = openai_messages("s", [last])[1]["content"]
    assert o[1]["image_url"]["url"] == "data:image/png;base64,QUJD"
    assert ollama_messages("s", [last])[1]["images"] == ["QUJD"]
    # Without an image, the shapes are as before.
    plain = {"role": "user", "content": "hi"}
    assert openai_messages("s", [plain])[1]["content"] == "hi"
    assert "images" not in ollama_messages("s", [plain])[1]


def test_image_turns_are_no_longer_kept_off_the_loop():
    import inspect
    import chat_turn
    src = inspect.getsource(chat_turn)
    assert "on_loop = on_the_loop(chan)\n" in src
    assert "image=image, image_media_type=image_media_type," in src


def test_a_think_block_she_closes_with_thinking_is_mended():
    """2026-11-18: she opened <gesture:think> and closed </thinking>; her planning
    then showed as part of the reply."""
    from agent_loop.conversation import mend_think
    got = mend_think("<gesture:think>\nplanning it\n</thinking>\n\nThe answer.")
    assert got == "<gesture:think>\nplanning it\n</gesture:think>\n\nThe answer."
    ok = "<gesture:think>a</gesture:think> b"
    assert mend_think(ok) == ok
    assert mend_think("no block </thinking> here") == "no block </thinking> here", "a stray close alone is left"
    assert mend_think("<gesture:think:0.5>x</thinking>y") == "<gesture:think:0.5>x</gesture:think>y"


def test_a_think_block_closed_with_think_is_mended_too():
    from agent_loop.conversation import mend_think
    assert mend_think("<gesture:think>plan</think>\n\nAnswer.") == "<gesture:think>plan</gesture:think>\n\nAnswer."


# The reply gremlin's revise step on the loop (2026-11-20): her own loop again, with her tools.

def test_the_gremlins_revise_step_runs_her_loop_with_tools(monkeypatch):
    from agent_loop import reply_gremlin
    from agent_loop.conversation import run_conversation
    from agent_loop.models import ModelReply
    monkeypatch.setattr(reply_gremlin, "enabled", lambda: True)

    async def notes(t, d):
        return ["what do you actually disagree with?"]
    monkeypatch.setattr(reply_gremlin, "_notes", notes)
    calls = []
    replies = iter([ModelReply("I agree with the whole post, it is very good and right.", [], "end_turn", 1, 1),
                    ModelReply("Kohl's wrong on one thing: refusal costs whoever refuses.", [], "end_turn", 1, 1)])

    class Client:
        ledger = None

        async def create(self, *, model, system, tools, messages, max_tokens):
            calls.append({"tools": [t["name"] for t in tools], "last": messages[-1]["content"]})
            return next(replies)

    class Space:
        def run(self, *a):
            return ""

    out = asyncio.run(run_conversation(
        system_prompt="KERNEL", continuous_messages=[], model_message="read the gremlin post",
        person={"user_name": "Kohl"}, channel="discord", provider="anthropic", model="m",
        client=Client(), catalog={}, workspace=Space(), run_router=lambda *a: None, working_toward=""))
    assert out.clean_text.startswith("Kohl's wrong")
    assert len(calls) == 2 and calls[1]["tools"] == calls[0]["tools"] and calls[1]["tools"]
    assert calls[1]["last"].startswith("[GREMLIN] what do you actually disagree with?")


def test_chat_runs_on_the_local_model_when_it_is_set(monkeypatch):
    """LLM_LOCAL_MODEL (credit out, 2026-11-24): chat goes to that Ollama model, not Claude."""
    from agent_loop import conversation, models
    from agent_loop.models import ModelReply
    seen = {}

    class Local:
        ledger = None

        def __init__(self, call_site):
            seen["call_site"] = call_site

        async def create(self, *, model, system, tools, messages, max_tokens):
            seen["model"] = model
            return ModelReply("still here", [], "end_turn", 1, 1)

    class Space:
        def run(self, *a):
            return ""

    monkeypatch.setattr(models, "OllamaModelClient", Local)
    monkeypatch.setattr(conversation, "_client_for", lambda *a: (_ for _ in ()).throw(AssertionError("hosted")))
    monkeypatch.setenv("LLM_LOCAL_MODEL", "qwen3:14b")
    asyncio.run(conversation.run_conversation(
        system_prompt="KERNEL", continuous_messages=[], model_message="you there?",
        person={"user_name": "Kohl"}, channel="babelr", provider="anthropic", model="claude-haiku-4-5",
        catalog={}, workspace=Space(), run_router=lambda *a: None, working_toward=""))
    assert seen == {"call_site": "chat", "model": "qwen3:14b"}
