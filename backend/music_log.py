"""
Her music, as a log the house can follow (Kohl, 2026-11-18): what she listened to, what
she wrote about songs (and how that changed), what she made in the studio and why, and
her noodling. Read by Babelr's "music" plugin through the record token
(routes/music.py), and shown only to the audience she chose (sharing.json). Anything
she hides (hidden.json) is left out entirely. Nothing here writes to her data except
those two settings, which are hers to set (studio share / hide / show).

Sources:
- listening activity: DATA_DIR/listening/activity.jsonl (her listen calls) and
  listening/ready.jsonl (records she asked for, finished)
- what she writes about songs: her workspace's listening/ folder, with earlier versions
  from the workspace history
- the studio: DATA_DIR/studio/<project>/drafts.json, each project's WRITEUP.md, the sketchbook
"""
from __future__ import annotations

import json
import re
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AUDIENCES = ("house", "kohl_and_daedalus", "kohl", "none")
DOC_DIRS = ("listening",)


def _data(data_dir=None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir)


def _settings(data_dir=None) -> Path:
    return _data(data_dir) / "music_log"


# --- her settings ------------------------------------------------------------------

def sharing(data_dir=None) -> Dict[str, Any]:
    try:
        return json.loads((_settings(data_dir) / "sharing.json").read_text())
    except (OSError, ValueError):
        return {"audience": "none", "set": None, "note": "she hasn't chosen yet"}


