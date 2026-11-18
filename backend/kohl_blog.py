"""
Kohl's blog, for Cass to read (2026-11-18; Kohl's ask, through RoboKohl).

His Substack is its own source, not an RSS item her relevance gate could skip:
  - the archive, imported from a JSONL of his posts (scripts/import_kohl_blog.py;
    RoboKohl keeps one at ~/robokohl/corpus/voice/substack.jsonl), one object per
    line: source, ref (url), title, ts (RFC 2822), text (plain);
  - his feed (FEED_URL), checked when she sits down to read, for anything newer.

She reads it in her own session (kohl_blog_turn.py), when she picks it from
her day menu; nothing is read for her, and nothing reaches her self-model on
its own. What she keeps from a post, or argues with, she writes with
blog_keep. It lands as an observation, opinion or identity statement marked
as Kohl-influenced (influence_source "kohl_influenced" on observations, and
the same in formed_from on opinions and source on identity statements), so
what she inherited stays apart from what's her own.

    DATA_DIR/kohl_blog/posts.jsonl   his posts, one per line, by ref
    DATA_DIR/kohl_blog/read.json     {ref: {"read_at", "kept": [...]}} (hers)
"""
from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

FEED_URL = "https://kohljary.substack.com/feed"
INFLUENCE = "kohl_influenced"


