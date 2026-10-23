"""
Smoke: a slow memory retrieval in one chat request must not stall the app.

Issue #85: POST /chat ran synchronous Chroma/embedding retrieval directly on
the event loop. One request froze the whole process (Discord, Home Assistant,
the scheduler, other HTTP clients) for minutes. Retrieval now runs in a worker
thread; these tests hold retrieval in a sleep and check that a trivial request
(GET /health) is still answered meanwhile.
"""
import threading
import time

RETRIEVAL_SECONDS = 2.0
# /health must come back well before the slow retrieval finishes.
HEALTH_DEADLINE = 1.0


def _health_latency_during(client, started: threading.Event, run_slow_request):
    """Start run_slow_request in a thread; once its retrieval has begun, time GET /health."""
    errors = []

    def worker():
        try:
            run_slow_request()
        except Exception as e:  # surfaced below
            errors.append(e)

    t = threading.Thread(target=worker)
    t.start()
    try:
        assert started.wait(30), "slow retrieval never started"
        t0 = time.monotonic()
        resp = client.get("/health")
        latency = time.monotonic() - t0
        assert resp.status_code == 200, resp.text
    finally:
        t.join(60)
    assert not errors, errors
    return latency


def test_slow_retrieval_in_http_chat_does_not_block_other_requests(
        booted_app, fake_llm, smoke_user, monkeypatch):
    # POST /chat now runs the shared chat turn (chat_turn.py), whose context
    # step is build_continuous_context, the same as the websocket's.
    import continuous_context
    _, token = smoke_user
    fake_llm.queue_text("still here")

    started = threading.Event()
    real_build = continuous_context.build_continuous_context

    def slow_build(*args, **kwargs):
        started.set()
        time.sleep(RETRIEVAL_SECONDS)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(continuous_context, "build_continuous_context", slow_build)

    def slow_chat():
        resp = booted_app.post(
            "/chat",
            json={"message": "hello, slowly", "include_memory": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["text"] == "still here"

    latency = _health_latency_during(booted_app, started, slow_chat)
    assert latency < HEALTH_DEADLINE, (
        f"/health took {latency:.2f}s while a chat retrieval was in flight; "
        "retrieval is blocking the event loop")


def test_slow_retrieval_in_websocket_chat_does_not_block_other_requests(
        booted_app, fake_llm, smoke_user, monkeypatch):
    import continuous_context
    _, token = smoke_user
    fake_llm.queue_text("still here over ws")

    started = threading.Event()
    real_build = continuous_context.build_continuous_context

    def slow_build(*args, **kwargs):
        started.set()
        time.sleep(RETRIEVAL_SECONDS)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(continuous_context, "build_continuous_context", slow_build)

    def slow_ws_chat():
        with booted_app.websocket_connect(f"/ws?token={token}") as ws:
            assert ws.receive_json()["type"] == "connected"
            ws.send_json({"type": "chat", "message": "hello, slowly"})
            while True:
                frame = ws.receive_json()
                if frame.get("type") not in {"thinking", "debug", "title_updated", "status"}:
                    break
        assert frame["type"] == "response", frame

    latency = _health_latency_during(booted_app, started, slow_ws_chat)
    assert latency < HEALTH_DEADLINE, (
        f"/health took {latency:.2f}s while a websocket chat retrieval was in flight; "
        "context building is blocking the event loop")


def test_slow_retrieval_in_relay_chat_does_not_block_other_requests(
        booted_app, fake_llm, smoke_user, monkeypatch):
    import continuous_context
    import main_sdk
    user_id, _token = smoke_user
    fake_llm.queue_text("still here over relay")

    started = threading.Event()
    real_build = continuous_context.build_continuous_context

    def slow_build(*args, **kwargs):
        started.set()
        time.sleep(RETRIEVAL_SECONDS)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(continuous_context, "build_continuous_context", slow_build)

    def slow_relay_chat():
        result = booted_app.portal.call(
            main_sdk.process_relay_chat_message,
            "smoke-relay-client", user_id, {"type": "chat", "message": "hello, slowly"},
        )
        assert result.get("type") != "error", result

    latency = _health_latency_during(booted_app, started, slow_relay_chat)
    assert latency < HEALTH_DEADLINE, (
        f"/health took {latency:.2f}s while a relay chat retrieval was in flight; "
        "context building is blocking the event loop")
