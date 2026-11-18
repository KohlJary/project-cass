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
            out.append({"path": rel, "title": p.stem, "updated": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
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
    return {"sharing": sh, "crate": crate, "records_she_asked_for": ready, "docs": d, "studio": st,
            "sketchbook": sk, "timeline": timeline(data_dir, crate, d, st, sk)}


# --- audio -------------------------------------------------------------------------

def audio(kind: str, ident: str, data_dir=None) -> Optional[Path]:
    """A draft's or sketch's render as MP3 (cached), if shared and not hidden."""
    if sharing(data_dir).get("audience") == "none":
        return None
    h = hidden(data_dir)
    if kind == "draft":
        slug, _, n = ident.partition(":")
        if ident in h["drafts"]:
            return None
        src = _data(data_dir) / "studio" / slug / f"draft-{int(n)}" / "render.wav"
    elif kind == "sketch":
        if str(ident) in [str(x) for x in h["sketches"]]:
            return None
        src = _data(data_dir) / "studio" / "sketchbook" / str(int(ident)) / "render.wav"
    else:
        return None
    if not src.exists():
        return None
    cache = _settings(data_dir) / "audio" / f"{kind}-{ident.replace(':', '-')}.mp3"
    if not cache.exists() or cache.stat().st_mtime < src.stat().st_mtime:
        cache.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-codec:a", "libmp3lame", "-q:a", "2", str(cache)],
                       check=True, capture_output=True, timeout=120)
    return cache
