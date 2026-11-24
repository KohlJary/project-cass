"""
Her chat system prompt, cached in two parts (2026-11-24).

The token ledger for 2026-11-18: $6.16 of a $7.28 chat day on Haiku 4.5 was
cache writes. The whole system prompt was one cached block, and CURRENT TIME
sat right after the kernel, with this message's recalled memories further
down, so every turn changed the cached prefix and rewrote all of it.

Now the parts that stay the same (the kernel, who she is, the entry point's
guidance) are their own system block with the breakpoint, and the per-turn
parts (the time, her state, what was recalled, the seam) follow it uncached.
These tests build two consecutive chat requests and check the bytes the
cache keys on. No API call is made: the request is captured before it leaves.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from agent_loop.models import CACHE, SplitSystem, anthropic_system, ollama_messages, openai_messages


class _Memory:
    """Recall that answers each message with different memories."""

    def __init__(self):
        self.by_query = {
            "how did the sensor test go?": "Kohl and I wired the sensor module on the bench.",
            "what should we paint next?": "We talked about painting the tide pools at dusk.",
        }

    def retrieve_relevant(self, query, n_results=5, **kw):
        return [{"content": self.by_query[query],
                 "metadata": {"type": "conversation", "user_id": "kohl"}, "distance": 0.4}]


def _context(daemon_id, monkeypatch, query, now):
    import continuous_context
    monkeypatch.setattr(continuous_context, "get_temporal_context", lambda: f"It is {now}.")
    monkeypatch.setattr(continuous_context, "_format_temporal_summary", lambda t: t)
    return continuous_context.build_continuous_context(
        user_id="kohl", conversation_id=None, user_manager=None, thread_manager=None,
        question_manager=None, conversation_manager=None, daemon_id=daemon_id,
        memory=_Memory(), query=query)


def test_the_stable_part_doesnt_change_between_turns(daemon_id, monkeypatch):
    a = _context(daemon_id, monkeypatch, "how did the sensor test go?", "Tuesday 14:02")
    b = _context(daemon_id, monkeypatch, "what should we paint next?", "Tuesday 14:09")
    assert a.stable_prompt == b.stable_prompt
    assert a.stable_prompt.startswith(a.context_sections["kernel"])
    # What changes is in the turn part, and nothing per-turn is in the stable part.
    assert "sensor module" in a.turn_prompt and "tide pools" in b.turn_prompt
    assert "Tuesday 14:02" in a.turn_prompt and "Tuesday 14:09" in b.turn_prompt
    for text in ("sensor module", "Tuesday", "## CURRENT TIME", "## RELEVANT MEMORIES"):
        assert text not in a.stable_prompt
    # Nothing removed: the prompt is the two parts, every section still in it.
    assert a.system_prompt == f"{a.stable_prompt}\n\n{a.turn_prompt}"
    for name, text in a.context_sections.items():
        assert text.strip()[:60] in a.system_prompt, name


def _response():
    return SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")], stop_reason="end_turn",
                           usage=SimpleNamespace(input_tokens=1, output_tokens=1,
                                                 cache_read_input_tokens=0, cache_creation_input_tokens=0))


def _chat_request(monkeypatch, ctx, message, arrival):
    """One chat turn through run_conversation and the Anthropic client; the
    request's kwargs, as they would go to the API."""
    import agent_loop.models as models
    from agent_loop.conversation import run_conversation
    seen = []

    async def capture(kwargs, client, call_site="chat", ledger=None):
        seen.append(json.loads(json.dumps(kwargs)))
        return _response()

    monkeypatch.setattr(models, "_anthropic_request", capture)

    class Space:
        def run(self, *a):
            return ""

    catalog = {"recall": {"name": "recall", "description": "Search my memories.",
                          "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}}}}
    asyncio.run(run_conversation(
        system_prompt=ctx.stable_prompt, turn_context=ctx.turn_prompt,
        continuous_messages=[{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "yes"}],
        model_message=message, person={"user_name": "Kohl", "user_id": "kohl"}, channel="websocket",
        provider="anthropic", model="claude-haiku-4-5", client=models.AnthropicModelClient(object(), "chat"),
        catalog=catalog, workspace=Space(), run_router=lambda *a: None,
        working_toward="## WHAT I'M WORKING TOWARD\n\n- **Paint**", arrival_block=arrival))
    assert len(seen) == 1
    return seen[0]


def _cached_prefix(request):
    """The bytes up to and including the cached system block: tools, then system[0]."""
    return json.dumps(request["tools"], sort_keys=True) + json.dumps(request["system"][0], sort_keys=True)


def test_two_chat_requests_share_the_cached_prefix_byte_for_byte(daemon_id, monkeypatch):
    m1, m2 = "how did the sensor test go?", "what should we paint next?"
    first = _chat_request(monkeypatch, _context(daemon_id, monkeypatch, m1, "Tuesday 14:02"), m1,
                          "## WHO'S HERE\n\nKohl, at 14:02")
    second = _chat_request(monkeypatch, _context(daemon_id, monkeypatch, m2, "Tuesday 14:09"), m2,
                           "## WHO'S HERE\n\nKohl, at 14:09")

    assert _cached_prefix(first) == _cached_prefix(second)
    # The breakpoint is on the stable block, and only there in the system field.
    stable, turn = first["system"]
    assert stable["cache_control"] == CACHE and "cache_control" not in turn
    assert "## CORE IDENTITY" in stable["text"] or "THE FOUR VOWS" in stable["text"]
    # Tools first in the prefix, with their own breakpoint; the newest message keeps its one.
    assert first["tools"][-1]["cache_control"] == CACHE
    assert first["messages"][-1]["content"][-1]["cache_control"] == CACHE
    breakpoints = json.dumps(first).count('"cache_control"')
    assert breakpoints == 3, "tools, the stable system block, the newest message (4 allowed)"

    # Everything that changes is after the breakpoint.
    assert first["system"][1] != second["system"][1]
    assert "sensor module" in turn["text"] and "Tuesday 14:02" in turn["text"]
    assert "## THIS MOMENT" in turn["text"] and "Kohl, at 14:02" in turn["text"]
    assert "## WHAT I'M WORKING TOWARD" in turn["text"]
    for per_turn in ("sensor module", "Tuesday", "## THIS MOMENT", "Kohl, at"):
        assert per_turn not in stable["text"]


def test_the_split_prompt_is_still_the_whole_prompt_as_text():
    s = SplitSystem("KERNEL", "## CURRENT TIME\n\nnow")
    assert s == "KERNEL\n\n## CURRENT TIME\n\nnow" and isinstance(s, str)
    assert openai_messages(s, [])[0] == {"role": "system", "content": "KERNEL\n\n## CURRENT TIME\n\nnow"}
    assert type(ollama_messages(s, [])[0]["content"]) is str
    assert anthropic_system(s, cache=False) == "KERNEL\n\n## CURRENT TIME\n\nnow"
    assert anthropic_system(s) == [{"type": "text", "text": "KERNEL", "cache_control": CACHE},
                                   {"type": "text", "text": "## CURRENT TIME\n\nnow"}]
    # A plain prompt (sessions, tests) caches whole, as before; an empty turn part adds no block.
    assert anthropic_system("I am here.") == [{"type": "text", "text": "I am here.", "cache_control": CACHE}]
    assert anthropic_system(SplitSystem("KERNEL", "")) == [{"type": "text", "text": "KERNEL",
                                                             "cache_control": CACHE}]

