"""
Runtime hazards on the chat path (cards/CAPABILITIES.md "Fix first", card 01):

- the shared LLM client must not mix two users' turns
- the websocket tool loop is capped and survives a tool that raises
- OpenAI/Ollama get the same memory prompt and history as Anthropic
- a provider switch reaches sockets that are already open
- each chat turn marks the user as active (idle-only jobs wait)
- a relay (mobile) turn persists the same artifacts as a websocket turn
"""
import asyncio
import json

import pytest

from tests.fakes.llm import ScriptedResponse
from tests.smoke.conftest import access_token, create_user

PROGRESS_FRAMES = {"thinking", "debug", "title_updated", "status"}


def _chat(client, token, message, conversation_id=None):
    """One authenticated /ws chat turn; returns (final_frame, all_frames)."""
    frames = []
    with client.websocket_connect(f"/ws?token={token}") as ws:
        assert ws.receive_json()["type"] == "connected"
        payload = {"type": "chat", "message": message}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        ws.send_json(payload)
        while True:
            frame = ws.receive_json()
            frames.append(frame)
            if frame.get("type") not in PROGRESS_FRAMES:
                return frame, frames


def _stored(conversation_id):
    from database import get_db
    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content, marks_json, input_tokens, output_tokens, provider FROM messages "
            "WHERE conversation_id = ? ORDER BY timestamp, rowid",
            (conversation_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _token_rows(conversation_id):
    from database import get_db
    with get_db() as conn:
        rows = conn.execute(
            "SELECT category, operation, input_tokens, output_tokens FROM token_usage_records "
            "WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _chat_calls(fake_llm):
    """Calls from the chat clients (title generation sends no tools)."""
    return [c for c in fake_llm.calls if c.tools]


# ---------------------------------------------------------------------------
# 1. Two overlapping turns never see each other's state
# ---------------------------------------------------------------------------

def _user_text(messages):
    """The current turn's user message (the last plain-text user message)."""
    for msg in reversed(messages):
        if msg["role"] == "user" and isinstance(msg["content"], str):
            return msg["content"]
    return None


def test_overlapping_turns_do_not_cross_users(booted_app, fake_llm, monkeypatch):
    """Two relay turns for different users interleave inside their tool calls.

    Before the fix the shared CassAgentClient kept history/system prompt/tools
    on the instance, so the first turn's continuation ran on the second turn's
    messages and prompt.
    """
    import main_sdk

    users = {}
    for name in ("Alice", "Bob"):
        users[name] = create_user(display_name=name)

    # Model: first call of a turn asks for a tool whose id names the asker;
    # the continuation answers with text.
    def responder(source, kwargs):
        if source != "anthropic.async" or not kwargs.get("tools"):
            return None
        last = kwargs["messages"][-1]
        if isinstance(last["content"], str):
            return ScriptedResponse(tool_uses=[{
                "id": f"toolu_{last['content'].split()[-1]}",
                "name": "lookup_person", "input": {"name": "x"},
            }])
        return ScriptedResponse(text="done")

    fake_llm.responder = responder

    # Both turns must be inside tool execution at the same time.
    both_in_tools = asyncio.Event()
    arrived = []

    async def interleaving_batch(tool_uses, ctx, executors):
        arrived.append(ctx.user_id)
        if len(arrived) == 2:
            both_in_tools.set()
        await asyncio.wait_for(both_in_tools.wait(), timeout=10)
        return [{"tool_use_id": t["id"], "result": f"result-for-{ctx.user_id}", "is_error": False}
                for t in tool_uses]

    monkeypatch.setattr(main_sdk, "execute_tool_batch", interleaving_batch)

    async def both_turns():
        return await asyncio.gather(*[
            main_sdk.process_relay_chat_message(
                "client", user_id, {"type": "chat", "message": f"hello from {name}"})
            for name, user_id in users.items()
        ])

    results = booted_app.portal.call(both_turns)
    assert [r["type"] for r in results] == ["response", "response"], results

    firsts = {}
    continuations = []
    for call in _chat_calls(fake_llm):
        last = call.messages[-1]
        if isinstance(last["content"], str):
            firsts[last["content"]] = call
        else:
            continuations.append(call)
    assert set(firsts) == {"hello from Alice", "hello from Bob"}
    assert len(continuations) == 2

    for call in continuations:
        asker = _user_text(call.messages)
        name = asker.split()[-1]
        # Same system prompt and tools as this turn's first call
        assert call.system_text == firsts[asker].system_text
        assert call.tool_names == firsts[asker].tool_names
        # Only this user's message in the history sent
        texts = [m["content"] for m in call.messages if isinstance(m["content"], str)]
        assert not any(t.startswith("hello from") and t != asker for t in texts)
        # The tool result belongs to this turn's tool call and this user
        result = call.messages[-1]["content"][0]
        assert result["tool_use_id"] == f"toolu_{name}"
        assert result["content"] == f"result-for-{users[name]}"


# ---------------------------------------------------------------------------
# 2. Websocket tool loop: iteration cap and tool exceptions
# ---------------------------------------------------------------------------

def test_tool_loop_is_capped(booted_app, fake_llm, smoke_user, monkeypatch):
    """A model that never stops calling tools ends the turn at the cap."""
    import config
    monkeypatch.setattr(config, "CHAT_MAX_TOOL_ITERATIONS", 3)
    user_id, token = smoke_user

    def always_tools(source, kwargs):
        if source == "anthropic.async" and kwargs.get("tools"):
            return ScriptedResponse(text="again", tool_uses=[
                {"id": f"toolu_loop_{len(kwargs['messages'])}", "name": "lookup_person",
                 "input": {"name": "Kohl"}}])
        return None

    fake_llm.responder = always_tools

    frame, frames = _chat(booted_app, token, "loop forever")

    assert frame["type"] == "response", frames
    # 1 initial call + 3 continuations, then the loop stops
    assert len(_chat_calls(fake_llm)) == 4
    stored = _stored(frame["conversation_id"])
    assert [m["role"] for m in stored] == ["user", "assistant"]


def test_tool_exception_becomes_error_result(booted_app, fake_llm, smoke_user, monkeypatch):
    """A tool that raises: the model sees an error, the turn is saved, the socket lives."""
    import main_sdk
    user_id, token = smoke_user

    async def exploding_executor(**kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setitem(main_sdk.TOOL_EXECUTORS, "peopledex", exploding_executor)
    # Strict mode would re-raise the reported exception; this test is about
    # production behavior (CASS_STRICT unset).
    monkeypatch.setenv("CASS_STRICT", "0")

    fake_llm.queue_tool_use("lookup_person", {"name": "Kohl"}, tool_id="toolu_boom")
    fake_llm.queue_text("Sorry, that lookup failed.")

    with booted_app.websocket_connect(f"/ws?token={token}") as ws:
        assert ws.receive_json()["type"] == "connected"
        ws.send_json({"type": "chat", "message": "who is Kohl?"})
        while True:
            frame = ws.receive_json()
            if frame.get("type") not in PROGRESS_FRAMES:
                break
        assert frame["type"] == "response", frame
        assert frame["text"] == "Sorry, that lookup failed."
        conversation_id = frame["conversation_id"]

        # Connection still alive (skip late title/progress frames)
        ws.send_json({"type": "ping"})
        while (frame_type := ws.receive_json()["type"]) in PROGRESS_FRAMES:
            pass
        assert frame_type == "pong"

    result = _chat_calls(fake_llm)[1].messages[-1]["content"][0]
    assert result["tool_use_id"] == "toolu_boom"
    assert result["is_error"] is True
    assert "kaboom" in result["content"]
    assert [m["role"] for m in _stored(conversation_id)] == ["user", "assistant"]


def test_tool_exception_is_loud_in_strict_mode():
    """Under CASS_STRICT=1 (tests/CI) the swallowed tool error is reported loudly."""
    import websocket_handlers

    async def raising_batch(tool_uses, ctx, executors):
        raise RuntimeError("kaboom")

    async def run():
        return await websocket_handlers.execute_tools_safely(
            raising_batch, [{"id": "t1", "tool": "x", "input": {}}], None, {})

    with pytest.raises(RuntimeError, match="kaboom"):
        asyncio.run(run())


# ---------------------------------------------------------------------------
# 4. OpenAI/Ollama get memory + history; provider switch reaches open sockets
# ---------------------------------------------------------------------------

class _OpenAIStub:
    """Stands in for openai.AsyncOpenAI (the package is optional).

    Records each chat.completions.create call in the fake LLM's log as
    source "openai.async", and answers from its queue.
    """

    def __init__(self, fake_llm):
        from types import SimpleNamespace as NS

        async def create(**kwargs):
            resp = fake_llm._next("openai.async", kwargs)
            message = NS(content=resp.text or None, tool_calls=None)
            return NS(choices=[NS(message=message, finish_reason="stop")],
                      usage=NS(prompt_tokens=resp.input_tokens, completion_tokens=resp.output_tokens))

        self.chat = NS(completions=NS(create=create))


@pytest.fixture
def openai_provider(booted_app, fake_llm, monkeypatch):
    """Install a real OpenAIClient (its API calls go to the fake LLM) as a provider."""
    import openai_client
    import websocket_handlers

    monkeypatch.setattr(openai_client, "OPENAI_AVAILABLE", True)
    monkeypatch.setattr(openai_client, "AsyncOpenAI", lambda **kw: _OpenAIStub(fake_llm), raising=False)
    client = openai_client.OpenAIClient(daemon_id=websocket_handlers._state["daemon_id"])
    monkeypatch.setitem(websocket_handlers._state, "openai_client", client)
    yield client
    websocket_handlers.set_llm_provider("anthropic")


def test_openai_gets_continuous_prompt_and_history(booted_app, fake_llm, smoke_user, openai_provider):
    import websocket_handlers
    user_id, token = smoke_user

    fake_llm.queue_text("first answer")
    first, _ = _chat(booted_app, token, "remember the blue door")
    anthropic_call = _chat_calls(fake_llm)[-1]

    websocket_handlers.set_llm_provider("openai")
    fake_llm.queue_text("second answer")
    frame, frames = _chat(booted_app, token, "what colour was the door?",
                          conversation_id=first["conversation_id"])
    assert frame["type"] == "response", frames
    assert frame["provider"] == "openai"

    call = fake_llm.calls_from("openai")[-1]
    system = call.messages[0]
    assert system["role"] == "system"
    # Same continuous-context prompt the Anthropic path builds (it starts with
    # the kernel/identity and carries the memory sections), not the bare kernel.
    shared_head = anthropic_call.system_text[:500]
    assert system["content"].startswith(shared_head)
    # Recent history comes along
    contents = [m["content"] for m in call.messages[1:]]
    assert contents[-3:] == ["remember the blue door", "first answer", "what colour was the door?"]


def test_ollama_gets_continuous_prompt_and_history(booted_app, fake_llm, smoke_user, monkeypatch):
    import websocket_handlers
    from agent_client import OllamaClient, OLLAMA_TOOL_GUIDANCE

    sent = []

    class FakeHTTPResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"message": {"content": "local answer"}, "prompt_eval_count": 3, "eval_count": 2}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, timeout=None):
            # Snapshot: the client keeps appending to the same list
            sent.append({**json, "messages": list(json["messages"])})
            return FakeHTTPResponse()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = OllamaClient(daemon_id=websocket_handlers._state["daemon_id"])
    monkeypatch.setitem(websocket_handlers._state, "ollama_client", client)

    user_id, token = smoke_user
    fake_llm.queue_text("first answer")
    first, _ = _chat(booted_app, token, "remember the blue door")
    anthropic_call = _chat_calls(fake_llm)[-1]

    websocket_handlers.set_llm_provider("local")
    try:
        frame, frames = _chat(booted_app, token, "what colour was the door?",
                              conversation_id=first["conversation_id"])
    finally:
        websocket_handlers.set_llm_provider("anthropic")
    assert frame["type"] == "response", frames
    assert frame["provider"] == "local"

    messages = sent[-1]["messages"]
    assert messages[0]["content"].startswith(anthropic_call.system_text[:500])
    assert messages[0]["content"].endswith(OLLAMA_TOOL_GUIDANCE)
    assert [m["content"] for m in messages[1:]][-3:] == [
        "remember the blue door", "first answer", "what colour was the door?"]


def test_provider_switch_reaches_open_socket(booted_app, fake_llm, smoke_user, openai_provider):
    """Switching provider mid-connection changes the next turn on that same socket."""
    import websocket_handlers
    user_id, token = smoke_user

    fake_llm.queue_text("from claude")
    with booted_app.websocket_connect(f"/ws?token={token}") as ws:
        assert ws.receive_json()["type"] == "connected"

        def turn(message):
            ws.send_json({"type": "chat", "message": message})
            while True:
                frame = ws.receive_json()
                if frame.get("type") not in PROGRESS_FRAMES:
                    return frame

        assert turn("one")["provider"] == "anthropic"
        websocket_handlers.set_llm_provider("openai")
        fake_llm.queue_text("from openai")
        frame = turn("two")
    assert frame["provider"] == "openai"
    assert frame["text"] == "from openai"


# ---------------------------------------------------------------------------
# 5. Each chat turn marks activity
# ---------------------------------------------------------------------------

def test_chat_turn_marks_activity(booted_app, fake_llm, smoke_user):
    from datetime import datetime, timedelta, timezone
    from routes.admin.scheduler import get_scheduler

    scheduler = get_scheduler()
    assert scheduler is not None
    # Pretend the last activity was long ago, so the scheduler thinks it's idle
    scheduler._last_activity = datetime.now(timezone.utc) - timedelta(hours=2)
    assert scheduler.is_idle()

    user_id, token = smoke_user
    fake_llm.queue_text("hi")
    frame, _ = _chat(booted_app, token, "hello")
    assert frame["type"] == "response"
    assert not scheduler.is_idle()


# ---------------------------------------------------------------------------
# 9. Relay turn == websocket turn (persisted artifacts)
# ---------------------------------------------------------------------------

REPLY = "Noted. <mark:insight>a pattern</mark> Talk soon."


def _spy_memory(monkeypatch):
    """Record what reaches ChromaDB (memory.store_conversation)."""
    import websocket_handlers
    memory = websocket_handlers._state["memory"]
    stored = []
    original = memory.store_conversation

    async def spy(**kwargs):
        stored.append(kwargs)
        return await original(**kwargs)

    monkeypatch.setattr(memory, "store_conversation", spy)
    return stored


def test_relay_turn_persists_same_artifacts_as_websocket(booted_app, fake_llm, monkeypatch):
    import main_sdk
    import websocket_handlers

    chroma = _spy_memory(monkeypatch)
    marks = []
    marker_store = websocket_handlers._state["marker_store"]
    original_store_marks = marker_store.store_marks
    monkeypatch.setattr(marker_store, "store_marks",
                        lambda m: marks.append([x.category for x in m]) or original_store_marks(m))

    ws_user = create_user("Websocket User")
    relay_user = create_user("Relay User")

    fake_llm.queue_text(REPLY, input_tokens=50, output_tokens=7)
    ws_frame, frames = _chat(booted_app, access_token(ws_user), "hi there")
    assert ws_frame["type"] == "response", frames

    fake_llm.queue_text(REPLY, input_tokens=50, output_tokens=7)
    relay = booted_app.portal.call(
        main_sdk.process_relay_chat_message, "client", relay_user,
        {"type": "chat", "message": "hi there"})
    assert relay["type"] == "response", relay

    # Same cleaned reply text
    assert relay["text"] == ws_frame["text"] == "Noted. Talk soon."

    def normalized(rows):
        return [{k: v for k, v in r.items()} for r in rows]

    ws_rows = normalized(_stored(ws_frame["conversation_id"]))
    relay_rows = normalized(_stored(relay["conversation_id"]))
    assert ws_rows == relay_rows
    assert json.loads(relay_rows[1]["marks_json"]) == [{"category": "insight", "description": "a pattern"}]

    # Chat token usage recorded for both (title generation runs in the
    # background and may not have finished; it isn't what's compared here)
    def chat_tokens(conversation_id):
        return [r for r in _token_rows(conversation_id) if r["category"] == "chat"]

    assert chat_tokens(relay["conversation_id"]) == chat_tokens(ws_frame["conversation_id"])
    assert chat_tokens(relay["conversation_id"]) == [
        {"category": "chat", "operation": "initial_message", "input_tokens": 50, "output_tokens": 7}]

    # Both reached ChromaDB and the mark store
    assert [c["conversation_id"] for c in chroma] == [ws_frame["conversation_id"], relay["conversation_id"]]
    assert marks == [["insight"], ["insight"]]
