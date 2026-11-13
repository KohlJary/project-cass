"""
The agent loop's core (epic #70, step 1): provider-neutral history, the
nudge, the token budget, and the three model clients (Anthropic with prompt
caching, OpenAI, Ollama-native), each driven through llm_caller.

The first half needs no SDK (fast CI job): the loop against a stub client and
the pure history translations. The second half runs each client against the
fake LLM, and a whole session through the Turn on a non-Claude assignment.
"""
import asyncio
import json

import pytest

from agent_loop.loop import ModelReply, nudge_text, run_loop
from agent_loop.models import anthropic_messages, ollama_messages, openai_messages
from agent_loop.spec import session_spec

HISTORY = [
    {"role": "user", "content": "begin"},
    {"role": "assistant", "text": "Looking.", "calls": [
        {"id": "c1", "name": "recall_memories", "input": {"query": "tide pools"}}]},
    {"role": "tool", "results": [{"id": "c1", "name": "recall_memories", "content": '{"hits": 2}'}]},
    {"role": "assistant", "text": "", "calls": []},
    {"role": "user", "content": nudge_text("session_complete")},
]


# ---------------------------------------------------------------------------
# The loop: done, nudge, budget (stub client)
# ---------------------------------------------------------------------------

class StubClient:
    provider = "stub"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        if not self.replies:
            return ModelReply("", [], "end_turn", 1, 1)
        return self.replies.pop(0)


def _text(text):
    return ModelReply(text, [], "end_turn", 10, 5)


def _call(name, tool_input=None, tokens=(10, 5)):
    return ModelReply("", [{"id": f"id_{name}", "name": name, "input": tool_input or {}}],
                      "tool_use", *tokens)


def _run(client, spec=None, tools=None, **kw):
    spec = spec or session_spec("reflection")
    executed = []

    async def execute(name, tool_input):
        executed.append(name)
        return {"success": True}
    tools = tools if tools is not None else [{"name": n} for n in spec.tool_names()]
    out = asyncio.run(run_loop(spec=spec, client=client, model="m", system="sys", tools=tools,
                               messages=[{"role": "user", "content": "begin"}], execute=execute, **kw))
    return out, executed


def test_a_reply_without_a_tool_call_is_nudged_then_she_finishes():
    client = StubClient([_text("I'd look at my observations next."),
                         _call("list_observations"),
                         _call("session_complete", {"summary": "Looked."})])
    out, executed = _run(client)
    assert out.end_reason == "I said I was done" and out.completion == {"summary": "Looked."}
    assert out.nudges == 1 and out.steps[0].nudged
    assert executed == ["list_observations", "session_complete"]
    # The nudge went to the model as a user message naming the end tool.
    second = client.calls[1]["messages"]
    assert second[-1] == {"role": "user", "content": nudge_text("session_complete")}
    assert "session_complete" in second[-1]["content"]


def test_nudges_run_out_and_the_turn_ends_saying_so():
    client = StubClient([_text("Thinking."), _text("Still thinking."), _text("never asked")])
    out, _ = _run(client, nudges=1)
    assert out.model_calls == 2 and out.nudges == 1
    assert out.status == "completed" and out.end_reason == "I stopped without saying I was done"


def test_no_end_tool_offered_means_no_nudge():
    client = StubClient([_text("Hello.")])
    out, _ = _run(client, tools=[{"name": "list_observations"}])
    assert out.model_calls == 1 and out.nudges == 0 and out.end_reason == "I finished"


def test_the_token_budget_ends_the_turn():
    client = StubClient([_call("list_observations", tokens=(600, 100)) for _ in range(5)])
    out, _ = _run(client, token_budget=1000)
    assert out.model_calls == 2  # 700 after one step, 1400 after two
    assert out.status == "completed" and out.end_reason == "reached the token budget"


def test_cache_tokens_count_toward_the_budget_and_are_kept():
    reply = ModelReply("", [{"id": "x", "name": "list_observations", "input": {}}], "tool_use",
                       10, 5, cache_read_tokens=900, cache_write_tokens=200)
    client = StubClient([reply, reply])
    out, _ = _run(client, token_budget=1000)
    assert out.model_calls == 1
    assert (out.cache_read_tokens, out.cache_write_tokens) == (900, 200)


def test_session_specs_carry_a_nudge_and_a_budget():
    spec = session_spec("research")
    assert spec.nudges == 1 and spec.turn_token_budget


