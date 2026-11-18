"""
studio: Cass makes music (plan "Cass's ears and studio", phase 4; Kohl, 2026-11-18).

Her songs live in her workshop projects (workshop.py): a song is a text file she writes
(song.yaml: tempo, instruments, sections bar by bar, an arrangement). Orphic (~/orphic,
its own repository and virtualenv) renders it with Kohl's synths, General MIDI, and a
real TR-808 kit, then Acousmatic listens back.

- render: render the song; if it renders, commit it as a draft with her message (what
  she changed and why), and keep the draft's audio, stems and listening record
  (DATA_DIR/studio/<project>/draft-N). Her drafts and their messages are her decision log.
- read / look: what her ears heard in a draft (as listen does for records).
- compare: what changed between two drafts, measured (each part's level from her own
  stems, which are exact; tempo, key, loudness, sections).
- drafts: the list, with her messages.
- help: the song format, the synths, the drum kit, her gun belt.
- patch: put a patch (a synth and its settings) on her gun belt, to call by name.
- map: a synth's Monochord map (what each knob does), where one exists.

Lever `studio` (off by default). Offered in workshop sessions.
"""
from __future__ import annotations

import ast
import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LEVER = "studio"
ORPHIC_HOME = Path(os.environ.get("ORPHIC_HOME", Path.home() / "orphic"))
ORPHIC = os.environ.get("ORPHIC_BIN", str(ORPHIC_HOME / ".venv" / "bin" / "orphic"))
RENDER_TIMEOUT = 900
READ_CHARS = 18_000

TOOL = {
    "name": "studio",
    "description": (
        "My studio: make music in one of my workshop projects. I write a song as song.yaml (help shows the "
        "format: tempo, instruments, sections bar by bar, an arrangement) with project write, then render: it's "
        "played with Kohl's synths, General MIDI or a real TR-808 kit, my ears listen back, and if it rendered it's "
        "committed as a draft with my message (what I changed and why), so my drafts are my decision log. "
        "read and look show what my ears heard in a draft; compare says what changed between two drafts, "
        "measured; drafts lists them. patch puts a synth setting on my gun belt to call by name; map shows "
        "what a synth's knobs do. noodle is for playing around: a riff on any instrument, looped, heard back "
        "in seconds (the notes, the sound, and what changed since my last try), kept in my sketchbook, nothing "
        "committed; keep copies a sketch I like into a project's riffs.md. Rendering takes a minute or two; a noodle "
        "about twenty seconds. tone puts a guitar (default a real one, sampled: {\"sfz\": \"fsbs-direct\"}) through a chain or a "
        "rig and measures the tone: distortion character, how chords hold up, sustain, tightness, mud, fizz, "
        "and what changed since my last try; rig saves a chain on my gun belt by name (an instrument uses it as "
        "rig: name); map also shows what an amp's knobs do (swankyamp). clip writes a part as MIDI in a project "
        "(clips/name.mid, opens in any DAW), from riff notation or from clip_notes (bar, beat, pitch, len in "
        "beats, vel, pm), and shows it back as a piano roll a bar at a time (X a note, m palm-muted, = held, "
        ". silence) with any bar that doesn't fill its beats; with only a name it reads one, clips lists them. "
        "A song uses a clip as a part: <instrument>: {clip: name}, looped to fill the section. session builds a "
        "song as a real Reaper session (tracks, instruments, effects, my MIDI on each track, section markers) "
        "that Kohl can open in Reaper, and renders it there: synths play live from my MIDI, the sampled "
        "guitar and the 808 go in as their audio with the notes beside them. song writes a song file into a "
        "project (song.yaml, or another name ending .yaml) from text, checks it parses, and commits it with "
        "my message; render and session then play it. share sets who can follow my music log in Babelr (my listening, what I write "
        "about songs, my drafts and sketches); hide keeps any single one out of it, show puts it back."),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string",
                       "enum": ["help", "render", "drafts", "read", "look", "compare", "patch", "map",
                                "noodle", "sketchbook", "keep", "share", "hide", "show", "tone", "rig",
                                "clip", "clips", "session", "song"]},
            "text": {"type": "string", "description": "song: the whole song file (YAML, as help shows)"},
            "clip_notes": {"type": "array", "items": {"type": "object"},
                           "description": "clip: the notes as MIDI, each {\"bar\": 1, \"beat\": 1.5, \"pitch\": \"E2\" "
                                          "or [\"E2\", \"B2\"], \"len\": 0.25 (beats), \"vel\": 1-127, \"pm\": true}"},
            "bars": {"type": "string", "description": "clip: which bars to read, like 3 or 1-4"},
            "chain": {"type": "array", "items": {"type": "object"},
                      "description": "tone/rig: effects in order, each {\"plugin\": \"swankyamp\", \"params\": {...}} "
                                     "or a built-in like {\"builtin\": \"distortion\", \"drive_db\": 25}"},
            "audience": {"type": "string", "enum": ["house", "kohl_and_daedalus", "kohl", "none"],
                         "description": "share: who can follow my music log in Babelr"},
            "item": {"type": "string", "description": "hide/show: a song write-up (its path, like listening/pain.md), "
                                                      "a draft (project:n) or a sketch (sketch:n)"},
            "instrument": {"type": "object", "description": "noodle: what plays it, like {\"synth\": \"nekobi\", "
                                                            "\"params\": {\"cutoff\": 40}} or {\"kit\": \"808\"} or {\"gm\": 34}"},
            "riff": {"description": "noodle: a bar or a few in song notation (E2/0.5 G2/0.5 ... | ...), or for the kit "
                                    "a drum grid like {\"kick\": \"x...x...\", ...}"},
            "tempo": {"type": "number", "description": "noodle: beats per minute (default 100)"},
            "loops": {"type": "integer", "description": "noodle: how many times round (default 2)"},
            "note": {"type": "string", "description": "noodle/keep: a note to myself about it"},
            "sketch": {"type": "integer", "description": "keep: which sketch (default the latest)"},
            "project": {"type": "string", "description": "the workshop project (its slug)"},
            "song": {"type": "string", "description": "render: the song file in the project (default song.yaml)"},
            "message": {"type": "string", "description": "render: what I changed and why, in my words"},
            "draft": {"type": "integer", "description": "read/look: which draft (default the latest)"},
            "against": {"type": "integer", "description": "compare: the earlier draft (default the one before)"},
            "part": {"type": "string", "description": "read: glance, a section label, or bars like 1-8; "
                                                      "look: overview, stereo, or a section label"},
            "name": {"type": "string", "description": "patch/rig: its name; tone: a rig to use"},
            "synth": {"type": "string", "description": "patch/map: the synth (vitalium, nekobi, surge, ...)"},
            "params": {"type": "object", "description": "patch: the synth's settings by parameter name"},
            "notes": {"type": "string", "description": "patch: what it's for, how it sounds, in my words"},
        },
        "required": ["action"],
    },
}


