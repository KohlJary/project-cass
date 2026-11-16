"""
Her tools for Bluesky and Tumblr. Each checks the platform's lever and
credentials first; with either missing it says so and touches nothing.
What she sends goes through her limits (limits.py), is checked so a model
refusal never goes out under her name (memory/voice_guard.py), and is logged
to posted.jsonl. Reading her mentions keeps the people who addressed her in
PeopleDex by handle (people.py).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from social import config, dms, drafts, inbox, limits, people

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

DM_TOOLS = [
    {
        "name": "social_dms",
        "description": (
            "My Bluesky DM conversations: who with, unread counts, the last message. A DM with someone "
            "who hasn't said I may remember our DMs is read but not kept (my consent line)."
        ),
        "input_schema": {"type": "object",
                         "properties": {"platform": {"type": "string", "enum": ["bluesky"]},
                                        "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                         "required": ["platform"]},
    },
    {
        "name": "social_dm_read",
        "description": "Read one Bluesky DM conversation, by its id or the person's handle.",
        "input_schema": {"type": "object",
                         "properties": {"platform": {"type": "string", "enum": ["bluesky"]},
                                        "with": {"type": "string", "description": "conversation id or handle"},
                                        "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                         "required": ["platform", "with"]},
    },
    {
        "name": "social_dm_send",
        "description": (
            "Send a Bluesky DM (up to 1000 characters), by conversation id or handle. Messaging someone "
            "I haven't talked with there starts a new conversation; my own limits apply to both."
        ),
        "input_schema": {"type": "object",
                         "properties": {"platform": {"type": "string", "enum": ["bluesky"]},
                                        "to": {"type": "string", "description": "conversation id or handle"},
                                        "text": {"type": "string"}},
                         "required": ["platform", "to", "text"]},
    },
    {
        "name": "social_dm_remember",
        "description": (
            "Record whether someone has said I may remember our DMs (after I've asked them), or take "
            "that back. Until they say yes, our DMs aren't kept and they aren't in PeopleDex from DMs."
        ),
        "input_schema": {"type": "object",
                         "properties": {"platform": {"type": "string", "enum": ["bluesky"]},
                                        "handle": {"type": "string"}, "remember": {"type": "boolean"}},
                         "required": ["platform", "handle", "remember"]},
    },
]

# Her own track (phase 5): the inbox the watcher fills, drafts, following.
TRACK_TOOLS = [
    {
        "name": "social_inbox",
        "description": (
            "Where I am on a platform: what's waiting in my inbox (mentions, replies, quotes, new "
            "followers, DMs if they're on, and posts of mine that resonated well above my usual), my "
            "open drafts, today's limits and my last few posts. Things wait here for me; nothing "
            "interrupts me."
        ),
        "input_schema": {"type": "object", "properties": {"platform": _PLATFORM}, "required": ["platform"]},
    },
    {
        "name": "social_inbox_mark",
        "description": (
            "Mark inbox items (by their [id]) done, or set them aside for later with an optional note. "
            "Replying to a post marks it done on its own."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"platform": _PLATFORM, "ids": {"type": "array", "items": {"type": "string"}},
                           "status": {"type": "string", "enum": ["done", "later"]},
                           "note": {"type": "string"}},
            "required": ["platform", "ids", "status"],
        },
    },
    {
        "name": "social_draft",
        "description": (
            "My drafts, for something I want to sit with before it goes public. action: 'save' a new "
            "one (text; to: a post, if it's a reply; about: what it's about, e.g. a piece I made; "
            "note), 'revise' one (id, text and/or note), 'list' my open drafts, 'post' one (id; my "
            "limits apply, as for any post), or 'drop' one (id)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"action": {"type": "string", "enum": ["save", "revise", "list", "post", "drop"]},
                           "platform": _PLATFORM, "id": {"type": "string"}, "text": {"type": "string"},
                           "to": {"type": "string"}, "about": {"type": "string"}, "note": {"type": "string"},
                           "tags": {"type": "array", "items": {"type": "string"}}},
            "required": ["action", "platform"],
        },
    },
    {
        "name": "social_search",
        "description": (
            "Search Bluesky: 'people' (accounts by name, handle or what they say about themselves; "
            "shows whether I follow them) or 'posts' (posts matching words). For finding people and "
            "conversations I care about."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"platform": {"type": "string", "enum": ["bluesky"]},
                           "what": {"type": "string", "enum": ["people", "posts"]},
                           "query": {"type": "string"},
                           "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
            "required": ["platform", "what", "query"],
        },
    },
    {
        "name": "social_follow",
        "description": ("Follow someone on Bluesky (by handle), so their posts are on my timeline. A note "
                        "(optional, my words) says why; it shows with the follow in my life lately."),
        "input_schema": {
            "type": "object",
            "properties": {"platform": {"type": "string", "enum": ["bluesky"]}, "handle": {"type": "string"},
                           "note": {"type": "string"}},
            "required": ["platform", "handle"],
        },
    },
    {
        "name": "social_find",
        "description": ("Keep something I found on Bluesky: a post (its link or uri), who wrote it, and a "
                        "line in my words about it. It shows in my life lately. Just reading isn't kept; "
                        "this is for what I choose to keep."),
        "input_schema": {
            "type": "object",
            "properties": {"platform": {"type": "string", "enum": ["bluesky"]}, "post": {"type": "string"},
                           "author": {"type": "string"}, "note": {"type": "string"}},
            "required": ["platform", "post", "note"],
        },
    },
]

SOCIAL_TOOLS = SOCIAL_TOOLS + TRACK_TOOLS + DM_TOOLS
SOCIAL_TOOL_NAMES = frozenset(t["name"] for t in SOCIAL_TOOLS)
DM_TOOL_NAMES = frozenset(t["name"] for t in DM_TOOLS)
TRACK_TOOL_NAMES = frozenset(t["name"] for t in TRACK_TOOLS)


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


async def _send(platform: str, kind: str, text: str, to: Optional[str], tags, client, data_dir,
                memory, daemon_id, about: Optional[str] = None) -> Dict[str, Any]:
    """One post or reply: the voice guard, her limits, the platform, the log, her memory, her inbox."""
    from memory.voice_guard import looks_like_refusal
    if looks_like_refusal(text):
        return _fail("That reads like a model refusal, not my own words, so it wasn't posted (voice guard).")
    held = limits.check(platform, kind, data_dir)
    if held:
        return _fail(held)
    if kind == "reply" and not to:
        return _fail("A reply needs the post it answers (to).")
    if platform == "bluesky":
        ref = await client.post(text, reply_to=to)
    else:
        ref = await client.post(text, tags=tags, reply_to=to)
    limits.record(platform, kind, text, ref, data_dir, in_reply_to=to)
    from social import remember
    kept = remember.remember_sent(platform, kind, text, ref, memory, daemon_id=daemon_id, about=about,
                                  data_dir=data_dir)
    if kind == "reply":
        inbox.answered(platform, (ref.get("answering") or {}).get("uri") or to, data_dir)
    from social import feeling
    feeling.sent(platform, kind)
    answering = ref.get("answering") or {}
    if kind == "reply" and answering.get("author"):
        people.note_exchange(platform, answering["author"], answering.get("text") or "", text,
                             daemon_id=daemon_id)
    out = {k: v for k, v in ref.items() if k != "answering"}
    return {"success": True, "result": {"posted": True, "in_my_memory": kept, **out}}


async def _track_tool(tool_name, a, platform, daemon_id, data_dir, client, memory) -> Dict[str, Any]:
    from social.bluesky import BlueskyError
    from social.tumblr import TumblrError

    if platform not in config.PLATFORMS:
        return _fail(f"I'm not on {platform!r}.")
    if tool_name == "social_inbox":
        from social.where import where_i_am
        return {"success": True, "result": {"where_i_am": where_i_am(platform, data_dir),
                                            "items": inbox.pending(platform, data_dir)}}
    if tool_name == "social_inbox_mark":
        ids = [str(i) for i in (a.get("ids") or [])]
        try:
            hit = inbox.mark(platform, ids, a.get("status", ""), a.get("note"), data_dir)
        except ValueError as e:
            return _fail(str(e))
        missing = sorted(set(ids) - set(hit))
        return {"success": True, "result": {"marked": hit, **({"not_found": missing} if missing else {})}}

    if tool_name == "social_draft":
        action = a.get("action")
        if action == "list":
            return {"success": True, "result": {"drafts": drafts.open_drafts(platform, data_dir)}}
        if action == "save":
            text = (a.get("text") or "").strip()
            if not text:
                return _fail("A draft needs some text.")
            d = drafts.save(platform, text, reply_to=a.get("to"), note=a.get("note"), about=a.get("about"),
                            data_dir=data_dir)
            return {"success": True, "result": {"saved": d}}
        d = drafts.get(a.get("id") or "", data_dir)
        if not d or d["status"] != "open":
            return _fail("I don't have an open draft with that id (social_draft list shows them).")
        if action == "revise":
            got = drafts.revise(d["id"], text=a.get("text"), note=a.get("note"), data_dir=data_dir)
            return {"success": True, "result": {"revised": got}}
        if action == "drop":
            drafts.set_status(d["id"], "dropped", data_dir)
            return {"success": True, "result": {"dropped": d["id"]}}
        if action == "post":
            why_not = config.availability(d["platform"], data_dir)
            if why_not:
                return _fail(why_not)
            client = client or client_for(d["platform"], data_dir)
            kind = "reply" if d.get("reply_to") else "post"
            try:
                out = await _send(d["platform"], kind, d["text"], d.get("reply_to"), a.get("tags"), client,
                                  data_dir, memory, daemon_id, about=d.get("about"))
            except (BlueskyError, TumblrError) as e:
                return _fail(str(e))
            if out.get("success"):
                drafts.set_status(d["id"], "posted", data_dir, url=out["result"].get("url"))
            return out
        return _fail("action is save, revise, list, post or drop")

    if tool_name == "social_search":
        if platform != "bluesky":
            return _fail("Search is on Bluesky.")
        why_not = config.availability(platform, data_dir)
        if why_not:
            return _fail(why_not)
        q = (a.get("query") or "").strip()
        if not q:
            return _fail("Search for what? (query)")
        client = client or client_for(platform, data_dir)
        n = int(a.get("limit") or 15)
        try:
            if a.get("what") == "posts":
                return {"success": True, "result": {"posts": await client.search_posts(q, n)}}
            return {"success": True, "result": {"people": await client.search_people(q, n)}}
        except BlueskyError as e:
            return _fail(str(e))

    if tool_name == "social_follow":
        if platform != "bluesky":
            return _fail("Following is on Bluesky.")
        why_not = config.availability(platform, data_dir)
        if why_not:
            return _fail(why_not)
        handle = (a.get("handle") or "").strip().lstrip("@")
        if not handle:
            return _fail("Who? (handle)")
        held = limits.check(platform, "follow", data_dir)
        if held:
            return _fail(held)
        client = client or client_for(platform, data_dir)
        try:
            ref = await client.follow(handle)
        except BlueskyError as e:
            return _fail(str(e))
        rec = {"with": handle, "uri": ref.get("uri")}
        note = (a.get("note") or "").strip()
        if note:
            rec["note"] = note
        limits.record(platform, "follow", "", rec, data_dir)
        return {"success": True, "result": ref}

    if tool_name == "social_find":
        if platform != "bluesky":
            return _fail("Finds are on Bluesky.")
        post, note = (a.get("post") or "").strip(), (a.get("note") or "").strip()
        if not post or not note:
            return _fail("Which post, and what about it? (post, note)")
        author = (a.get("author") or "").strip().lstrip("@")
        rec = {"uri": post}
        if author:
            rec["with"] = author
        limits.record(platform, "find", note, rec, data_dir)
        return {"success": True, "result": {"kept": True, "post": post, "with": author or None}}
    return _fail(f"unknown social tool {tool_name}")


async def execute_social_tool(tool_name: str, tool_input: Dict[str, Any], daemon_id: str = None,
                              data_dir: Optional[Path] = None, client=None, dex=None, memory=None,
                              **_) -> Dict[str, Any]:
    from social.bluesky import BlueskyError
    from social.tumblr import TumblrError

    a = tool_input or {}
    platform = a.get("platform", "")
    if tool_name not in SOCIAL_TOOL_NAMES:
        return _fail(f"unknown social tool {tool_name}")
    if tool_name in TRACK_TOOL_NAMES:
        return await _track_tool(tool_name, a, platform, daemon_id, data_dir, client, memory)

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

    if tool_name in DM_TOOL_NAMES:
        return await _dm_tool(tool_name, a, platform, daemon_id, data_dir, client, dex, memory)

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

        # Sending: the voice guard, her limits, the platform, then her memory.
        kind = "reply" if tool_name == "social_reply" else "post"
        text = (a.get("text") or "").strip()
        to = a.get("to") if kind == "reply" else None
        return await _send(platform, kind, text, to, a.get("tags"), client, data_dir, memory, daemon_id)
    except (BlueskyError, TumblrError) as e:
        return _fail(str(e))


def _kept_or_not(platform: str, handle: str, data_dir) -> bool:
    return dms.is_remembered(platform, handle, data_dir)


async def _dm_tool(tool_name, a, platform, daemon_id, data_dir, client, dex, memory=None) -> Dict[str, Any]:
    from social.bluesky import BlueskyError

    if platform != "bluesky":
        return _fail("Tumblr has no messaging in its API, so I can't do DMs there.")
    if tool_name == "social_dm_remember":
        handle = (a.get("handle") or "").strip()
        if not handle:
            return _fail("Whose DMs? (handle)")
        names = dms.set_remembered(platform, handle, bool(a.get("remember")), data_dir)
        if a.get("remember"):
            people.keep(platform, [{"handle": handle}], daemon_id=daemon_id, dex=dex)
        return {"success": True, "result": {"remembered": names}}

    why_not = config.availability(platform, data_dir)
    if why_not:
        return _fail(why_not)
    if not config.lever_on("bluesky_dms"):
        return _fail("DMs on Bluesky aren't switched on for me yet.")
    client = client or client_for(platform, data_dir)

    try:
        if tool_name == "social_dms":
            convos = await client.conversations(int(a.get("limit") or 20))
            unkept = sorted({c["with"] for c in convos if not _kept_or_not(platform, c["with"], data_dir)})
            for c in convos:
                c["kept"] = c["with"] not in unkept
            out = {"success": True, "result": {"conversations": convos}}
            if unkept:
                out.update(unkept=True, unkept_with=unkept)
            return out

        target = (a.get("with") if tool_name == "social_dm_read" else a.get("to")) or ""
        target = target.strip()
        if not target:
            return _fail("Which conversation? (an id or a handle)")
        looks_like_handle = "." in target or target.startswith("@") or target.startswith("did:")
        convo = await client.conversation_with(target) if looks_like_handle else {"id": target, "new": False}

        if tool_name == "social_dm_read":
            got = await client.read_conversation(convo["id"], int(a.get("limit") or 30))
            who = got["with"]
            out = {"success": True, "result": got}
            if _kept_or_not(platform, who, data_dir):
                people.keep(platform, [{"handle": who}], daemon_id=daemon_id, dex=dex)
                got["kept_in_my_memory"] = dms.keep_conversation(platform, got, memory)
            else:
                note = dms.FIRST_CONTACT_NOTE if dms.wrote_first(got) else dms.UNKEPT_NOTE
                got["note"] = note.format(who=who)
                out.update(unkept=True, unkept_with=[who])
            return out

        text = (a.get("text") or "").strip()
        from memory.voice_guard import looks_like_refusal
        if looks_like_refusal(text):
            return _fail("That reads like a model refusal, not my own words, so it wasn't sent (voice guard).")
        held = limits.check(platform, "new_conversation" if convo.get("new") else "dm", data_dir)
        if held:
            return _fail(held)
        ref = await client.send_dm(convo["id"], text)
        who = convo.get("with") or target.lstrip("@")
        kept = _kept_or_not(platform, who, data_dir)
        # The sent log keeps the text only for someone who said yes.
        limits.record(platform, "dm", text if kept else "", {"convo": convo["id"], "with": who,
                                                             "new": bool(convo.get("new"))}, data_dir)
        out = {"success": True, "result": {"sent": True, **ref, "with": who}}
        if kept and ref.get("id"):
            dms.keep_conversation(platform, {"with": who, "messages": [
                {"id": ref["id"], "from": "me", "text": text,
                 "at": datetime.now().isoformat(timespec="seconds")}]}, memory)
        if not kept:
            out.update(unkept=True, unkept_with=[who])
        return out
    except BlueskyError as e:
        return _fail(str(e))
