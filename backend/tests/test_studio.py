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


TONE = r'''#!/usr/bin/env python3
import json, sys
from pathlib import Path
args = sys.argv
if "check-chain" in args:
    print(json.dumps({"ok": True})); sys.exit(0)
inst = json.loads(args[args.index("--instrument") + 1])
chain = json.loads(args[args.index("--chain") + 1]) if "--chain" in args else []
drive = (chain[0].get("params") or {}).get("preampdrive", 0.5) if chain else 0.5
t = {"band_fizz_db": -20 + 10 * drive, "odd_even_db": -6.0}
out = {"tone": t, "in_words": ["driven" if drive > 0.3 else "clean"], "labels": {}}
if "--previous" in args:
    prev = json.loads(Path(args[args.index("--previous") + 1]).read_text())
    out["since_last_try"] = [f"fizz: {prev['band_fizz_db']} -> {t['band_fizz_db']}"]
print(json.dumps(out))
'''


def test_tone_tries_and_rigs(tmp_path, monkeypatch):
    import sys
    fake = tmp_path / "orphic"
    fake.write_text(TONE.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
    fake.chmod(0o755)
    monkeypatch.setattr(ST, "ORPHIC", str(fake))
    monkeypatch.setattr(ST, "enabled", lambda: True)
    r = ST.handle({"action": "rig", "name": "First Crunch", "chain": [{"plugin": "swankyamp"}]}, tmp_path)
    assert r["saved"] == "first-crunch" and (tmp_path / "studio" / "belt" / "first-crunch.json").exists()
    a = ST.handle({"action": "tone", "chain": [{"plugin": "swankyamp", "params": {"preampdrive": 0.2}}]}, tmp_path)
    assert a["try"] == 1 and a["in_words"] == ["clean"] and "since_last_try" not in a
    b = ST.handle({"action": "tone", "chain": [{"plugin": "swankyamp", "params": {"preampdrive": 0.9}}]}, tmp_path)
    assert b["try"] == 2 and b["since_last_try"] == ["fizz: -18.0 -> -11.0"]


def test_chat_offers_the_studio_while_its_lever_is_on(monkeypatch):
    from agent_loop import spec
    monkeypatch.setattr(spec, "_studio_on", lambda: True)
    assert "studio_chat" in spec.conversation_spec().packs
    monkeypatch.setattr(spec, "_studio_on", lambda: False)
    assert "studio_chat" not in spec.conversation_spec().packs


def test_the_router_runs_the_studio(monkeypatch, tmp_path):
    import asyncio
    from handlers.tool_router import TOOL_REGISTRY
    assert TOOL_REGISTRY["studio"] == "studio"
    monkeypatch.setattr(ST, "enabled", lambda: True)
    monkeypatch.setattr(ST, "handle", lambda a, data_dir=None: {"help": "ok", "asked": a.get("action")})
    out = asyncio.run(ST.execute_studio_tool("studio", {"action": "help"}))
    assert out == {"success": True, "result": {"help": "ok", "asked": "help"}}
    monkeypatch.setattr(ST, "enabled", lambda: False)
    assert asyncio.run(ST.execute_studio_tool("studio", {"action": "help"}))["success"] is False


def test_the_router_dispatches_the_studio_end_to_end():
    """Through route_tool itself: the first chat try (2026-11-18) failed with
    'Unhandled executor type: studio' because the dispatch branch was missing."""
    import asyncio
    from handlers.tool_router import ToolContext, route_tool

    async def fake(tool_name, tool_input, **_):
        return {"success": True, "result": {"ran": tool_input.get("action")}}
    out = asyncio.run(route_tool("studio", {"action": "tone"}, ToolContext(), {"studio": fake}))
    assert out == {"success": True, "result": {"ran": "tone"}}


@pytest.mark.skipif(not Path(ST.ORPHIC).exists(), reason="needs Orphic installed")
def test_clips_write_read_and_list_in_a_project(tmp_path, monkeypatch):
    import workshop as W
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setattr(W, "_project", lambda slug, data_dir=None: proj)
    monkeypatch.setattr(ST, "enabled", lambda: True)
    w = ST.handle({"action": "clip", "project": "p", "name": "Chug One",
                   "riff": "[E2 B2 E3]/0.25pm [E2 B2 E3]/0.25pm r/3.5"}, tmp_path)
    assert w["clip"] == "chug-one" and (proj / "clips" / "chug-one.mid").exists()
    assert "m" in w["roll"] and "sounds 0.5 of 4 beats" in w["roll"]
    n = ST.handle({"action": "clip", "project": "p", "name": "lift",
                   "clip_notes": [{"bar": 1, "beat": 1, "pitch": ["G2", "D3"], "len": 4}]}, tmp_path)
    assert n["as_notation"] == "[G2 D3]/4"
    r = ST.handle({"action": "clip", "project": "p", "name": "lift"}, tmp_path)
    assert r["notes"] == 2 and "X===" in r["roll"]
    assert {c["clip"] for c in ST.handle({"action": "clips", "project": "p"}, tmp_path)["clips"]} == {"chug-one", "lift"}
    assert "error" in ST.handle({"action": "clip", "project": "p", "name": "nope"}, tmp_path)


def test_session_builds_in_her_studio_folder(tmp_path, monkeypatch):
    import sys
    import workshop as W
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "song.yaml").write_text("tempo: 100\n")
    monkeypatch.setattr(W, "_project", lambda slug, data_dir=None: proj)
    monkeypatch.setattr(ST, "enabled", lambda: True)
    fake = tmp_path / "orphic"
    fake.write_text(f"#!{sys.executable}\nimport json, sys\na = sys.argv\n"
                    "print(json.dumps({'session': a[a.index('-o') + 1] + '/session.rpp', 'tracks': []}))\n")
    fake.chmod(0o755)
    monkeypatch.setattr(ST, "ORPHIC", str(fake))
    out = ST.handle({"action": "session", "project": "p"}, tmp_path)
    assert out["session"] == str(tmp_path / "studio" / "p" / "session" / "session.rpp")
    assert "Reaper" in out["for_kohl"]
    assert "error" in ST.handle({"action": "session", "project": "p", "song": "nope.yaml"}, tmp_path)