def set_sharing(audience: str, data_dir=None) -> Dict[str, Any]:
    if audience not in AUDIENCES:
        return {"error": f"audience is one of {', '.join(AUDIENCES)}"}
    d = _settings(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    s = {"audience": audience, "set": datetime.now().isoformat(timespec="seconds")}
    (d / "sharing.json").write_text(json.dumps(s))
    return {"success": True, **s}


def hidden(data_dir=None) -> Dict[str, List]:
    try:
        h = json.loads((_settings(data_dir) / "hidden.json").read_text())
    except (OSError, ValueError):
        h = {}
    return {"docs": h.get("docs", []), "drafts": h.get("drafts", []), "sketches": h.get("sketches", [])}


def set_hidden(kind: str, ident: str, hide: bool, data_dir=None) -> Dict[str, Any]:
    if kind not in ("docs", "drafts", "sketches"):
        return {"error": "what to hide: a doc (its path), a draft (project:n) or a sketch (its number)"}
    h = hidden(data_dir)
    ident = str(ident)
    if hide and ident not in h[kind]:
        h[kind].append(ident)
    if not hide and ident in h[kind]:
        h[kind].remove(ident)
    d = _settings(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "hidden.json").write_text(json.dumps(h, indent=1))
    return {"success": True, "hidden": hide, kind[:-1]: ident}


# --- what goes in the log ------------------------------------------------------------

def _jsonl(p: Path) -> List[Dict[str, Any]]:
    out = []
    try:
        for line in p.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out


def log_activity(action: str, song: Optional[Dict[str, Any]] = None, data_dir=None) -> None:
    """One line per listen call of hers (listening.handle calls this)."""
    try:
        p = _data(data_dir) / "listening" / "activity.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {"at": datetime.now().isoformat(timespec="seconds"), "action": action}
        if song:
            row.update({k: song.get(k) for k in ("artist", "album", "title") if song.get(k)})
        with open(p, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception as e:
        logger.warning(f"[music_log] couldn't log listening: {e}")


def docs(data_dir=None) -> List[Dict[str, Any]]:
    """What she writes about songs, with earlier versions (oldest first)."""
    root = _data(data_dir) / "workspace"
    hist = _data(data_dir) / "agent_loop" / "workspace_history"
    hide = set(hidden(data_dir)["docs"])
    out = []
    for d in DOC_DIRS:
        for p in sorted((root / d).rglob("*.md")) if (root / d).exists() else []:
            rel = str(p.relative_to(root))
            if rel in hide:
                continue
            versions = []
            h = hist / rel.replace("/", "__")
            for v in sorted(h.glob("*.txt")) if h.exists() else []:
                try:
                    at = datetime.strptime(v.stem[:15], "%Y%m%d-%H%M%S").isoformat()
                except ValueError:
                    at = None
                versions.append({"at": at, "text": v.read_text(errors="replace")})
            parts = Path(rel).parts   # listening/Artist/Album/Song.md (or _album.md)
            artist, album = (parts[1], parts[2]) if len(parts) >= 4 else (None, None)
            song = None if p.stem == "_album" else (p.stem if artist else None)
            out.append({"path": rel, "title": p.stem, "artist": artist, "album": album, "song": song,
                        "album_note": p.stem == "_album", "updated": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                        "text": p.read_text(errors="replace"), "earlier": versions})
    return out


def studio(data_dir=None) -> List[Dict[str, Any]]:
    import workshop as W
    base = _data(data_dir) / "studio"
    hide = set(hidden(data_dir)["drafts"])
    out = []
    for dj in sorted(base.glob("*/drafts.json")) if base.exists() else []:
        slug = dj.parent.name
        try:
            drafts = json.loads(dj.read_text())
        except ValueError:
            continue
        try:
            proj = W._project(slug, data_dir)
            meta = W.meta(proj)
            writeup = (proj / "WRITEUP.md").read_text() if (proj / "WRITEUP.md").exists() else None
            project_md = (proj / "PROJECT.md").read_text() if (proj / "PROJECT.md").exists() else ""
        except Exception:
            meta, writeup, project_md = {}, None, ""
        shown = []
        for d in drafts:
            if f"{slug}:{d['n']}" in hide:
                continue
            dd = base / slug / f"draft-{d['n']}"
            glance = ""
            rec = dd / "listening" / "record.md"
            if rec.exists():
                from listening import read_part
                glance = read_part(rec.read_text(), "glance")
            shown.append({**d, "has_audio": (dd / "render.wav").exists(), "heard": glance})
        out.append({"project": slug, "name": meta.get("name", slug), "kind": meta.get("kind"),
                    "project_md": project_md, "writeup": writeup, "drafts": shown})
    return out


def sketchbook(data_dir=None) -> List[Dict[str, Any]]:
    from studio import sketches
    hide = set(str(x) for x in hidden(data_dir)["sketches"])
    return [{k: v for k, v in s.items() if k != "sound_raw"} for s in sketches(data_dir) if str(s["n"]) not in hide]


def timeline(data_dir=None, crate=None, docs_=None, studio_=None, sketches_=None) -> List[Dict[str, Any]]:
    ev = []
    for a in crate if crate is not None else _jsonl(_data(data_dir) / "listening" / "activity.jsonl"):
        ev.append({"at": a["at"], "kind": "listening", "what": f"{a['action']}: {a.get('artist', '')} – {a.get('title', '')}".strip(" –")})
    for d in docs_ if docs_ is not None else docs(data_dir):
        for v in d["earlier"]:
            if v["at"]:
                ev.append({"at": v["at"], "kind": "writing", "what": f"revised {d['path']}"})
        ev.append({"at": d["updated"], "kind": "writing", "what": f"latest {d['path']}"})
    for p in studio_ if studio_ is not None else studio(data_dir):
        for d in p["drafts"]:
            ev.append({"at": d["at"], "kind": "studio", "what": f"{p['name']} draft {d['n']}: {d['message']}"})
    for s in sketches_ if sketches_ is not None else sketchbook(data_dir):
        inst = s.get("instrument") or {}
        what = inst.get("synth") or inst.get("patch") or ("808 kit" if inst.get("kit") else f"GM {inst.get('gm')}")
        ev.append({"at": s["at"], "kind": "sketch", "what": f"sketch {s['n']} on {what}" + (f": {s['note']}" if s.get("note") else "")})
    return sorted(ev, key=lambda e: e["at"] or "", reverse=True)


def shelf_ready(data_dir=None, asked=None) -> List[Dict[str, Any]]:
    """Every record on her shelf that's ready to read, and whether she asked for it or it was
    prepared for her (One-X and Hybrid Theory, by Daedalus at Kohl's ask, before she had the tool)."""
    asked_keys = {r.get("key") for r in (asked or [])}
    out = []
    for tj in (_data(data_dir) / "listening" / "records").glob("*/track.json"):
        try:
            t = json.loads(tj.read_text())
        except (OSError, ValueError):
            continue
        key = tj.parent.name
        out.append({"key": key, "artist": t.get("artist"), "album": t.get("album"), "title": t.get("title"),
                    "track": t.get("track"), "ready": datetime.fromtimestamp(tj.stat().st_mtime).isoformat(timespec="seconds"),
                    "how": "she asked for it" if key in asked_keys else "prepared for her"})
    def order(r):
        try:
            n = int(str(r.get("track") or 0).split("/")[0])
        except ValueError:
            n = 0
        return (r.get("artist") or "", r.get("album") or "", n)
    return sorted(out, key=order)


def _album_key(artist: str, album: str) -> str:
    import hashlib
    return hashlib.sha1(f"{artist}|{album}".lower().encode()).hexdigest()[:12]


def _norm(x) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", " ", str(x or "").lower()).strip()


def _measured(key, data_dir=None):
    """The record's basics for a track (what her ears measured, not her take)."""
    if not key:
        return None
    try:
        r = json.loads((_data(data_dir) / "listening" / "records" / key / "record.json").read_text())
        return {"tempo": r["rhythm"]["tempo"], "meter": f"{r['rhythm']['meter']}/4", "key": r["harmony"]["key"]["name"],
                "form": " ".join(x["label"] for x in r["form"]["sections"]),
                "lufs": r["loudness"]["integrated_lufs"], "minutes": round(r["source"]["duration"] / 60, 2),
                "words": len((r.get("words") or {}).get("lines", []))}
    except (OSError, ValueError, KeyError):
        return None


def albums(shelf: List[Dict[str, Any]], crate: List[Dict[str, Any]], docs_: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The crate as albums: her take on each album, each track with her take and when she
    listened. Albums she's touched (listened, read or written about) first."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in shelf:
        k = _album_key(r.get("artist") or "", r.get("album") or "")
        a = out.setdefault(k, {"key": k, "artist": r.get("artist"), "album": r.get("album"), "tracks": [],
                                "note": None, "how": r.get("how"), "touched": False})
        a["tracks"].append({"title": r.get("title"), "track": r.get("track"), "how": r.get("how"),
                            "listened": [], "note": None, "measured": _measured(r.get("key"))})
    def track_of(a, title):
        return next((t for t in a["tracks"] if _norm(t["title"]) == _norm(title)), None)
    for c in crate:
        for a in out.values():
            if _norm(c.get("artist")) == _norm(a["artist"]):
                t = track_of(a, c.get("title"))
                if t is not None:
                    t["listened"].append({"at": c["at"], "action": c["action"]})
                    a["touched"] = True
                elif c.get("title") and _norm(c["title"]).startswith(_norm(a["album"])):
                    a["touched"] = True
    for d in docs_:
        if not d.get("artist"):
            continue
        for a in out.values():
            from listening import _safe
            # her own folders may spell names differently (Three_Days_Grace/One_X): match loosely
            if _norm(a["artist"]) == _norm(d["artist"]) and _norm(a["album"]) == _norm(d["album"]):
                a["touched"] = True
                t = None if d["album_note"] else next(
                    (t for t in a["tracks"] if _norm(t["title"]) == _norm(d["song"])), None)
                if t is not None:
                    t["note"] = d
                elif d["album_note"] or a["note"] is None:
                    # an album note, or a note of hers about the album under another name
                    if a["note"] is not None and not a["note"].get("album_note"):
                        a.setdefault("other_notes", []).append(a["note"])
                    elif a["note"] is not None:
                        a.setdefault("other_notes", []).append(d)
                        continue
                    a["note"] = d
                else:
                    a.setdefault("other_notes", []).append(d)
    res = list(out.values())
    for a in res:
        a["tracks"].sort(key=lambda t: int(str(t.get("track") or 0).split("/")[0] or 0)
                         if str(t.get("track") or "0").split("/")[0].isdigit() else 0)
    return sorted(res, key=lambda a: (not a["touched"], a["artist"] or "", a["album"] or ""))


def cover(key: str, data_dir=None) -> Optional[Path]:
    """An album's cover: the art embedded in its first track, or a cover image in its folder."""
    if sharing(data_dir).get("audience") == "none":
        return None
    cache = _settings(data_dir) / "covers" / f"{key}.jpg"
    if cache.exists():
        return cache
    try:
        from listening import MUSIC_DIR
    except Exception:
        return None
    for tj in (_data(data_dir) / "listening" / "records").glob("*/track.json"):
        try:
            t = json.loads(tj.read_text())
        except (OSError, ValueError):
            continue
        if _album_key(t.get("artist") or "", t.get("album") or "") != key:
            continue
        f = MUSIC_DIR / t["id"]
        cache.parent.mkdir(parents=True, exist_ok=True)
        imgs = sorted([p for p in f.parent.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")],
                      key=lambda p: (not any(w in p.stem.lower() for w in ("cover", "folder", "front")), p.name))
        if imgs:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(imgs[0]), "-vf", "scale=300:-1",
                            str(cache)], capture_output=True, timeout=60)
            return cache if cache.exists() else None
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(f), "-an", "-vf", "scale=300:-1", "-frames:v", "1",
                        str(cache)], capture_output=True, timeout=60)
        return cache if cache.exists() else None
    return None


