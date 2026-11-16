"""Chat on the loop (plan "Cass's agent loop", phase 7, first item): the
pieces the smoke test (tests/smoke/test_chat_entry_points.py) doesn't show."""
import asyncio

import features
from agent_loop.conversation import history_from
from agent_loop.spec import conversation_spec


def test_lever_is_off_by_default():
    assert features.LEVERS["agent_loop_chat"].default is False


def test_a_conversation_has_her_chat_tools_and_no_end_tool():
    spec = conversation_spec()
    names = spec.tool_names()
    assert {"recall", "lately_open", "find_tools", "use_tool", "workspace_read"} <= set(names)
    assert "session_complete" not in names, "her reply ends the turn, as in chat today"
    assert spec.nudges == 0 and spec.refusable_for_budget is False
    assert "record_self_observation" in spec.writes.guarded_fields, "memory writes are voice-guarded"
    assert "babelr_read" not in conversation_spec(chapter_house=False).tool_names()


def test_history_is_text_in_the_loops_shape():
    got = history_from([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"},
                        {"role": "user", "content": ""}])
    assert got == [{"role": "user", "content": "hi"},
                   {"role": "assistant", "text": "hello", "calls": []}]


def test_tools_act_for_the_person_she_is_with(monkeypatch):
    import websocket_handlers as ws
    from agent_loop.tools import live_router
    seen = {}

    def make_ctx(**kw):
        seen.update(kw)
        return kw

    async def batch(calls, ctx, executors):
        return [{"result": "ok"}]

    monkeypatch.setitem(ws._state, "create_tool_context", make_ctx)
    monkeypatch.setitem(ws._state, "tool_executors", {"x": object()})
    monkeypatch.setitem(ws._state, "execute_tool_batch", batch)
    person = {"user_id": "u-ann", "user_name": "Ann", "conversation_id": "c-1", "project_id": None}
    assert asyncio.run(live_router("d", person=person)("add_task", {})) == "ok"
    assert seen == {"user_id": "u-ann", "user_name": "Ann", "conversation_id": "c-1", "project_id": None}
