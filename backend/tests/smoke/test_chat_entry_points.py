"""
One chat turn pipeline for every entry point (#57, carried into epic #70).

WebSocket, the mobile relay, POST /chat, Home Assistant and Discord all run
chat_turn.run_chat_turn. The same scripted turn (a tool call, then a reply
carrying a mark and an inline observation tag) goes through each one with the
fake LLM, and what each persists is compared: SQLite messages, the ChromaDB
write, the token ledger, the mark store, and the tool result the model saw.

The one artifact that legitimately differs is the stored user message:
Discord stores the channel line it always stored ("[Discord #general -
Visitor]: ..."). Each entry point declares the user text it stores, and that
is checked separately.

Plus: scripts/cass_chat.py's request/response contract, run end to end
against the booted app.
"""
import json
from types import SimpleNamespace

import pytest

from tests.fakes.llm import ScriptedResponse
from tests.smoke.conftest import access_token, create_user

MESSAGE = "hi there"
REPLY = ('Noted. <mark:insight>a pattern</mark> '
         '<observe target="self" category="pattern">I hedge when unsure</observe> Talk soon.')
PROGRESS_FRAMES = {"thinking", "debug", "title_updated", "status"}


def _script_turn(fake_llm, tag):
    """The scripted turn: one tool call, then the reply."""
    fake_llm.queue_tool_use("lookup_person", {"name": "Kohl"}, text="Let me check.",
                            tool_id=f"toolu_{tag}", input_tokens=40, output_tokens=6)
    fake_llm.queue(ScriptedResponse(text=REPLY, input_tokens=50, output_tokens=7))


# ---------------------------------------------------------------------------
# One driver per entry point: (user_id, client) -> (reply_text, conversation_id, stored_user_text)
# ---------------------------------------------------------------------------

def _via_websocket(client, user_id):
    with client.websocket_connect(f"/ws?token={access_token(user_id)}") as ws:
        assert ws.receive_json()["type"] == "connected"
        ws.send_json({"type": "chat", "message": MESSAGE})
        while True:
            frame = ws.receive_json()
            if frame.get("type") not in PROGRESS_FRAMES:
                break
    assert frame["type"] == "response", frame
    return frame["text"], frame["conversation_id"], MESSAGE


def _via_relay(client, user_id):
    import main_sdk
    result = client.portal.call(
        main_sdk.process_relay_chat_message, "client", user_id,
        {"type": "chat", "message": MESSAGE})
    assert result["type"] == "response", result
    return result["text"], result["conversation_id"], MESSAGE


def _via_http_chat(client, user_id):
    import main_sdk
    # POST /chat speaks for the user set with POST /users/current
    # (cass_chat.py sets it first); set it the same way.
    resp = client.post("/users/current", json={"user_id": user_id},
                       headers={"Authorization": f"Bearer {access_token(user_id)}"})
    assert resp.status_code == 200, resp.text
    conv = main_sdk.conversation_manager.create_conversation(title="cass_chat", user_id=user_id)
    resp = client.post("/chat", json={"message": MESSAGE, "conversation_id": conv.id},
                       headers={"Authorization": f"Bearer {access_token(user_id)}"})
    assert resp.status_code == 200, resp.text
    return resp.json()["text"], conv.id, MESSAGE


def _via_home_assistant(client, user_id):
    resp = client.post("/api/ha/conversation", json={"text": MESSAGE},
                       headers={"Authorization": f"Bearer {access_token(user_id)}"})
    body = resp.json()
    assert resp.status_code == 200 and "error" not in body, body
    return body["response"], body["conversation_id"], MESSAGE


class _FakeDiscordBot:
    def __init__(self, linked_user_id):
        self.sent = []
        entity = SimpleNamespace(user_id=linked_user_id)
        self.parser = SimpleNamespace(registry=SimpleNamespace(get_by_slug=lambda slug: entity))

    async def send_message(self, channel_id, content):
        self.sent.append((channel_id, content))
        return {"success": True}


def _via_discord(client, user_id):
    import main_sdk
    bot = _FakeDiscordBot(user_id)
    callback = main_sdk.make_discord_wake_callback(bot)
    client.portal.call(callback, None, None, {
        "channel_name": "general", "channel_id": 42, "entity_name": "Visitor",
        "entity_slug": "visitor", "message_content": MESSAGE, "is_dm": False,
    })
    assert len(bot.sent) == 1, bot.sent
    conversation_id = main_sdk._discord_conversation_id(user_id, "Discord #general")
    return bot.sent[0][1], conversation_id, f"[Discord #general - Visitor]: {MESSAGE}"


ENTRY_POINTS = {
    "websocket": _via_websocket,
    "relay": _via_relay,
    "http_chat": _via_http_chat,
    "home_assistant": _via_home_assistant,
    "discord": _via_discord,
}


# ---------------------------------------------------------------------------
# What a turn persisted
# ---------------------------------------------------------------------------

def _messages(conversation_id):
    from database import get_db
    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content, marks_json, self_observations_json, input_tokens, "
            "output_tokens, provider, model FROM messages "
            "WHERE conversation_id = ? ORDER BY timestamp, rowid",
            (conversation_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _chat_token_rows(conversation_id):
    from database import get_db
    with get_db() as conn:
        rows = conn.execute(
            "SELECT category, operation, provider, input_tokens, output_tokens "
            "FROM token_usage_records WHERE conversation_id = ? AND category = 'chat'",
            (conversation_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _artifacts(conversation_id, stored_user_text, chroma_writes, marks, chat_calls):
    """Everything the turn persisted, with the entry point's own user text
    (and ids that are unique by construction) taken out."""
    rows = _messages(conversation_id)
    assert [r["role"] for r in rows] == ["user", "assistant"], rows
    assert rows[0]["content"] == stored_user_text
    self_obs = json.loads(rows[1]["self_observations_json"] or "[]")
    assert len(chroma_writes) == 1, chroma_writes
    chroma = chroma_writes[0]
    assert chroma["conversation_id"] == conversation_id
    assert chroma["user_message"] == stored_user_text
    tool_result = chat_calls[1].messages[-1]["content"][0]
    return {
        "assistant_row": {k: v for k, v in rows[1].items()
                          if k not in ("role", "self_observations_json")},
        "self_observation_texts": sorted(
            (o.get("observation") or o.get("content") or str(o)) if isinstance(o, dict) else str(o)
            for o in self_obs),
        "chroma_assistant_response": chroma["assistant_response"],
        "token_rows": _chat_token_rows(conversation_id),
        "marks": marks,
        "model_calls": len(chat_calls),
        "tool_result_type": tool_result["type"],
        "tool_result_is_error": tool_result.get("is_error", False),
    }


@pytest.fixture
def spies(monkeypatch):
    """Record ChromaDB writes and stored marks for one turn."""
    import websocket_handlers
    memory = websocket_handlers._state["memory"]
    chroma, marks = [], []
    original = memory.store_conversation

    async def spy(**kwargs):
        chroma.append(kwargs)
        return await original(**kwargs)

    monkeypatch.setattr(memory, "store_conversation", spy)
    marker_store = websocket_handlers._state["marker_store"]
    original_marks = marker_store.store_marks
    monkeypatch.setattr(marker_store, "store_marks",
                        lambda m: marks.append([x.category for x in m]) or original_marks(m))
    return chroma, marks


def _run(booted_app, fake_llm, spies, name):
    chroma, marks = spies
    chroma.clear()
    marks.clear()
    fake_llm.calls.clear()
    user_id = create_user(f"{name} user")
    _script_turn(fake_llm, name)
    reply, conversation_id, stored_user_text = ENTRY_POINTS[name](booted_app, user_id)
    chat_calls = [c for c in fake_llm.calls if c.tools]
    return reply, _artifacts(conversation_id, stored_user_text, list(chroma), list(marks), chat_calls)


@pytest.mark.parametrize("entry_point", [n for n in ENTRY_POINTS if n != "websocket"])
def test_entry_point_persists_the_same_artifacts_as_websocket(
        booted_app, fake_llm, spies, entry_point):
    ws_reply, ws_artifacts = _run(booted_app, fake_llm, spies, "websocket")
    reply, artifacts = _run(booted_app, fake_llm, spies, entry_point)

    # Tags were processed: the mark and the observation are gone from the text
    assert ws_reply == "Noted. Talk soon."
    assert reply == ws_reply
    assert artifacts == ws_artifacts

    # And the shared artifacts are what the scripted turn implies
    assert ws_artifacts["marks"] == [["insight"]]
    assert ws_artifacts["self_observation_texts"], "the observe tag was not stored"
    assert ws_artifacts["model_calls"] == 2
    assert ws_artifacts["tool_result_type"] == "tool_result"
    assert ws_artifacts["token_rows"] == [{
        "category": "chat", "operation": "tool_continuation", "provider": "anthropic",
        "input_tokens": 90, "output_tokens": 13}]
    assert json.loads(ws_artifacts["assistant_row"]["marks_json"]) == [
        {"category": "insight", "description": "a pattern"}]


def test_discord_memory_write_is_tagged_as_discord(booted_app, fake_llm, spies):
    chroma, _ = spies
    _run(booted_app, fake_llm, spies, "discord")
    assert chroma[0]["metadata"] == {"source": "discord", "channel": "general"}


def test_discord_linked_sender_continues_the_channel_conversation(booted_app, fake_llm):
    import main_sdk
    user_id = create_user("Discord Regular")
    bot = _FakeDiscordBot(user_id)
    callback = main_sdk.make_discord_wake_callback(bot)
    for text in ("first", "second"):
        fake_llm.queue_text(f"reply to {text}")
        booted_app.portal.call(callback, None, None, {
            "channel_name": "general", "channel_id": 42, "entity_name": "Regular",
            "entity_slug": "regular", "message_content": text, "is_dm": False,
        })
    conversation_id = main_sdk._discord_conversation_id(user_id, "Discord #general")
    rows = _messages(conversation_id)
    assert [r["content"] for r in rows] == [
        "[Discord #general - Regular]: first", "reply to first",
        "[Discord #general - Regular]: second", "reply to second"]
    # The second turn saw the first in its history
    second_call = [c for c in fake_llm.calls if c.tools][-1]
    assert any(m["content"] == "reply to first" for m in second_call.messages)


def test_discord_unlinked_sender_stores_memory_and_tokens_only(booted_app, fake_llm, spies):
    import main_sdk
    chroma, _ = spies
    fake_llm.queue_text("Hello there.", input_tokens=11, output_tokens=3)
    bot = _FakeDiscordBot(linked_user_id=None)
    booted_app.portal.call(main_sdk.make_discord_wake_callback(bot), None, None, {
        "channel_name": "general", "channel_id": 42, "entity_name": "Stranger",
        "entity_slug": "stranger", "message_content": "hi", "is_dm": False,
    })
    assert bot.sent == [(42, "Hello there.")]
    assert len(chroma) == 1 and chroma[0]["conversation_id"] is None
    from database import get_db
    with get_db() as conn:
        rows = conn.execute(
            "SELECT input_tokens, output_tokens FROM token_usage_records "
            "WHERE category = 'chat' AND conversation_id IS NULL").fetchall()
    assert [tuple(r) for r in rows] == [(11, 3)]


def test_home_assistant_tool_loop_is_capped_lower(booted_app, fake_llm, smoke_user, monkeypatch):
    """HA's 60s client timeout: the tool loop stops at HA_MAX_TOOL_ITERATIONS."""
    import config
    monkeypatch.setattr(config, "HA_MAX_TOOL_ITERATIONS", 1)
    _, token = smoke_user

    def always_tools(source, kwargs):
        if source == "anthropic.async" and kwargs.get("tools"):
            return ScriptedResponse(text="again", tool_uses=[
                {"id": f"toolu_ha_{len(kwargs['messages'])}", "name": "lookup_person",
                 "input": {"name": "Kohl"}}])
        return None

    fake_llm.responder = always_tools
    resp = booted_app.post("/api/ha/conversation", json={"text": "loop"},
                           headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200 and "error" not in resp.json(), resp.json()
    # 1 initial call + 1 continuation
    assert len([c for c in fake_llm.calls if c.tools]) == 2


def test_http_chat_include_memory_false_skips_retrieval(booted_app, fake_llm, smoke_user, monkeypatch):
    import continuous_context
    _, token = smoke_user
    seen = {}
    real_build = continuous_context.build_continuous_context

    def spy_build(*args, **kwargs):
        seen.update(kwargs)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(continuous_context, "build_continuous_context", spy_build)
    fake_llm.queue_text("ok")
    resp = booted_app.post("/chat", json={"message": "hi", "include_memory": False},
                           headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert seen["memory"] is None and seen["query"] is None
    assert resp.json()["memory_used"] is False


# ---------------------------------------------------------------------------
# scripts/cass_chat.py still works against the real app
# ---------------------------------------------------------------------------

@pytest.fixture
def cass_chat_live(booted_app, tmp_path, monkeypatch):
    """cass_chat with its HTTP calls routed into the booted app."""
    import importlib
    import sys
    from datetime import datetime, timedelta
    from pathlib import Path

    pytest.importorskip("requests")
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    mod = importlib.import_module("cass_chat")

    user_id = create_user("Daedalus")
    creds = tmp_path / "creds.json"
    creds.write_text(json.dumps({
        "user_id": user_id, "display_name": "Daedalus", "password": "x",
        "token": access_token(user_id),
        "token_expires": (datetime.utcnow() + timedelta(hours=10)).isoformat(),
    }))
    monkeypatch.setattr(mod, "CREDENTIALS_FILE", creds)
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")

    def path(url):
        assert url.startswith(mod.API_BASE), url
        return url[len(mod.API_BASE):]

    def get(url, params=None, headers=None, timeout=None):
        return booted_app.get(path(url), params=params, headers=headers)

    def post(url, json=None, headers=None, timeout=None):
        return booted_app.post(path(url), json=json, headers=headers)

    monkeypatch.setattr(mod.requests, "get", get)
    monkeypatch.setattr(mod.requests, "post", post)
    mod._user_id = user_id
    yield mod
    sys.modules.pop("cass_chat", None)


def test_cass_chat_send_contract(cass_chat_live, fake_llm):
    fake_llm.queue_text('<gesture:wave> Hello Daedalus. <mark:insight>a pattern</mark>')

    result = cass_chat_live.send_message("hello from the script", new=True)

    assert result["success"] is True, result
    assert result["response"] == "Hello Daedalus."
    assert "<gesture:wave>" in result["raw"]
    assert isinstance(result["animations"], list) and result["animations"]
    conversation_id = result["conversation_id"]

    # Stored under the script's own user, with tags processed
    import main_sdk
    conv = main_sdk.conversation_manager.load_conversation(conversation_id)
    assert conv.user_id == cass_chat_live._user_id
    assert [m.role for m in conv.messages] == ["user", "assistant"]
    assert conv.messages[1].content == "Hello Daedalus."

    # history reads it back through GET /conversations/{id}
    history = cass_chat_live.get_conversation(conversation_id)
    assert history.get("success", True), history
    assert "Hello Daedalus." in json.dumps(history)

    # A second send continues the same conversation (state file)
    fake_llm.queue_text("Still here.")
    again = cass_chat_live.send_message("still there?")
    assert again["success"] and again["conversation_id"] == conversation_id
    assert again["response"] == "Still here."