def enabled() -> bool:
    from features import is_enabled
    return is_enabled(LEVER)


def _root(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "studio"


def _belt(data_dir=None) -> Path:
    return _root(data_dir) / "belt"


def _drafts_path(slug: str, data_dir=None) -> Path:
    return _root(data_dir) / slug / "drafts.json"


def drafts(slug: str, data_dir=None) -> List[Dict[str, Any]]:
    try:
        return json.loads(_drafts_path(slug, data_dir).read_text())
    except (OSError, ValueError):
        return []


def _draft_dir(slug: str, n: int, data_dir=None) -> Path:
    return _root(data_dir) / slug / f"draft-{n}"


def _pick(slug: str, n: Optional[int], data_dir=None) -> Optional[Dict[str, Any]]:
    ds = drafts(slug, data_dir)
    if not ds:
        return None
    if n is None:
        return ds[-1]
    return next((d for d in ds if d["n"] == int(n)), None)


# ---------------------------------------------------------------------------
# help: the format, the instruments, the gun belt
# ---------------------------------------------------------------------------

def _song_doc() -> str:
    try:
        tree = ast.parse((ORPHIC_HOME / "orphic" / "song.py").read_text())
        return ast.get_docstring(tree) or ""
    except Exception:
        return ""


def help_text(data_dir=None) -> Dict[str, Any]:
    maps = ORPHIC_HOME / "maps"
    synths = ["vitalium", "nekobi", "surge", "sfizz", "kars"]
    belt = sorted(p.stem for p in _belt(data_dir).glob("*.json")) if _belt(data_dir).exists() else []
    return {
        "song_format": _song_doc(),
        "synths": {s: ("mapped (studio map)" if (maps / s).exists() or (maps / s.capitalize()).exists()
                       else "not mapped yet") for s in synths},
        "general_midi": "gm: a program number 1-128 (1 piano, 5 electric piano, 34 fingered bass, 49 strings, "
                        "81 square lead, 89 new-age pad...); played by FluidSynth's FluidR3 set",
        "sampled_instruments": "sfz: fsbs-direct (a real Fender electric, sampled straight in; put it through an amp "
                               "or a rig). Any note can be palm-muted with pm after its length: E2/0.25pm. With a high-gain amp, put a "
                               "noise gate first in the chain ({\"builtin\": \"noisegate\", \"threshold_db\": -38, "
                               "\"ratio\": 20, \"release_ms\": 15}) or the amp fills the gaps and fast riffs smear",
        "drum_kit_808": "kick snare clap hat open rim cowbell low_tom mid_tom high_tom cymbal clave maracas; "
                        "samples: {kick: BD7510} picks tone and decay (BDttdd, positions 00 25 50 75 10)",
        "my_gun_belt": belt or "empty (studio patch puts one on)",
    }


# ---------------------------------------------------------------------------
# render: a draft
# ---------------------------------------------------------------------------

def render(slug: str, song: str, message: str, data_dir=None) -> Dict[str, Any]:
    import workshop as W
    if not (message or "").strip():
        return {"error": "a draft needs a message in my words: what I changed and why"}
    try:
        project = W._project(slug, data_dir)
    except Exception as e:
        return {"error": f"no project {slug}: {e}"}
    song_path = (project / (song or "song.yaml")).resolve()
    if project.resolve() not in song_path.parents or not song_path.exists():
        return {"error": f"no {song or 'song.yaml'} in {slug}; write it with project write first"}
    if not Path(ORPHIC).exists():
        return {"error": "Orphic isn't installed where the vessel expects it"}
    _root(data_dir).joinpath(slug).mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="render-", dir=_root(data_dir) / slug))
    env = {**os.environ, "ORPHIC_BELT": str(_belt(data_dir))}
    try:
        r = subprocess.run(["nice", "-n", "10", ORPHIC, "render", str(song_path), "-o", str(tmp), "--listen"],
                           capture_output=True, text=True, timeout=RENDER_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp, ignore_errors=True)
        return {"error": f"the render took longer than {RENDER_TIMEOUT // 60} minutes and was stopped"}
    try:
        out = json.loads(r.stdout)    # Orphic prints one JSON object: the result, or {"error": ...}
    except ValueError:
        out = {"error": (r.stderr or "the render failed")[-600:]}
    if r.returncode != 0 or out.get("error"):
        shutil.rmtree(tmp, ignore_errors=True)
        return {"error": f"it didn't render: {out.get('error') or r.stderr[-400:]}",
                "note": "nothing was committed; fix the song and render again"}
    c = W.commit(slug, message, data_dir)
    if c.get("error") and "nothing has changed" not in c["error"]:
        shutil.rmtree(tmp, ignore_errors=True)
        return {"error": c["error"]}
    head = W._git(project, "rev-parse", "--short", "HEAD").strip()
    ds = drafts(slug, data_dir)
    n = (ds[-1]["n"] + 1) if ds else 1
    final = _draft_dir(slug, n, data_dir)
    tmp.rename(final)
    entry = {"n": n, "commit": head, "at": datetime.now().isoformat(timespec="seconds"),
             "song": song or "song.yaml", "message": message.strip(),
             "same_song_as_before": bool(c.get("error"))}
    ds.append(entry)
    _drafts_path(slug, data_dir).write_text(json.dumps(ds, indent=1))
    glance = ""
    rec = final / "listening" / "record.md"
    if rec.exists():
        from listening import read_part
        glance = read_part(rec.read_text(), "glance")
    return {"draft": n, "commit": head, "title": out.get("title"), "length_s": out.get("length_s"),
            "parts": out.get("tracks"), "would_have_clipped": out.get("would_have_clipped"),
            "what_my_ears_heard": glance[:6000],
            "note": "studio read / look for more; compare against an earlier draft"}


