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
    assert second[-1]["content"].startswith("[LOOP] ")  # marked as the loop's, not a person's


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
    # Writes at full weight, reads at a tenth: 10 + 5 + 200 + 900/10 = 305 a step.
    reply = ModelReply("", [{"id": "x", "name": "list_observations", "input": {}}], "tool_use",
                       10, 5, cache_read_tokens=900, cache_write_tokens=200)
    client = StubClient([reply] * 5)
    out, _ = _run(client, token_budget=1000)
    assert out.model_calls == 4  # 305, 610, 915, then 1220 ends it
    assert (out.cache_read_tokens, out.cache_write_tokens) == (3600, 800)


def test_cache_reads_dont_cut_off_a_normal_session():
    # The 2026-11-15 shape: ~30k tokens a step, almost all read from cache.
    from agent_loop.spec import SESSION_TOKEN_BUDGET
    reply = ModelReply("", [{"id": "x", "name": "list_observations", "input": {}}], "tool_use",
                       6, 800, cache_read_tokens=30_000, cache_write_tokens=0)
    client = StubClient([reply] * 30)
    out, _ = _run(client, token_budget=SESSION_TOKEN_BUDGET)
    assert out.end_reason.startswith("reached the cap of"), out.end_reason  # the step cap, not the budget


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


# The day-planning shape of 2026-11-17: session_complete written into the reply.
WRITTEN_END = '''Done. The plan is set.

<session_complete>
<parameter name="summary">Day planning session complete.</parameter>
<parameter name="key_insights">["one", "two"]</parameter>
</session_complete>'''


def test_session_complete_written_as_text_is_made_as_the_call():
    client = StubClient([_text(WRITTEN_END)])
    out, executed = _run(client)
    assert executed == ["session_complete"]
    assert out.end_reason == "I said I was done" and out.nudges == 0
    assert out.completion == {"summary": "Day planning session complete.", "key_insights": ["one", "two"]}
    assert out.written_end_calls == 1


def test_a_mention_of_session_complete_is_not_a_call():
    client = StubClient([_text("I'll call session_complete once I've looked."),
                         _call("session_complete", {"summary": "Looked."})])
    out, _ = _run(client)
    assert out.nudges == 1 and out.written_end_calls == 0


def test_a_refused_written_end_keeps_the_turn_going():
    from agent_loop.loop import run_loop
    spec = session_spec("reflection")
    client = StubClient([_text(WRITTEN_END), _call("session_complete", {"summary": "ok"})])
    seen = []

    async def execute(name, tool_input):
        seen.append(name)
        return {"error": "someone is waiting"} if len(seen) == 1 else {"success": True}
    out = asyncio.run(run_loop(spec=spec, client=client, model="m", system="sys",
                               tools=[{"name": n} for n in spec.tool_names()],
                               messages=[{"role": "user", "content": "begin"}], execute=execute))
    assert seen == ["session_complete", "session_complete"]
    # The written call went back to the model as a real call with its result.
    second = client.calls[1]["messages"]
    assert second[-2]["calls"][0]["name"] == "session_complete"
    assert second[-1]["role"] == "tool" and second[-1]["results"][0]["id"] == second[-2]["calls"][0]["id"]
    assert out.end_reason == "I said I was done"


# The step cap she can see coming (Kohl, 2026-11-18).

def _spec(n):
    from dataclasses import replace
    return replace(session_spec("reflection"), max_iterations=n)


def test_a_warning_comes_one_step_before_the_cap():
    from agent_loop.loop import cap_warning
    client = StubClient([_call("list_observations"), _call("list_observations"),
                         _call("session_complete", {"summary": "done", "pick_up_next": "the kernel"})])
    out, _ = _run(client, spec=_spec(3))
    warned = [m for c in client.calls for m in c["messages"] if m.get("content") == cap_warning("session_complete")]
    assert warned and out.end_reason == "I said I was done" and out.completion["pick_up_next"] == "the kernel"


def test_she_can_extend_once():
    client = StubClient([_call("extend_session"), _call("extend_session"), _call("list_observations"),
                         _call("session_complete", {"summary": "finished"})])
    out, executed = _run(client, spec=_spec(2))
    assert out.extended == 12 and out.end_reason == "I said I was done"
    results = [r for s in out.steps for r in s.tool_results if r["tool_name"] == "extend_session"]
    assert results[0]["result"]["extended_by"] == 12 and "already extended" in results[1]["result"]["error"]
    assert "extend_session" not in executed, "the loop handles it; it never reaches a tool"


def test_at_the_cap_she_writes_her_summary():
    from agent_loop.loop import cap_summary_request
    client = StubClient([_call("list_observations"), _call("list_observations"),
                         _text("I read my Thymos code and filed one ask.\\nPick up next: the vows in the kernel.")])
    out, _ = _run(client, spec=_spec(2))
    assert out.status == "max_turns" and out.summarized_at_cap
    assert out.completion["summary"].startswith("I read my Thymos code")
    assert out.completion["pick_up_next"] == "the vows in the kernel."
    assert client.calls[-1]["messages"][-1]["content"] == cap_summary_request()


