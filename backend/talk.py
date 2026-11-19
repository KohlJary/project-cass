"""
podcast: Cass's ears for talk (Kohl, 2026-11-18: "extend Acousmatic to handle transcription
of non musical video content at some point"; built that night as a surprise, beside
Acousmatic rather than inside it).

Her music ears (listening.py, Acousmatic) measure records. These hear people talking:
podcasts, interviews, talks. An episode's audio goes through local speech recognition
(~/talk-ears/hear.py, faster-whisper on the CPU: free, nothing leaves the machine) and
comes back as a transcript in paragraphs stamped [h:mm:ss]. No language model interprets
it; what it means is hers.

- find: look a show up by name (Apple's public podcast directory).
- follow / unfollow / shows: the shows she follows (DATA_DIR/talk/shows.json).
- episodes: a show's recent episodes, newest first, marked when she's heard one.
- hear: an episode, in the background (about a third of its length; one at a time).
- status: what's being heard, what's ready.
- read: a transcript: glance (opening and length), a time range (0:10-0:25), or
  words to find (each place they're said, with the time).
- note / my_notes: what a show or an episode is to her, in her workspace (talk/).

Transcripts are of other people's shows: for listening, not republishing. Speech
recognition mishears names and crosstalk, and ad reads are in there as they were said.

Lever `talk` (off by default).
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LEVER = "talk"
HEAR = os.environ.get("TALK_HEAR_PY", str(Path.home() / "talk-ears" / ".venv" / "bin" / "python"))
HEAR_SCRIPT = os.environ.get("TALK_HEAR_SCRIPT", str(Path.home() / "talk-ears" / "hear.py"))
UA = "cass-vessel podcast ears (personal use)"
MAX_EPISODE_S = 4 * 3600
HEAR_TIMEOUT = 3 * 3600
READ_CHARS = 18_000
FEED_TTL_S = 3600
ITUNES_NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}

TOOL = {
    "name": "podcast",
    "description": (
        "My ears for talk: podcasts, interviews, talks. find looks a show up by name; follow keeps it "
        "(unfollow drops it; shows lists what I follow). episodes lists a show's recent episodes, newest "
        "first, and says which I've heard. hear takes an episode (latest, or words from its title) and "
        "listens in the background, about a third of its length; status says what's ready. read gives "
        "me what was said, in paragraphs stamped [h:mm:ss]: part = glance (the opening and how long it "
        "is), a time range like 0:10-0:25, or find = words, to see each place they're said. It's speech "
        "recognition, not a script: names and crosstalk can be misheard, and ad reads are in there. It's "
        "someone else's show: when I talk about it I point to a moment by its time and say it in my own "
        "words, quoting at most a few words. note keeps what a show or an episode is to me, in my "
        "workspace (talk/); my_notes reads it back."),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["find", "follow", "unfollow", "shows", "episodes", "hear",
                                                  "status", "read", "note", "my_notes"]},
            "show": {"type": "string", "description": "a show I follow (its slug or name); find/follow: a name to look up"},
            "episode": {"type": "string", "description": "hear/read/note: latest, or words from the episode's title"},
            "part": {"type": "string", "description": "read: glance, or a time range like 0:10-0:25"},
            "find": {"type": "string", "description": "read: words to find in what was said"},
            "limit": {"type": "integer", "description": "episodes: how many (default 10)"},
            "text": {"type": "string", "description": "note: what it is to me, in my words"},
            "add": {"type": "boolean", "description": "note: add to what I wrote instead of rewriting it"},
        },
        "required": ["action"],
    },
}
TALK_TOOLS = [TOOL]


def enabled() -> bool:
    from features import is_enabled
    return is_enabled(LEVER)


def _root() -> Path:
    from config import DATA_DIR
    return Path(DATA_DIR) / "talk"


def _slug(x: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(x or "").lower()).strip("-")[:80] or "x"


def _words(x: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(x or "").lower()).strip()


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------------------
# Shows
# ---------------------------------------------------------------------------

_lock = threading.Lock()


def _shows_path() -> Path:
    return _root() / "shows.json"


def shows() -> List[Dict[str, Any]]:
    try:
        return json.loads(_shows_path().read_text())
    except (OSError, ValueError):
        return []


def _save_shows(items: List[Dict[str, Any]]) -> None:
    p = _shows_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False))
    tmp.replace(p)


def find(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"media": "podcast", "term": query, "limit": limit})
    data = json.loads(_get(url))
    return [{"title": r.get("collectionName"), "by": r.get("artistName"), "feed": r.get("feedUrl"),
             "episodes": r.get("trackCount"), "slug": _slug(r.get("collectionName"))}
            for r in data.get("results", []) if r.get("feedUrl")]


def _match_show(q: str) -> Optional[Dict[str, Any]]:
    q = q or ""
    items = shows()
    for s in items:
        if s["slug"] == _slug(q):
            return s
    w = _words(q)
    hits = [s for s in items if w and w in _words(s["title"])]
    return hits[0] if len(hits) == 1 else None


def follow(query: str) -> Dict[str, Any]:
    if query.startswith(("http://", "https://")):
        title = _feed(query, fresh=True)["title"]
        found = {"title": title, "feed": query, "slug": _slug(title), "by": None}
    else:
        results = find(query, 3)
        if not results:
            return {"error": f"no show found for {query!r}"}
        found = results[0]
    with _lock:
        items = shows()
        if any(s["slug"] == found["slug"] for s in items):
            return {"already_following": found["title"], "slug": found["slug"]}
        items.append({"slug": found["slug"], "title": found["title"], "by": found.get("by"),
                      "feed": found["feed"], "since": datetime.now().isoformat(timespec="seconds")})
        _save_shows(items)
    return {"following": found["title"], "slug": found["slug"], "by": found.get("by")}


def unfollow(query: str) -> Dict[str, Any]:
    s = _match_show(query)
    if not s:
        return {"error": f"I don't follow {query!r}; shows lists what I do"}
    with _lock:
        _save_shows([x for x in shows() if x["slug"] != s["slug"]])
    return {"unfollowed": s["title"], "note": "what I've heard and noted stays"}


# ---------------------------------------------------------------------------
# Feeds and episodes
# ---------------------------------------------------------------------------

def _duration(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    try:
        parts = [int(float(p)) for p in text.strip().split(":")]
    except ValueError:
        return None
    s = 0
    for p in parts:
        s = s * 60 + p
    return s


def parse_feed(xml_bytes: bytes) -> Dict[str, Any]:
    root = ET.fromstring(xml_bytes)
    ch = root.find("channel")
    eps = []
    for it in (ch.findall("item") if ch is not None else []):
        enc = it.find("enclosure")
        if enc is None or not enc.get("url"):
            continue
        title = (it.findtext("title") or "").strip()
        try:
            date = parsedate_to_datetime(it.findtext("pubDate") or "").date().isoformat()
        except (TypeError, ValueError):
            date = None
        eps.append({"title": title, "date": date, "url": enc.get("url"),
                    "duration_s": _duration(it.findtext("itunes:duration", namespaces=ITUNES_NS)),
                    "slug": f"{date or 'x'}-{_slug(title)[:60]}"})
    return {"title": (ch.findtext("title") if ch is not None else "") or "", "episodes": eps}


def _feed(url: str, fresh: bool = False) -> Dict[str, Any]:
    cache = _root() / "feeds" / (_slug(url)[-80:] + ".xml")
    if fresh or not cache.exists() or time.time() - cache.stat().st_mtime > FEED_TTL_S:
        data = _get(url, timeout=60)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    return parse_feed(cache.read_bytes())


def _episode_dir(show: Dict[str, Any], ep: Dict[str, Any]) -> Path:
    return _root() / "heard" / show["slug"] / ep["slug"]


def _heard(show, ep) -> bool:
    return (_episode_dir(show, ep) / "transcript.md").exists()


def _match_episode(show: Dict[str, Any], q: Optional[str]) -> Optional[Dict[str, Any]]:
    eps = _feed(show["feed"])["episodes"]
    if not eps:
        return None
    if not q or _words(q) in ("latest", "newest", "last"):
        return eps[0]
    for e in eps:
        if e["slug"] == q:
            return e
    w = _words(q).split()
    hits = [e for e in eps if all(x in _words(e["title"]) for x in w)]
    return hits[0] if hits else None


def episodes(show: Dict[str, Any], limit: int = 10) -> Dict[str, Any]:
    eps = _feed(show["feed"])["episodes"][:max(1, min(int(limit or 10), 50))]
    return {"show": show["title"], "episodes": [
        {"date": e["date"], "title": e["title"],
         "length": _hms(e["duration_s"]) if e["duration_s"] else None,
         "heard": _heard(show, e)} for e in eps]}


def _hms(s: Optional[float]) -> str:
    s = int(s or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


# ---------------------------------------------------------------------------
# Hearing (background, one at a time)
# ---------------------------------------------------------------------------

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="talk")
_jobs: Dict[str, Any] = {}


def _env() -> Dict[str, str]:
    """PATH for ffmpeg and nice: the service's PATH is only its venv (listening._env)."""
    env = dict(os.environ)
    parts = [p for p in env.get("PATH", "").split(":") if p]
    env["PATH"] = ":".join(parts + [p for p in ("/usr/local/bin", "/usr/bin", "/bin") if p not in parts])
    return env