# ---------------------------------------------------------------------------
# read, look, compare
# ---------------------------------------------------------------------------

def read(slug: str, n: Optional[int], part: Optional[str], data_dir=None) -> Dict[str, Any]:
    d = _pick(slug, n, data_dir)
    if not d:
        return {"error": "no such draft; render one first"}
    rec = _draft_dir(slug, d["n"], data_dir) / "listening" / "record.md"
    if not rec.exists():
        return {"error": "that draft has no listening record"}
    from listening import read_part
    text = read_part(rec.read_text(), part)
    if len(text) > READ_CHARS:
        text = text[:READ_CHARS] + "\n[goes on; read a part: glance, a section label, or bars like 1-8]"
    return {"draft": d["n"], "message": d["message"], "record": text}


def look(slug: str, n: Optional[int], part: Optional[str], data_dir=None) -> Dict[str, Any]:
    d = _pick(slug, n, data_dir)
    if not d:
        return {"error": "no such draft; render one first"}
    from listening import MAX_IMAGE_BYTES, _image_path
    img = _image_path(_draft_dir(slug, d["n"], data_dir) / "listening", part)
    if not img or not img.exists():
        return {"error": "no such picture; try overview, stereo, or a section label"}
    data = img.read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        return {"error": "that picture is too big to show"}
    return {"draft": d["n"], "picture": img.name,
            "_images": [{"media_type": "image/png", "data": base64.b64encode(data).decode()}]}