def build(data_dir=None) -> Dict[str, Any]:
    sh = sharing(data_dir)
    if sh.get("audience") == "none":
        return {"sharing": sh, "note": "she hasn't shared her music log", "crate": [], "docs": [], "studio": [],
                "sketchbook": [], "timeline": []}
    ready = _jsonl(_data(data_dir) / "listening" / "ready.jsonl")
    # the crate: her listen calls (logged since 2026-11-18 07:49) and every record she asked
    # to hear (logged when it was ready), in one list, newest last
    crate = _jsonl(_data(data_dir) / "listening" / "activity.jsonl") + [
        {"at": r["at"], "action": "listened", "artist": r.get("artist"), "album": r.get("album"), "title": r.get("title")}
        for r in ready]
    crate.sort(key=lambda c: c.get("at") or "")
    d, st, sk = docs(data_dir), studio(data_dir), sketchbook(data_dir)
    shelf = shelf_ready(data_dir, ready)
    return {"sharing": sh, "crate": crate, "records_she_asked_for": ready, "shelf_ready": shelf,
            "albums": albums(shelf, crate, d), "docs": d, "studio": st,
            "sketchbook": sk, "timeline": timeline(data_dir, crate, d, st, sk)}


# --- audio -------------------------------------------------------------------------

def render_wav(kind: str, ident: str, data_dir=None) -> Optional[Path]:
    """Where a draft's ("project:n") or sketch's ("n") render is, if it has one."""
    try:
        if kind == "draft":
            slug, _, n = str(ident).partition(":")
            if not re.fullmatch(r"[\w.-]+", slug):
                return None
            src = _data(data_dir) / "studio" / slug / f"draft-{int(n)}" / "render.wav"
        elif kind == "sketch":
            src = _data(data_dir) / "studio" / "sketchbook" / str(int(ident)) / "render.wav"
        else:
            return None
    except ValueError:
        return None
    return src if src.exists() else None


def mp3_of(src: Path, name: str, data_dir=None) -> Path:
    """A WAV as MP3, cached in her music_log folder and remade when the WAV changes."""
    cache = _settings(data_dir) / "audio" / f"{name}.mp3"
    if not cache.exists() or cache.stat().st_mtime < src.stat().st_mtime:
        cache.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-codec:a", "libmp3lame", "-q:a", "2", str(cache)],
                       check=True, capture_output=True, timeout=120)
    return cache


def audio(kind: str, ident: str, data_dir=None) -> Optional[Path]:
    """A draft's or sketch's render as MP3 (cached), if shared and not hidden."""
    if sharing(data_dir).get("audience") == "none":
        return None
    h = hidden(data_dir)
    if kind == "draft" and ident in h["drafts"]:
        return None
    if kind == "sketch" and str(ident) in [str(x) for x in h["sketches"]]:
        return None
    src = render_wav(kind, ident, data_dir)
    if src is None:
        return None
    return mp3_of(src, f"{kind}-{str(ident).replace(':', '-')}", data_dir)