def test_history_is_neutral_between_steps():
    client = StubClient([_call("list_observations"), _call("session_complete", {"summary": "ok"})])
    _run(client)
    second = client.calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "tool"]
    assert second[1]["calls"][0]["name"] == "list_observations"
    assert second[2]["results"][0] == {"id": "id_list_observations", "name": "list_observations",
                                       "content": json.dumps({"success": True})}


# ---------------------------------------------------------------------------
# Translations (pure)
# ---------------------------------------------------------------------------

def test_anthropic_translation_pairs_tool_results_and_caches_the_newest_block():
    msgs = anthropic_messages(HISTORY)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant", "user"]
    assert msgs[1]["content"][1] == {"type": "tool_use", "id": "c1", "name": "recall_memories",
                                     "input": {"query": "tide pools"}}
    assert msgs[2]["content"][0]["type"] == "tool_result" and msgs[2]["content"][0]["tool_use_id"] == "c1"
    assert msgs[3]["content"] == [{"type": "text", "text": "(no reply)"}]  # never empty
    marked = [b for m in msgs for b in m["content"] if "cache_control" in b]
    assert marked == [msgs[-1]["content"][-1]]
    assert "cache_control" not in str(anthropic_messages(HISTORY, cache=False))
    # Translating doesn't mutate the history.
    assert "cache_control" not in str(HISTORY)


def test_openai_translation():
    msgs = openai_messages("sys", HISTORY)
    assert msgs[0] == {"role": "system", "content": "sys"}
    call = msgs[2]["tool_calls"][0]
    assert call["id"] == "c1" and json.loads(call["function"]["arguments"]) == {"query": "tide pools"}
    assert msgs[3] == {"role": "tool", "tool_call_id": "c1", "content": '{"hits": 2}'}
    assert msgs[4]["content"] == "(no reply)"


def test_ollama_translation():
    msgs = ollama_messages("sys", HISTORY)
    assert msgs[2]["tool_calls"] == [{"function": {"name": "recall_memories",
                                                   "arguments": {"query": "tide pools"}}}]
    assert msgs[3] == {"role": "tool", "content": '{"hits": 2}', "tool_name": "recall_memories"}


# ---------------------------------------------------------------------------
# Each client through llm_caller, against the fake LLM
# ---------------------------------------------------------------------------

