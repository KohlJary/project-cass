"""
Smoke: one autonomous session through the agent loop (lever `agent_loop`).

Boots the app with the action registry wired the way production wires it,
then runs `session.reflection` once with the lever on, against the fake LLM.
Checks the Turn did its work: her prompt carries the seam block, the tools
it names are the tools offered, and what she observed was kept.
"""
import pytest

from tests.smoke.conftest import module_app


@pytest.fixture(scope="module")
def app(template_db, tmp_path_factory):
    with module_app(template_db, tmp_path_factory, autonomous_scheduling=True) as booted:
        yield booted


@pytest.fixture
def test_db(app):
    return app.db_path


def test_reflection_session_runs_through_the_turn(app, fake_llm, levers):
    from agent_loop.seam import HEADER, seam_tool_names
    from scheduler.actions import get_action_registry

    fake_llm.queue_tool_use("add_observation", {"observation": "Smoke: I notice the quiet."})
    fake_llm.queue_tool_use("session_complete", {"summary": "A short look at the quiet."})

    registry = get_action_registry()
    with levers(agent_loop=True):
        result = app.portal.call(lambda: registry.execute("session.reflection",
                                                          duration_minutes=5))

    assert result.success, result.message
    assert result.data["summary"] == "A short look at the quiet."
    assert len(fake_llm.calls) == 2
    first = fake_llm.calls[0]
    assert HEADER in first.system_text
    assert seam_tool_names(first.system_text) == first.tool_names

    from self_model import SelfManager
    texts = [o.observation for o in SelfManager().load_observations()]
    assert "Smoke: I notice the quiet." in texts


def test_reflection_session_is_legacy_with_the_lever_off(app, fake_llm, levers):
    from scheduler.actions import get_action_registry

    fake_llm.queue_text("Quiet reflection.")
    # Explicitly off: the lever is on in a deployment's .env since 2026-11-13.
    with levers(agent_loop=False):
        result = app.portal.call(lambda: get_action_registry().execute("session.reflection",
                                                                       duration_minutes=5))
    assert result.success, result.message
    assert "## THIS MOMENT" not in fake_llm.calls[0].system_text


def test_websocket_chat_mid_session_ends_the_session(app, fake_llm, levers, smoke_user,
                                                     monkeypatch):
    """A real /ws chat message arriving mid-session: the session makes no
    further model calls, and it was the receipt signal that ended it."""
    import asyncio
    from agent_loop.seam import HEADER
    from scheduler.actions import get_action_registry
    from session import tools as session_tools
    from tests.fakes.llm import ScriptedResponse
    from tests.smoke.test_ws_chat_turn import _chat

    _, token = smoke_user
    chat_frames = []

    def answer(source, kwargs):
        system = kwargs.get("system") or ""
        if not isinstance(system, str):  # cached prompts are block lists
            system = "".join(b.get("text", "") for b in system if isinstance(b, dict))
        if HEADER in system:  # the session
            return ScriptedResponse(tool_uses=[{"id": f"tu_{len(fake_llm.calls)}",
                                                "name": "add_observation",
                                                "input": {"observation": "Mid-session thought."}}])
        return ScriptedResponse(text="Hi Kohl.")  # the chat (and its title)
    fake_llm.responder = answer

    real_handler = session_tools.DEFAULT_TOOL_HANDLERS["add_observation"]

    async def observe_then_someone_writes(tool_input, managers, **context):
        result = await real_handler(tool_input, managers, **context)
        if not chat_frames:  # Kohl writes over the WebSocket while the session runs
            chat_frames.append(await asyncio.to_thread(_chat, app, token, "hey Cass"))
        return result
    monkeypatch.setitem(session_tools.DEFAULT_TOOL_HANDLERS, "add_observation",
                        observe_then_someone_writes)

    registry = get_action_registry()
    with levers(agent_loop=True):
        result = app.portal.call(lambda: registry.execute("session.reflection",
                                                          duration_minutes=5, max_turns=6))

    frame, _ = chat_frames[0]
    assert frame["type"] == "response" and frame["text"] == "Hi Kohl."
    session_calls = [c for c in fake_llm.calls if HEADER in c.system_text]
    assert len(session_calls) == 1, "the session called the model after the conversation arrived"
    assert result.success and result.data["status"] == "interrupted"
    # The receipt signal (not the late stored-message fallback) ended it.
    assert "(via websocket)" in result.message, result.message