def test_song_writes_and_commits_a_song_file(tmp_path, monkeypatch):
    import workshop as W
    monkeypatch.setattr(ST, "enabled", lambda: True)
    slug = W.new("Song Test", "music", "a test", tmp_path)["project"]
    ok = ST.handle({"action": "song", "project": slug, "message": "First song file",
                    "text": "tempo: 100\ninstruments: {g: {gm: 30}}\nsections: {a: {bars: 1, g: 'E2/4'}}\n"}, tmp_path)
    assert ok["written"] == "song.yaml" and ok["committed"]
    assert "First song file" in W.log(slug, data_dir=tmp_path)["log"][0]["message"] if isinstance(W.log(slug, data_dir=tmp_path).get("log"), list) else True
    assert "valid YAML" in ST.handle({"action": "song", "project": slug, "text": "tempo: [1"}, tmp_path)["error"]
    assert "tempo" in ST.handle({"action": "song", "project": slug, "text": "title: x"}, tmp_path)["error"]
    assert ".yaml" in ST.handle({"action": "song", "project": slug, "song": "../x.yaml", "text": "tempo: 1"}, tmp_path)["error"]


@pytest.mark.skipif(not Path(ST.ORPHIC).exists(), reason="needs Orphic installed")
def test_a_rig_with_knobs_that_dont_exist_isnt_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(ST, "enabled", lambda: True)
    bad = ST.handle({"action": "rig", "name": "x", "chain": [{"builtin": "eq", "low_cut_hz": 100}]}, tmp_path)
    assert "not saved" in bad["error"] and "highpass" in bad["error"]
    assert not (tmp_path / "studio" / "belt" / "x.json").exists()
    ok = ST.handle({"action": "rig", "name": "x", "chain": [{"builtin": "highpass", "cutoff_frequency_hz": 100}]}, tmp_path)
    assert ok["saved"] == "x"


