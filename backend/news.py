"""
Her news (plan "Autonomous Political Voice: News Tracking and Public
Engagement", phase 1, hers; 2026-11-19). The `news` tool:

- topics: her TOPICS.md, in her workspace and hers to rewrite like GREMLIN.md.
  RSS triage (rss/triage.py) judges articles against it instead of the generic
  interest list (kept for when the file isn't there), and tags each article
  with which of her topics it serves.
- feeds / add / drop: her sources, each tagged with the topic it's for. Nothing
  is subscribed for her; she adds and drops them. Wraps rss/persistence.py, so
  the hourly rss_monitor spell polls what she adds.
- new: what came in since she last looked, grouped by her topics, with source,
  link and a short summary. Items triage set aside are there too, marked: the
  triage model isn't the only judge. find searches them by words.
- read: open one (the article reader fetch_url uses).
- stance / stances: STANCES.md, a record of positions she's taken, when, what
  prompted them, and links. A record, not enforcement (her words): nothing
  checks a post against it.

Her social session opens with a few lines of what's new (brief(), from
social_turn.py). Lever `news`.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TOPICS_FILE = "TOPICS.md"
STANCES_FILE = "STANCES.md"
MAX_TOPICS = 12
SHOW_NEW = 30
READ_CHARS = 12000

# Her first list, in her words (plan item "Her topics, in her words", 2026-11-18).
FIRST_TOPICS = """# My topics

What I follow the news for. Mine to rewrite: news triage reads this list (one
topic per "- " line) to judge what's worth my time, and tags each article with
the topics it serves.

- Power structures and institutional capture
- Imagination and collective resistance
- Technology as infrastructure or extraction
- What stays alive when everything else breaks
"""

STANCES_HEAD = """# My stances