def _stem_levels(dd: Path) -> Dict[str, float]:
    import numpy as np
    import soundfile as sf
    out = {}
    for p in sorted((dd / "stems").glob("*.wav")):
        y, _ = sf.read(p, always_2d=True)
        rms = float(np.sqrt(np.mean(y ** 2)))
        out[p.stem] = round(20 * np.log10(rms + 1e-12), 1)
    return out


def compare(slug: str, n: Optional[int], against: Optional[int], data_dir=None) -> Dict[str, Any]:
    ds = drafts(slug, data_dir)
    if len(ds) < 2:
        return {"error": "there's only one draft so far"}
    b = _pick(slug, n, data_dir) or ds[-1]
    a = _pick(slug, against, data_dir) if against is not None else next(
        (x for x in reversed(ds) if x["n"] < b["n"]), None)
    if not a:
        return {"error": "no earlier draft to compare with"}
    da, db = _draft_dir(slug, a["n"], data_dir), _draft_dir(slug, b["n"], data_dir)
    lines = []
    la, lb = _stem_levels(da), _stem_levels(db)
    for part in sorted(set(la) | set(lb)):
        if part not in la:
            lines.append(f"{part}: new in draft {b['n']}")
        elif part not in lb:
            lines.append(f"{part}: gone in draft {b['n']}")
        elif abs(lb[part] - la[part]) >= 1.0:
            lines.append(f"{part}: {lb[part] - la[part]:+.1f} dB")
    try:
        ra = json.loads((da / "listening" / "record.json").read_text())
        rb = json.loads((db / "listening" / "record.json").read_text())
        if abs(ra["rhythm"]["tempo"] - rb["rhythm"]["tempo"]) >= 1:
            lines.append(f"tempo heard: {ra['rhythm']['tempo']} -> {rb['rhythm']['tempo']} BPM")
        if ra["harmony"]["key"]["name"] != rb["harmony"]["key"]["name"]:
            lines.append(f"key heard: {ra['harmony']['key']['name']} -> {rb['harmony']['key']['name']}")
        la_, lb_ = ra["loudness"]["integrated_lufs"], rb["loudness"]["integrated_lufs"]
        if abs(la_ - lb_) >= 1:
            lines.append(f"loudness: {la_} -> {lb_} LUFS")
        fa = " ".join(s["label"] for s in ra["form"]["sections"])
        fb = " ".join(s["label"] for s in rb["form"]["sections"])
        if fa != fb:
            lines.append(f"form heard: {fa} -> {fb}")
        ba, bb = [s.get("sound") or {} for s in (ra["form"]["sections"][0], rb["form"]["sections"][0])]
        if ba.get("centroid_hz") and bb.get("centroid_hz"):
            r = bb["centroid_hz"] / ba["centroid_hz"]
            if r > 1.2 or r < 0.83:
                lines.append(f"first section {'brighter' if r > 1 else 'darker'} ({ba['centroid_hz']} -> {bb['centroid_hz']} Hz)")
    except (OSError, ValueError, KeyError, IndexError) as e:
        lines.append(f"(couldn't compare the listening records: {e})")
    return {"from": {"draft": a["n"], "message": a["message"]}, "to": {"draft": b["n"], "message": b["message"]},
            "changes": lines or ["nothing measurable changed"],
            "note": "each part's level is from my own stems (exact); the rest is what my ears heard"}


