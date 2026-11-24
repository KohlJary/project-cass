"""ollama_raw asks for no hidden thinking (qwen3 thinks by default on /api/chat,
and a reply that spends num_predict thinking comes back empty: Eris's Babelr
replies, 2026-11-24)."""
import asyncio

import llm_caller


def _capture(monkeypatch):
    seen = {}

    async def fake(url, endpoint, body, timeout):
        seen.update(body)
        return {"message": {"content": "hi"}, "prompt_eval_count": 1, "eval_count": 1}

    monkeypatch.setattr(llm_caller, "_ollama_request", fake)
    monkeypatch.setattr(llm_caller, "_record_response", lambda *a, **k: None)
    return seen


def test_no_hidden_thinking_by_default(monkeypatch):
    seen = _capture(monkeypatch)
    asyncio.run(llm_caller.ollama_raw("session.generic", {"model": "qwen3:14b", "messages": []},
                                      default_model="qwen3:14b"))
    assert seen["think"] is False


def test_a_caller_can_still_ask_for_thinking(monkeypatch):
    seen = _capture(monkeypatch)
    asyncio.run(llm_caller.ollama_raw("session.generic", {"model": "qwen3:14b", "messages": [], "think": True},
                                      default_model="qwen3:14b"))
    assert seen["think"] is True