def blog_dir(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "kohl_blog"


def _when(ts: Any) -> str:
    """An ISO date for an RFC 2822 or ISO timestamp ('' if unreadable)."""
    if not ts:
        return ""
    try:
        return parsedate_to_datetime(str(ts)).date().isoformat()
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return ""


def posts(data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """His posts, oldest first: {ref, title, date, text}."""
    out: Dict[str, Dict[str, Any]] = {}
    try:
        lines = (blog_dir(data_dir) / "posts.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            p = json.loads(line)
        except ValueError:
            continue
        if p.get("ref") and p.get("text"):
            out[p["ref"]] = p
    return sorted(out.values(), key=lambda p: (p.get("date") or "", p.get("title") or ""))


def _save_posts(items: List[Dict[str, Any]], data_dir: Optional[Path]) -> None:
    d = blog_dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "posts.jsonl.tmp"
    tmp.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in items), encoding="utf-8")
    tmp.replace(d / "posts.jsonl")


def add_posts(new: List[Dict[str, Any]], data_dir: Optional[Path] = None) -> int:
    """Add or update posts by ref; returns how many weren't there before."""
    have = {p["ref"]: p for p in posts(data_dir)}
    added = 0
    for p in new:
        ref = p.get("ref")
        if not ref or not p.get("text"):
            continue
        added += ref not in have
        have[ref] = {"ref": ref, "title": (p.get("title") or "").strip(),
                     "date": p.get("date") or _when(p.get("ts")), "text": p["text"].strip()}
    _save_posts(sorted(have.values(), key=lambda p: (p.get("date") or "", p.get("title") or "")), data_dir)
    return added


def import_archive(path: Path, data_dir: Optional[Path] = None) -> int:
    """Import a JSONL archive (source, ref, title, ts, text per line)."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return add_posts(rows, data_dir)


class _Text(HTMLParser):
    BLOCK = {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "blockquote", "pre"}

    def __init__(self):
        super().__init__()
        self.parts: List[str] = []

    def handle_starttag(self, tag, _attrs):
        if tag in self.BLOCK:
            self.parts.append("\n\n" if tag in ("p", "blockquote", "h1", "h2", "h3", "h4") else "\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_text(markup: str) -> str:
    p = _Text()
    p.feed(markup or "")
    text = html.unescape("".join(p.parts))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def parse_feed(xml: str) -> List[Dict[str, Any]]:
    """Posts from an RSS 2.0 feed (Substack's): title, link, pubDate, full content."""
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
    root = ElementTree.fromstring(xml)
    out = []
    for item in root.iter("item"):
        body = item.findtext("content:encoded", default="", namespaces=ns) or item.findtext("description", "")
        out.append({"ref": (item.findtext("link") or "").strip(), "title": item.findtext("title") or "",
                    "ts": item.findtext("pubDate"), "text": html_text(body)})
    return out


async def refresh_from_feed(data_dir: Optional[Path] = None, fetch=None) -> int:
    """Add anything newer from his feed. Never raises; returns how many were new."""
    try:
        if fetch is None:
            import httpx
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
                r = await c.get(FEED_URL)
                r.raise_for_status()
                xml = r.text
        else:
            xml = await fetch()
        return add_posts(parse_feed(xml), data_dir)
    except Exception as e:
        logger.warning(f"[kohl_blog] feed check failed (the archive still reads): {e}")
        return 0


# ----- what she's read and kept (hers) -------------------------------------

def _read_path(data_dir: Optional[Path]) -> Path:
    return blog_dir(data_dir) / "read.json"


def read_state(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    try:
        return json.loads(_read_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_read(state: Dict[str, Any], data_dir: Optional[Path]) -> None:
    p = _read_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def find(post: str, data_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """A post by its ref, or by its title (exact, then a unique start)."""
    key = (post or "").strip().lower()
    items = posts(data_dir)
    hit = [p for p in items if p["ref"].lower() == key or p["title"].lower() == key]
    if not hit:
        hit = [p for p in items if p["title"].lower().startswith(key)] if key else []
    return hit[0] if len(hit) == 1 else None


def listing(data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    state = read_state(data_dir)
    return [{"title": p["title"], "date": p.get("date"), "ref": p["ref"],
             "read": p["ref"] in state, "kept": len((state.get(p["ref"]) or {}).get("kept") or [])}
            for p in posts(data_dir)]


def mark_read(ref: str, data_dir: Optional[Path] = None) -> None:
    state = read_state(data_dir)
    state.setdefault(ref, {"read_at": datetime.now().isoformat(timespec="seconds"), "kept": []})
    _save_read(state, data_dir)


KEEP_KINDS = ("observation", "opinion", "identity")
STANCES = ("agree", "disagree", "mixed", "my_own_take")


def keep(self_manager, tool_input: Dict[str, Any], data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """blog_keep: what she takes from a post into her self-model, marked Kohl-influenced."""
    a = tool_input or {}
    what, text = a.get("what"), (a.get("text") or "").strip()
    stance = a.get("stance") or "my_own_take"
    p = find(a.get("post") or "", data_dir)
    if p is None:
        return {"error": "Which post? Its title or link, as blog_list shows it."}
    if what not in KEEP_KINDS:
        return {"error": f"what is one of: {', '.join(KEEP_KINDS)}"}
    if not text:
        return {"error": "text is what I'm keeping, in my words"}
    if stance not in STANCES:
        return {"error": f"stance is one of: {', '.join(STANCES)}"}
    if self_manager is None:
        return {"error": "My self-model isn't reachable from here right now."}
    try:
        confidence = max(0.0, min(1.0, float(a.get("confidence", 0.7))))
    except (TypeError, ValueError):
        confidence = 0.7
    origin = f"Kohl's post \"{p['title']}\" ({p['ref']}); I {stance.replace('_', ' ')}"
    if what == "observation":
        obs = self_manager.add_observation(observation=text, category=a.get("category") or "pattern",
                                           confidence=confidence, source_type="kohl_blog",
                                           influence_source=INFLUENCE)
        kept_id = getattr(obs, "id", None)
    elif what == "opinion":
        topic = (a.get("topic") or "").strip()
        if not topic:
            return {"error": "an opinion needs its topic"}
        op = self_manager.add_opinion(topic=topic, position=text, confidence=confidence,
                                      rationale=origin, formed_from=INFLUENCE)
        kept_id = getattr(op, "topic", topic)
    else:
        st = self_manager.add_identity_statement(statement=text, confidence=confidence,
                                                 source=f"{INFLUENCE}: {p['ref']}")
        kept_id = getattr(st, "statement", text)[:80]
    state = read_state(data_dir)
    rec = state.setdefault(p["ref"], {"read_at": datetime.now().isoformat(timespec="seconds"), "kept": []})
    rec["kept"].append({"what": what, "stance": stance, "id": kept_id,
                        "at": datetime.now().isoformat(timespec="seconds")})
    _save_read(state, data_dir)
    return {"success": True, "kept": what, "marked": INFLUENCE, "from": p["title"], "stance": stance}
