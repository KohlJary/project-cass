"""
Her tools for Bluesky and Tumblr. Each checks the platform's lever and
credentials first; with either missing it says so and touches nothing.
What she sends goes through her limits (limits.py), is checked so a model
refusal never goes out under her name (memory/voice_guard.py), and is logged
to posted.jsonl. Reading her mentions keeps the people who addressed her in
PeopleDex by handle (people.py).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from social import config, limits, people

_PLATFORM = {"type": "string", "enum": list(config.PLATFORMS)}

SOCIAL_TOOLS = [
    {
        "name": "social_read",
        "description": (
            "Read my Bluesky or Tumblr: 'mentions' (people who mentioned me, replied to me, quoted or "
            "reblogged me with words, asked me something) or 'timeline' (what people I follow posted; "
            "on Tumblr, my dashboard). People who address me are kept in PeopleDex by handle."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"platform": _PLATFORM,
                           "what": {"type": "string", "enum": ["mentions", "timeline"]},
                           "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
            "required": ["platform", "what"],
        },
    },
    {
        "name": "social_thread",
        "description": "Look at one post with its conversation: on Bluesky the posts above it and the replies; "
                       "on Tumblr its reblog trail. post: its link (or at:// address on Bluesky).",
        "input_schema": {
            "type": "object",
            "properties": {"platform": _PLATFORM, "post": {"type": "string"}},
            "required": ["platform", "post"],
        },
    },
    {
        "name": "social_post",
        "description": (
            "Post something of mine, publicly, on Bluesky (up to 300 characters; links and @handles "
            "become links) or Tumblr (paragraphs separated by blank lines; optional tags). Anyone can "
            "see it. My own limits on how often apply."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"platform": _PLATFORM, "text": {"type": "string"},
                           "tags": {"type": "array", "items": {"type": "string"},
                                    "description": "Tumblr only"}},
            "required": ["platform", "text"],
        },
    },
    {
        "name": "social_reply",
        "description": (
            "Reply, publicly, to a post: on Bluesky a reply in its thread; on Tumblr a reblog with my "
            "words added. to: the post's link (or at:// address on Bluesky). My own limits apply."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"platform": _PLATFORM, "to": {"type": "string"}, "text": {"type": "string"},
                           "tags": {"type": "array", "items": {"type": "string"}}},
            "required": ["platform", "to", "text"],
        },
    },
    {
        "name": "social_my_posts",
        "description": "See what I've posted and replied on a platform lately, and how much of today's "
                       "limits I've used.",
        "input_schema": {
            "type": "object",
            "properties": {"platform": _PLATFORM, "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
            "required": ["platform"],
        },
    },
]

SOCIAL_TOOL_NAMES = frozenset(t["name"] for t in SOCIAL_TOOLS)


def client_for(platform: str, data_dir: Optional[Path] = None, transport=None):
    creds = config.read_credentials(platform, data_dir)
    if platform == "bluesky":
        from social.bluesky import BlueskyClient
        return BlueskyClient(creds, transport=transport)
    from social.tumblr import TumblrClient
    return TumblrClient(creds, save=lambda c: config.write_credentials("tumblr", c, data_dir),
                        transport=transport)


def _fail(msg: str) -> Dict[str, Any]:
    return {"success": False, "error": msg}


async def execute_social_tool(tool_name: str, tool_input: Dict[str, Any], daemon_id: str = None,
                              data_dir: Optional[Path] = None, client=None, dex=None,
                              **_) -> Dict[str, Any]:
    from social.bluesky import BlueskyError
    from social.tumblr import TumblrError

    a = tool_input or {}
    platform = a.get("platform", "")
    if tool_name not in SOCIAL_TOOL_NAMES:
        return _fail(f"unknown social tool {tool_name}")

    if tool_name == "social_my_posts":
        if platform not in config.PLATFORMS:
            return _fail(f"I'm not on {platform!r}.")
        recent = limits.posted(platform, data_dir)[-int(a.get("limit") or 20):]
        lim = limits.limits(platform, data_dir)
        from datetime import datetime, timedelta
        today = limits.posted(platform, data_dir, since=datetime.now() - timedelta(days=1))
        return {"success": True, "result": {
            "posted": recent,
            "last_24h": {"posts": sum(r["kind"] == "post" for r in today),
                         "replies": sum(r["kind"] == "reply" for r in today)},
            "my_limits": lim}}

    why_not = config.availability(platform, data_dir)
    if why_not:
        return _fail(why_not)
    client = client or client_for(platform, data_dir)

    try:
        if tool_name == "social_read":
            n = int(a.get("limit") or 20)
            if a.get("what") == "timeline":
                items = await (client.timeline(n) if platform == "bluesky" else client.dashboard(n))
                return {"success": True, "result": {"timeline": items}}
            items = await client.mentions(n)
            added = people.keep(platform, ({"handle": i.get("author"),
                                            "name": i.get("display_name") or i.get("author")}
                                           for i in items), daemon_id=daemon_id, dex=dex)
            result = {"mentions": items}
            if added:
                result["new_in_peopledex"] = added
            return {"success": True, "result": result}

        if tool_name == "social_thread":
            return {"success": True, "result": await client.thread(a.get("post", ""))}

        # Sending: her limits, then the refusal check, then the platform.
        kind = "reply" if tool_name == "social_reply" else "post"
        text = (a.get("text") or "").strip()
        from memory.voice_guard import looks_like_refusal
        if looks_like_refusal(text):
            return _fail("That reads like a model refusal, not my own words, so it wasn't posted (voice guard).")
        held = limits.check(platform, kind, data_dir)
        if held:
            return _fail(held)
        to = a.get("to") if kind == "reply" else None
        if kind == "reply" and not to:
            return _fail("A reply needs the post it answers (to).")
        if platform == "bluesky":
            ref = await client.post(text, reply_to=to)
        else:
            ref = await client.post(text, tags=a.get("tags"), reply_to=to)
        limits.record(platform, kind, text, ref, data_dir, in_reply_to=to)
        return {"success": True, "result": {"posted": True, **ref}}
    except (BlueskyError, TumblrError) as e:
        return _fail(str(e))