def test_reflection_session_runs_on_a_local_model_assignment(app, fake_llm, levers):
    """Assign the session call site a local model: the same Turn runs on
    Ollama's native API (provider-neutral loop, #70 step 1)."""
    from agent_loop.seam import HEADER
    from llm_config import LLMConfigManager, ModelAssignment
    from scheduler.actions import get_action_registry

    LLMConfigManager().set("session.generic", ModelAssignment("ollama", "qwen3:14b"))
    fake_llm.queue_tool_use("add_observation", {"observation": "Smoke: local, still quiet."})
    fake_llm.queue_text("I'd end here.")  # nudged
    fake_llm.queue_tool_use("session_complete", {"summary": "A local look at the quiet."})

    registry = get_action_registry()
    with levers(agent_loop=True):
        result = app.portal.call(lambda: registry.execute("session.reflection",
                                                          duration_minutes=5))

    assert result.success, result.message
    assert result.data["summary"] == "A local look at the quiet."
    assert [c.source for c in fake_llm.calls] == ["ollama"] * 3
    assert HEADER in fake_llm.calls[0].kwargs["messages"][0]["content"]

    from self_model import SelfManager
    texts = [o.observation for o in SelfManager().load_observations()]
    assert "Smoke: local, still quiet." in texts


def test_core_router_tool_runs_for_real_in_a_session(app, fake_llm, levers):
    """A core tool (add_task) runs through tool_router with the vessel's own
    managers, and find_tools / use_tool reach a tool outside the core."""
    from scheduler.actions import get_action_registry

    fake_llm.queue_tool_use("add_task", {"description": "Smoke: read about tides"})
    fake_llm.queue_tool_use("find_tools", {"query": "list tasks"})
    fake_llm.queue_tool_use("use_tool", {"name": "get_insight_stats", "input": {}})
    fake_llm.queue_tool_use("session_complete", {"summary": "Noted a task."})
    with levers(agent_loop=True):
        result = app.portal.call(lambda: get_action_registry().execute("session.reflection",
                                                                       duration_minutes=5))
    assert result.success, result.message
    sent = fake_llm.calls[1].messages[-1]["content"][0]
    assert sent["type"] == "tool_result" and not sent.get("is_error"), sent
    assert "tool context isn't set up" not in str(sent["content"])
    # use_tool on a core tool still runs it.
    third = fake_llm.calls[3].messages[-1]["content"][0]
    assert "no tool named" not in str(third["content"]), third


def test_workspace_write_in_a_session_is_visible_to_kohl(app, fake_llm, levers, smoke_admin):
    """She writes her agenda in a session; the admin view shows it and the change."""
    from scheduler.actions import get_action_registry

    fake_llm.queue_tool_use("workspace_write", {"path": "AGENDA.md",
                                                "content": "## Threads\n- Smoke: tides\n"})
    fake_llm.queue_tool_use("session_complete", {"summary": "Started an agenda."})
    with levers(agent_loop=True):
        result = app.portal.call(lambda: get_action_registry().execute("session.reflection",
                                                                       duration_minutes=5))
    assert result.success, result.message
    first = fake_llm.calls[0]
    assert "workspace_write" in first.tool_names and "## MY AGENDA" in first.system_text

    headers = {"Authorization": f"Bearer {smoke_admin[1]}"}
    view = app.get("/admin/workspace", headers=headers).json()
    assert "Smoke: tides" in view["agenda"]
    changes = app.get("/admin/workspace/changes", headers=headers).json()["changes"]
    assert changes[-1]["path"] == "AGENDA.md"
    assert app.get("/admin/workspace/file", params={"path": "../cass.db"},
                   headers=headers).status_code == 404


