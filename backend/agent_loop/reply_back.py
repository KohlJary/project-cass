"""
Reply back to where it came from (Kohl, 2026-11-18: "make sure she can reply
back when the session finishes too, in all channels").

A session that answers something (one she started from a chat, a happening
that woke her) carries its origin: where the asking happened. The session's
prompt names it, and reply_back(message) sends there through the tool that
already speaks in that place, with its limits, its logs and the gremlin's
review (reply_back is reviewed like any outward tool).

An origin is a dict:
    {"channel": one of CHANNELS, "target": where in it, "who": "Kohl",
     "label": "a DM with @kohl on Babelr"}
  babelr_dm       target: their Babelr username
  babelr_channel  target: the channel name
  bluesky_dm      target: the conversation id or their handle
  bluesky_post    target: the post's at:// address (a public reply)
  chat            target: unused; her main thread with her partner (say)
  discord         target: the channel id
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

TOOL = "reply_back"

# channel -> (router tool, how to build its input from (target, message))
ROUTES: Dict[str, Tuple[str, Callable[[str, str], Dict[str, Any]]]] = {
    "babelr_dm": ("babelr_dm", lambda t, m: {"person": t.lstrip("@"), "content": m}),
    "babelr_channel": ("babelr_post", lambda t, m: {"channel": t.lstrip("#"), "content": m}),
    "bluesky_dm": ("social_dm_send", lambda t, m: {"platform": "bluesky", "to": t, "text": m}),
    "bluesky_post": ("social_reply", lambda t, m: {"platform": "bluesky", "to": t, "text": m}),
    "chat": ("reach_out", lambda _t, m: {"message": m}),
    "discord": ("discord_respond", lambda t, m: {"channel_id": t, "content": m}),
}
CHANNELS = tuple(ROUTES)
NEEDS_TARGET = {c for c in CHANNELS if c != "chat"}


def _from_conversation(raw: Dict[str, Any]) -> Dict[str, Any]:
    """A start_session origin (agent_loop/wakes.origin_of: the chat's channel, its
    "where", and the place / channel_id the chat carried) in this module's terms."""
    import re
    ch = str(raw.get("channel") or "")
    place = str(raw.get("place") or raw.get("babelr_place") or "")
    out = {"who": raw.get("who"), "label": ""}
    if ch == "babelr_dm":
        m = re.search(r"@([\w.\-]+)", place) or re.search(r"@([\w.\-]+)", str(raw.get("where") or ""))
        partner = raw.get("partner") or (m.group(1) if m else "")
        out.update(channel="babelr_dm", target=partner)
    elif ch == "babelr":
        out.update(channel="babelr_channel", target=place if place.startswith("#") else "")
    elif ch == "discord":
        out.update(channel="discord", target=str(raw.get("channel_id") or ""))
    else:   # the web or mobile app, the relay: her main thread with them
        out.update(channel="chat", target="")
    return out


def origin(raw: Any) -> Optional[Dict[str, str]]:
    """A clean origin from a dict, or None if it can't be replied to. Takes this
    module's form or a start_session origin (wakes.origin_of)."""
    if not isinstance(raw, dict):
        return None
    if "target" not in raw and str(raw.get("channel") or "") not in ("chat",):
        raw = _from_conversation(raw)
    channel = str(raw.get("channel") or "").strip()
    target = str(raw.get("target") or "").strip()
    if channel not in ROUTES or (channel in NEEDS_TARGET and not target):
        return None
    who = str(raw.get("who") or "").strip()
    label = str(raw.get("label") or "").strip() or _default_label(channel, target)
    return {"channel": channel, "target": target, "who": who, "label": label}


def _default_label(channel: str, target: str) -> str:
    return {"babelr_dm": f"a DM with @{target.lstrip('@')} on Babelr",
            "babelr_channel": f"#{target.lstrip('#')} on Babelr",
            "bluesky_dm": "a Bluesky DM",
            "bluesky_post": "a Bluesky thread",
            "chat": "our main chat",
            "discord": "a Discord channel"}[channel]


def prompt_line(o: Dict[str, str]) -> str:
    who = f"{o['who']} asked" if o.get("who") else "This came"
    return (f"\n\n## WHERE THIS CAME FROM\n\n{who} in {o['label']}. When I've got something to say back, "
            f"reply_back sends it there.")


def tool_def(o: Dict[str, str]) -> Dict[str, Any]:
    return {
        "name": TOOL,
        "description": (f"Reply where this came from: {o['label']}. Optional; if I'd rather say "
                        "nothing yet, I don't have to."),
        "input_schema": {"type": "object", "properties": {"message": {"type": "string"}},
                         "required": ["message"]},
    }


def handler(o: Dict[str, str], run_router: Callable[[str, Dict[str, Any]], Awaitable[Any]]):
    tool, build = ROUTES[o["channel"]]

    async def reply(a: Dict[str, Any]) -> Any:
        message = str((a or {}).get("message") or "").strip()
        if not message:
            return {"error": "an empty reply; what do I want to say?"}
        return await run_router(tool, build(o["target"], message))
    return reply
