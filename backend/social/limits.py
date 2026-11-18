"""
Her limits on what she sends out, and the log of what she sent.

Defaults are deliberately small until she sets her own (the plan's first
step asks her how often she wants to post): DATA_DIR/social/<platform>/
limits.json overrides any of them.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from social.config import platform_dir

DEFAULTS = {
    "posts_per_day": 3,
    "replies_per_day": 10,
    "minutes_between": 10,   # between any two posts or replies on one platform
    "dms_per_day": 40,       # DMs she sends (a conversation is back and forth, so no spacing)
    "new_conversations_per_day": 2,  # DMs to someone she hasn't talked with there before
    "follows_per_day": 20,
}


def limits(platform: str, data_dir: Optional[Path] = None) -> Dict[str, int]:
    out = dict(DEFAULTS)
    try:
        mine = json.loads((platform_dir(platform, data_dir) / "limits.json").read_text(encoding="utf-8"))
        out.update({k: int(v) for k, v in mine.items() if k in DEFAULTS})
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    return out


def _log_path(platform: str, data_dir: Optional[Path]) -> Path:
    return platform_dir(platform, data_dir) / "posted.jsonl"


def posted(platform: str, data_dir: Optional[Path] = None, since: Optional[datetime] = None) -> List[dict]:
    try:
        lines = _log_path(platform, data_dir).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since is None or datetime.fromisoformat(rec["at"]) >= since:
            out.append(rec)
    return out


# A pause (2026-11-17): DATA_DIR/social/<platform>/paused.json holds every
# send (posts, replies, DMs, follows) until it's lifted or its `until`
# passes. Reading goes on. She sets it with social_pause; Kohl with
# scripts/social_pause.py.
def _pause_path(platform: str, data_dir: Optional[Path]) -> Path:
    return platform_dir(platform, data_dir) / "paused.json"


def paused(platform: str, data_dir: Optional[Path] = None,
           now: Optional[datetime] = None) -> Optional[dict]:
    """The pause in force on a platform, or None."""
    try:
        p = json.loads(_pause_path(platform, data_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    until = p.get("until")
    try:
        if until and datetime.fromisoformat(until) <= (now or datetime.now()):
            return None
    except (TypeError, ValueError):
        pass
    return p


def pause(platform: str, by: str, reason: str = "", until: Optional[str] = None,
          data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> dict:
    if until:
        datetime.fromisoformat(until)  # ValueError if it isn't a date
    rec = {"by": by, "at": (now or datetime.now()).isoformat(timespec="seconds"),
           "reason": reason, "until": until}
    path = _pause_path(platform, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def resume(platform: str, data_dir: Optional[Path] = None) -> bool:
    try:
        _pause_path(platform, data_dir).unlink()
        return True
    except FileNotFoundError:
        return False


def check(platform: str, kind: str, data_dir: Optional[Path] = None,
          now: Optional[datetime] = None) -> Optional[str]:
    """None if she can send this now, else why not. kind: post | reply | dm | new_conversation | follow."""
    now = now or datetime.now()
    held = paused(platform, data_dir, now)
    if held:
        who = "I" if held.get("by") == "cass" else held.get("by") or "someone"
        until = f" until {held['until']}" if held.get("until") else ""
        why = f" ({held['reason']})" if held.get("reason") else ""
        return f"{platform.capitalize()} is paused{until}: {who} paused it{why}. Reading still works."
    lim = limits(platform, data_dir)
    recent = posted(platform, data_dir, since=now - timedelta(days=1))
    if kind == "follow":
        if sum(1 for r in recent if r.get("kind") == "follow") >= lim["follows_per_day"]:
            return f"I've followed {lim['follows_per_day']} accounts on {platform} today, my limit."
        return None
    if kind in ("dm", "new_conversation"):
        dms = [r for r in recent if r.get("kind") == "dm"]
        if len(dms) >= lim["dms_per_day"]:
            return f"I've used my {lim['dms_per_day']} DMs on {platform} for today."
        if kind == "new_conversation" and sum(1 for r in dms if r.get("new")) >= lim["new_conversations_per_day"]:
            return (f"I've started my {lim['new_conversations_per_day']} new conversations on {platform} "
                    f"for today.")
        return None
    public = [r for r in recent if r.get("kind") in ("post", "reply")]
    if public:
        last = max(datetime.fromisoformat(r["at"]) for r in public)
        wait = last + timedelta(minutes=lim["minutes_between"]) - now
        if wait > timedelta(0):
            return (f"I sent something on {platform} {int((now - last).total_seconds() // 60)} min ago; "
                    f"my limit is one every {lim['minutes_between']} min.")
    cap = lim["posts_per_day" if kind == "post" else "replies_per_day"]
    used = sum(1 for r in recent if r.get("kind") == kind)
    if used >= cap:
        return f"I've used my {cap} {kind}s on {platform} for today."
    return None


def record(platform: str, kind: str, text: str, ref: dict, data_dir: Optional[Path] = None,
           in_reply_to: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    rec = {"at": (now or datetime.now()).isoformat(timespec="seconds"), "kind": kind,
           "text": text, **ref}
    if in_reply_to:
        rec["in_reply_to"] = in_reply_to
    path = _log_path(platform, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec
