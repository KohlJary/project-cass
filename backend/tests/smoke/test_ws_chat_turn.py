"""
Smoke (b): one full websocket chat turn end to end against the fake LLM.

Message in -> continuous context -> CassAgentClient -> (tool loop) ->
response frame out -> turn persisted to SQLite.
"""
from tests.fakes.llm import ScriptedResponse


def _chat(client, message):
    """Send one chat message over /ws; return (response_frame, all_frames)."""
    frames = []
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "connected"
        ws.send_json({"type": "chat", "message": message})
        while True:
            frame = ws.receive_json()
            frames.append(frame)
            if frame["type"] in ("response", "error"):
                return frame, frames


def _stored_messages(conversation_id):
    from database import get_db
    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content, input_tokens, output_tokens FROM messages "
            "WHERE conversation_id = ? ORDER BY timestamp, rowid",
            (conversation_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _chat_calls(fake_llm):
    """Calls made by the main chat client (title generation also uses the fake)."""
    return [c for c in fake_llm.calls if c.tools]


def test_plain_chat_turn(booted_app, fake_llm):
    fake_llm.queue_text("Hello Kohl, good to see you.", input_tokens=120, output_tokens=9)

    frame, frames = _chat(booted_app, "hi cass")

    assert frame["type"] == "response", frames
    assert frame["text"] == "Hello Kohl, good to see you."
    assert frame["input_tokens"] == 120 and frame["output_tokens"] == 9
    conversation_id = frame["conversation_id"]

    # Exactly one model call for the chat itself, carrying the real prompt.
    chat_calls = _chat_calls(fake_llm)
    assert len(chat_calls) == 1
    request = chat_calls[0]
    assert request.source == "anthropic.async"
    assert request.system_text  # continuous-context system prompt was built
    assert request.messages[-1] == {"role": "user", "content": "hi cass"}
    assert "lookup_person" in request.tool_names  # always-on tools offered

    # Turn persisted to SQLite.
    stored = _stored_messages(conversation_id)
    assert [m["role"] for m in stored] == ["user", "assistant"]
    assert stored[0]["content"] == "hi cass"
    assert stored[1]["content"] == "Hello Kohl, good to see you."
    assert stored[1]["input_tokens"] == 120


def test_chat_turn_with_tool_call(booted_app, fake_llm):
    # Turn 1: the model calls a tool. Turn 2: it answers using the result.
    fake_llm.queue_tool_use("lookup_person", {"name": "Kohl"}, text="Let me check.",
                            tool_id="toolu_smoke_1")
    fake_llm.queue(ScriptedResponse(text="I don't have notes on Kohl yet."))

    frame, frames = _chat(booted_app, "what do you know about Kohl?")

    assert frame["type"] == "response", frames
    assert frame["text"] == "I don't have notes on Kohl yet."

    chat_calls = _chat_calls(fake_llm)
    assert len(chat_calls) == 2
    continuation = chat_calls[1]
    # The tool result went back to the model, matched to the tool_use id.
    last = continuation.messages[-1]
    assert last["role"] == "user"
    result_block = last["content"][0]
    assert result_block["type"] == "tool_result"
    assert result_block["tool_use_id"] == "toolu_smoke_1"
    # lookup_person really ran (PeopleDex is empty, so it reports not found).
    assert "Kohl" in str(result_block["content"])

    stored = _stored_messages(frame["conversation_id"])
    assert [m["role"] for m in stored] == ["user", "assistant"]
    assert stored[1]["content"] == "I don't have notes on Kohl yet."
