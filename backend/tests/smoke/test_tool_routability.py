"""
Smoke (c): every tool the model can be offered on the websocket path is routable.

For each tool definition any chat client can offer (CassAgentClient with every
keyword gate open, plus the Ollama and OpenAI clients), call the real
`route_tool` dispatcher and assert it reached an executor with arguments that
fit that executor's real signature. This checks *dispatch*, not success: the
executors are replaced by stand-ins that only bind the call to the real
function's signature, so nothing is written and no network is touched.

Known failures from the audit are xfail(strict=True). When one gets fixed the
test XPASSes, strict turns that into a failure, and you delete its entry from
KNOWN_UNROUTABLE. That is the point: the list can only shrink.
"""
import inspect
from unittest import mock

import pytest

from handlers.tool_router import CONSOLIDATED_ACTION_MAP, TOOL_REGISTRY, ToolContext, route_tool

# Known failures from the audit. Empty means every offered tool routes; add
# an entry (with the card that found it) only for a newly discovered gap.
KNOWN_UNROUTABLE = {}


def _offered_tools():
    """Every tool definition a websocket chat client can put in front of the model.

    Returns {name: needs_project_context}. Built at collection time so each
    tool is its own test case.
    """
    import agent_client
    import openai_client
    import tool_selector
    import discord_bot.config as discord_config

    gates = {n: (lambda message: True) for n in dir(agent_client) if n.startswith("should_include_")}
    openai_gates = {n: (lambda message: True) for n in dir(openai_client) if n.startswith("should_include_")}

    def names(client, project_id):
        tools = client.get_tools(project_id=project_id, message="")
        return {t.get("name") or t.get("function", {}).get("name") for t in tools}

    # Integration-gated groups are opened too, so their tools are checked
    # even though no integration is configured under test.
    with mock.patch.multiple(agent_client, **gates), \
            mock.patch.multiple(openai_client, **openai_gates), \
            mock.patch.object(discord_config, "DISCORD_ENABLED", True), \
            mock.patch.object(agent_client, "home_assistant_available", lambda: True), \
            mock.patch.object(tool_selector, "filter_blacklisted_tools", lambda tools: tools):
        clients = []
        cass = agent_client.CassAgentClient.__new__(agent_client.CassAgentClient)
        cass.enable_tools = cass.enable_memory_tools = True
        cass.daemon_id = None
        clients.append(cass)
        ollama = agent_client.OllamaClient.__new__(agent_client.OllamaClient)
        ollama.enable_tools = True
        clients.append(ollama)
        oai = openai_client.OpenAIClient.__new__(openai_client.OpenAIClient)
        oai.enable_tools = oai.enable_memory_tools = True
        clients.append(oai)

        offered = {}
        for client in clients:
            plain = names(client, None)
            with_project = names(client, "project-1")
            for name in plain:
                offered[name] = False
            for name in with_project - plain:
                offered.setdefault(name, True)
    return offered


OFFERED = _offered_tools()


def _minimal_input(tool_name):
    executor_type = TOOL_REGISTRY.get(tool_name, "")
    if executor_type.startswith("consolidated_"):
        # Consolidated tools need a valid action to be translated.
        return {"action": next(iter(CONSOLIDATED_ACTION_MAP[executor_type]))}
    return {}


def _recording_executors(dispatched):
    """Stand-ins for main_sdk.TOOL_EXECUTORS that check call signatures only."""
    import main_sdk

    def make(key, real):
        signature = inspect.signature(real)

        def record(*args, **kwargs):
            signature.bind(*args, **kwargs)  # TypeError if the router calls it wrong
            dispatched.append(key)
            # Valid JSON so routes that json.loads() the result also work.
            return '{"success": true, "result": "dispatched"}'

        if inspect.iscoroutinefunction(real):
            async def arecord(*args, **kwargs):
                return record(*args, **kwargs)
            return arecord
        return record

    return {key: make(key, fn) for key, fn in main_sdk.TOOL_EXECUTORS.items()}


def _params():
    for name in sorted(OFFERED):
        marks = []
        if name in KNOWN_UNROUTABLE:
            marks.append(pytest.mark.xfail(strict=True, reason=KNOWN_UNROUTABLE[name]))
        yield pytest.param(name, id=name, marks=marks)


def test_offered_tool_list_is_not_empty():
    # Guards against the collection helper silently finding nothing.
    assert len(OFFERED) > 150
    assert "lookup_person" in OFFERED


def test_known_unroutable_entries_are_still_offered():
    # A stale entry (tool renamed/removed) should be deleted, not linger.
    assert set(KNOWN_UNROUTABLE) <= set(OFFERED)


@pytest.mark.parametrize("tool_name", list(_params()))
async def test_tool_is_routable(tool_name):
    dispatched = []
    executors = _recording_executors(dispatched)
    ctx = ToolContext(
        daemon_id="smoke-daemon",
        user_id="smoke-user",
        conversation_id="smoke-conversation",
        project_id="project-1" if OFFERED[tool_name] else None,
    )

    result = await route_tool(tool_name, _minimal_input(tool_name), ctx, executors)

    error = result.get("error", "") if isinstance(result, dict) else ""
    assert dispatched, f"{tool_name} was not dispatched to any executor: {error or result!r}"


async def test_longitudinal_tools_get_their_manager():
    # cards/07 (test runner): the router used to drop longitudinal_manager, so
    # the 5 longitudinal tools always answered "not available" on /ws.
    seen = {}
    manager = object()

    async def testing_executor(tool_name, tool_input, **kwargs):
        seen.update(kwargs)
        return {"success": True}

    await route_tool("list_test_batteries", {}, ToolContext(longitudinal_manager=manager),
                     {"testing": testing_executor})
    assert seen.get("longitudinal_manager") is manager


def test_tool_context_carries_longitudinal_manager_and_world_state():
    import main_sdk

    ctx = main_sdk.create_tool_context(user_id="u")
    assert ctx.longitudinal_manager is main_sdk.longitudinal_test_manager
    assert ctx.world_state_source is main_sdk.world_state_source