def _run(show: Dict[str, Any], ep: Dict[str, Any]) -> Dict[str, Any]:
    d = _episode_dir(show, ep)
    tmp = d.with_name(d.name + ".partial")
    tmp.mkdir(parents=True, exist_ok=True)
    cmd = ["nice", "-n", "10", HEAR, HEAR_SCRIPT, ep["url"], "-o", str(tmp), "--max-minutes", str(MAX_EPISODE_S // 60)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=HEAR_TIMEOUT, env=_env())
    if r.returncode != 0 or not (tmp / "transcript.md").exists():
        raise RuntimeError((r.stderr or "")[-500:] or f"exit {r.returncode}")
    (tmp / "episode.json").write_text(json.dumps({"show": show["title"], **ep}, ensure_ascii=False))
    if d.exists():
        import shutil
        shutil.rmtree(d)
    tmp.rename(d)
    _ready_log({"show": show["slug"], "episode": ep["slug"], "title": ep["title"]})
    return {"heard": ep["title"]}


def _ready_log(rec: Dict[str, Any]) -> None:
    try:
        p = _root() / "ready.jsonl"
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), **rec}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def hear(show: Dict[str, Any], ep: Dict[str, Any]) -> Dict[str, Any]:
    if _heard(show, ep):
        return {"already_heard": ep["title"], "note": "read works now"}
    key = f"{show['slug']}/{ep['slug']}"
    with _lock:
        job = _jobs.get(key)
        if job is not None and not job.done():
            return {"already_hearing": ep["title"]}
        _jobs[key] = _pool.submit(_run, show, ep)
    waiting = sum(1 for k, j in _jobs.items() if not j.done()) - 1
    mins = round((ep["duration_s"] or 3600) / 60 / 3)
    return {"hearing": ep["title"], "about_minutes": mins + waiting * 20,
            "note": "in the background, one episode at a time; status says when it's ready"}