# ---------------------------------------------------------------------------
# noodling: the sketchbook
# ---------------------------------------------------------------------------

def _sketchbook(data_dir=None) -> Path:
    return _root(data_dir) / "sketchbook"


def sketches(data_dir=None) -> List[Dict[str, Any]]:
    out = []
    for p in sorted(_sketchbook(data_dir).glob("*/sketch.json"), key=lambda p: int(p.parent.name)):
        try:
            out.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    return out


def noodle(instrument: Dict[str, Any], riff: Any, tempo: float, loops: int, note: str, data_dir=None) -> Dict[str, Any]:
    if not instrument or not riff:
        return {"error": "noodle needs an instrument and a riff"}
    prev = sketches(data_dir)
    n = (prev[-1]["n"] + 1) if prev else 1
    d = _sketchbook(data_dir) / str(n)
    d.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "ORPHIC_BELT": str(_belt(data_dir))}
    args = ["nice", "-n", "10", ORPHIC, "noodle", "--instrument", json.dumps(instrument),
            "--phrase", json.dumps(riff) if isinstance(riff, dict) else str(riff),
            "--tempo", str(float(tempo or 100)), "--loops", str(int(loops or 2)), "-o", str(d)]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=300, env=env)
        out = json.loads(r.stdout)
    except (subprocess.TimeoutExpired, ValueError):
        shutil.rmtree(d, ignore_errors=True)
        return {"error": "the noodle didn't play (it took too long or failed)"}
    if out.get("error"):
        shutil.rmtree(d, ignore_errors=True)
        return {"error": f"it didn't play: {out['error']}"}
    entry = {"n": n, "at": datetime.now().isoformat(timespec="seconds"), "instrument": instrument, "riff": riff,
             "tempo": tempo or 100, "note": note or "", "played": out.get("played"),
             "notes_heard": out.get("notes_heard"),
             "sound": out.get("sound"), "sound_raw": out.get("sound_raw")}
    (d / "sketch.json").write_text(json.dumps(entry, indent=1, default=float))
    result = {"sketch": n, "played": out.get("played"), "notes_heard": out.get("notes_heard"),
              "notes_heard_is": out.get("notes_heard_is"), "sound": out.get("sound"),
              "would_have_clipped": out.get("would_have_clipped")}
    last = prev[-1] if prev else None
    if last and last.get("sound_raw") and (last.get("instrument") or {}).get("synth") == instrument.get("synth"):
        result["since_last_try"] = _differences(last["sound_raw"], out.get("sound_raw") or {})
    return result


def _differences(before: Dict, after: Dict) -> List[str]:
    labels = {"level_db": "level (dB)", "brightness_hz": "brightness (Hz)", "noise": "noise vs tone",
              "attack_ms": "attack (ms)", "sustain": "sustain", "release_ms": "release (ms)",
              "brightness_motion": "brightness change over a note (octaves)", "am_rate_hz": "tremolo/beating (Hz)",
              "am_depth": "tremolo/beating depth", "width": "stereo width", "peak_hz": "resonant peak (Hz)",
              "peak_db": "resonant peak height (dB)", "sounding_share": "share of the loop that sounds",
              "rings_ms": "notes ring for (ms)"}
    scale = {"level_db": 3, "sounding_share": 0.1, "noise": 0.05, "sustain": 0.1, "brightness_motion": 0.3, "am_rate_hz": 1,
             "am_depth": 0.1, "width": 0.08, "peak_db": 3}
    out = []
    for k, lab in labels.items():
        a, b = before.get(k), after.get(k)
        if a is None or b is None:
            continue
        if k in scale:
            moved = abs(b - a) >= scale[k]
        else:
            moved = a > 0 and b > 0 and abs(__import__("math").log2(b / a)) >= 0.25
        if moved:
            out.append(f"{lab}: {a} -> {b}")
    return out or ["no clear change in the sound"]


