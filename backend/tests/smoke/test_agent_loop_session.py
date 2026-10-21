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


def test_reflection_session_is_legacy_with_the_lever_off(app, fake_llm):
    from scheduler.actions import get_action_registry

    fake_llm.queue_text("Quiet reflection.")
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
        if isinstance(system, str) and HEADER in system:  # the session
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