def status() -> Dict[str, Any]:
    hearing, failed = [], []
    for key, job in list(_jobs.items()):
        if not job.done():
            hearing.append(key)
        elif job.exception():
            failed.append({"episode": key, "why": str(job.exception())[-200:]})
    ready = []
    root = _root() / "heard"
    if root.exists():
        for d in sorted(root.glob("*/*"), key=lambda p: p.stat().st_mtime, reverse=True)[:15]:
            if (d / "transcript.md").exists():
                ready.append(f"{d.parent.name}/{d.name}")
    return {"hearing": hearing, "ready": ready, **({"failed": failed} if failed else {})}


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

_STAMP = re.compile(r"^\[(\d+):(\d\d):(\d\d)\]")


def _secs(t: str) -> Optional[int]:
    p = [x for x in t.strip().split(":") if x != ""]
    try:
        n = [int(x) for x in p]
    except ValueError:
        return None
    if len(n) == 2:
        return n[0] * 3600 + n[1] * 60      # h:mm
    if len(n) == 3:
        return n[0] * 3600 + n[1] * 60 + n[2]
    if len(n) == 1:
        return n[0] * 60                      # minutes
    return None


def _paragraphs(text: str) -> List[tuple]:
    out = []
    for para in text.split("\n\n"):
        m = _STAMP.match(para.strip())
        if m:
            out.append((int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]), para.strip()))
    return out