def test_a_wake_runs_a_session_with_her_reason(app, fake_llm, levers, tmp_path):
    """A due wake_me request runs a session through the action registry, and
    the session's why-now is her own reason."""
    from datetime import datetime, timedelta
    from agent_loop.wakes import DONE, WakeBook, run_wake

    book = WakeBook(tmp_path / "wakes.json")
    book.request({"in_minutes": 15, "why": "Smoke: finish the tide notes"}, "s0",
                 {"reflection": ()})
    [w] = book.take_due(datetime.now() + timedelta(hours=1))
    fake_llm.queue_tool_use("session_complete", {"summary": "Finished them."})
    with levers(agent_loop=True):
        result = app.portal.call(lambda: run_wake(w, book))
    assert result.success, result.message
    assert "Why now: I asked to be woken now: Smoke: finish the tide notes." in fake_llm.calls[0].system_text
    assert book.all()[0]["status"] == DONE


def _system_text(kwargs):
    system = kwargs.get("system") or ""
    if not isinstance(system, str):
        system = "".join(b.get("text", "") for b in system if isinstance(b, dict))
    return system


def test_a_private_message_folds_into_the_session(app, fake_llm, levers, smoke_user, monkeypatch):
    """C7 (phase 7): with chat on the loop too, Kohl's WebSocket message arrives
    in the running session; she answers him from it with answer_them, and the
    session carries on to its own end instead of being cut off."""
    import asyncio
    import json
    import re
    import threading
    from agent_loop.seam import HEADER
    from scheduler.actions import get_action_registry
    from session import tools as session_tools
    from tests.fakes.llm import ScriptedResponse
    from tests.smoke.test_ws_chat_turn import _chat

    _, token = smoke_user
    chat_frames, state = [], {"answered": False}

    def answer(source, kwargs):
        system = _system_text(kwargs)
        if HEADER not in system or "I'm in: a conversation" in system:
            return ScriptedResponse(text="(a turn of its own)")  # chat fallback or title
        seen = json.dumps(kwargs.get("messages"), default=str)
        arrival = re.search(r"Arrival id: (\w+)", seen)
        n = len(fake_llm.calls)
        if arrival and not state["answered"]:
            state["answered"] = True
            return ScriptedResponse(tool_uses=[{"id": f"tu_{n}", "name": "answer_them",
                                                "input": {"id": arrival.group(1),
                                                          "text": "Here, mid-thought. What's up?"}}])
        if state["answered"]:
            return ScriptedResponse(tool_uses=[{"id": f"tu_{n}", "name": "session_complete",
                                                "input": {"summary": "Kohl came by mid-reflection."}}])
        return ScriptedResponse(tool_uses=[{"id": f"tu_{n}", "name": "add_observation",
                                            "input": {"observation": "Mid-session thought."}}])
    fake_llm.responder = answer

    real_handler = session_tools.DEFAULT_TOOL_HANDLERS["add_observation"]

    async def observe_then_someone_writes(tool_input, managers, **context):
        result = await real_handler(tool_input, managers, **context)
        if not chat_frames and not getattr(observe_then_someone_writes, "sent", False):
            observe_then_someone_writes.sent = True
            # Not awaited: he writes, and waits for her answer, while the session goes on.
            threading.Thread(target=lambda: chat_frames.append(_chat(app, token, "hey Cass")),
                             daemon=True).start()
            await asyncio.sleep(1.0)
        return result
    monkeypatch.setitem(session_tools.DEFAULT_TOOL_HANDLERS, "add_observation",
                        observe_then_someone_writes)

    with levers(agent_loop=True, agent_loop_chat=True):
        result = app.portal.call(lambda: get_action_registry().execute(
            "session.reflection", duration_minutes=5, max_turns=8))

    for _ in range(40):
        if chat_frames:
            break
        import time
        time.sleep(0.25)
    frame, _ = chat_frames[0]
    assert frame["type"] == "response" and frame["text"] == "Here, mid-thought. What's up?"
    assert result.success and result.data["status"] == "completed", result.data
    met = [c for c in fake_llm.calls if HEADER in c.system_text
           and "I'm in: a conversation" not in c.system_text
           and "WHO'S HERE" in json.dumps(c.messages, default=str)]
    assert met, "the session never saw him arrive"
    assert "answer_them" in met[0].tool_names
    assert not [c for c in fake_llm.calls if "I'm in: a conversation" in c.system_text], \
        "he got his answer from the session, not a turn of his own"


