"""talk.py: her ears for talk (podcasts), lever talk. Feeds parse, episodes match,
hearing runs the transcriber in the background, transcripts read by time or words."""
import json
import time

import pytest

import talk

FEED = b"""<?xml version="1.0"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel><title>Smoke Cast</title>
<item><title>Episode 2: The Tide</title><pubDate>Fri, 13 Nov 2026 08:00:00 GMT</pubDate>
<enclosure url="https://example.invalid/2.mp3" type="audio/mpeg"/><itunes:duration>01:23:46</itunes:duration></item>
<item><title>Episode 1: The Moon</title><pubDate>Wed, 04 Nov 2026 08:00:00 GMT</pubDate>
<enclosure url="https://example.invalid/1.mp3" type="audio/mpeg"/><itunes:duration>3600</itunes:duration></item>
<item><title>No audio</title></item>
</channel></rss>"""

TRANSCRIPT = ("[0:00:00] Welcome to the show, tonight the tide.\n\n"
              "[0:12:30] The moon pulls on the water, Henry says.\n\n"
              "[1:05:00] That's the episode, thanks for listening.\n")


@pytest.fixture
def ears(tmp_path, monkeypatch, levers):
    monkeypatch.setattr(talk, "_root", lambda: tmp_path / "talk")
    monkeypatch.setattr(talk, "_get", lambda url, timeout=30: FEED)
    monkeypatch.setattr(talk, "find", lambda q, limit=5: [
        {"title": "Smoke Cast", "by": "Smoke Network", "feed": "https://example.invalid/feed", "slug": "smoke-cast"}])
    with levers(talk=True):
        yield tmp_path


def test_feed_parses_newest_first_and_skips_items_without_audio():
    f = talk.parse_feed(FEED)
    assert f["title"] == "Smoke Cast" and [e["title"] for e in f["episodes"]] == ["Episode 2: The Tide", "Episode 1: The Moon"]
    assert f["episodes"][0]["duration_s"] == 5026 and f["episodes"][1]["duration_s"] == 3600
    assert f["episodes"][0]["slug"].startswith("2026-11-13-episode-2")


def test_follow_episodes_and_match(ears):
    assert talk.handle({"action": "follow", "show": "smoke"})["following"] == "Smoke Cast"
    assert "already_following" in talk.handle({"action": "follow", "show": "smoke"})
    eps = talk.handle({"action": "episodes", "show": "smoke cast"})["episodes"]
    assert eps[0]["length"] == "1:23:46" and eps[0]["heard"] is False
    show = talk.shows()[0]
    assert talk._match_episode(show, "latest")["title"] == "Episode 2: The Tide"
    assert talk._match_episode(show, "moon")["title"] == "Episode 1: The Moon"
    assert "error" in talk.handle({"action": "read", "show": "smoke-cast", "episode": "no such thing"})


def test_hear_runs_the_transcriber_then_read_by_glance_time_and_words(ears, monkeypatch, tmp_path):
    fake = tmp_path / "hear.py"
    fake.write_text(
        "import sys, json, pathlib\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1]); out.mkdir(parents=True, exist_ok=True)\n"
        f"(out / 'transcript.md').write_text({TRANSCRIPT!r})\n"
        "(out / 'hear.json').write_text(json.dumps({'duration_s': 5026, 'words': 22}))\n")
    import sys
    monkeypatch.setattr(talk, "HEAR", sys.executable)
    monkeypatch.setattr(talk, "HEAR_SCRIPT", str(fake))
    talk.handle({"action": "follow", "show": "smoke"})
    out = talk.handle({"action": "hear", "show": "smoke", "episode": "latest"})
    assert out["hearing"] == "Episode 2: The Tide"
    for _ in range(100):
        if talk.status()["ready"]:
            break
        time.sleep(0.05)
    assert talk.status()["ready"] and "already_heard" in talk.handle({"action": "hear", "show": "smoke", "episode": "tide"})
    g = talk.handle({"action": "read", "show": "smoke", "episode": "tide"})
    assert g["part"] == "glance" and "Welcome" in g["said"] and g["length"] == "1:23:46"
    r = talk.handle({"action": "read", "show": "smoke", "episode": "tide", "part": "0:10-0:20"})
    assert "moon pulls" in r["said"] and "Welcome" not in r["said"]
    f = talk.handle({"action": "read", "show": "smoke", "episode": "tide", "find": "Henry"})
    assert f["places"] == 1 and "[0:12:30]" in f["said"]
    ready = (ears / "talk" / "ready.jsonl").read_text()
    assert "Episode 2: The Tide" in ready
    assert talk.handle({"action": "episodes", "show": "smoke"})["episodes"][0]["heard"] is True


def test_too_long_an_episode_is_said_not_started(ears, monkeypatch):
    talk.handle({"action": "follow", "show": "smoke"})
    monkeypatch.setattr(talk, "MAX_EPISODE_S", 60)
    assert "I hear up to" in talk.handle({"action": "hear", "show": "smoke", "episode": "tide"})["error"]


def test_off_says_so(levers):
    with levers(talk=False):
        assert "aren't switched on" in talk.handle({"action": "shows"})["error"]


def test_unfollow_keeps_what_was_heard(ears):
    talk.handle({"action": "follow", "show": "smoke"})
    assert talk.handle({"action": "unfollow", "show": "smoke"})["unfollowed"] == "Smoke Cast"
    assert talk.shows() == []