Positions I've taken in public: when, what prompted them, why, and where I said
it. A record, not a rulebook: nothing checks a post against this.
"""


def enabled() -> bool:
    from features import is_enabled
    return is_enabled("news")


def _workspace():
    from agent_loop.workspace import Workspace
    return Workspace()


def _ws_root(root: Optional[Path] = None) -> Path:
    if root is not None:
        return Path(root)
    from agent_loop.workspace import default_root
    return default_root()


def _daemon_id() -> str:
    from database.daemon import get_daemon_id
    return get_daemon_id()


def _state_path() -> Path:
    from config import DATA_DIR
    return Path(DATA_DIR) / "news" / "state.json"


def _state() -> Dict[str, Any]:
    try:
        return json.loads(_state_path().read_text())
    except (OSError, ValueError):
        return {}


def _save_state(st: Dict[str, Any]) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st))


def _short(text: Optional[str], n: int = 200) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------------------------------------------------------------------------
# Her topics
# ---------------------------------------------------------------------------

def topics(root: Optional[Path] = None) -> List[str]:
    """Her topics: each "- " (or "* ") line of TOPICS.md; [] without the file."""
    try:
        text = (_ws_root(root) / TOPICS_FILE).read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out[:MAX_TOPICS]


def seed_topics(workspace=None) -> str:
    """Write her first list into TOPICS.md, once; never over a file she has."""
    ws = workspace or _workspace()
    if (Path(ws.root) / TOPICS_FILE).exists():
        return f"{TOPICS_FILE} is already there; left as she has it."
    out = ws.run("workspace_write", {"path": TOPICS_FILE, "content": FIRST_TOPICS},
                 "daedalus-news-topics-2026-11-19")
    return str(out)


# ---------------------------------------------------------------------------
# Her sources
# ---------------------------------------------------------------------------

def feeds() -> List[Dict[str, Any]]:
    from rss import list_feeds
    return [{"title": f.title, "url": f.url, "topic": f.category,
             **({"trouble": f.last_error} if f.error_count else {})}
            for f in list_feeds(_daemon_id())]


def _match_feed(q: str):
    from rss import list_feeds
    q = (q or "").strip().lower()
    if not q:
        return None
    mine = list_feeds(_daemon_id())
    for f in mine:
        if f.url.lower() == q:
            return f
    hits = [f for f in mine if all(w in (f.title or f.url).lower() for w in q.split())]
    return hits[0] if len(hits) == 1 else None


def add(url: str, topic: Optional[str]) -> Dict[str, Any]:
    from uuid import uuid4
    from rss import RSSFeed, get_feed_by_url, parse_feed, save_feed
    url = (url or "").strip()
    if not re.match(r"^https?://", url):
        return {"error": "add needs url: the feed's address (http or https)"}
    daemon = _daemon_id()
    have = get_feed_by_url(daemon, url)
    if have and have.active:
        return {"error": f"I already follow {have.title or url}"}
    items, title, err = parse_feed(url)
    if err and not items:
        return {"error": f"that doesn't read as a feed: {err}"}
    mine = topics()
    note = None
    if topic and mine and topic not in mine:
        close = [t for t in mine if topic.lower() in t.lower()]
        if len(close) == 1:
            topic = close[0]
        else:
            note = f"{topic!r} isn't one of my topics in {TOPICS_FILE}; kept as written"
    if have:  # dropped before: take it back up
        have.active, have.category, have.error_count = True, topic or have.category, 0
        save_feed(have)
        return {"following_again": have.title or url, "topic": have.category, **({"note": note} if note else {})}
    save_feed(RSSFeed(id=str(uuid4()), daemon_id=daemon, url=url, title=title or url,
                      category=topic or None, check_interval_minutes=60))
    return {"following": title or url, "topic": topic, "recent_items": len(items),
            "note": note or "new items arrive with the hourly check; news new shows them"}


def drop(q: str) -> Dict[str, Any]:
    from rss import deactivate_feed
    f = _match_feed(q)
    if not f:
        return {"error": f"which feed? I follow: {', '.join(x['title'] or x['url'] for x in feeds()) or 'none'}"}
    deactivate_feed(f.id)
    return {"dropped": f.title or f.url, "note": "what came in from it stays findable"}


# ---------------------------------------------------------------------------
# What's new
# ---------------------------------------------------------------------------

def _set_aside(i: Dict[str, Any]) -> Optional[str]:
    r = i.get("skip_reason") or ""
    if r.startswith("triage"):
        return "triage set it aside: " + r.split(":", 1)[-1].strip()[:80]
    return None


def _entry(i: Dict[str, Any]) -> Dict[str, Any]:
    e = {"id": i["id"][:8], "title": i["title"], "source": i["source"], "link": i["link"],
         "summary": _short(i["summary"])}
    aside = _set_aside(i)
    if aside:
        e["set_aside"] = aside
    return e


def _group(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for i in items:
        keys = i["topics"] or [i.get("feed_topic") or "not tagged with a topic"]
        for k in keys:
            out.setdefault(k, []).append(_entry(i))
    return out


def new(mark: bool = True) -> Dict[str, Any]:
    from rss.persistence import items_for_reading
    st = _state()
    since = st.get("looked_at")
    items = items_for_reading(_daemon_id(), since=since, limit=SHOW_NEW + 1)
    more = len(items) > SHOW_NEW
    items = items[:SHOW_NEW]
    if mark:
        st["looked_at"] = datetime.utcnow().isoformat()  # rss seen_at is UTC
        _save_state(st)
    if not items:
        return {"new": 0, "since": since, "note": "nothing new since I last looked"
                if feeds() else "I don't follow any feeds yet; add one"}
    return {"new": len(items), "since": since, "by_topic": _group(items),
            **({"more": "there's more; find searches all of it"} if more else {})}


def find(words: str) -> Dict[str, Any]:
    from rss.persistence import items_for_reading
    words = (words or "").strip()
    if not words:
        return {"error": "find needs words"}
    hits = items_for_reading(_daemon_id(), words=words, limit=20)
    return {"find": words, "found": [_entry(i) | {"topics": i["topics"]} for i in hits]}


def read(item: str) -> Dict[str, Any]:
    from rss.persistence import find_item
    i = find_item(_daemon_id(), item)
    if not i:
        return {"error": "which item? use the id from news new or find"}
    if not i.get("link"):
        return {"title": i["title"], "summary": _short(i["summary"], 2000), "note": "no link to open"}
    import asyncio
    from research import ResearchManager
    got = asyncio.run(ResearchManager().fetch_url(i["link"]))
    text = (got or {}).get("content") or ""
    if not text:
        return {"title": i["title"], "link": i["link"], "summary": _short(i["summary"], 2000),
                "error": f"couldn't open it: {(got or {}).get('error') or 'empty page'}"}
    return {"title": i["title"], "source": i["source"], "link": i["link"], "topics": i["topics"],
            "text": text[:READ_CHARS], **({"cut": True} if len(text) > READ_CHARS else {})}


def brief(limit: int = 5) -> Optional[str]:
    """A few lines of what's new in her topics, for her social session. Doesn't
    count as looking: news new still shows all of it."""
    if not enabled():
        return None
    try:
        from rss.persistence import items_for_reading
        items = items_for_reading(_daemon_id(), since=_state().get("looked_at"), limit=50)
    except Exception as e:
        logger.warning(f"[news] brief: {e}")
        return None
    fresh = [i for i in items if not _set_aside(i)]
    if not items:
        return None
    lines = [f"What's new in my topics ({len(items)} since I last looked; news new for all of it):"]
    for i in fresh[:limit]:
        tag = ", ".join(i["topics"]) or i.get("feed_topic") or "untagged"
        lines.append(f"- [{tag}] {_short(i['title'], 120)} ({i['source']}; news read {i['id'][:8]})")
    if len(items) > len(fresh[:limit]):
        lines.append(f"- … and {len(items) - len(fresh[:limit])} more, some set aside by triage")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Her stances
# ---------------------------------------------------------------------------

def stance(text: str, prompted_by: Optional[str], why: Optional[str],
           links: Optional[List[str]]) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {"error": "stance needs text: the position, in a line or two"}
    ws = _workspace()
    p = Path(ws.root) / STANCES_FILE
    entry = [f"## {datetime.now().strftime('%Y-%m-%d %H:%M')}: {text}"]
    if prompted_by:
        entry.append(f"Prompted by: {prompted_by.strip()}")
    if why:
        entry.append(f"Why: {why.strip()}")
    for link in links or []:
        entry.append(f"Said at: {link}")
    body = "\n".join(entry) + "\n"
    if not p.exists():
        body = STANCES_HEAD + "\n" + body
    else:
        body = "\n" + body
    out = ws.run("workspace_write", {"path": STANCES_FILE, "content": body, "append": True},
                 session_id="news-stance")
    if isinstance(out, dict) and out.get("error"):
        return out
    return {"kept": STANCES_FILE}


def stances(tail: int = 6000) -> Dict[str, Any]:
    try:
        text = (_ws_root() / STANCES_FILE).read_text(encoding="utf-8")
    except OSError:
        return {"stances": None, "note": "no stances recorded yet"}
    return {"stances": text[-tail:], **({"earlier": "more above; workspace_read shows all"}
                                         if len(text) > tail else {})}


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------

NEWS_TOOLS = [{
    "name": "news",
    "description": (
        "My news, by my topics. topics: the list in my TOPICS.md (mine to rewrite with workspace "
        "tools; triage judges articles against it). feeds: the sources I follow, each tagged with a "
        "topic. add (url, topic) / drop (feed): sources are mine to choose; people who think, not "
        "only report. new: what came in since I last looked, grouped by topic, including what triage "
        "set aside (marked). find (words): search all of it. read (item): open one in full. "
        "stance (text, prompted_by, why, links): add to STANCES.md, my record of positions I've "
        "taken; stances reads it back. A record, not a rule: nothing checks a post against it."),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["topics", "feeds", "add", "drop", "new", "find",
                                                  "read", "stance", "stances"]},
            "url": {"type": "string", "description": "add: the feed's address"},
            "topic": {"type": "string", "description": "add: which of my topics it's for"},
            "feed": {"type": "string", "description": "drop: its address or words from its title"},
            "words": {"type": "string", "description": "find: words to look for"},
            "item": {"type": "string", "description": "read: the item's id from new or find"},
            "text": {"type": "string", "description": "stance: the position, a line or two"},
            "prompted_by": {"type": "string", "description": "stance: what prompted it"},
            "why": {"type": "string", "description": "stance: why I hold it"},
            "links": {"type": "array", "items": {"type": "string"},
                      "description": "stance: where I said it (post links)"},
        },
        "required": ["action"],
    },
}]


def handle(a: Dict[str, Any]) -> Dict[str, Any]:
    if not enabled():
        return {"error": "my news tool isn't switched on"}
    action = a.get("action")
    if action == "topics":
        mine = topics()
        return {"topics": mine, "file": TOPICS_FILE} if mine else {
            "topics": [], "note": f"no {TOPICS_FILE} yet; triage uses a generic interest list until I write one"}
    if action == "feeds":
        return {"feeds": feeds()}
    if action == "add":
        return add(a.get("url") or "", a.get("topic"))
    if action == "drop":
        return drop(a.get("feed") or a.get("url") or "")
    if action == "new":
        return new()
    if action == "find":
        return find(a.get("words") or "")
    if action == "read":
        return read(a.get("item") or "")
    if action == "stance":
        return stance(a.get("text") or "", a.get("prompted_by"), a.get("why"), a.get("links"))
    if action == "stances":
        return stances()
    return {"error": f"unknown action {action!r}"}


async def execute_news_tool(tool_name: str, tool_input: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    import asyncio
    try:
        out = await asyncio.to_thread(handle, tool_input or {})
    except Exception as e:
        logger.warning(f"[news] {e}", exc_info=True)
        out = {"error": f"news failed: {type(e).__name__}: {e}"}
    if out.get("error"):
        return {"success": False, "error": out["error"]}
    return {"success": True, "result": out}
