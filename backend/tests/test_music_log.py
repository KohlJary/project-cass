"""Her music log (music_log.py): nothing until she chooses an audience; what she hides
stays out; writing about songs carries its earlier versions; a timeline across it all."""
import json

import music_log as M


def _setup(tmp_path):
    ws = tmp_path / "workspace" / "listening"
    ws.mkdir(parents=True)
    (ws / "pain.md").write_text("Pain: now I hear the walk down in the bass.")
    (ws / "private-one.md").write_text("not for anyone yet")
    h = tmp_path / "agent_loop" / "workspace_history" / "listening__pain.md"
    h.mkdir(parents=True)
    (h / "20261118-090000-000000.txt").write_text("Pain: first listen, mostly the chorus.")
    act = tmp_path / "listening"
    act.mkdir(parents=True)
    (act / "ready.jsonl").write_text(json.dumps({"at": "2026-11-18T07:12:18", "artist": "Tool", "title": "Parabola",
                                                 "key": "k", "record": "x"}) + "\n")
    (act / "activity.jsonl").write_text(json.dumps({"at": "2026-11-18T08:30:00", "action": "read",
                                                    "artist": "Three Days Grace", "title": "Pain"}) + "\n")
    sb = tmp_path / "studio" / "sketchbook" / "1"
    sb.mkdir(parents=True)
    (sb / "sketch.json").write_text(json.dumps({"n": 1, "at": "2026-11-18T10:00:00", "instrument": {"synth": "nekobi"},
                                                "riff": "E2/1", "tempo": 100, "note": "walking down like Pain"}))


def test_nothing_until_she_chooses(tmp_path):
    _setup(tmp_path)
    out = M.build(tmp_path)
    assert out["sharing"]["audience"] == "none" and out["docs"] == [] and out["timeline"] == []
    assert M.audio("sketch", "1", tmp_path) is None


def test_shared_log_with_history_hidden_items_and_a_timeline(tmp_path):
    _setup(tmp_path)
    assert M.set_sharing("house", tmp_path)["audience"] == "house"
    assert "error" in M.set_sharing("everyone", tmp_path)
    M.set_hidden("docs", "listening/private-one.md", True, tmp_path)
    out = M.build(tmp_path)
    paths = [d["path"] for d in out["docs"]]
    assert paths == ["listening/pain.md"]
    assert out["docs"][0]["earlier"][0]["text"].startswith("Pain: first listen")
    assert any("Parabola" in e["what"] for e in out["timeline"])
    assert [c["title"] for c in out["crate"]] == ["Parabola", "Pain"]
    kinds = [e["kind"] for e in out["timeline"]]
    assert {"listening", "writing", "sketch"} <= set(kinds)
    assert out["timeline"][0]["at"] >= out["timeline"][-1]["at"]
    M.set_hidden("sketches", "1", True, tmp_path)
    assert M.build(tmp_path)["sketchbook"] == []
    M.set_hidden("sketches", "1", False, tmp_path)
    assert len(M.build(tmp_path)["sketchbook"]) == 1
