"""
Finding memes (Kohl, 2026-11-24: "They gotta be able to find the hot memes.
I'm way behind on my meme intake. Tasteful though.").

find_memes looks at what's top in a few meme communities today and shows her
the pictures themselves, so she picks with her own eyes and her own taste. The
ones she looked at are saved under memes/ in her data, so babelr_dm or
babelr_post can attach one (files: ["memes/<file>"]). Nothing is sent by this
tool; sharing is hers.

The source is Lemmy (lemmy.world's open API, communities federated from other
instances). Reddit's JSON now refuses requests without an app login.

Her sources are hers (Kohl, same night: "configurable and also self-modifiable
by the daemons"): memes/sources.json in her data, which she changes with the
meme_sources tool. Until she does, the list is MEME_COMMUNITIES
(comma-separated, name@instance) or the defaults below.

NSFW is two keys ("And make NSFW a toggle"): the house's MEME_NSFW_ALLOWED
(off unless set to 1) and her own choice. NSFW posts show only when both are on.
Porn and gore are never shown either way: the pictures go to the model.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

API = "https://lemmy.world/api/v3/post/list"
USER_AGENT = "house-vessel/0.1 (meme finder)"  # generic; nothing about her or Kohl
DEFAULT_COMMUNITIES = (
    "memes@lemmy.world",
    "memes@lemmy.ml",
    "programmer_humor@programming.dev",
    "science_memes@mander.xyz",
    "mathmemes@lemmy.blahaj.zone",
    "comics@lemmy.world",
    "196@lemmy.blahaj.zone",
)
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".webp": "image/webp", ".gif": "image/gif"}
MAX_BYTES = 3_500_000          # Anthropic's per-image limit is 5 MB as base64
MAX_SHOWN = 4
SEEN_KEEP = 1000
KEEP_DAYS = 7
HARD_SKIP = re.compile(r"\b(nsfl|gore|porn|porno|hentai|nude|nudes)\b", re.I)
NSFW_WORD = re.compile(r"\bnsfw\b", re.I)
COMMUNITY = re.compile(r"^[a-z0-9_]{1,64}@[a-z0-9.-]+\.[a-z]{2,}$", re.I)

FIND_MEMES_TOOL = {
    "name": "find_memes",
    "description": (
        "Look at what's funny on the internet today: the top posts from a few meme communities, "
        "shown to you as the pictures themselves. Pass a topic to look for something particular "
        "(e.g. 'music', 'programming', 'cats'). The ones you see are saved as files, so you can "
        "attach one to a DM or a post with babelr_dm / babelr_post (files: [\"memes/<file>\"]). "
        "Share only the ones you actually like; nothing is sent by this tool. Where it looks is "
        "yours to change with meme_sources."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Optional: words to look for in titles"},
            "count": {"type": "integer", "description": "How many to look at (1-4, default 4)"},
            "period": {"type": "string", "enum": ["day", "week"],
                       "description": "Top of the day (default) or of the week"},
        },
    },
}


def house_defaults() -> List[str]:
    import os
    raw = os.environ.get("MEME_COMMUNITIES", "").strip()
    return [c.strip() for c in raw.split(",") if c.strip()] if raw else list(DEFAULT_COMMUNITIES)


def nsfw_allowed_by_house() -> bool:
    import os
    return os.environ.get("MEME_NSFW_ALLOWED", "").strip().lower() in ("1", "true", "yes", "on")


def _settings() -> Dict[str, Any]:
    try:
        s = json.loads((_dir() / "sources.json").read_text())
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_settings(s: Dict[str, Any]) -> None:
    (_dir() / "sources.json").write_text(json.dumps(s, indent=1))


def communities() -> List[str]:
    """Hers if she's set them, else the house's defaults."""
    mine = _settings().get("communities")
    return list(mine) if isinstance(mine, list) else house_defaults()


def nsfw_on() -> bool:
    return nsfw_allowed_by_house() and bool(_settings().get("nsfw"))


def _dir() -> Path:
    from config import DATA_DIR
    d = Path(DATA_DIR) / "memes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _seen() -> List[str]:
    try:
        return json.loads((_dir() / "seen.json").read_text())
    except (OSError, ValueError):
        return []


def _remember(ids: List[str]) -> None:
    keep = (_seen() + ids)[-SEEN_KEEP:]
    (_dir() / "seen.json").write_text(json.dumps(keep))


def _tidy(now: Optional[float] = None) -> None:
    """Pictures she looked at and didn't keep go after a week."""
    cutoff = (now or time.time()) - KEEP_DAYS * 86400
    for f in _dir().iterdir():
        if f.suffix in IMAGE_TYPES and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)