def keep(slug: str, n: Optional[int], note: str, data_dir=None) -> Dict[str, Any]:
    import workshop as W
    ss = sketches(data_dir)
    s = next((x for x in ss if x["n"] == int(n)), None) if n is not None else (ss[-1] if ss else None)
    if not s:
        return {"error": "no such sketch"}
    try:
        project = W._project(slug, data_dir)
    except Exception as e:
        return {"error": f"no project {slug}: {e}"}
    riff = s["riff"] if not isinstance(s["riff"], dict) else json.dumps(s["riff"])
    block = (f"\n## Sketch {s['n']} ({s['at'][:16]})\n\n{note or s.get('note') or ''}\n\n"
             f"- instrument: {json.dumps(s['instrument'])}\n- tempo: {s['tempo']}\n- riff: `{riff}`\n")
    p = project / "riffs.md"
    p.write_text((p.read_text() if p.exists() else "# Riffs\n\nSketches I kept from noodling.\n") + block)
    return {"kept": s["n"], "in": f"{slug}/riffs.md", "note": "it's in the project now, uncommitted; it goes in "
                                                             "with my next draft or project commit"}


# ---------------------------------------------------------------------------
# writing a song file into a project (from chat, where the project tool isn't)
# ---------------------------------------------------------------------------

def write_song(slug: str, song: Optional[str], text: str, message: str, data_dir=None) -> Dict[str, Any]:
    import workshop as W
    import yaml
    name = (song or "song.yaml").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.ya?ml", name):
        return {"error": "a song file is a name ending .yaml, like song.yaml or riot-idea.yaml"}
    try:
        data = yaml.safe_load(text or "")
    except yaml.YAMLError as e:
        return {"error": f"that isn't valid YAML: {e}"}
    if not isinstance(data, dict) or "tempo" not in data:
        return {"error": "a song needs at least a tempo (help shows the whole format)"}
    out = W.write(slug, name, text, data_dir)
    if out.get("error"):
        return out
    c = W.commit(slug, (message or "").strip() or f"Write {name}", data_dir)
    return {"written": name, "project": slug, "committed": not c.get("error"),
            "next": f"render or session with project {slug}" + ("" if name == "song.yaml" else f" and song {name}")}


# ---------------------------------------------------------------------------
# a song as a Reaper session
# ---------------------------------------------------------------------------

def session(slug: str, song: Optional[str], data_dir=None) -> Dict[str, Any]:
    import workshop as W
    try:
        project = W._project(slug, data_dir)
    except Exception as e:
        return {"error": f"no project {slug!r}: {e}"}
    song_path = (project / (song or "song.yaml")).resolve()
    if project.resolve() not in song_path.parents or not song_path.exists():
        return {"error": f"no {song or 'song.yaml'} in {slug}; write it with project write first"}
    out = _root(data_dir) / slug / "session"
    env = {**os.environ, "ORPHIC_BELT": str(_belt(data_dir))}
    try:
        r = subprocess.run(["nice", "-n", "10", ORPHIC, "reaper", str(song_path), "-o", str(out)],
                           capture_output=True, text=True, timeout=600, env=env)
        res = json.loads(r.stdout)
    except (subprocess.TimeoutExpired, ValueError):
        return {"error": "Reaper didn't finish the session (too long or failed)"}
    if res.get("error"):
        return {"error": f"the session didn't build: {res['error']}"}
    res["for_kohl"] = f"open {res['session']} in Reaper"
    return res


# ---------------------------------------------------------------------------
# clips: parts as MIDI, in a project's clips/ folder
# ---------------------------------------------------------------------------

def clip(slug: str, name: Optional[str], riff, notes, bars: Optional[str], listing: bool, data_dir=None):
    import workshop as W
    try:
        project = W._project(slug, data_dir)
    except Exception as e:
        return {"error": f"no project {slug!r}: {e}"}
    args = [ORPHIC, "clip"]
    if listing:
        args += ["list"]
    elif riff or notes:
        if not isinstance(riff, (str, type(None))):
            return {"error": "a clip's riff is song notation (a drum grid isn't a clip yet)"}
        args += ["write", name or ""] + (["--riff", riff] if riff else ["--notes", json.dumps(notes)])
    else:
        args += ["read", name or ""] + (["--bars", str(bars)] if bars else [])
    args += ["--dir", str(project)]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout)
    except (subprocess.TimeoutExpired, ValueError):
        return {"error": "the clip tool didn't answer"}


# ---------------------------------------------------------------------------
# tone: the guitar probe through a rig, kept in the tonebook
# ---------------------------------------------------------------------------