TOOLS = [{"name": "recall_memories", "description": "Search memories.",
          "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}},
         {"name": "session_complete", "description": "End.",
          "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}}}]


def _ledger(call_site):
    from database import get_db
    with get_db() as conn:
        return [tuple(r) for r in conn.execute(
            "SELECT provider, model FROM token_usage_records WHERE call_site = ?", (call_site,))]


def _drive(client, model):
    async def execute(name, tool_input):
        return {"memories": ["the tide pools at dusk"]} if name == "recall_memories" else {"ok": True}
    spec = session_spec("reflection")
    return asyncio.run(run_loop(spec=spec, client=client, model=model, system="I am here.",
                                tools=TOOLS, messages=[{"role": "user", "content": "begin"}],
                                execute=execute))


def _script(fake):
    fake.queue_tool_use("recall_memories", {"query": "tide pools"})
    fake.queue_text("I'd write the summary now.")      # nudged
    fake.queue_tool_use("session_complete", {"summary": "Remembered the tide pools."})


@pytest.fixture
def fake(fake_llm):
    pytest.importorskip("anthropic")
    return fake_llm


def test_anthropic_client_caches_and_runs_the_turn(fake):
    from agent_loop.models import AnthropicModelClient
    _script(fake)
    out = _drive(AnthropicModelClient(), "claude-haiku-4-5-20251001")
    assert out.completion == {"summary": "Remembered the tide pools."} and out.nudges == 1
    first, last = fake.calls[0].kwargs, fake.calls[-1].kwargs
    assert first["system"] == [{"type": "text", "text": "I am here.", "cache_control": {"type": "ephemeral"}}]
    assert first["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in first["tools"][0]
    assert "cache_control" not in TOOLS[-1]  # the caller's list is untouched
    # Tool result paired with its call, the nudge as the newest (cached) message.
    results = [b for m in last["messages"] for b in m["content"] if b.get("type") == "tool_result"]
    assert results[0]["tool_use_id"] == fake.calls[0].response.tool_uses[0]["id"]
    assert "tide pools at dusk" in results[0]["content"]
    assert last["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert _ledger("session.generic") == [("anthropic", "claude-haiku-4-5-20251001")] * 3


def test_openai_client_runs_the_turn(fake, monkeypatch):
    pytest.importorskip("openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from agent_loop.models import OpenAIModelClient
    _script(fake)
    out = _drive(OpenAIModelClient(), "gpt-4o")
    assert out.completion == {"summary": "Remembered the tide pools."}
    assert [c.source for c in fake.calls] == ["openai.async"] * 3
    first, last = fake.calls[0].kwargs, fake.calls[-1].kwargs
    assert first["model"] == "gpt-4o" and first["messages"][0] == {"role": "system", "content": "I am here."}
    assert fake.calls[0].tool_names == ["recall_memories", "session_complete"]
    tool_msg = next(m for m in last["messages"] if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == fake.calls[0].response.tool_uses[0]["id"]
    assert _ledger("session.generic") == [("openai", "gpt-4o")] * 3


def test_ollama_client_runs_the_turn_with_num_ctx(fake):
    from agent_loop.models import OllamaModelClient
    _script(fake)
    out = _drive(OllamaModelClient(num_ctx=16384), "qwen3:14b")
    assert out.completion == {"summary": "Remembered the tide pools."}
    assert [c.source for c in fake.calls] == ["ollama"] * 3
    first, last = fake.calls[0].kwargs, fake.calls[-1].kwargs
    assert first["endpoint"] == "chat" and first["model"] == "qwen3:14b"
    assert first["options"]["num_ctx"] == 16384
    assert first["tools"][0]["function"]["name"] == "recall_memories"
    tool_msg = next(m for m in last["messages"] if m["role"] == "tool")
    assert tool_msg["tool_name"] == "recall_memories" and "tide pools at dusk" in tool_msg["content"]
    # Synthesized call ids are unique across the turn.
    ids = [c["id"] for s in out.steps for c in s.tool_calls]
    assert len(ids) == len(set(ids)) == 2
    assert _ledger("session.generic") == [("ollama", "qwen3:14b")] * 3


@pytest.mark.parametrize("provider,model,cls", [
    ("anthropic", "claude-sonnet-4-6", "AnthropicModelClient"),
    ("openai", "gpt-4o", "OpenAIModelClient"),
    ("ollama", "qwen3:14b", "OllamaModelClient"),
])
def test_the_call_sites_assignment_picks_the_client(provider, model, cls):
    from agent_loop import models
    from llm_config import LLMConfigManager, ModelAssignment
    client, chosen = models.model_client_for("session.generic", "claude-haiku-4-5-20251001")
    assert type(client).__name__ == "AnthropicModelClient" and chosen == "claude-haiku-4-5-20251001"
    LLMConfigManager().set("session.generic", ModelAssignment(provider, model))
    client, chosen = models.model_client_for("session.generic", "claude-haiku-4-5-20251001")
    assert type(client).__name__ == cls and chosen == model and client.provider == provider


# ---------------------------------------------------------------------------
# A whole session through the Turn, on a local model
# ---------------------------------------------------------------------------

def test_a_session_runs_through_the_turn_on_an_ollama_assignment(tmp_path, fake, levers):
    pytest.importorskip("networkx")  # agent_client (the kernel) imports it
    from agent_loop import interrupt
    from llm_config import LLMConfigManager, ModelAssignment
    from scheduler.actions.session_handlers import reflection_action
    from self_model import SelfManager
    from session import GenericSessionRunner

    interrupt.reset()
    LLMConfigManager().set("session.generic", ModelAssignment("ollama", "qwen3:14b"))
    runner = GenericSessionRunner(data_dir=tmp_path, model="claude-haiku-4-5-20251001")
    managers = {"session_runner": runner, "self_manager": SelfManager(), "data_dir": tmp_path}
    fake.queue_tool_use("add_observation", {"observation": "On a local model, I still notice the quiet."})
    fake.queue_tool_use("session_complete", {"summary": "A quiet look, run locally."})
    with levers(agent_loop=True):
        action = asyncio.run(reflection_action({"managers": managers, "duration_minutes": 5,
                                                "max_turns": 4}))
    interrupt.reset()

    assert action.success, action.message
    assert action.data["summary"] == "A quiet look, run locally."
    assert [c.source for c in fake.calls] == ["ollama", "ollama"]
    assert "## THIS MOMENT" in fake.calls[0].kwargs["messages"][0]["content"]
    texts = [o.observation for o in SelfManager().load_observations()]
    assert "On a local model, I still notice the quiet." in texts
    log = json.loads(next((runner.logs_dir / "reflection").rglob("*.json")).read_text())
    assert log["provider"] == "ollama" and log["model"] == "qwen3:14b"
    assert log["estimated_cost_usd"] == 0.0