def _ext(url: str) -> Optional[str]:
    path = url.lower().split("?")[0]
    return next((e for e in IMAGE_TYPES if path.endswith(e)), None)


def candidates(posts: List[Dict[str, Any]], topic: Optional[str], seen: List[str],
               nsfw: bool = False) -> List[Dict[str, Any]]:
    """Image posts worth showing her, best first: nothing she's seen, NSFW only
    when `nsfw`, porn and gore never."""
    words = [w for w in re.findall(r"\w+", (topic or "").lower()) if len(w) > 2]
    out = []
    for row in posts:
        p, c, counts = row.get("post") or {}, row.get("community") or {}, row.get("counts") or {}
        url = p.get("url") or ""
        key = p.get("ap_id") or str(p.get("id"))
        title = p.get("name") or ""
        flagged = p.get("nsfw") or c.get("nsfw") or NSFW_WORD.search(title)
        if ((flagged and not nsfw) or p.get("removed") or p.get("deleted")
                or not _ext(url) or key in seen or HARD_SKIP.search(title)):
            continue
        hay = f"{p.get('name') or ''} {c.get('name') or ''} {c.get('title') or ''}".lower()
        if words and not any(w[:6] in hay for w in words):  # a stem: "programming" finds programmer_humor
            continue
        out.append({"key": key, "title": p.get("name") or "", "url": url,
                    "community": c.get("name") or "", "score": counts.get("score", 0),
                    "link": p.get("ap_id") or ""})
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def _fetch_posts(period: str) -> List[Dict[str, Any]]:
    sort = "TopWeek" if period == "week" else "TopDay"
    rows: List[Dict[str, Any]] = []
    for name in communities():
        try:
            params = {"community_name": name, "sort": sort, "limit": 20}
            if nsfw_on():
                params["show_nsfw"] = "true"
            r = requests.get(API, params=params,
                             headers={"User-Agent": USER_AGENT}, timeout=10)
            if r.ok:
                rows += r.json().get("posts") or []
            else:
                logger.info(f"[memes] {name}: HTTP {r.status_code}")
        except (requests.RequestException, ValueError) as e:
            logger.info(f"[memes] {name}: {e}")
    return rows


def _download(c: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ext = _ext(c["url"])
    try:
        r = requests.get(c["url"], headers={"User-Agent": USER_AGENT}, timeout=15, stream=True)
        if not r.ok:
            return None
        data = r.raw.read(MAX_BYTES + 1, decode_content=True)
    except requests.RequestException:
        return None
    if len(data) > MAX_BYTES or not data:
        return None
    safe = re.sub(r"[^\w-]", "", c["key"].rsplit("/", 1)[-1])[:40] or str(abs(hash(c["key"])))
    name = f"{safe}{ext}"
    (_dir() / name).write_bytes(data)
    return {"file": f"memes/{name}", "media_type": IMAGE_TYPES[ext],
            "data": base64.b64encode(data).decode()}


def find_memes(topic: Optional[str] = None, count: int = MAX_SHOWN, period: str = "day") -> Dict[str, Any]:
    count = max(1, min(MAX_SHOWN, int(count or MAX_SHOWN)))
    _tidy()
    pool = candidates(_fetch_posts(period), topic, _seen(), nsfw=nsfw_on())
    shown, images, shown_keys = [], [], []
    for c in pool:
        if len(shown) >= count:
            break
        got = _download(c)
        if not got:
            continue
        shown_keys.append(c["key"])
        shown.append({"n": len(shown) + 1, "title": c["title"], "community": c["community"],
                      "score": c["score"], "file": got["file"], "link": c["link"]})
        images.append({"media_type": got["media_type"], "data": got["data"]})
    _remember(shown_keys)
    if not shown:
        why = "nothing new matching that" if topic else "nothing new right now"
        return {"success": True, "memes": [], "note": f"{why}; try period 'week' or another topic"}
    return {"success": True, "memes": shown,
            "note": "The pictures follow, in this order. Attach one with files: [its file].",
            "_images": images}


# --- her sources ------------------------------------------------------------------

COMMUNITY_API = "https://lemmy.world/api/v3/community"

MEME_SOURCES_TOOL = {
    "name": "meme_sources",
    "description": (
        "See or change where find_memes looks: your own list of meme communities (Lemmy, written "
        "name@instance, e.g. programmer_humor@programming.dev), and whether NSFW memes are shown to "
        "you. The list is yours to shape; reset goes back to the house's defaults."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "add", "remove", "reset", "nsfw_on", "nsfw_off"]},
            "community": {"type": "string", "description": "For add/remove: name@instance"},
        },
        "required": ["action"],
    },
}


