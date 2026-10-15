"""
Smoke (c2): every offered tool, called for real with schema-valid fake args,
gets past dispatch into its handler without a wiring error.

test_tool_routability.py proves each tool reaches an executor with a valid
signature. This battery goes one step further: it boots the app, builds a
real ToolContext (the same create_tool_context /ws uses) and calls the real
executor with arguments made from the tool's own input_schema.

The fake args are deliberately meaningless ("smoke", 1, ...), so a tool may
legitimately answer "not found", "not configured" or "X is required". What
must NOT happen is a wiring failure: an exception escaping the router, an
"Unknown tool"/"No executor" answer, or a Python error (AttributeError on a
None manager, TypeError, a SQL error) coming back as the result. Those mean
the tool can never work, whatever the model passes.

Known failures are xfail(strict=True) in KNOWN_BROKEN, same rule as the
other batteries: fix it, delete the entry.
"""
import re
from unittest import mock

import pytest

from handlers.tool_router import CONSOLIDATED_ACTION_MAP, TOOL_REGISTRY, route_tool
from tests.smoke.conftest import create_user, module_app

SELF_MODEL_AWAIT = (
    "handlers/self_model.py execute_self_model_tool awaits every handler, but "
    "this one is sync, so it always fails with \"object dict can't be used in "
    "'await' expression\" (owned by the memory/self-model fix)")

KNOWN_BROKEN = {
    **dict.fromkeys([
        "reflect_on_self", "record_self_observation", "form_opinion", "note_disagreement",
        "review_self_model", "add_growth_observation", "trace_observation_evolution",
        "recall_development_stage", "compare_self_over_time", "list_developmental_milestones",
        "get_cognitive_metrics", "get_cognitive_snapshot", "compare_cognitive_snapshots",
        "get_cognitive_trend", "list_cognitive_snapshots", "check_milestones", "list_milestones",
        "get_milestone_details", "acknowledge_milestone", "get_milestone_summary",
        "get_unacknowledged_milestones", "trace_belief_sources", "find_self_contradictions",
        "query_self_graph", "check_growth_edge_evidence", "get_graph_stats",
        "get_narration_metrics", "analyze_narration", "register_intention",
        "log_intention_outcome", "get_active_intentions", "review_friction",
        "update_intention_status", "log_situational_inference", "get_situational_inferences",
        "analyze_inference_patterns", "log_presence", "get_presence_logs",
        "analyze_presence_patterns",
    ], SELF_MODEL_AWAIT),
}

# Error text that means "the code path is broken", not "the input was wrong".
WIRING_ERRORS = re.compile(
    r"Unknown tool|No executor registered|Unhandled executor type|"
    r"object has no attribute|NoneType|can't be used in 'await'|"
    r"unexpected keyword argument|missing \d+ required positional|takes \d+ positional|"
    r"no such table|no such column|has no column named|Error binding parameter|"
    r"attempted relative import|is not defined|object is not callable|"
    r"not subscriptable|not iterable",
)


def _schemas():
    """{name: tool definition} for every tool CassAgentClient can offer."""
    import agent_client
    import tool_selector
    import discord_bot.config as discord_config

    gates = {n: (lambda message: True) for n in dir(agent_client) if n.startswith("should_include_")}
    with mock.patch.multiple(agent_client, **gates), \
            mock.patch.object(discord_config, "DISCORD_ENABLED", True), \
            mock.patch.object(agent_client, "home_assistant_available", lambda: True), \
            mock.patch.object(tool_selector, "filter_blacklisted_tools", lambda tools: tools):
        client = agent_client.CassAgentClient.__new__(agent_client.CassAgentClient)
        client.enable_tools = client.enable_memory_tools = True
        client.daemon_id = None
        return {t["name"]: t for t in client.get_tools(project_id="project-1", message="")}


SCHEMAS = _schemas()

_FAKE_BY_TYPE = {"string": "smoke", "integer": 1, "number": 0.5, "boolean": False,
                 "array": [], "object": {}}


def _fake_value(prop):
    if "enum" in prop:
        return prop["enum"][0]
    return _FAKE_BY_TYPE.get(prop.get("type"), "smoke")


def fake_args(name):
    schema = SCHEMAS[name].get("input_schema", {})
    props = schema.get("properties", {})
    args = {key: _fake_value(props.get(key, {})) for key in schema.get("required", [])}
    executor_type = TOOL_REGISTRY.get(name, "")
    if executor_type.startswith("consolidated_"):
        args.setdefault("action", next(iter(CONSOLIDATED_ACTION_MAP[executor_type])))
    return args


@pytest.fixture(scope="module")
def app(template_db, tmp_path_factory):
    with module_app(template_db, tmp_path_factory) as booted:
        yield booted


@pytest.fixture
def test_db(app):
    return app.db_path


@pytest.fixture(scope="module")
def user_id(app):
    # A real user row: several tools write rows with a users(id) foreign key.
    return create_user("Smoke Tool Tester")


@pytest.fixture(scope="module")
def conversation_id(app, user_id):
    # A real conversation row, for the same foreign-key reason.
    import main_sdk
    return main_sdk.conversation_manager.create_conversation(title="smoke", user_id=user_id).id


def _params():
    for name in sorted(SCHEMAS):
        marks = []
        if name in KNOWN_BROKEN:
            marks.append(pytest.mark.xfail(strict=True, reason=KNOWN_BROKEN[name]))
        yield pytest.param(name, id=name, marks=marks)


def test_known_broken_entries_are_still_offered():
    assert set(KNOWN_BROKEN) <= set(SCHEMAS)


@pytest.mark.parametrize("tool_name", list(_params()))
def test_tool_executes_without_wiring_error(tool_name, app, user_id, conversation_id):
    import main_sdk

    ctx = main_sdk.create_tool_context(
        user_id=user_id, user_name="Smoke", conversation_id=conversation_id,
        project_id="project-1",
    )
    result = app.portal.call(route_tool, tool_name, fake_args(tool_name), ctx, main_sdk.TOOL_EXECUTORS)

    assert isinstance(result, dict), result
    text = " ".join(str(result.get(k) or "") for k in ("error", "result"))
    assert not WIRING_ERRORS.search(text), f"{tool_name}: {text[:300]}"
