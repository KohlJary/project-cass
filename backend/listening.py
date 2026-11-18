"""
listen: Cass's ears (plan "Cass's ears and studio", phase 2; Kohl, 2026-11-18).

Acousmatic (github.com/KohlJary/acousmatic, its own repository and virtualenv)
listens to a record from Kohl's library and writes a listening record: form,
tempo and bars, key and chords, the words in the bars where they're sung, the
lead and bass lines, the drums, how each part sounds and where it sits, with
spectrograms and a score. No language model takes part in it; the same song
always gives the same record. What it means is hers.

- shelf: browse the library (artists, albums, tracks), from file tags.
- listen: a track or a whole album. Records are kept (DATA_DIR/listening/records,
  one per file, by its hash), so a song is listened to once; new ones run in the
  background, a few at a time, at low priority. Each one that finishes is logged to
  DATA_DIR/listening/ready.jsonl, which happenings.py turns into a wake (a record she
  asked for is ready). Until that's on, status says what's done.
- read: a record, whole or a part of it (glance, a section, bars, the words).
- album: every track's at-a-glance lines side by side, for an album as a whole.
- look: a picture from a record (spectrogram, stereo field, a section, a score page),
  as an image she sees.
What she makes of a song she writes in her own workspace (listening/), not here.

Lever `listening` (off by default).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LEVER = "listening"
MUSIC_DIR = Path(os.environ.get("CASS_MUSIC_DIR", "/home/music"))
ACOUSMATIC = os.environ.get("ACOUSMATIC_BIN", str(Path.home() / "acousmatic" / ".venv" / "bin" / "acousmatic"))
AUDIO = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".wma", ".aiff", ".aif"}
WORKERS = int(os.environ.get("LISTENING_WORKERS", "3"))
LISTEN_TIMEOUT = 1800
READ_CHARS = 18_000
MAX_IMAGE_BYTES = 1_500_000

TOOL = {
    "name": "listen",
    "description": (
        "My ears: listen to records from Kohl's music library. shelf browses it (query narrows by artist, "
        "album or title). listen takes a track or a whole album; each song is listened to once and kept, "
        "and a new one takes a few minutes in the background (status says what's ready). read gives me a "
        "song's listening record, in the order it's heard: form, tempo and bars, key and chords, the words "
        "in the bars where they're sung, the lead and bass lines, the drums, how each part sounds and where "
        "it sits. Whole, or one part: part = glance, words, a section label (A, B...), or bars like 20-40. "
        "album lays an album's songs side by side. look shows me a picture: overview (spectrogram with "
        "sections), stereo, a section label, or score. The record is measured, not interpreted, and its "
        "notes and chords are transcriptions that can be wrong. note keeps what a song (or a whole album) is "
        "to me, in my words, in my workspace (listening/Artist/Album/); rewriting it keeps the earlier "
        "versions, so I can see how my take changed. my_notes reads back what I've written."),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["shelf", "listen", "status", "read", "album", "look", "note", "my_notes"]},
            "text": {"type": "string", "description": "note: what the song (or album) is to me, in my words"},
            "add": {"type": "boolean", "description": "note: add to what I wrote before instead of rewriting it"},
            "query": {"type": "string", "description": "shelf/listen/read/album/look: artist, album or song, in words"},
            "part": {"type": "string", "description": "read: glance, words, a section label, or bars like 20-40; "
                                                      "look: overview, stereo, a section label, or score (score 2 for page 2)"},
        },
        "required": ["action"],
    },
}
LISTENING_TOOLS = [TOOL]


def enabled() -> bool:
    from features import is_enabled
    return is_enabled(LEVER)


def _root() -> Path:
    from config import DATA_DIR
    return Path(DATA_DIR) / "listening"


# ---------------------------------------------------------------------------
# The shelf
# ---------------------------------------------------------------------------

_index_lock = threading.Lock()


def _tags(path: Path) -> Dict[str, str]:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "format_tags=title,artist,album,album_artist,track,date:format=duration",
                              "-of", "json", str(path)], capture_output=True, text=True, timeout=20).stdout
        d = json.loads(out).get("format", {})
        t = {k.lower(): v for k, v in (d.get("tags") or {}).items()}
        t["duration"] = d.get("duration")
        return t
    except Exception:
        return {}


def index(music_dir: Optional[Path] = None, cache: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Every track: {id (path under the library), artist, album, title, track, duration}.
    Tags read once and cached; refreshed when a file is added or changed."""
    music_dir = music_dir or MUSIC_DIR
    cache = cache or (_root() / "shelf.json")
    with _index_lock:
        try:
            known = {t["id"]: t for t in json.loads(cache.read_text())}
        except (OSError, ValueError):
            known = {}
        out, changed = [], False
        for p in sorted(music_dir.rglob("*")):
            if p.suffix.lower() not in AUDIO or not p.is_file():
                continue
            rid = str(p.relative_to(music_dir))
            mtime = int(p.stat().st_mtime)
            t = known.get(rid)
            if not t or t.get("mtime") != mtime:
                tg = _tags(p)
                folder = p.parent.name
                t = {"id": rid, "mtime": mtime,
                     "artist": tg.get("artist") or tg.get("album_artist") or folder,
                     "album": tg.get("album") or folder,
                     "title": tg.get("title") or re.sub(r"^\d+[\s.\-_]*", "", p.stem),
                     "track": (tg.get("track") or "").split("/")[0],
                     "duration": round(float(tg["duration"]), 1) if tg.get("duration") else None}
                changed = True
            out.append(t)
        if changed or len(out) != len(known):
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(out))
        return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def find(query: str, tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Tracks a query names. A query that names an album gives the album (One X is both an
    album and a song on it: the album, unless she says "song"); a title gives the song."""
    raw = (query or "").lower()
    q = _norm(re.sub(r"\b(the )?(album|record|song|track)\b|\bby\b", " ", raw))
    if not q:
        return {"tracks": [], "kind": None}
    words = q.split()
    def hay(t):
        return _norm(f"{t['artist']} {t['album']} {t['title']} {Path(t['id']).parent.name}")
    hits = [t for t in tracks if all(w in hay(t) for w in words)]
    if not hits:
        return {"tracks": [], "kind": None}
    def names_album(t):
        alb, folder = _norm(t["album"]), _norm(Path(t["id"]).parent.name)
        return q == alb or q.endswith(alb) or q == folder or (len(alb) > 3 and alb in q)
    def names_title(t):
        ti = _norm(t["title"])
        return q == ti or q.endswith(" " + ti)
    by_album = [t for t in hits if names_album(t)]
    by_title = [t for t in hits if names_title(t)]
    want_song = bool(re.search(r"\b(song|track)\b", raw))
    if by_album and not want_song and len({t["album"] for t in by_album}) == 1:
        return {"tracks": sorted(by_album, key=_order), "kind": "album"}
    if by_title:
        return {"tracks": sorted(by_title, key=_order), "kind": "song" if len(by_title) == 1 else "several"}
    if len({t["album"] for t in hits}) == 1 and len(hits) > 1:
        return {"tracks": sorted(hits, key=_order), "kind": "album"}
    return {"tracks": sorted(hits, key=_order), "kind": "song" if len(hits) == 1 else "several"}


def _order(t):
    try:
        n = int(t.get("track") or 0)
    except ValueError:
        n = 0
    return (t["artist"], t["album"], n, t["id"])


def shelf(query: str = "", tracks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    tracks = tracks if tracks is not None else index()
    if query:
        tracks = find(query, tracks)["tracks"] or [t for t in tracks if _norm(query) in _norm(t["artist"])]
    albums: Dict[str, Dict[str, Any]] = {}
    for t in sorted(tracks, key=_order):
        key = f"{t['artist']} — {t['album']}"
        albums.setdefault(key, {"artist": t["artist"], "album": t["album"], "tracks": []})["tracks"].append(
            {"title": t["title"], "minutes": round((t["duration"] or 0) / 60, 1), "ready": _ready(t) is not None})
    out = list(albums.values())
    if not query and len(out) > 40:
        return {"albums": [{"artist": a["artist"], "album": a["album"], "tracks": len(a["tracks"])} for a in out],
                "note": "query an artist or album to see its tracks"}
    return {"albums": out}


# ---------------------------------------------------------------------------
# Listening (background, a few at a time)
# ---------------------------------------------------------------------------

_pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="listen")
_jobs: Dict[str, Any] = {}
_jobs_lock = threading.Lock()


def _key(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _record_dir(t: Dict[str, Any]) -> Path:
    if "key" not in t:
        t["key"] = _key(MUSIC_DIR / t["id"])
    return _root() / "records" / t["key"]


def _ready(t: Dict[str, Any]) -> Optional[Path]:
    try:
        d = _record_dir(t)
    except OSError:
        return None
    return d if (d / "record.md").exists() else None


def _run(t: Dict[str, Any]) -> Dict[str, Any]:
    d = _record_dir(t)
    tmp = d.with_name(d.name + ".partial")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["nice", "-n", "10", ACOUSMATIC, "listen", str(MUSIC_DIR / t["id"]), "-o", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=LISTEN_TIMEOUT)
    if r.returncode != 0 or not (tmp / "record.md").exists():
        raise RuntimeError((r.stderr or "")[-600:] or f"exit {r.returncode}")
    if d.exists():
        import shutil
        shutil.rmtree(d)
    tmp.rename(d)
    (d / "track.json").write_text(json.dumps({k: t[k] for k in ("id", "artist", "album", "title", "track", "duration")}))
    _log_ready(t, d)
    return {"ready": True}


def _log_ready(t: Dict[str, Any], d: Path) -> None:
    """One line per finished record, for happenings.py to wake her with."""
    from datetime import datetime
    try:
        line = {"key": t.get("key"), "artist": t.get("artist"), "album": t.get("album"), "title": t.get("title"),
                "id": t.get("id"), "at": datetime.now().isoformat(timespec="seconds"), "record": str(d / "record.md")}
        with open(_root() / "ready.jsonl", "a") as f:
            f.write(json.dumps(line) + "\n")
    except Exception as e:
        logger.warning(f"[listening] couldn't log a ready record: {e}")


def start(tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
    ready, started, running = [], [], []
    with _jobs_lock:
        for t in tracks:
            if _ready(t):
                ready.append(t["title"]); continue
            job = _jobs.get(t["key"])
            if job and not job.done():
                running.append(t["title"]); continue
            _jobs[t["key"]] = _pool.submit(_run, t)
            _jobs[t["key"]].track = t
            started.append(t["title"])
    return {"ready": ready, "started": started, "already_listening": running}


def status() -> Dict[str, Any]:
    with _jobs_lock:
        jobs = list(_jobs.items())
    listening, failed, done = [], [], []
    for key, job in jobs:
        t = getattr(job, "track", {})
        name = f"{t.get('artist')} — {t.get('title')}"
        if not job.done():
            listening.append(name)
        elif job.exception():
            failed.append({"song": name, "why": str(job.exception())[-300:]})
        else:
            done.append(name)
    return {"listening": listening, "finished": done, "failed": failed,
            "note": "a song takes a few minutes; several run at once"}


# ---------------------------------------------------------------------------
# Reading a record
# ---------------------------------------------------------------------------

def _sections(md: str) -> List[str]:
    parts = re.split(r"(?m)^(?=## )", md)
    return parts


def read_part(md: str, part: Optional[str]) -> str:
    parts = _sections(md)
    head = parts[0]
    body = {p.split("\n", 1)[0]: p for p in parts[1:]}
    if not part:
        return md
    p = part.strip().lower()
    if p in ("glance", "at a glance", "summary"):
        glance = next((v for k, v in body.items() if k.lower().startswith("## at a glance")), "")
        heads = [k for k in body if not k.lower().startswith(("## at a glance", "## methods"))]
        return head + glance + "\nSections:\n" + "\n".join(f"- {h[3:]}" for h in heads)
    if p in ("words", "lyrics"):
        lines = [l for l in md.splitlines() if l.startswith("- bar ") or l.strip().startswith("words:")]
        out, bar = [], ""
        for l in lines:
            if l.startswith("- bar "):
                bar = l.split(")")[0] + ")"
            else:
                out.append(f"{bar[2:]} {l.strip()[7:]}")
        return head + "\n".join(out) if out else head + "(no words in this record)"
    m = re.match(r"(?:bars?\s*)?(\d+)\s*[-–]\s*(\d+)$", p)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        keep, on = [], False
        for l in md.splitlines():
            mm = re.match(r"- bar (\d+)", l)
            if mm:
                on = a <= int(mm.group(1)) <= b
            elif l.startswith("## ") or (l.startswith("  bars ") and on is False):
                on = False
            if on:
                keep.append(l)
        return head + "\n".join(keep) if keep else head + f"(no bars {a}-{b})"
    hit = [v for k, v in body.items() if re.match(rf"## {re.escape(part.strip())}\b", k, re.I)]
    if hit:
        return head + "\n".join(hit)
    return head + f"(no part {part!r}; try glance, words, a section label, or bars like 20-40)"


def _safe(name: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]+", "-", (name or "unknown").strip()).strip(". ") or "unknown"


def note_path(t: Dict[str, Any], album_level: bool) -> str:
    """Where her take on a song (or album) lives in her workspace."""
    base = f"listening/{_safe(t['artist'])}/{_safe(t['album'])}"
    return f"{base}/_album.md" if album_level else f"{base}/{_safe(t['title'])}.md"


def _glance_lines(d: Path) -> Dict[str, Any]:
    rec = json.loads((d / "record.json").read_text())
    t = json.loads((d / "track.json").read_text()) if (d / "track.json").exists() else {}
    rh, h = rec["rhythm"], rec["harmony"]
    secs = rec["form"]["sections"]
    lead = rec["notes"]["lead"]
    return {"title": t.get("title") or rec["source"]["tags"].get("title"),
            "minutes": round(rec["source"]["duration"] / 60, 2),
            "tempo": rh["tempo"], "meter": f"{rh['meter']}/4", "key": h["key"]["name"], "mode": h["mode"]["best"],
            "loudness_lufs": rec["loudness"]["integrated_lufs"], "crest_db": rec["loudness"]["crest_db"],
            "form": " ".join(s["label"] for s in secs),
            "chords_used": len({c["name"] for c in h["chord_spans"] if c["name"] != "N"}),
            "borrowed_chords": len([c for c in h["chord_spans"] if c.get("borrowed")]),
            "lead_range": f"{_note(min(n['midi'] for n in lead))}–{_note(max(n['midi'] for n in lead))}" if lead else None,
            "word_lines": len((rec.get("words") or {}).get("lines", [])),
            "width": round(sum((s.get("sound") or {}).get("width_overall", 0) for s in secs) / max(len(secs), 1), 3)}


def _note(m):
    names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    return f"{names[m % 12]}{m // 12 - 1}"


def _image_path(d: Path, part: Optional[str]) -> Optional[Path]:
    p = (part or "overview").strip().lower()
    if p in ("overview", "spectrogram"):
        return d / "images" / "overview.png"
    if p in ("stereo", "stereo field", "stereo-field"):
        return d / "images" / "stereo-field.png"
    m = re.match(r"score\s*(\d*)", p)
    if m:
        n = int(m.group(1) or 1)
        pages = sorted(d.glob("score*.png"))
        named = [x for x in pages if x.stem.endswith(f"page{n}")] or ([pages[n - 1]] if len(pages) >= n else [])
        return named[0] if named else None
    hits = sorted((d / "images").glob(f"section-*-{p.upper()}.png"))
    return hits[0] if hits else None


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------

def handle(a: Dict[str, Any]) -> Dict[str, Any]:
    if not enabled():
        return {"error": "my ears aren't switched on right now"}
    action = (a.get("action") or "").strip()
    query = (a.get("query") or "").strip()
    if action == "shelf":
        return shelf(query)
    if action == "status":
        return status()
    if not query:
        return {"error": f"{action} needs a query: an artist, album or song"}
    if not Path(ACOUSMATIC).exists():
        return {"error": "Acousmatic isn't installed where the vessel expects it"}
    found = find(query, index())
    tracks = found["tracks"]
    if tracks:
        try:
            from music_log import log_activity
            first = tracks[0] if (found["kind"] == "song" or action not in ("listen", "album")) else \
                {"artist": tracks[0]["artist"], "album": tracks[0]["album"], "title": f"{tracks[0]['album']} (album)"}
            log_activity(action, first)
        except Exception as e:
            logger.warning(f"[listening] activity log: {e}")
    if not tracks:
        return {"error": f"nothing on the shelf matches {query!r}; shelf with a query shows what's there"}
    if action in ("note", "my_notes"):
        album_level = found["kind"] == "album" or len(tracks) > 1
        t = tracks[0]
        rel = note_path(t, album_level)
        from agent_loop.workspace import Workspace
        ws = Workspace()
        if action == "my_notes":
            p = ws.resolve(rel)
            folder = ws.resolve(str(Path(rel).parent))
            others = sorted(x.name for x in folder.glob("*.md")) if folder and folder.exists() else []
            return {"note": p.read_text() if p and p.exists() else None, "path": rel,
                    "also_in_this_album": others}
        text = (a.get("text") or "").strip()
        if not text:
            return {"error": "note needs the text: what it is to me"}
        out = ws.run("workspace_write", {"path": rel, "content": text, "append": bool(a.get("add"))},
                     session_id="listen-note")
        if isinstance(out, dict) and out.get("error"):
            return out
        return {"kept": rel, "about": f"{t['artist']} – {t['album']}" + ("" if album_level else f" – {t['title']}"),
                "note": "earlier versions are kept when I rewrite it"}
    if action == "listen":
        out = start(tracks)
        if out["started"] or out["already_listening"]:
            n = len(out["started"]) + len(out["already_listening"])
            out["note"] = (f"{n} song(s) listening now, {WORKERS} at a time, a few minutes each; "
                           "status shows progress, and read works as each is ready")
        if out["ready"] and not out["started"] and not out["already_listening"]:
            out["note"] = ("Already listened: all of these are ready now, nothing to wait for. listen read with a "
                           "song opens it (part: glance for an overview); listen album lays them side by side.")
        elif out["ready"]:
            out["note"] = out.get("note", "") + f"; {len(out['ready'])} already ready to read now"
        return out
    if action == "album":
        rows, missing = [], []
        for t in tracks:
            d = _ready(t)
            if d:
                try:
                    rows.append(_glance_lines(d))
                except Exception as e:
                    rows.append({"title": t["title"], "error": str(e)})
            else:
                missing.append(t["title"])
        return {"album": tracks[0]["album"], "artist": tracks[0]["artist"], "songs": rows,
                "not_listened_yet": missing,
                "keys": "tempo BPM; loudness in LUFS (higher = louder master); crest = peak over average (lower = "
                        "more compressed); width 0 = mono, higher = wider; form = section letters in order"}
    t = tracks[0]
    if len(tracks) > 1 and found["kind"] != "song":
        return {"error": f"{query!r} names {len(tracks)} songs; name one (album shows them side by side)",
                "songs": [x["title"] for x in tracks][:30]}
    d = _ready(t)
    if not d:
        return {"error": f"I haven't listened to {t['title']} yet; listen first", "song": t["title"]}
    if action == "read":
        md = (d / "record.md").read_text()
        text = read_part(md, a.get("part"))
        if len(text) > READ_CHARS:
            text = (text[:READ_CHARS] + "\n[the record goes on; read a part: glance, words, a section label, "
                    "or bars like 40-80]")
        return {"song": t["title"], "artist": t["artist"], "album": t["album"], "record": text}
    if action == "look":
        img = _image_path(d, a.get("part"))
        if not img or not img.exists():
            return {"error": "no such picture; try overview, stereo, a section label, or score"}
        data = img.read_bytes()
        if len(data) > MAX_IMAGE_BYTES:
            return {"error": "that picture is too big to show"}
        return {"song": t["title"], "picture": img.name,
                "_images": [{"media_type": "image/png", "data": base64.b64encode(data).decode()}]}
    return {"error": "action is one of shelf, listen, status, read, album, look"}


async def execute_listening_tool(tool_name: str, tool_input: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    import asyncio
    try:
        out = await asyncio.to_thread(handle, tool_input or {})
    except Exception as e:
        logger.warning(f"[listening] {e}", exc_info=True)
        out = {"error": f"listen failed: {type(e).__name__}: {e}"}
    if out.get("error"):
        return {"success": False, "error": out["error"]}
    images = out.pop("_images", None)
    if images:
        # A list of content blocks passes through tool_router as it is (tool_result_content)
        # and the loop shows the images to her as images.
        return {"success": True, "result": [{"type": "text", "text": json.dumps(out)}] + [
            {"type": "image", "source": {"type": "base64", "media_type": i["media_type"], "data": i["data"]}}
            for i in images]}
    return {"success": True, "result": out}
