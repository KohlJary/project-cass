"""studio (plan "Cass's ears and studio", phase 4): a draft is committed only when it
renders, with her message; drafts can be read and compared; patches go on her gun belt."""
import json
import stat
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import studio as ST
import workshop as W

FAKE = r'''#!/usr/bin/env python3
import json, sys, os
from pathlib import Path
import numpy as np, soundfile as sf
song, out = sys.argv[2], Path(sys.argv[4])
text = open(song).read()
if "BROKEN" in text:
    print(json.dumps({"error": "bar 1 'E2/5' has 5 beats, more than 4"})); sys.exit(2)
gain = 0.5 if "loud" in text else 0.1
(out / "stems").mkdir(parents=True, exist_ok=True); (out / "listening").mkdir(exist_ok=True)
sf.write(out / "stems" / "bass.wav", np.full((4410, 2), gain), 44100)
(out / "listening" / "record.md").write_text("# Song\n\n## At a glance\n- Form: A B\n\n## A · bars 1–4\n- bar 1 (0:00) Em (i)\n")
(out / "listening" / "record.json").write_text(json.dumps({"rhythm": {"tempo": 92.0}, "harmony": {"key": {"name": "E minor"}},
    "loudness": {"integrated_lufs": -14.0 if gain > 0.2 else -20.0}, "form": {"sections": [{"label": "A", "sound": {"centroid_hz": 900}}]}}))
print(json.dumps({"title": "Song", "length_s": 10.4, "tracks": {"bass": {"plays": "nekobi"}}, "would_have_clipped": False}, indent=1))
'''


@pytest.fixture
def setup(tmp_path, monkeypatch):
    fake = tmp_path / "orphic"
    import sys
    fake.write_text(FAKE.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(ST, "ORPHIC", str(fake))
    monkeypatch.setattr(ST, "enabled", lambda: True)
    r = W.new("First Light", "other", "My first track.", data_dir=tmp_path)
    slug = r["project"]
    W.write(slug, "song.yaml", "title: x\ntempo: 92\n", data_dir=tmp_path)
    return tmp_path, slug


def test_a_draft_is_committed_with_her_message_only_when_it_renders(setup):
    data, slug = setup
    before = len(W.log(slug, data_dir=data)["log"])
    out = ST.handle({"action": "render", "project": slug, "message": "First sketch: a bass line in E minor"}, data)
    assert out["draft"] == 1 and "Form: A B" in out["what_my_ears_heard"]
    log = W.log(slug, data_dir=data)["log"]
    assert len(log) == before + 1 and log[0]["message"] == "First sketch: a bass line in E minor"
    W.write(slug, "song.yaml", "BROKEN\n", data_dir=data)
    bad = ST.handle({"action": "render", "project": slug, "message": "try"}, data)
    assert "didn't render" in bad["error"] and "5 beats" in bad["error"]
    assert len(W.log(slug, data_dir=data)["log"]) == before + 1        # nothing committed
    assert len(ST.drafts(slug, data)) == 1
    assert "message" in ST.handle({"action": "render", "project": slug, "message": ""}, data)["error"]


def test_read_compare_and_drafts(setup):
    data, slug = setup
    ST.handle({"action": "render", "project": slug, "message": "quiet bass"}, data)
    W.write(slug, "song.yaml", "title: x\ntempo: 92\n# loud\n", data_dir=data)
    ST.handle({"action": "render", "project": slug, "message": "bass up: it was buried"}, data)
    r = ST.handle({"action": "read", "project": slug, "part": "A"}, data)
    assert r["draft"] == 2 and "Em (i)" in r["record"]
    c = ST.handle({"action": "compare", "project": slug}, data)
    assert c["from"]["draft"] == 1 and c["to"]["draft"] == 2
    assert any(l.startswith("bass: +") for l in c["changes"]) and any("loudness" in l for l in c["changes"])
    ds = ST.handle({"action": "drafts", "project": slug}, data)["drafts"]
    assert [d["message"] for d in ds] == ["quiet bass", "bass up: it was buried"]


def test_patch_goes_on_the_gun_belt(tmp_path, monkeypatch):
    monkeypatch.setattr(ST, "enabled", lambda: True)
    out = ST.handle({"action": "patch", "name": "Glass Bass", "synth": "vitalium",
                     "params": {"filter_1_cutoff": 40}, "notes": "dark, round"}, tmp_path)
    assert out["saved"] == "glass-bass"
    saved = json.loads((tmp_path / "studio" / "belt" / "glass-bass.json").read_text())
    assert saved["synth"] == "vitalium" and saved["params"]["filter_1_cutoff"] == 40


def test_the_lever_and_where_she_has_it(monkeypatch):
    monkeypatch.setattr(ST, "enabled", lambda: False)
    assert "switched on" in ST.handle({"action": "help"})["error"]
    assert ST.studio_tools() is None
    monkeypatch.setattr(ST, "enabled", lambda: True)
    assert set(ST.studio_tools("x")) == {"studio"}
    import workshop_turn
    assert "studio" in workshop_turn.STUDIO_LINE


NOODLE = r'''#!/usr/bin/env python3
import json, sys
from pathlib import Path
args = sys.argv
inst = json.loads(args[args.index("--instrument") + 1])
cut = (inst.get("params") or {}).get("cutoff", 50)
print(json.dumps({"notes_heard": ["E2@0.00s", "G2@0.50s"], "sound": {"brightness": cut * 30},
                  "sound_raw": {"brightness_hz": cut * 30.0, "level_db": -6.0}, "would_have_clipped": False}))
'''


def test_noodling_keeps_sketches_and_says_what_a_knob_did(tmp_path, monkeypatch):
    import sys
    fake = tmp_path / "orphic"
    fake.write_text(NOODLE.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
    fake.chmod(0o755)
    monkeypatch.setattr(ST, "ORPHIC", str(fake))
    monkeypatch.setattr(ST, "enabled", lambda: True)
    a = ST.handle({"action": "noodle", "instrument": {"synth": "nekobi", "params": {"cutoff": 20}},
                   "riff": "E2/0.5 G2/0.5", "note": "dark"}, tmp_path)
    assert a["sketch"] == 1 and a["notes_heard"][0] == "E2@0.00s" and "since_last_try" not in a
    b = ST.handle({"action": "noodle", "instrument": {"synth": "nekobi", "params": {"cutoff": 80}},
                   "riff": "E2/0.5 G2/0.5"}, tmp_path)
    assert b["sketch"] == 2 and any(l.startswith("brightness (Hz): 600.0 -> 2400.0") for l in b["since_last_try"])
    assert [s["n"] for s in ST.handle({"action": "sketchbook"}, tmp_path)["sketches"]] == [1, 2]
    slug = W.new("First Light", "other", "x", data_dir=tmp_path)["project"]
    k = ST.handle({"action": "keep", "project": slug, "sketch": 1, "note": "the verse riff?"}, tmp_path)
    riffs = (W._project(slug, tmp_path) / "riffs.md").read_text()
    assert k["kept"] == 1 and "the verse riff?" in riffs and "E2/0.5 G2/0.5" in riffs