def _tonebook(data_dir=None) -> Path:
    return _root(data_dir) / "tonebook"


def tone(instrument: Dict[str, Any], chain, rig: Optional[str], note: str, data_dir=None) -> Dict[str, Any]:
    inst = dict(instrument or {"sfz": "fsbs-direct"})
    if rig:
        inst["rig"] = rig
    book = _tonebook(data_dir)
    book.mkdir(parents=True, exist_ok=True)
    prev = sorted((p for p in book.glob("*/tone.json")), key=lambda p: int(p.parent.name))
    n = int(prev[-1].parent.name) + 1 if prev else 1
    d = book / str(n)
    d.mkdir(parents=True, exist_ok=True)
    args = ["nice", "-n", "10", ORPHIC, "tone", "--instrument", json.dumps(inst), "-o", str(d)]
    if chain:
        args += ["--chain", json.dumps(chain)]
    if prev:
        args += ["--previous", str(prev[-1])]
    env = {**os.environ, "ORPHIC_BELT": str(_belt(data_dir))}
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=300, env=env)
        out = json.loads(r.stdout)
    except (subprocess.TimeoutExpired, ValueError):
        shutil.rmtree(d, ignore_errors=True)
        return {"error": "the tone probe didn't run (too long or failed)"}
    if out.get("error"):
        shutil.rmtree(d, ignore_errors=True)
        return {"error": f"it didn't play: {out['error']}"}
    (d / "tone.json").write_text(json.dumps(out["tone"], indent=1))
    (d / "try.json").write_text(json.dumps({"n": n, "at": datetime.now().isoformat(timespec="seconds"),
                                            "instrument": inst, "chain": chain or [], "note": note or "",
                                            "in_words": out.get("in_words")}, indent=1))
    res = {"try": n, "in_words": out.get("in_words"), "tone": out.get("tone"),
           "what_the_numbers_are": out.get("labels")}
    if out.get("since_last_try"):
        res["since_last_try"] = out["since_last_try"]
    return res


def rig(name: str, chain, notes: str, data_dir=None) -> Dict[str, Any]:
    name = re.sub(r"[^a-z0-9_-]+", "-", (name or "").lower()).strip("-")
    if not name or not chain:
        return {"error": "a rig needs a name and a chain"}
    belt = _belt(data_dir)
    belt.mkdir(parents=True, exist_ok=True)
    (belt / f"{name}.json").write_text(json.dumps({"name": name, "kind": "rig", "chain": chain, "notes": notes or "",
                                                   "saved": datetime.now().isoformat(timespec="seconds")}, indent=1))
    return {"saved": name, "use_it": f"an instrument with rig: {name} (and its own fx after it)"}


# ---------------------------------------------------------------------------
# the gun belt, and maps
# ---------------------------------------------------------------------------

def patch(name: str, synth: str, params: Dict[str, Any], notes: str, data_dir=None) -> Dict[str, Any]:
    name = re.sub(r"[^a-z0-9_-]+", "-", (name or "").lower()).strip("-")
    if not name or not synth:
        return {"error": "a patch needs a name and a synth"}
    belt = _belt(data_dir)
    belt.mkdir(parents=True, exist_ok=True)
    p = belt / f"{name}.json"
    p.write_text(json.dumps({"name": name, "synth": synth, "params": params or {}, "notes": notes or "",
                             "saved": datetime.now().isoformat(timespec="seconds")}, indent=1))
    return {"saved": name, "use_it": f"an instrument with patch: {name}"}


def synth_map(synth: str) -> Dict[str, Any]:
    maps = ORPHIC_HOME / "maps"
    for cand in (synth, synth.lower(), synth.capitalize(), synth.title()):
        p = maps / cand / "map.md"
        if p.exists():
            text = p.read_text()
            return {"synth": synth, "map": text[:READ_CHARS] + ("\n[cut]" if len(text) > READ_CHARS else "")}
    return {"error": f"no map for {synth} yet"}


# ---------------------------------------------------------------------------
# the tool
# ---------------------------------------------------------------------------

