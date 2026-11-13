"""Found by the 2026-11-13 live check: one oversized tool result (her
list_growth_edges, 1.9 MB) took a whole session down at 466k tokens."""
import asyncio
from types import SimpleNamespace

from agent_loop.loop import MAX_TOOL_RESULT_CHARS, ModelReply, cap_tool_result, run_loop
from agent_loop.spec import session_spec


def test_cap_leaves_small_results_alone_and_says_when_it_cuts():
    assert cap_tool_result("short") == "short"
    cut = cap_tool_result("x" * (MAX_TOOL_RESULT_CHARS + 500))
    assert cut.startswith("x" * 100) and "result cut at 20000 of 20500 characters" in cut
    assert len(cut) < MAX_TOOL_RESULT_CHARS + 200


def test_an_oversized_result_reaches_the_model_capped():
    sent = []

    class Client:
        provider = "fake"

        async def create(self, *, model, system, tools, messages, max_tokens):
            sent.append(messages)
            if len(sent) == 1:
                return ModelReply("", [{"id": "c1", "name": "big", "input": {}}], "tool_use", 1, 1)
            return ModelReply("", [{"id": "c2", "name": "session_complete", "input": {"summary": "ok"}}],
                              "tool_use", 1, 1)

    async def execute(name, tool_input):
        return "y" * 2_000_000 if name == "big" else {"ok": True}

    tools = [{"name": "big", "description": "", "input_schema": {"type": "object"}},
             {"name": "session_complete", "description": "", "input_schema": {"type": "object"}}]
    out = asyncio.run(run_loop(spec=session_spec("reflection"), client=Client(), model="m", system="s",
                               tools=tools, messages=[{"role": "user", "content": "go"}], execute=execute))
    assert out.status == "completed"
    tool_turn = sent[1][-1]
    assert len(tool_turn["results"][0]["content"]) < MAX_TOOL_RESULT_CHARS + 200


def test_list_growth_edges_returns_the_top_few_not_all():
    from session.tools import handle_list_growth_edges
    edges = [SimpleNamespace(edge_id=str(i), area=f"a{i}", current_state="", desired_state="",
                             observations=[], importance=i / 100, last_touched="") for i in range(100)]
    managers = {"self_manager": SimpleNamespace(load_profile=lambda: SimpleNamespace(growth_edges=edges))}
    out = asyncio.run(handle_list_growth_edges({}, managers))
    assert out["total"] == 100 and out["showing"] == 20
    assert out["growth_edges"][0]["title"] == "a99"
    assert asyncio.run(handle_list_growth_edges({"limit": 5}, managers))["showing"] == 5
