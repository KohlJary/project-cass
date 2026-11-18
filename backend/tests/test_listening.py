"""listen (plan "Cass's ears and studio", phase 2): the shelf, which songs a query
names, reading parts of a record, pictures as images, and the lever."""
import base64
import json
from pathlib import Path

import pytest

import listening as L
from agent_loop import models

TRACKS = [
    {"id": f"One X/{i:02d} {t}.mp3", "artist": "Three Days Grace", "album": "One X", "title": t, "track": str(i),
     "duration": 200.0, "key": f"k{i}"}
    for i, t in enumerate(["It's All Over", "Pain", "Animal I Have Become", "One X"], 1)
] + [
    {"id": f"Linkin Park - Hybrid Theory (2000)/{i:02d} {t}.mp3", "artist": "Linkin Park", "album": "Hybrid Theory",
     "title": t, "track": str(i), "duration": 200.0, "key": f"h{i}"}
    for i, t in enumerate(["Papercut", "In the End"], 1)
]

MD = """# Pain
Three Days Grace

Listening record.

## At a glance
- Length 3:20
- Form: A B A

## A · bars 1–8 · 0:00–0:16
- Harmony: key here E minor

- bar 1 (0:00) Em (i)
  words: "Pain, without love"
- bar 2 (0:02) C (VI)
  bars 3–8: same as bar 2

## B · bars 9–16 · 0:16–0:32
- bar 9 (0:16) G (III)
  words: "I want to feel"

## Methods
- x: y
"""


def test_a_query_names_an_album_or_a_song():
    assert L.find("One X", TRACKS)["kind"] == "album"
    assert len(L.find("One-X", TRACKS)["tracks"]) == 4
    song = L.find("the song One X", TRACKS)
    assert song["kind"] == "song" and song["tracks"][0]["title"] == "One X"
    assert L.find("In the End", TRACKS)["tracks"][0]["title"] == "In the End"
    assert L.find("hybrid theory", TRACKS)["kind"] == "album"
    assert L.find("nothing like this", TRACKS)["tracks"] == []


def test_reading_parts_of_a_record():
    glance = L.read_part(MD, "glance")
    assert "Form: A B A" in glance and "A · bars 1–8" in glance and "bar 1 (0:00)" not in glance
    words = L.read_part(MD, "words")
    assert '"Pain, without love"' in words and "bar 9" in words
    bars = L.read_part(MD, "bars 9-12")
    assert "G (III)" in bars and "Em (i)" not in bars
    section = L.read_part(MD, "B")
    assert "I want to feel" in section and "Pain, without love" not in section


@pytest.fixture
def shelf(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "enabled", lambda: True)
    monkeypatch.setattr(L, "_root", lambda: tmp_path / "listening")
    monkeypatch.setattr(L, "index", lambda *a, **k: [dict(t) for t in TRACKS])
    fake = tmp_path / "acousmatic"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setattr(L, "ACOUSMATIC", str(fake))
    d = tmp_path / "listening" / "records" / "k2"
    (d / "images").mkdir(parents=True)
    (d / "record.md").write_text(MD)
    (d / "images" / "overview.png").write_bytes(b"\x89PNG fake")
    return tmp_path


def test_read_and_look(shelf):
    out = L.handle({"action": "read", "query": "Pain", "part": "words"})
    assert out["song"] == "Pain" and "Pain, without love" in out["record"]
    look = L.handle({"action": "look", "query": "Pain"})
    assert look["_images"][0]["media_type"] == "image/png"
    assert base64.b64decode(look["_images"][0]["data"]) == b"\x89PNG fake"
    assert "listen first" in L.handle({"action": "read", "query": "Papercut"})["error"]


def test_the_lever(monkeypatch):
    monkeypatch.setattr(L, "enabled", lambda: False)
    assert "switched on" in L.handle({"action": "shelf"})["error"]


def test_pictures_reach_the_model_as_images():
    history = [{"role": "user", "text": "look"},
               {"role": "assistant", "text": "", "calls": [{"id": "t1", "name": "listen", "input": {}}]},
               {"role": "tool", "results": [{"id": "t1", "name": "listen", "content": "{}",
                                             "images": [{"media_type": "image/png", "data": "AAAA"}]}]}]
    a = models.anthropic_messages(history, cache=False)
    block = a[-1]["content"][0]
    assert block["type"] == "tool_result" and block["content"][1]["type"] == "image"
    o = models.openai_messages("sys", history)
    assert o[-1]["role"] == "user" and o[-1]["content"][1]["type"] == "image_url"
    plain = [{"role": "user", "text": "x"},
             {"role": "assistant", "text": "", "calls": [{"id": "t2", "name": "n", "input": {}}]},
             {"role": "tool", "results": [{"id": "t2", "name": "n", "content": "ok"}]}]
    assert models.anthropic_messages(plain, cache=False)[-1]["content"][0]["content"] == "ok"