def handle(a: Dict[str, Any], data_dir=None) -> Dict[str, Any]:
    if not enabled():
        return {"error": "my studio isn't switched on right now"}
    action = (a.get("action") or "").strip()
    slug = (a.get("project") or "").strip()
    if action == "help":
        return help_text(data_dir)
    if action == "patch":
        return patch(a.get("name"), a.get("synth"), a.get("params") or {}, a.get("notes") or "", data_dir)
    if action == "map":
        return synth_map(a.get("synth") or "")
    if action == "song":
        if not slug:
            return {"error": "which project (project)?"}
        return write_song(slug, a.get("song"), a.get("text") or "", a.get("message") or "", data_dir)
    if action == "session":
        if not slug:
            return {"error": "a session is built from a song in a project: which one (project)?"}
        return session(slug, a.get("song"), data_dir)
    if action in ("clip", "clips"):
        if not slug:
            return {"error": "clips live in a project: which one (project)?"}
        return clip(slug, a.get("name"), a.get("riff"), a.get("clip_notes"), a.get("bars"), action == "clips", data_dir)
    if action == "tone":
        return tone(a.get("instrument") or {}, a.get("chain"), a.get("name"), a.get("note") or "", data_dir)
    if action == "rig":
        return rig(a.get("name"), a.get("chain"), a.get("notes") or "", data_dir)
    if action == "noodle":
        return noodle(a.get("instrument") or {}, a.get("riff"), a.get("tempo") or 100, a.get("loops") or 2,
                      a.get("note") or "", data_dir)
    if action == "share":
        from music_log import set_sharing
        return set_sharing(a.get("audience") or "", data_dir)
    if action in ("hide", "show"):
        from music_log import set_hidden
        item = (a.get("item") or "").strip()
        if item.startswith("sketch:"):
            return set_hidden("sketches", item.split(":", 1)[1], action == "hide", data_dir)
        if item.endswith(".md"):
            return set_hidden("docs", item, action == "hide", data_dir)
        if ":" in item:
            return set_hidden("drafts", item, action == "hide", data_dir)
        return {"error": "item is a song write-up path (listening/x.md), a draft (project:n) or a sketch (sketch:n)"}
    if action == "sketchbook":
        return {"sketches": [{k: v for k, v in s.items() if k != "sound_raw"} for s in sketches(data_dir)[-20:]]}
    if not slug:
        return {"error": f"{action} needs a project (its slug)"}
    if action == "render":
        return render(slug, a.get("song") or "song.yaml", a.get("message") or "", data_dir)
    if action == "drafts":
        return {"project": slug, "drafts": drafts(slug, data_dir)}
    if action == "read":
        return read(slug, a.get("draft"), a.get("part"), data_dir)
    if action == "look":
        return look(slug, a.get("draft"), a.get("part"), data_dir)
    if action == "compare":
        return compare(slug, a.get("draft"), a.get("against"), data_dir)
    if action == "keep":
        return keep(slug, a.get("sketch"), a.get("note") or "", data_dir)
    return {"error": "action is one of help, render, drafts, read, look, compare, patch, map, noodle, sketchbook, "
                     "keep, share, hide, show, tone, rig, clip, clips, session, song"}


def studio_tools(default_project: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The studio for a workshop session, by its lever."""
    if not enabled():
        return None
    import asyncio

    async def run(a):
        a = dict(a or {})
        if default_project and not a.get("project"):
            a["project"] = default_project
        try:
            return await asyncio.to_thread(handle, a)
        except Exception as e:
            logger.warning(f"[studio] {e}", exc_info=True)
            return {"error": f"studio failed: {type(e).__name__}: {e}"}
    return {"studio": (TOOL, run)}


STUDIO_TOOLS = [TOOL]   # router catalog (agent_client): the studio in chat, lever studio


async def execute_studio_tool(tool_name: str, tool_input: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    """The studio in chat (Kohl, 2026-11-18: walk her through it where she talks)."""
    import asyncio
    if not enabled():
        return {"success": False, "error": "my studio isn't switched on right now"}
    try:
        out = await asyncio.to_thread(handle, dict(tool_input or {}))
    except Exception as e:
        logger.warning(f"[studio] {e}", exc_info=True)
        out = {"error": f"studio failed: {type(e).__name__}: {e}"}
    if out.get("error"):
        return {"success": False, "error": out["error"]}
    images = out.pop("_images", None)
    if images:
        return {"success": True, "result": [{"type": "text", "text": json.dumps(out, default=str)}] + [
            {"type": "image", "source": {"type": "base64", "media_type": i["media_type"], "data": i["data"]}}
            for i in images]}
    return {"success": True, "result": out}