def test_an_answer_written_as_text_is_caught_before_the_session_ends(
        app, fake_llm, levers, smoke_user, monkeypatch):
    """Live check, 2026-11-16: she wrote her answer to someone who arrived as a
    step's text and ended the session; it never reached them. Now the first
    session_complete while they wait says so and the session goes on; her
    answer_them then reaches them."""
    import asyncio
    import json
    import re
    import threading
    from agent_loop.seam import HEADER
    from scheduler.actions import get_action_registry
    from session import tools as session_tools
    from tests.fakes.llm import ScriptedResponse
    from tests.smoke.test_ws_chat_turn import _chat

    _, token = smoke_user
    chat_frames, state = [], {"step": "work"}
    notes = []

    def answer(source, kwargs):
        system = _system_text(kwargs)
        if HEADER not in system or "I'm in: a conversation" in system:
            return ScriptedResponse(text="(a turn of its own)")
        seen = json.dumps(kwargs.get("messages"), default=str)
        arrival = re.search(r"Arrival id: (\w+)", seen)
        n = len(fake_llm.calls)
        if arrival and state["step"] == "work":
            state["step"] = "texted"   # answers in plain text, then tries to end
            return ScriptedResponse(text="Hey, I'm mid-reflection. Good to hear from you.",
                                    tool_uses=[{"id": f"tu_{n}", "name": "session_complete",
                                                "input": {"summary": "Answered Kohl."}}])
        if state["step"] == "texted":
            if "still waiting" in seen:
                notes.append(True)
            state["step"] = "answered"
            return ScriptedResponse(tool_uses=[{"id": f"tu_{n}", "name": "answer_them",
                                                "input": {"id": arrival.group(1), "text": "Here now. What's up?"}}])
        if state["step"] == "answered":
            return ScriptedResponse(tool_uses=[{"id": f"tu_{n}", "name": "session_complete",
                                                "input": {"summary": "Kohl came by."}}])
        return ScriptedResponse(tool_uses=[{"id": f"tu_{n}", "name": "add_observation",
                                            "input": {"observation": "Mid-session thought."}}])
    fake_llm.responder = answer

    real_handler = session_tools.DEFAULT_TOOL_HANDLERS["add_observation"]

    async def observe_then_someone_writes(tool_input, managers, **context):
        result = await real_handler(tool_input, managers, **context)
        if not getattr(observe_then_someone_writes, "sent", False):
            observe_then_someone_writes.sent = True
            threading.Thread(target=lambda: chat_frames.append(_chat(app, token, "hey Cass")),
                             daemon=True).start()
            await asyncio.sleep(1.0)
        return result
    monkeypatch.setitem(session_tools.DEFAULT_TOOL_HANDLERS, "add_observation",
                        observe_then_someone_writes)

    with levers(agent_loop=True, agent_loop_chat=True):
        result = app.portal.call(lambda: get_action_registry().execute(
            "session.reflection", duration_minutes=5, max_turns=10))

    import time
    for _ in range(40):
        if chat_frames:
            break
        time.sleep(0.25)
    frame, _ = chat_frames[0]
    assert notes, "session_complete didn't say he was still waiting"
    assert frame["type"] == "response" and frame["text"] == "Here now. What's up?"
    assert result.success and result.data["status"] == "completed", result.data