def test_a_conversation_has_no_cap_warning_or_extension():
    from agent_loop.loop import run_loop
    from agent_loop.spec import conversation_spec
    spec = conversation_spec(max_iterations=2)
    client = StubClient([_call("recall_memories"), _call("recall_memories")])
    out = asyncio.run(run_loop(spec=spec, client=client, model="m", system="s",
                               tools=[{"name": "recall_memories"}, {"name": "hold_reply"}],
                               messages=[{"role": "user", "content": "hi"}],
                               execute=lambda n, i: asyncio.sleep(0, {"ok": True}), end_tool="hold_reply", nudges=0))
    assert not out.summarized_at_cap and not any("[LOOP] One step left" in str(m) for c in client.calls for m in c["messages"])


def test_a_session_opens_with_where_she_left_off_in_that_kind(tmp_path):
    import json
    from datetime import datetime
    from agent_loop.session import left_off
    now = datetime(2026, 11, 18, 9, 0)

    def log(kind, at, **kw):
        d = tmp_path / kind / at[:10]
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{at[11:13]}.json").write_text(json.dumps({"started_at": at, "summary": "read the kernel", **kw}))
    log("new_capabilities", "2026-11-18T01:22:00", pick_up_next="the vows in the kernel", summarized_at_cap=True)
    log("new_capabilities", "2026-11-17T23:00:00", pick_up_next="older note")
    log("reflection", "2026-11-18T02:00:00", pick_up_next="not this kind")
    log("new_capabilities", "2026-11-05T10:00:00", pick_up_next="too old")
    text = left_off("new_capabilities", tmp_path, now)
    assert text.startswith("## WHERE I LEFT OFF") and "the vows in the kernel" in text
    assert "ran out of steps" in text and "older note" not in text and "not this kind" not in text
    assert left_off("writing", tmp_path, now) is None
    log("writing", "2026-11-01T10:00:00", pick_up_next="stale")
    assert left_off("writing", tmp_path, now) is None


# Q1 of the coherence audit (2026-11-18): every written form she's used.

def test_every_written_form_of_session_complete_is_read():
    from agent_loop.loop import written_end_call as w
    assert w("Done.\n<session_complete>\n<summary>Read the kernel.</summary>\n<key_insights><item>a</item>"
             "<item>b</item></key_insights>\n<pick_up_next>the vows</pick_up_next>\n</session_complete>",
             "session_complete") == {"summary": "Read the kernel.", "key_insights": ["a", "b"],
                                     "pick_up_next": "the vows"}
    assert w('<session_complete summary="Planned the day." />', "session_complete") == {"summary": "Planned the day."}
    assert w("Wrapping up.\n<session_complete>\nI planned three things and I'm done.", "session_complete") == \
        {"summary": "I planned three things and I'm done."}
    assert w("Like this:\n```\n<session_complete><summary>x</summary></session_complete>\n```\nanyway",
             "session_complete") is None, "an example in a code fence isn't a call"


def test_a_bare_tag_says_plainly_that_nothing_ended():
    from agent_loop.loop import written_tag_note
    client = StubClient([_text("Done.\n<session_complete></session_complete>"),
                         _call("session_complete", {"summary": "Done for real."})])
    out, executed = _run(client)
    assert executed == ["session_complete"] and out.completion == {"summary": "Done for real."}
    assert client.calls[1]["messages"][-1]["content"] == written_tag_note("session_complete")


def test_a_found_tool_called_by_name_runs_through_use_tool():
    """Q3 of the coherence audit: she called get_recent_activity by name after
    finding it, and was told it wasn't available."""
    from agent_loop.loop import run_loop
    spec = session_spec("reflection")
    seen = []

    async def execute(name, tool_input):
        seen.append((name, tool_input))
        return {"ok": True}
    client = StubClient([_call("get_recent_activity", {"days": 2}), _call("not_a_tool"),
                         _call("session_complete", {"summary": "s"})])
    out = asyncio.run(run_loop(spec=spec, client=client, model="m", system="s",
                               tools=[{"name": n} for n in spec.tool_names()] + [{"name": "use_tool"}],
                               messages=[{"role": "user", "content": "go"}], execute=execute,
                               also_callable={"get_recent_activity"}))
    assert seen[0] == ("use_tool", {"name": "get_recent_activity", "input": {"days": 2}})
    assert "isn't available here" in out.steps[1].tool_results[0]["result"]["error"]


def test_a_social_session_runs_on_its_own_assignment_when_set():
    """session.social (Kohl, 2026-11-18: try social on Sonnet): its override wins for
    social sessions only; without one, social runs on session.generic like the rest."""
    from agent_loop.session import session_call_site
    from llm_config import LLMConfigManager, ModelAssignment
    assert session_call_site("social") == "session.generic"
    LLMConfigManager().set("session.social", ModelAssignment("anthropic", "claude-sonnet-4-6"))
    assert session_call_site("social") == "session.social"
    assert session_call_site("reflection") == "session.generic"
    assert session_call_site("no_such_type") == "session.generic"
