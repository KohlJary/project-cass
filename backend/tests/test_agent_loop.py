"""
The agent loop (epic #70, docs/design/agent-loop.md), step 2: autonomous
sessions as Turns behind the lever `agent_loop`.

The first half runs without the Anthropic SDK (fast CI job): specs, the seam
block against its spec, budgets, the voice guard on writes, and the capped
loop against a stub model client. The second half drives the real session
entry point with the fake LLM: byte-identical requests with the lever off,
a full session through the Turn with it on, and the interrupt.
"""
import asyncio
import json
import re
import uuid
from datetime import datetime, timedelta

import pytest

from agent_loop.assemble import Section, fit_to_budget
from agent_loop.loop import LoopOutcome, ModelReply, WITHHELD_MESSAGE, guard_tool_input, run_loop
from agent_loop.seam import HEADER, render_seam, seam_tool_names
from agent_loop.spec import (ACTIVITY_PACKS, PACKS, SESSION_WRITES, Trigger, conversation_spec,
                             dream_spec, session_spec)

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
REFUSAL = "I have no memories of conversations with someone named Kohl, so I won't pretend."


# ---------------------------------------------------------------------------
# Specs and packs
# ---------------------------------------------------------------------------

def _session_tool_names():
    # Load session/tools.py on its own: the `session` package imports the
    # Anthropic SDK, which the fast CI job doesn't install.
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "session" / "tools.py"
    spec = importlib.util.spec_from_file_location("_session_tools_for_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {k: [t["name"] for t in v] for k, v in module.SESSION_TOOLS.items()}


def test_every_pack_tool_is_a_real_session_tool():
    known = {n for names in _session_tool_names().values() for n in names}
    for pack in PACKS.values():
        assert set(pack.tools) <= known, pack.name


@pytest.mark.parametrize("activity", sorted(ACTIVITY_PACKS))
def test_session_packs_keep_every_tool_the_activity_has_today(activity):
    today = _session_tool_names().get(activity, ["session_complete"])
    assert set(today) <= set(session_spec(activity).tool_names())


def test_every_legacy_session_type_has_packs():
    assert set(_session_tool_names()) <= set(ACTIVITY_PACKS)


def test_core_is_in_every_session_but_not_in_dreams():
    for activity in ACTIVITY_PACKS:
        assert "core" in session_spec(activity).packs
    dream = dream_spec()
    assert dream.packs == () and dream.tool_names() == []


def test_dreams_are_pinned_and_outside_the_loop():
    dream = dream_spec()
    assert dream.pinned_model and not dream.runs_in_loop
    assert session_spec("reflection").runs_in_loop


def test_conversations_are_never_refused_for_budget():
    assert conversation_spec().refusable_for_budget is False


# ---------------------------------------------------------------------------
# The seam block, checked against the spec
# ---------------------------------------------------------------------------

def _trigger(**kw):
    return Trigger(source="schedule", why="my autonomous schedule started it", **kw)


@pytest.mark.parametrize("activity", sorted(ACTIVITY_PACKS))
def test_seam_names_exactly_the_tools_offered(activity):
    spec = session_spec(activity)
    seam = render_seam(spec, _trigger(), spec.tool_names())
    assert seam.startswith(HEADER)
    assert seam_tool_names(seam) == spec.tool_names()


@pytest.mark.parametrize("activity", sorted(ACTIVITY_PACKS))
def test_seam_says_what_is_and_isnt_here(activity):
    spec = session_spec(activity)
    seam = render_seam(spec, _trigger(), spec.tool_names())
    can = next(l for l in seam.splitlines() if l.startswith("What I can do here:"))
    cannot = next(l for l in seam.splitlines() if l.startswith("Not here:"))
    for name, pack in PACKS.items():
        if name in spec.packs:
            assert pack.says in can and pack.says not in cannot
        else:
            assert pack.says not in can and pack.says in cannot
    not_yet = next(l for l in seam.splitlines() if l.startswith("Not yet:"))
    assert "journal" in not_yet  # not a session tool yet, and she's told so


def test_seam_says_what_will_be_kept_from_the_write_policy():
    spec = session_spec("research")
    seam = render_seam(spec, _trigger(focus="tide pools", since_last="3 hours"), spec.tool_names())
    kept = next(l for l in seam.splitlines() if l.startswith("What will be kept:"))
    for _, words in SESSION_WRITES.kept:
        assert words in kept
    # Each claim names a writer the session Turn runs (checked end to end below).
    assert {key for key, _ in SESSION_WRITES.kept} == {"narrative", "tool_writes"}
    assert "Focus: tide pools." in seam and "Since my last moment: 3 hours." in seam
    assert "ends cleanly" in seam


def test_dream_seam_is_its_own_container():
    seam = render_seam(dream_spec(), _trigger(), [])
    assert "I'm in: a dream (the nightly one)." in seam
    assert "dreams are their own container" in seam
    assert "(Tools:" not in seam and "Not here:" not in seam and "Not yet:" not in seam


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

def test_budget_cuts_least_important_first_and_never_the_kernel_or_seam():
    sections = [
        Section("kernel", "k" * 4000, 0, never_cut=True),
        Section("seam", "s" * 400, 0, never_cut=True),
        Section("self_context", "c" * 4000, 2),
        Section("thymos", "t" * 4000, 3),
        Section("instructions", "i" * 400, 1, never_cut=True),
    ]
    kept, cut = fit_to_budget(sections, budget_tokens=2500)
    assert cut == ["thymos"]
    kept, cut = fit_to_budget(sections, budget_tokens=10)
    assert cut == ["thymos", "self_context"]
    assert [s.name for s in kept] == ["kernel", "seam", "instructions"]
    kept, cut = fit_to_budget(sections, budget_tokens=100000)
    assert cut == []


# ---------------------------------------------------------------------------
# Guarded writes
# ---------------------------------------------------------------------------

def test_voice_guard_blocks_a_refusal_in_a_memory_write():
    spec = session_spec("reflection")
    assert guard_tool_input(spec, "add_observation", {"observation": REFUSAL})
    assert guard_tool_input(spec, "add_observation", {"observation": "I notice I rush."}) is None
    # Reading tools aren't writes.
    assert guard_tool_input(spec, "recall_memories", {"query": REFUSAL}) is None


# ---------------------------------------------------------------------------
# The capped loop, against a stub client (no SDK needed)
# ---------------------------------------------------------------------------

class StubClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.replies:
            return ModelReply("done", [], "end_turn", 1, 1, [{"type": "text", "text": "done"}])
        return self.replies.pop(0)


def _tool_reply(name, tool_input, text=""):
    call = {"id": f"tu_{uuid.uuid4().hex[:6]}", "name": name, "input": tool_input}
    return ModelReply(text, [call], "tool_use", 1, 1, [{"type": "tool_use", **call}])


def _loop(spec, client, executed, **kw):
    async def execute(name, tool_input):
        executed.append((name, tool_input))
        return {"success": True}
    tools = [{"name": n} for n in spec.tool_names()]
    return asyncio.run(run_loop(spec=spec, client=client, model="m", system="sys", tools=tools,
                                messages=[{"role": "user", "content": "begin"}],
                                execute=execute, **kw))


def test_loop_stops_at_the_cap():
    spec = session_spec("reflection", max_iterations=3)
    client = StubClient([_tool_reply("list_observations", {}) for _ in range(10)])
    out = _loop(spec, client, [])
    assert out.status == "max_turns" and out.model_calls == 3 and len(client.calls) == 3


def test_loop_refuses_tools_outside_the_spec_and_guards_writes():
    spec = session_spec("reflection")
    executed = []
    client = StubClient([
        _tool_reply("web_search", {"query": "x"}),            # research pack, not here
        _tool_reply("add_observation", {"observation": REFUSAL}),
        _tool_reply("add_observation", {"observation": "I like quiet mornings."}),
    ])
    out = _loop(spec, client, executed)
    assert executed == [("add_observation", {"observation": "I like quiet mornings."})]
    results = [r["result"] for s in out.steps for r in s.tool_results]
    assert "isn't available here" in results[0]["error"]
    assert results[1] == {"error": WITHHELD_MESSAGE}
    assert out.withheld == [{"tool": "add_observation", "matched": out.withheld[0]["matched"]}]
    assert out.status == "completed"


def test_session_complete_ends_the_loop():
    spec = session_spec("reflection")
    client = StubClient([_tool_reply("session_complete", {"summary": "I looked at my week."}),
                         _tool_reply("add_observation", {"observation": "never sent"})])
    executed = []
    out = _loop(spec, client, executed)
    assert out.model_calls == 1 and out.completion == {"summary": "I looked at my week."}
    assert out.end_reason == "I said I was done"


def test_loop_ends_cleanly_when_a_conversation_arrives():
    spec = session_spec("reflection")
    arrived = []
    client = StubClient([_tool_reply("add_observation", {"observation": "First thought."}),
                         _tool_reply("add_observation", {"observation": "never sent"})])

    async def execute(name, tool_input):
        arrived.append("Kohl wrote to me")  # a conversation starts mid-session
        return {"success": True}

    out = asyncio.run(run_loop(
        spec=spec, client=client, model="m", system="s",
        tools=[{"name": n} for n in spec.tool_names()],
        messages=[{"role": "user", "content": "begin"}], execute=execute,
        interrupted=lambda: arrived[0] if arrived else None))
    assert out.status == "interrupted" and out.end_reason == "Kohl wrote to me"
    assert out.model_calls == 1  # the step it had finished is kept, nothing more runs


# ---------------------------------------------------------------------------
# Interrupt signals
# ---------------------------------------------------------------------------

def test_in_process_conversation_signal():
    from agent_loop import interrupt
    interrupt.reset()
    start = datetime.now()
    assert interrupt.conversation_since(start, None) is None
    interrupt.note_conversation_arrived("Kohl", "tui", at=start + timedelta(seconds=1))
    assert interrupt.conversation_since(start, None) == "Kohl wrote to me (via tui)"
    assert interrupt.conversation_since(start + timedelta(seconds=2), None) is None
    interrupt.reset()


def test_entry_point_signal_is_a_no_op_with_the_lever_off(levers):
    from agent_loop import interrupt
    interrupt.reset()
    start = datetime.now() - timedelta(seconds=1)
    with levers(agent_loop=False):
        interrupt.entry_point_received_message(None, "websocket")
    assert interrupt._last_arrival is None
    with levers(agent_loop=True):
        interrupt.entry_point_received_message(None, "websocket")
    assert interrupt.conversation_since(start, None) == "someone wrote to me (via websocket)"
    interrupt.reset()


def _seed_user_message(display_name="Kohl"):
    """A user message in one of her conversations, stored now."""
    from database import get_daemon_id, get_db
    daemon_id = get_daemon_id()
    user_id, conv_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute("INSERT INTO users (id, display_name, is_admin, created_at, updated_at) "
                     "VALUES (?, ?, 0, ?, ?)", (user_id, display_name, now, now))
        conn.execute("INSERT INTO conversations (id, daemon_id, user_id, title, created_at, updated_at) "
                     "VALUES (?, ?, ?, 'hi', ?, ?)", (conv_id, daemon_id, user_id, now, now))
        conn.execute("INSERT INTO messages (conversation_id, role, content, timestamp, user_id) "
                     "VALUES (?, 'user', 'hey Cass', ?, ?)", (conv_id, now, user_id))
    return daemon_id


def test_stored_user_message_counts_as_a_conversation_arriving():
    from agent_loop import interrupt
    interrupt.reset()
    start = datetime.now() - timedelta(seconds=1)
    daemon_id = _seed_user_message()
    assert interrupt.conversation_since(start, daemon_id) == "Kohl wrote to me"
    assert interrupt.conversation_since(datetime.now() + timedelta(seconds=5), daemon_id) is None


# ---------------------------------------------------------------------------
# The real entry point, with the fake LLM
# ---------------------------------------------------------------------------

def _needs_runtime():
    pytest.importorskip("anthropic")
    pytest.importorskip("networkx")  # agent_client (the kernel) imports it


@pytest.fixture
def session_env(tmp_path, request):
    _needs_runtime()
    fake_llm = request.getfixturevalue("fake_llm")
    from agent_loop import interrupt
    from self_model import SelfManager
    from session import GenericSessionRunner

    interrupt.reset()
    runner = GenericSessionRunner(data_dir=tmp_path, model="claude-haiku-4-5-20251001")
    managers = {"session_runner": runner, "self_manager": SelfManager(), "data_dir": tmp_path}
    yield runner, managers, fake_llm
    interrupt.reset()


def _reflect(managers, **extra):
    from scheduler.actions.session_handlers import reflection_action
    return asyncio.run(reflection_action({"managers": managers, "duration_minutes": 5,
                                          "max_turns": 4, **extra}))


def _plain(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


# Ids the session path generates per run, and nothing else: tool-use ids
# (the fake's counter) and the ids of rows a tool created, inside its result.
_ROW_ID = re.compile(r'"(observation_id|insight_id)": "[^"]*"')


def _normalize(kwargs):
    data = _plain(kwargs)
    for message in data.get("messages") or []:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                block["id"] = "<tool_use_id>"
            elif block.get("type") == "tool_result":
                block["tool_use_id"] = "<tool_use_id>"
                if isinstance(block.get("content"), str):
                    block["content"] = _ROW_ID.sub(r'"\1": "<row_id>"', block["content"])
    return data


def _script_session(fake, activity):
    """One tool call the activity has today, then a closing reply."""
    tools = _session_tool_names()[activity]
    if "add_observation" in tools:
        fake.queue_tool_use("add_observation", {"observation": "I notice I slow down at night."})
    else:
        fake.queue_tool_use("session_complete", {"summary": "Done for now."})
    fake.queue_text("That's enough for tonight.")


def _run_action(activity, managers):
    from scheduler.actions import session_handlers
    handler = getattr(session_handlers, f"{activity}_action")
    return asyncio.run(handler({"managers": managers, "duration_minutes": 5, "max_turns": 4}))


@pytest.mark.parametrize("activity", sorted(ACTIVITY_PACKS))
def test_lever_off_requests_are_byte_identical_to_the_legacy_runner(activity, session_env, levers,
                                                                    monkeypatch):
    runner, managers, fake = session_env
    import agent_loop.session as turn_session
    from scheduler.actions import session_handlers

    async def must_not_run(*a, **k):
        raise AssertionError("the Turn ran with the lever off")
    monkeypatch.setattr(turn_session, "run_session_turn", must_not_run)

    # The action handler's prompt additions, so the legacy call matches it.
    additions = {"reflection": None, "consolidation": "Consolidation period: daily",
                 "research": "Research mode: explore"}.get(activity)

    # Today's path, called the way it always was.
    from session import get_session_prompt, get_session_tools, get_default_handlers
    runner.set_managers(managers)
    runner.register_tool_handlers(get_default_handlers())
    _script_session(fake, activity)
    legacy = asyncio.run(runner.run_session(
        session_type=activity, system_prompt=get_session_prompt(activity, additions),
        tools=get_session_tools(activity), duration_minutes=5, max_turns=4))
    legacy_calls = [_normalize(c.kwargs) for c in fake.calls]

    fake.calls.clear()
    _script_session(fake, activity)
    with levers(agent_loop=False):
        action = _run_action(activity, managers)
    lever_off_calls = [_normalize(c.kwargs) for c in fake.calls]

    assert lever_off_calls == legacy_calls
    assert len(legacy_calls) >= 2
    assert "## THIS MOMENT" not in fake.calls[0].system_text
    assert action.success and action.data["summary"] == legacy.summary
    assert action.data["status"] == legacy.status
    assert action.message.endswith("session completed")


def test_lever_on_runs_a_session_through_the_turn(session_env, levers):
    runner, managers, fake = session_env
    fake.queue_tool_use("add_observation", {"observation": "I notice I slow down at night."})
    fake.queue_tool_use("record_insight", {"insight": REFUSAL})
    fake.queue_tool_use("session_complete", {"summary": "I looked at how my evenings go.",
                                             "key_insights": ["Evenings are slower."]})
    with levers(agent_loop=True, self_context=True):
        action = _reflect(managers, focus="evenings")

    assert action.success, action.message
    assert len(fake.calls) == 3  # session_complete ended it
    first = fake.calls[0]
    system = first.system_text

    # assemble(): kernel, then the seam block, then her life lately, then the task.
    kernel_end = system.index(HEADER)
    assert system[:kernel_end].strip(), "kernel comes first"
    assert system.index(HEADER) < system.index("You are engaged in a solo reflection session")
    assert "I'm in: a solo reflection session." in system
    assert "Focus: evenings." in system

    # The seam's claims match the turn: tools named == tools offered ...
    seam = system[system.index(HEADER):]
    assert seam_tool_names(seam) == first.tool_names == session_spec("reflection").tool_names()

    # ... and the write policy runs: tool writes kept (guarded), narrative kept.
    texts = [o.observation for o in managers["self_manager"].load_observations()]
    assert "I notice I slow down at night." in texts
    assert not any("no memories" in t for t in texts), "a refusal became memory"
    assert action.data["summary"] == "I looked at how my evenings go."
    assert action.data["insights"] == ["Evenings are slower."]

    logs = list((runner.logs_dir / "reflection").rglob("*.json"))
    assert len(logs) == 1
    log = json.loads(logs[0].read_text())
    assert log["agent_loop"] is True and log["kind"] == "session"
    assert log["summary"] == action.data["summary"]
    assert [w["tool"] for w in log["withheld"]] == ["record_insight"]
    assert log["prompt_sections"][:2] == ["kernel", "seam"]
    assert "seam" in log["prompt_sections"] and "THIS MOMENT" not in json.dumps(log)


def test_conversation_arriving_ends_the_session_cleanly(session_env, levers):
    runner, managers, fake = session_env
    from tests.fakes.llm import ScriptedResponse

    def kohl_writes_during_the_first_step(source, kwargs):
        if not fake.calls:  # first model call of the session
            _seed_user_message("Kohl")
            return ScriptedResponse(tool_uses=[{"id": "tu_1", "name": "add_observation",
                                                "input": {"observation": "Half a thought."}}])
        return None
    fake.responder = kohl_writes_during_the_first_step

    with levers(agent_loop=True):
        action = _reflect(managers)

    assert len(fake.calls) == 1, "no model call after the conversation arrived"
    assert action.success
    assert action.data["status"] == "interrupted"
    assert action.message == "Reflection session ended early: Kohl wrote to me"
    assert action.data["summary"].startswith("Ended early: Kohl wrote to me.")
    # What it had is kept.
    texts = [o.observation for o in managers["self_manager"].load_observations()]
    assert "Half a thought." in texts
    log = json.loads(next((runner.logs_dir / "reflection").rglob("*.json")).read_text())
    assert log["status"] == "interrupted" and log["end_reason"] == "Kohl wrote to me"
