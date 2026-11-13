"""
A tool_result's content must be a string or a list of content blocks; the
Messages API rejects anything else and the whole chat turn fails with it.
Found 2026-11-13: Cass's babelr_boundaries get_settings returned Babelr's
JSON object as `result`, and her DM turn died with a 400.
"""
import asyncio
import json

from handlers.tool_router import execute_tool_batch, tool_result_content


def test_strings_pass_through():
    assert tool_result_content("ok") == "ok"


def test_objects_and_plain_lists_become_json_text():
    assert json.loads(tool_result_content({"dmPolicy": "anyone"})) == {"dmPolicy": "anyone"}
    assert json.loads(tool_result_content([{"actorId": "a1"}])) == [{"actorId": "a1"}]
    assert tool_result_content([]) == "[]"


def test_content_blocks_are_kept():
    blocks = [{"type": "text", "text": "here"},
              {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "x"}}]
    assert tool_result_content(blocks) is blocks


def test_execute_tool_batch_sends_an_api_object_as_text(monkeypatch):
    import handlers.tool_router as tr

    async def fake_route(tool_name, tool_input, ctx, executors):
        return {"success": True, "result": {"dmPolicy": "housemates", "allowlist": []}}
    monkeypatch.setattr(tr, "route_tool", fake_route)
    [res] = asyncio.run(execute_tool_batch(
        [{"id": "tu_1", "tool": "babelr_boundaries", "input": {"action": "get_settings"}}], None, {}))
    assert isinstance(res["result"], str)
    assert json.loads(res["result"])["dmPolicy"] == "housemates"
    assert res["is_error"] is False


def test_a_success_without_a_result_key_sends_its_fields():
    """Her Babelr tools (and ~20 handlers) report {"success", ...fields};
    those reached her as "Unknown error" before."""
    from handlers.tool_router import result_for_model
    out = result_for_model({"success": True, "plans": [{"plan": "cass-s-agent-loop-0qozz"}]})
    assert out == {"plans": [{"plan": "cass-s-agent-loop-0qozz"}]}
    assert json.loads(tool_result_content(out))["plans"][0]["plan"] == "cass-s-agent-loop-0qozz"
    assert result_for_model({"success": True, "message_id": "m1", "place": "general"}) == \
        {"message_id": "m1", "place": "general"}


def test_result_error_and_bare_success_are_unchanged():
    from handlers.tool_router import result_for_model
    assert result_for_model({"success": True, "result": "posted"}) == "posted"
    assert result_for_model({"success": False, "error": "nope"}) == "nope"
    assert result_for_model({"success": False}) == "Unknown error"
    assert result_for_model({"success": True}) == "Done."
    # A failure's other fields don't leak in place of its error.
    assert result_for_model({"success": False, "error": "403", "plans": []}) == "403"


def test_babelr_plans_list_reaches_her_through_the_batch(monkeypatch):
    import handlers.tool_router as tr

    async def fake_route(tool_name, tool_input, ctx, executors):
        return {"success": True, "plans": [{"plan": "cass-s-agent-loop-0qozz", "title": "Cass's agent loop",
                                            "status": "active", "phases_awaiting_you": 4}]}
    monkeypatch.setattr(tr, "route_tool", fake_route)
    [res] = asyncio.run(execute_tool_batch(
        [{"id": "tu_1", "tool": "babelr_plans", "input": {"action": "list"}}], None, {}))
    assert res["is_error"] is False and "Unknown error" not in res["result"]
    assert json.loads(res["result"])["plans"][0]["phases_awaiting_you"] == 4
