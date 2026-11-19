"""Spells that write in her name carry her gremlin (Kohl, 2026-11-19)."""
import asyncio
from types import SimpleNamespace

import grimoire.agent as agent_mod


def _agent(monkeypatch, gremlin_text):
    seen = []

    async def fake_call_llm(**kw):
        seen.append(kw["system_prompt"])
        return SimpleNamespace(success=True, content="ok", error=None)
    monkeypatch.setattr(agent_mod, "call_llm", fake_call_llm)
    import gremlin
    monkeypatch.setattr(gremlin, "section", lambda *a, **k: gremlin_text)
    cls = next(v for v in vars(agent_mod).values() if isinstance(v, type) and hasattr(v, "reflect") and hasattr(v, "generate"))
    a = cls.__new__(cls)
    a.daemon_id = "test"
    return a, seen


def test_generate_and_reflect_carry_her_gremlin(monkeypatch):
    a, seen = _agent(monkeypatch, "## MY GREMLIN\n\nthe bit is also dead serious")
    asyncio.run(a.generate("a check-in message", {}))
    asyncio.run(a.reflect("how did that go", {}))
    assert len(seen) == 2 and all("the bit is also dead serious" in s for s in seen)


def test_nothing_added_when_her_gremlin_is_off(monkeypatch):
    a, seen = _agent(monkeypatch, None)
    asyncio.run(a.generate("x", {}))
    assert "GREMLIN" not in seen[0]