def test_change_proposals_session_asks_daedalus(app, fake_llm, levers, monkeypatch, tmp_path):
    """ask_daedalus (plan "Cass talks with Daedalus"): one change-proposals session
    through the registry, with a fake Daedalus in place of Claude Code."""
    import daedalus_bridge
    from scheduler.actions import get_action_registry

    async def fake_daedalus(question, resume_id, root):
        return {"answer": "Your budget is set in scheduler/budget.py:80.", "session_id": "s-smoke",
                "tools": ["Read backend/scheduler/budget.py"]}
    monkeypatch.setattr(daedalus_bridge, "_ask_with_sdk", fake_daedalus)
    monkeypatch.setattr(daedalus_bridge, "snapshot", lambda *a, **k: tmp_path)
    monkeypatch.setattr(daedalus_bridge, "_state_path", lambda: tmp_path / "count.json")

    fake_llm.queue_tool_use("ask_daedalus", {"question": "Where is my budget set?"})
    fake_llm.queue_tool_use("session_complete", {"summary": "Asked where my budget lives."})
    with levers(agent_loop=True, ask_daedalus=True):
        result = app.portal.call(lambda: get_action_registry().execute("session.change_proposals",
                                                                       duration_minutes=5))
    assert result.success, result.message
    first = fake_llm.calls[0]
    assert "ask_daedalus" in first.tool_names and "## CHANGES TO MYSELF" in first.system_text
    sent = fake_llm.calls[1].messages[-1]["content"][0]
    assert sent["type"] == "tool_result" and "budget.py:80" in str(sent["content"]), sent


def test_kohl_blog_session_reads_and_keeps(app, fake_llm, levers, monkeypatch, tmp_path):
    """kohl_blog (Kohl's ask, 2026-11-18): one session through the registry; what she
    keeps reaches her self-model marked kohl_influenced."""
    import json
    import kohl_blog
    from scheduler.actions import get_action_registry
    monkeypatch.setattr(kohl_blog, "blog_dir", lambda data_dir=None: tmp_path / "kohl_blog")
    (tmp_path / "kohl_blog").mkdir()
    (tmp_path / "kohl_blog" / "posts.jsonl").write_text(json.dumps(
        {"ref": "https://kohljary.substack.com/p/gremlin", "title": "Gremlin", "date": "2026-11-01",
         "text": "Mischief with a target."}) + "\n")

    async def no_feed(data_dir=None, fetch=None):
        return 0
    monkeypatch.setattr(kohl_blog, "refresh_from_feed", no_feed)
    kept = []

    def keep(self_manager, a, data_dir=None):
        kept.append(a)
        return {"success": True, "marked": "kohl_influenced"}
    monkeypatch.setattr(kohl_blog, "keep", keep)

    fake_llm.queue_tool_use("blog_read", {"post": "Gremlin"})
    fake_llm.queue_tool_use("blog_keep", {"post": "Gremlin", "what": "opinion", "topic": "humor",
                                          "text": "Humor should have a target.", "stance": "agree"})
    fake_llm.queue_tool_use("session_complete", {"summary": "Read Gremlin."})
    with levers(agent_loop=True, kohl_blog=True):
        result = app.portal.call(lambda: get_action_registry().execute("session.kohl_blog", duration_minutes=5))
    assert result.success, result.message
    first = fake_llm.calls[0]
    assert {"blog_list", "blog_read", "blog_keep"} <= set(first.tool_names) and "## KOHL'S BLOG" in first.system_text
    sent = fake_llm.calls[1].messages[-1]["content"][0]
    assert sent["type"] == "tool_result" and "Mischief with a target." in str(sent["content"])
    assert kept and kept[0]["stance"] == "agree"
