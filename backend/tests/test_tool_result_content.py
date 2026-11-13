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
