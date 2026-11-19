"""listen (her ears, lever listening): reached in a session through find_tools and
use_tool; a record is read and a picture reaches the model as an image."""
import pytest

from tests.smoke.conftest import module_app


@pytest.fixture(scope="module")
def app(template_db, tmp_path_factory):
    with module_app(template_db, tmp_path_factory, autonomous_scheduling=True) as booted:
        yield booted


@pytest.fixture
def test_db(app):
    return app.db_path


def test_listen_reads_a_record_and_shows_a_picture(app, fake_llm, levers, monkeypatch, tmp_path):
    import listening
    from scheduler.actions import get_action_registry

    track = {"id": "Smoke/01 Tide Song.flac", "artist": "Smoke Band", "album": "Smoke", "title": "Tide Song",
             "track": "1", "duration": 120.0, "key": "smokekey"}
    monkeypatch.setattr(listening, "_root", lambda: tmp_path / "listening")
    monkeypatch.setattr(listening, "index", lambda *a, **k: [dict(track)])
    fake = tmp_path / "acousmatic"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setattr(listening, "ACOUSMATIC", str(fake))
    d = tmp_path / "listening" / "records" / "smokekey"
    (d / "images").mkdir(parents=True)
    (d / "record.md").write_text("# Tide Song\n\n## At a glance\n- Form: A B A\n\n## A · bars 1–4\n"
                                 "- bar 1 (0:00) C (I)\n  words: \"the tide comes in\"\n")
    (d / "images" / "overview.png").write_bytes(b"\x89PNG smoke")

    fake_llm.queue_tool_use("find_tools", {"query": "listen to music"})
    fake_llm.queue_tool_use("use_tool", {"name": "listen", "input": {"action": "read", "query": "Tide Song"}})
    fake_llm.queue_tool_use("use_tool", {"name": "listen", "input": {"action": "look", "query": "Tide Song"}})
    fake_llm.queue_tool_use("session_complete", {"summary": "Listened to Tide Song."})
    with levers(agent_loop=True, listening=True):
        result = app.portal.call(lambda: get_action_registry().execute("session.reflection", duration_minutes=5))
    assert result.success, result.message
    found = fake_llm.calls[1].messages[-1]["content"][0]
    assert "listen" in str(found["content"]), found
    read = fake_llm.calls[2].messages[-1]["content"][0]
    assert "the tide comes in" in str(read["content"]), read
    look = fake_llm.calls[3].messages[-1]["content"][0]
    assert isinstance(look["content"], list) and look["content"][1]["type"] == "image", look
    assert "_images" not in look["content"][0]["text"]


def test_listening_session_runs_with_her_ears(app, fake_llm, levers):
    """listening_session: one listening session through the registry with the fake LLM."""
    from scheduler.actions import get_action_registry
    fake_llm.queue_tool_use("session_complete", {"summary": "Listened.", "pick_up_next": "side two"})
    with levers(agent_loop=True, listening=True, listening_session=True):
        result = app.portal.call(lambda: get_action_registry().execute(
            "session.listening", duration_minutes=5, focus="One-X"))
    assert result.success, result.message
    first = fake_llm.calls[0]
    assert "## LISTENING" in first.system_text and "listen" in first.tool_names


def test_podcast_ears_follow_a_show_in_a_session(app, fake_llm, levers, monkeypatch, tmp_path):
    """talk (her ears for talk, lever talk): in a session she follows a show and lists
    its episodes through use_tool; nothing is fetched (the feed and directory are faked)."""
    import talk
    from scheduler.actions import get_action_registry
    feed = (b'<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel><title>Smoke Cast</title>'
            b'<item><title>Episode 1: The Tide</title><pubDate>Fri, 13 Nov 2026 08:00:00 GMT</pubDate>'
            b'<enclosure url="https://example.invalid/1.mp3"/><itunes:duration>3600</itunes:duration></item>'
            b'</channel></rss>')
    monkeypatch.setattr(talk, "_root", lambda: tmp_path / "talk")
    monkeypatch.setattr(talk, "_get", lambda url, timeout=30: feed)
    monkeypatch.setattr(talk, "find", lambda q, limit=5: [
        {"title": "Smoke Cast", "by": "Smoke", "feed": "https://example.invalid/feed", "slug": "smoke-cast"}])
    fake_llm.queue_tool_use("use_tool", {"name": "podcast", "input": {"action": "follow", "show": "Smoke Cast"}})
    fake_llm.queue_tool_use("use_tool", {"name": "podcast", "input": {"action": "episodes", "show": "smoke-cast"}})
    fake_llm.queue_tool_use("session_complete", {"summary": "Followed Smoke Cast."})
    with levers(agent_loop=True, talk=True):
        result = app.portal.call(lambda: get_action_registry().execute("session.reflection", duration_minutes=5))
    assert result.success, result.message
    eps = fake_llm.calls[2].messages[-1]["content"][0]
    assert "Episode 1: The Tide" in str(eps["content"]), eps
