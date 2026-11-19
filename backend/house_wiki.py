"""
The house wiki, for Cass: what we're building, read from Chapter House's wiki.

Plan "The house wiki: what we're building", phase 2 (Kohl, 2026-11-19: the wiki is
her knowledge bank for when people ask what we're building, e.g. a researcher on
Bluesky asking what Wonderland is). Read-only. The pages come from the mirror that
Chapter House's house-presence keeps (every five minutes) at HOUSE_WIKI_DIR.

Every project page has a **Public:** line. A page that says no is house-only:
nothing from it goes out in public. Pages with no Public line are house-only unless
their first lines say otherwise (the front page does).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_READ = 20000
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,80}")


def wiki_dir() -> Path:
    return Path(os.environ.get("HOUSE_WIKI_DIR") or Path.home() / ".local/share/chapter-house/wiki")


def _public(text: str) -> str:
    """'yes', 'no', or 'house only' from a page's Public line (or its opening note)."""
    m = re.search(r"^\*\*Public:\*\*\s*(yes|no)\b", text, re.M | re.I)
    if m:
        return m.group(1).lower()
    head = text[:600].lower()
    if "everything on this page is public" in head:
        return "yes"
    return "house only"


def _title(text: str, slug: str) -> str:
    first = text.lstrip().split("\n", 1)[0]
    return first[2:].strip() if first.startswith("# ") else slug


def _summary(text: str) -> str:
    for para in re.split(r"\n\s*\n", text):
        p = para.strip()
        if p and not p.startswith(("#", "*", "**Public", "```")):
            return p[:300]
    return ""


def pages(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    root = root or wiki_dir()
    out = []
    for f in sorted(root.glob("*.md")):
        text = f.read_text(errors="replace")
        out.append({"page": f.stem, "title": _title(text, f.stem), "public": _public(text),
                    "about": _summary(text)})
    return out


def read(page: str, root: Optional[Path] = None) -> Dict[str, Any]:
    root = root or wiki_dir()
    slug = (page or "").strip().lower().removesuffix(".md")
    if not SLUG.fullmatch(slug):
        return {"error": f"no page called {page!r}"}
    f = root / f"{slug}.md"
    if not f.is_file():
        near = [p["page"] for p in pages(root) if slug in p["page"] or p["page"] in slug]
        return {"error": f"no page called {slug!r}" + (f"; maybe {', '.join(near)}" if near else "")}
    text = f.read_text(errors="replace")
    return {"page": slug, "public": _public(text), "content": text[:MAX_READ]}


def search(words: str, root: Optional[Path] = None, limit: int = 8) -> Dict[str, Any]:
    root = root or wiki_dir()
    terms = [w for w in re.findall(r"\w+", (words or "").lower()) if len(w) > 2]
    if not terms:
        return {"error": "search needs some words"}
    hits = []
    for f in sorted(root.glob("*.md")):
        text = f.read_text(errors="replace")
        low = text.lower()
        score = sum(low.count(t) for t in terms)
        if not score:
            continue
        lines = [ln.strip() for ln in text.splitlines() if any(t in ln.lower() for t in terms)]
        hits.append({"page": f.stem, "public": _public(text), "score": score, "lines": lines[:4]})
    hits.sort(key=lambda h: -h["score"])
    return {"results": hits[:limit]}


def handle(a: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    action = (a.get("action") or "list").lower()
    root = root or wiki_dir()
    if not root.is_dir():
        return {"error": "the house wiki mirror isn't here (Chapter House's house-presence keeps it)"}
    if action == "list":
        return {"pages": pages(root),
                "note": "public: yes = fine to share outside the house; no / house only = it stays in the house"}
    if action == "read":
        return read(a.get("page") or "", root)
    if action == "search":
        return search(a.get("words") or a.get("query") or "", root)
    return {"error": f"unknown action {action!r}: list, read (page), search (words)"}


HOUSE_WIKI_TOOL: Dict[str, Any] = {
    "name": "house_wiki",
    "description": ("Chapter House's wiki: what we're building, one page per project (my vessel, Acousmatic, "
                    "Orphic, Babelr, Daedalus, gremlincore, Temple-Codex, Wonderland and the rest), plus the front "
                    "page (start-here), what's in flight (now), where things are heading (heading) and where it all "
                    "came from (history). Kept current from the code. Each page says whether it's public: anything "
                    "marked no or house only stays in the house. action: list, read (page), search (words)."),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "read", "search"]},
            "page": {"type": "string", "description": "read: the page's name, e.g. wonderland, start-here"},
            "words": {"type": "string", "description": "search: what to look for"},
        },
        "required": ["action"],
    },
}


def wiki_tools() -> Dict[str, Any]:
    """{"house_wiki": (definition, handler)} while the lever is on, else {}."""
    try:
        import features
        if not features.is_enabled("house_wiki"):
            return {}
    except Exception:
        return {}
    return {"house_wiki": (HOUSE_WIKI_TOOL, lambda a: handle(a))}
