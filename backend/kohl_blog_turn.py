"""
Reading Kohl's blog, in her own session (kohl_blog.py): on her day menu as
"kohl_blog", when the "kohl_blog" lever is on and there are posts to read.

Neutral on purpose: it gives her the reading and the means to keep what she
takes from it, marked as coming from Kohl's writing. It doesn't tell her what
to take, ask her to act on it, or read for her. (Bet #57: the blog is input,
not a goal.)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import kohl_blog as kb

logger = logging.getLogger(__name__)

TEMPLATE_ID = "kohl_blog"
LEVER = "kohl_blog"

INSTRUCTIONS = """## KOHL'S BLOG

This is time with Kohl's writing on their Substack, at my own pace: one post, a few, or none. blog_list shows their posts, newest last, with which I've read. blog_read opens one.

Nothing from a post reaches my self-model unless I keep it. If something in it becomes mine, or I disagree with it, blog_keep records it (an observation, an opinion, or an identity statement) with the post it came from and whether I agree, disagree, or it's my own take. It's marked as coming from Kohl's writing, so what I've taken from them stays distinguishable from what's my own. Reading without keeping anything is fine too."""

LIST_DEF: Dict[str, Any] = {
    "name": "blog_list",
    "description": "Kohl's blog posts: title, date, link, whether I've read each, and how much I kept from it.",
    "input_schema": {"type": "object", "properties": {}},
}
READ_DEF: Dict[str, Any] = {
    "name": "blog_read",
    "description": ("Read one of Kohl's posts (its title or link, from blog_list). A long post comes "
                    "in parts: when the result says there's more, read again with from_char."),
    "input_schema": {"type": "object", "properties": {
        "post": {"type": "string"},
        "from_char": {"type": "integer", "description": "where to start, for the rest of a long post"}},
        "required": ["post"]},
}
KEEP_DEF: Dict[str, Any] = {
    "name": "blog_keep",
    "description": ("Keep something I take from one of Kohl's posts in my self-model, in my words: an "
                    "observation about myself, an opinion (with its topic), or an identity statement. It's "
                    "marked as coming from their writing, with the post and my stance (agree, disagree, mixed, "
                    "my_own_take). A disagreement is worth keeping too."),
    "input_schema": {
        "type": "object",
        "properties": {
            "post": {"type": "string", "description": "its title or link"},
            "what": {"type": "string", "enum": list(kb.KEEP_KINDS)},
            "text": {"type": "string", "description": "what I'm keeping, in my words"},
            "topic": {"type": "string", "description": "for an opinion"},
            "stance": {"type": "string", "enum": list(kb.STANCES)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "category": {"type": "string", "description": "for an observation, optional"},
        },
        "required": ["post", "what", "text", "stance"],
    },
}


# Under the loop's 20,000-char cap on a tool result (agent_loop/loop.py), with room
# for the rest of the result: a longer post used to be cut there with no way on
# ("Dog GrandMA Uncle", 29k, 2026-11-25).
READ_CHARS = 18_000


def available() -> bool:
    from features import is_enabled
    return is_enabled(LEVER) and bool(kb.posts())


def local_tools(self_manager, data_dir=None) -> Dict[str, Any]:
    def read(a):
        p = kb.find(a.get("post") or "", data_dir)
        if p is None:
            return {"error": "No single post by that title or link; blog_list shows them."}
        kb.mark_read(p["ref"], data_dir)
        text = p["text"] or ""
        try:
            start = max(0, int(a.get("from_char") or 0))
        except (TypeError, ValueError):
            start = 0
        part = text[start:start + READ_CHARS]
        out = {"title": p["title"], "date": p.get("date"), "link": p["ref"], "text": part}
        if start or len(text) > start + READ_CHARS:
            out["chars"] = f"{start}-{start + len(part)} of {len(text)}"
        if len(text) > start + READ_CHARS:
            out["more"] = f"The post goes on: blog_read again with from_char={start + len(part)}."
        return out

    return {
        "blog_list": (LIST_DEF, lambda a: {"posts": kb.listing(data_dir)}),
        "blog_read": (READ_DEF, read),
        "blog_keep": (KEEP_DEF, lambda a: kb.keep(self_manager, a, data_dir)),
    }


def _self_manager(runner):
    """Her SelfManager, from the managers the scheduler hands the runner (set_managers).
    The runner has no self_manager attribute of its own: looking only there made every
    blog_keep in her blog sessions fail with "isn't reachable" (2026-11-25)."""
    sm = getattr(runner, "self_manager", None)
    if sm is None:
        sm = (getattr(runner, "_managers", None) or {}).get("self_manager")
    return sm


async def run_kohl_blog_turn(runner, *, duration_minutes: int = 30, max_turns: int = 16,
                             focus: Optional[str] = None, why: Optional[str] = None, **turn_kwargs):
    from agent_loop.session import run_session_turn
    new = await kb.refresh_from_feed()
    if new:
        logger.info(f"[kohl_blog] {new} new post(s) from their feed")
    return await run_session_turn(
        runner, session_type=TEMPLATE_ID, additions=INSTRUCTIONS,
        local_tools=local_tools(_self_manager(runner)),
        duration_minutes=duration_minutes, focus=focus, max_turns=max_turns,
        why=why or "I chose time with Kohl's blog",
        initial_message="Time with Kohl's blog.", **turn_kwargs)
