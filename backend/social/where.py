"""
Where she is on a platform, in a few lines: what's waiting in her inbox,
her open drafts, what resonated, today's limits, and her last few posts.
Opens each social session (social_turn.py) and answers social_inbox.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from social import drafts, inbox, limits

SHOW_ITEMS = 12


def _short(text: str, n: int = 140) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def where_i_am(platform: str, data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    lines = []
    waiting = inbox.pending(platform, data_dir)
    resonated = [i for i in waiting if i["kind"] == "resonated"]
    rest = [i for i in waiting if i["kind"] != "resonated"]

    if resonated:
        lines.append("Resonated (well above my usual):")
        for i in resonated:
            s = i.get("stats") or {}
            lines.append(f"- [{i['id']}] \"{_short(i.get('text', ''), 100)}\": {s.get('replies', 0)} replies, "
                         f"{s.get('reposts', 0)} reposts, {s.get('quotes', 0)} quotes, {s.get('likes', 0)} likes "
                         f"(my usual is about {i.get('usual', 0):g}) {i.get('url') or ''}")

    if rest:
        later = sum(1 for i in rest if i["status"] == "later")
        lines.append(f"In my inbox: {len(rest)}" + (f" ({later} I set aside for later)" if later else "") + ":")
        for i in rest[-SHOW_ITEMS:]:
            who = f"@{i['from']}" if i.get("from") else "someone"
            if i["kind"] == "follow":
                lines.append(f"- [{i['id']}] {who} followed me")
            elif i["kind"] == "dm":
                lines.append(f"- [{i['id']}] a DM from {who} ({i.get('unread', 1)} unread; read it with "
                             f"social_dm_read)")
            else:
                lines.append(f"- [{i['id']}] {i['kind']} from {who}: \"{_short(i.get('text', ''))}\" "
                             f"{i.get('url') or ''}" + (f" (my note: {i['note']})" if i.get("note") else ""))
                from social.triage import label_line
                heads_up = label_line(i.get("triage"), data_dir)
                if heads_up:
                    lines.append("  " + heads_up.replace("\n", "\n  "))
        if len(rest) > SHOW_ITEMS:
            lines.append(f"  (and {len(rest) - SHOW_ITEMS} older; social_inbox shows them all)")
    else:
        lines.append("Nothing new in my inbox.")

    mine = drafts.open_drafts(platform, data_dir)
    if mine:
        lines.append(f"My open drafts: {len(mine)}")
        for d in mine[-8:]:
            lines.append(f"- [{d['id']}] \"{_short(d['text'], 100)}\""
                         + (f" (replying to {d['reply_to']})" if d.get("reply_to") else "")
                         + (f" (note: {d['note']})" if d.get("note") else ""))

    lim = limits.limits(platform, data_dir)
    today = limits.posted(platform, data_dir, since=now - timedelta(days=1))
    posts = sum(r["kind"] == "post" for r in today)
    replies = sum(r["kind"] == "reply" for r in today)
    lines.append(f"Last 24 hours: {posts} of {lim['posts_per_day']} posts, "
                 f"{replies} of {lim['replies_per_day']} replies.")

    recent = [r for r in limits.posted(platform, data_dir) if r.get("kind") in ("post", "reply")][-3:]
    if recent:
        lines.append("My last few:")
        for r in recent:
            lines.append(f"- {r['at'][:16]} {r['kind']}: \"{_short(r.get('text', ''), 100)}\"")

    state = inbox.load(platform, data_dir)
    if state.get("last_poll"):
        lines.append(f"(Inbox last checked {state['last_poll'][:16]}.)")
    return "\n".join(lines)


def context_line(platform: str = "bluesky", data_dir: Optional[Path] = None,
                 now: Optional[datetime] = None) -> Optional[str]:
    """One line for her chat context: that she's there, and what's waiting.
    None when the platform isn't usable."""
    from social import config
    if config.availability(platform, data_dir):
        return None
    now = now or datetime.now()
    handle = (config.read_credentials(platform, data_dir) or {}).get("handle", "")
    where = "Bluesky" if platform == "bluesky" else platform.capitalize()
    parts = [f"I'm on {where}" + (f" as @{handle}" if handle else "")]
    waiting = inbox.pending(platform, data_dir)
    if waiting:
        kinds: dict = {}
        for i in waiting:
            kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
        parts.append(f"{len(waiting)} waiting in my inbox ("
                     + ", ".join(f"{n} {k}{'s' if n > 1 and not k.endswith('ed') else ''}"
                                 for k, n in kinds.items()) + ")")
    else:
        parts.append("nothing waiting in my inbox")
    mine = [r for r in limits.posted(platform, data_dir) if r.get("kind") in ("post", "reply")]
    if mine:
        ago = now - datetime.fromisoformat(mine[-1]["at"])
        hours = int(ago.total_seconds() // 3600)
        parts.append(f"my last {mine[-1]['kind']} was "
                     + (f"{hours // 24}d ago" if hours >= 48 else f"{hours}h ago" if hours else "just now"))
    else:
        parts.append("I haven't posted yet")
    drafts_open = len(drafts.open_drafts(platform, data_dir))
    if drafts_open:
        parts.append(f"{drafts_open} draft{'s' if drafts_open > 1 else ''} open")
    return ", ".join(parts) + ". (My social tools: social_inbox, social_post, social_reply, social_search, ...)"