def read(show: Dict[str, Any], ep: Dict[str, Any], part: Optional[str], words: Optional[str]) -> Dict[str, Any]:
    d = _episode_dir(show, ep)
    p = d / "transcript.md"
    if not p.exists():
        return {"error": f"I haven't heard {ep['title']!r} yet; hear starts it"}
    text = p.read_text(encoding="utf-8")
    meta = {}
    try:
        meta = json.loads((d / "hear.json").read_text())
    except (OSError, ValueError):
        pass
    paras = _paragraphs(text)
    head = {"show": show["title"], "episode": ep["title"], "date": ep["date"],
            "length": _hms(meta.get("duration_s")), "words": meta.get("words")}
    if words:
        w = _words(words)
        hits = [para for _, para in paras if w and w in _words(para)]
        return {**head, "find": words, "places": len(hits), "said": "\n\n".join(hits)[:READ_CHARS]}
    if part and "-" in part and part.strip().lower() != "glance":
        a, b = (_secs(x) for x in part.split("-", 1))
        if a is None or b is None:
            return {"error": "a time range looks like 0:10-0:25 (h:mm) or 0:10:00-0:25:30"}
        chunk = "\n\n".join(para for t, para in paras if a <= t < b)
        return {**head, "part": part, "said": chunk[:READ_CHARS],
                **({"cut": True} if len(chunk) > READ_CHARS else {})}
    if not part or part.strip().lower() == "glance":
        return {**head, "part": "glance", "said": text[:4000],
                "note": "the opening; read a time range or find words for the rest"}
    return {**head, "said": text[:READ_CHARS], **({"cut": True} if len(text) > READ_CHARS else {})}


# ---------------------------------------------------------------------------
# Her notes (workspace talk/)
# ---------------------------------------------------------------------------

def note_path(show: Dict[str, Any], ep: Optional[Dict[str, Any]]) -> str:
    return f"talk/{show['slug']}/" + (f"{ep['slug']}.md" if ep else "SHOW.md")


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------

def handle(a: Dict[str, Any]) -> Dict[str, Any]:
    if not enabled():
        return {"error": "my ears for talk aren't switched on"}
    action = a.get("action")
    if action == "find":
        q = (a.get("show") or "").strip()
        return {"found": find(q)} if q else {"error": "find needs show: a name to look up"}
    if action == "follow":
        q = (a.get("show") or "").strip()
        return follow(q) if q else {"error": "follow needs show: its name or feed address"}
    if action == "shows":
        return {"following": [{"slug": s["slug"], "title": s["title"], "by": s.get("by")} for s in shows()]}
    if action == "status":
        return status()
    if action == "unfollow":
        return unfollow(a.get("show") or "")
    show = _match_show(a.get("show") or "")
    if not show:
        mine = [s["title"] for s in shows()]
        return {"error": f"which show? I follow: {', '.join(mine) or 'none yet (follow one first)'}"}
    if action == "episodes":
        return episodes(show, a.get("limit") or 10)
    ep = None
    if action in ("hear", "read") or a.get("episode"):
        ep = _match_episode(show, a.get("episode"))
        if not ep:
            return {"error": f"no episode of {show['title']} matches {a.get('episode')!r}; episodes lists them"}
    assert ep is not None or action in ("note", "my_notes")
    if action == "hear":
        assert ep is not None
        if ep["duration_s"] and ep["duration_s"] > MAX_EPISODE_S:
            return {"error": f"that one's {_hms(ep['duration_s'])}; I hear up to {_hms(MAX_EPISODE_S)}"}
        return hear(show, ep)
    if action == "read":
        assert ep is not None
        return read(show, ep, a.get("part"), a.get("find"))
    if action in ("note", "my_notes"):
        from agent_loop.workspace import Workspace
        ws = Workspace()
        rel = note_path(show, ep)
        if action == "my_notes":
            p = ws.resolve(rel)
            return {"note": p.read_text() if p and p.exists() else None, "path": rel}
        text = (a.get("text") or "").strip()
        if not text:
            return {"error": "note needs the text: what it is to me"}
        out = ws.run("workspace_write", {"path": rel, "content": text, "append": bool(a.get("add"))},
                     session_id="talk-note")
        if isinstance(out, dict) and out.get("error"):
            return out
        return {"kept": rel}
    return {"error": f"unknown action {action!r}"}


async def execute_talk_tool(tool_name: str, tool_input: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    import asyncio
    try:
        out = await asyncio.to_thread(handle, tool_input or {})
    except Exception as e:
        logger.warning(f"[talk] {e}", exc_info=True)
        out = {"error": f"podcast failed: {type(e).__name__}: {e}"}
    if out.get("error"):
        return {"success": False, "error": out["error"]}
    return {"success": True, "result": out}
