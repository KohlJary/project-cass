"""studio (her studio, lever studio): in a workshop session she asks for the format,
renders a draft (Orphic faked) and it's committed with her message."""
import pytest

from tests.smoke.conftest import module_app


@pytest.fixture(scope="module")
def app(template_db, tmp_path_factory):
    with module_app(template_db, tmp_path_factory, autonomous_scheduling=True) as booted:
        yield booted


@pytest.fixture
def test_db(app):
    return app.db_path


def test_workshop_session_renders_a_draft(app, fake_llm, levers, monkeypatch, tmp_path):
    import sys
    import studio
    import workshop
    from scheduler.actions import get_action_registry
    from tests.test_studio import FAKE
    fake = tmp_path / "orphic"
    fake.write_text(FAKE.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
    fake.chmod(0o755)
    monkeypatch.setattr(studio, "ORPHIC", str(fake))
    monkeypatch.setattr(studio, "_root", lambda data_dir=None: tmp_path / "studio")
    monkeypatch.setattr(workshop, "root", lambda data_dir=None: tmp_path / "workshop")
    workshop.new("First Light", "other", "My first track.")
    workshop.write("first-light", "song.yaml", "title: First light\ntempo: 92\n")
    fake_llm.queue_tool_use("studio", {"action": "help"})
    fake_llm.queue_tool_use("studio", {"action": "render", "message": "First sketch"})
    fake_llm.queue_tool_use("session_complete", {"summary": "First draft.", "pick_up_next": "the chorus"})
    with levers(agent_loop=True, workshop=True, studio=True):
        result = app.portal.call(lambda: get_action_registry().execute(
            "session.workshop", duration_minutes=5, focus="first-light: the first sketch"))
    assert result.success, result.message
    assert "studio" in fake_llm.calls[0].tool_names and "My studio (studio)" in fake_llm.calls[0].system_text
    helped = fake_llm.calls[1].messages[-1]["content"][0]
    assert "song_format" in str(helped["content"]), helped
    rendered = fake_llm.calls[2].messages[-1]["content"][0]
    assert '"draft": 1' in str(rendered["content"]), rendered
    assert workshop.log("first-light")["log"][0]["message"] == "First sketch"


def test_workshop_session_offers_daedalus_in_the_project(app, fake_llm, levers, monkeypatch, tmp_path):
    """work_with_daedalus reaches the session's tools (it was built but never offered)."""
    import workshop
    from scheduler.actions import get_action_registry
    monkeypatch.setattr(workshop, "root", lambda data_dir=None: tmp_path / "workshop")
    workshop.new("Little Tool", "software", "A tool.")
    fake_llm.queue_tool_use("session_complete", {"summary": "Looked.", "pick_up_next": "start"})
    with levers(agent_loop=True, workshop=True, ask_daedalus=True):
        result = app.portal.call(lambda: get_action_registry().execute(
            "session.workshop", duration_minutes=5, focus="little-tool"))
    assert result.success, result.message
    assert "work_with_daedalus" in fake_llm.calls[0].tool_names