def _lookup(name: str) -> Dict[str, Any]:
    """The community as Lemmy knows it, or an error."""
    try:
        r = requests.get(COMMUNITY_API, params={"name": name}, headers={"User-Agent": USER_AGENT}, timeout=10)
    except requests.RequestException as e:
        return {"error": f"couldn't reach Lemmy: {e}"}
    if r.status_code == 404:
        return {"error": f"Lemmy doesn't know {name}"}
    if not r.ok:
        return {"error": f"Lemmy said {r.status_code}"}
    view = (r.json() or {}).get("community_view") or {}
    c = view.get("community") or {}
    return {"name": name, "title": c.get("title") or c.get("name"), "nsfw": bool(c.get("nsfw")),
            "subscribers": (view.get("counts") or {}).get("subscribers")}


def meme_sources(action: str, community: Optional[str] = None, now: Optional[str] = None) -> Dict[str, Any]:
    from datetime import datetime
    s = _settings()
    mine = communities()
    when = now or datetime.now().isoformat(timespec="seconds")

    def done(note: str) -> Dict[str, Any]:
        s.setdefault("log", []).append({"at": when, "did": note})
        s["log"] = s["log"][-50:]
        _save_settings(s)
        return {**view(), "did": note}

    def view() -> Dict[str, Any]:
        return {"success": True, "communities": communities(),
                "yours": isinstance(_settings().get("communities"), list),
                "nsfw": {"your_choice": bool(_settings().get("nsfw")), "house_allows": nsfw_allowed_by_house(),
                         "shown": nsfw_on()}}

    if action == "list":
        return view()
    if action == "reset":
        s.pop("communities", None)
        return done("back to the house's defaults")
    if action in ("nsfw_on", "nsfw_off"):
        s["nsfw"] = action == "nsfw_on"
        out = done(f"NSFW {'on' if s['nsfw'] else 'off'} (your side)")
        if s["nsfw"] and not nsfw_allowed_by_house():
            out["note"] = "The house hasn't allowed NSFW (MEME_NSFW_ALLOWED), so it stays off until it does."
        return out
    if action in ("add", "remove"):
        name = (community or "").strip().lstrip("!").lower()
        if not COMMUNITY.match(name):
            return {"success": False, "error": "write it as name@instance, e.g. memes@lemmy.ml"}
        if action == "remove":
            if name not in mine:
                return {"success": False, "error": f"{name} isn't in your list"}
            s["communities"] = [c for c in mine if c != name]
            return done(f"removed {name}")
        if name in mine:
            return {"success": False, "error": f"{name} is already in your list"}
        found = _lookup(name)
        if found.get("error"):
            return {"success": False, "error": found["error"]}
        s["communities"] = mine + [name]
        out = done(f"added {name}")
        out["added"] = found
        if found["nsfw"] and not nsfw_on():
            out["note"] = "That community is marked NSFW, so its posts won't show while NSFW is off."
        return out
    return {"success": False, "error": f"unknown action '{action}'"}
