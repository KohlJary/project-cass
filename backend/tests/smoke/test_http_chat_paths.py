"""
Smoke: the non-WebSocket chat/memory paths actually store what they say they do.

POST /chat and POST /memory/store called the async store_conversation without
await (nothing stored), /memory/export passed a path to a no-arg method, and
/api/ha/conversation referenced names that don't exist.
"""


def _memory_count():
    import main_sdk
    return main_sdk.memory.count()


def test_memory_store_route_stores(booted_app, smoke_admin):
    _, token = smoke_admin
    before = _memory_count()
    resp = booted_app.post(
        "/memory/store",
        json={"user_message": "hello", "assistant_response": "hi there"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert "coroutine" not in str(resp.json()["id"])
    assert _memory_count() == before + 1


def test_memory_export_route_writes_file(booted_app, smoke_admin):
    from pathlib import Path
    _, token = smoke_admin
    resp = booted_app.get("/memory/export", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Path(body["filepath"]).exists()
    assert body["count"] == _memory_count()


def test_http_chat_stores_in_memory(booted_app, fake_llm, smoke_user):
    _, token = smoke_user
    fake_llm.queue_text("Hello from POST /chat")
    before = _memory_count()
    resp = booted_app.post(
        "/chat",
        json={"message": "hi via http", "include_memory": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["text"] == "Hello from POST /chat"
    assert _memory_count() == before + 1


def test_ha_conversation_answers_and_stores(booted_app, fake_llm, smoke_user):
    import main_sdk
    _, token = smoke_user
    auth = {"Authorization": f"Bearer {token}"}
    fake_llm.queue_text("The lights are on.")
    before = _memory_count()

    resp = booted_app.post("/api/ha/conversation", json={"text": "are the lights on?"},
                           headers=auth)

    body = resp.json()
    assert resp.status_code == 200 and "error" not in body, body
    assert body["response"] == "The lights are on."
    conv = main_sdk.conversation_manager.load_conversation(body["conversation_id"])
    assert [m.role for m in conv.messages] == ["user", "assistant"]
    assert _memory_count() == before + 1

    # A follow-up with the same id continues that conversation.
    fake_llm.queue_text("Turning them off.")
    resp = booted_app.post("/api/ha/conversation",
                           json={"text": "turn them off", "conversation_id": body["conversation_id"]},
                           headers=auth)
    assert resp.json()["conversation_id"] == body["conversation_id"]