def test_form_writes_sections_that_play_clips(tmp_path, monkeypatch):
    import yaml
    import workshop as W
    monkeypatch.setattr(ST, "enabled", lambda: True)
    slug = W.new("Form Test", "music", "x", tmp_path)["project"]
    ST.handle({"action": "song", "project": slug, "message": "instruments",
               "text": "tempo: 100\ninstruments: {guitar: {sfz: fsbs-direct}, bass: {synth: vitalium}}\n"}, tmp_path)
    out = ST.handle({"action": "form", "project": slug,
                     "form": "intro 4 · verse 8 · chorus 8 · verse 8 · chorus 16 · outro 4"}, tmp_path)
    assert out["sections"] == ["intro 4", "verse 8", "chorus 8", "verse 8", "chorus-16 16", "outro 4"]
    assert "verse-guitar" in out["clips_to_write"] and "chorus-bass" in out["clips_to_write"]
    song = yaml.safe_load((W._project(slug, tmp_path) / "song.yaml").read_text())
    assert song["tempo"] == 100 and song["sections"]["verse"]["guitar"] == {"clip": "verse-guitar"}
    assert song["arrangement"][4] == "chorus-16"
    assert "error" in ST.handle({"action": "form", "project": slug, "form": "verse eight"}, tmp_path)



def test_form_reads_instruments_written_as_a_list(tmp_path, monkeypatch):
    import workshop as W
    monkeypatch.setattr(ST, "enabled", lambda: True)
    slug = W.new("Form List", "music", "x", tmp_path)["project"]
    ST.handle({"action": "song", "project": slug, "message": "instruments",
               "text": "tempo: 100\ninstruments:\n  - {name: melody, gm: 1}\n  - {name: bass, gm: 34}\n"}, tmp_path)
    out = ST.handle({"action": "form", "project": slug, "form": "verse 4"}, tmp_path)
    assert out.get("error") is None, out
    assert sorted(out["clips_to_write"]) == ["verse-bass", "verse-melody"]

AUDITION_SONG = """title: t
tempo: 120
instruments:
  keys: {gm: 1}
sections:
  a: {bars: 1, keys: "C/4"}
  b: {bars: 1, keys: "Am/4"}
arrangement: [a, b, a]
"""


@pytest.mark.skipif(not Path(ST.ORPHIC).exists(), reason="needs Orphic installed")
def test_audition_hears_a_section_in_place_and_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(ST, "enabled", lambda: True)
    r = W.new("Audition", "other", "x", data_dir=tmp_path)
    slug = r["project"]
    W.write(slug, "song.yaml", AUDITION_SONG, data_dir=tmp_path)
    W.commit(slug, "the song", tmp_path)
    head = W._git(W._project(slug, tmp_path), "rev-parse", "HEAD")
    out = ST.handle({"action": "audition", "project": slug, "section": "b", "swap": {"keys": "F/4"},
                     "repeat": 2}, tmp_path)
    assert out.get("error") is None, out
    assert out["heard"] == ["a", "b (trying)", "b (trying)", "a"]
    assert out["swapped"] == ["keys"] and out["what_my_ears_heard"]
    assert "findings" in out["the_mix"]                                      # she hears the mix too
    proj = W._project(slug, tmp_path)
    assert (proj / "song.yaml").read_text() == AUDITION_SONG                 # the song is untouched
    assert W._git(proj, "rev-parse", "HEAD") == head                         # nothing committed
    assert ST.drafts(slug, tmp_path) == []                                   # and it isn't a draft
    bad = ST.handle({"action": "audition", "project": slug, "section": "chorus"}, tmp_path)
    assert "no section" in bad["error"]
    assert "needs a section" in ST.handle({"action": "audition", "project": slug}, tmp_path)["error"]


@pytest.mark.skipif(not Path(ST.ORPHIC).exists(), reason="needs Orphic installed")
def test_her_own_space_goes_on_the_belt(tmp_path, monkeypatch):
    monkeypatch.setattr(ST, "enabled", lambda: True)
    assert "your words" in ST.handle({"action": "space", "name": "attic"}, tmp_path)["error"] or \
        "my words" in ST.handle({"action": "space", "name": "attic"}, tmp_path)["error"]
    out = ST.handle({"action": "space", "name": "Attic", "notes": "under the roof",
                     "params": {"size": 0.4, "walls_ms": 10}}, tmp_path)
    assert out.get("error") is None, out
    assert out["saved"]["name"] == "attic" and out["saved"]["ring_s"] > 0
    rooms = ST.handle({"action": "spaces"}, tmp_path)["spaces"]
    assert rooms["attic"]["mine"] is True and "cathedral" in rooms
    assert (ST._belt(tmp_path) / "spaces" / "attic.json").exists()
