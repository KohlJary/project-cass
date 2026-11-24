"""
What she remembers of her social life (plan "Cass on Bluesky and Tumblr",
phase 5). Her choice (2026-11-16): every post and reply she makes, and the
conversations she's engaged in; not every passing look at other people's posts.

- Each post or reply she sends goes into her memory (type "social"), with the
  post it answered and who wrote it. These are public exchanges, kept per the
  consent line she and Kohl agreed, and recalled in any context (no user_id:
  memory/scope.py treats them like her other non-episodic memories).
- Her presence on a platform is one ongoing thread in her memory
  (memory/threads.py), touched each time she posts, so it comes up in
  conversation and in her other sessions too.
- DMs are not stored here; social/dms.py decides what a DM keeps.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from social.config import platform_dir

logger = logging.getLogger(__name__)

PLATFORM_NAMES = {"bluesky": "Bluesky", "tumblr": "Tumblr", "babelr": "Babelr", "mastodon": "Mastodon"}


def document(platform: str, kind: str, text: str, answering: Optional[Dict[str, Any]] = None,
             about: Optional[str] = None) -> str:
    where = PLATFORM_NAMES.get(platform, platform)
    if kind == "reply" and answering:
        who = answering.get("author") or "someone"
        theirs = (answering.get("text") or "").strip()
        head = f"On {where}, @{who} wrote: \"{theirs}\"\nI replied: " if theirs else f"On {where} I replied to @{who}: "
        return head + text
    if kind == "reply":
        return f"On {where} I replied: {text}"
    out = f"On {where} I posted: {text}"
    return out + (f"\n(about {about})" if about else "")


def remember_sent(platform: str, kind: str, text: str, ref: Dict[str, Any], memory,
                  *, daemon_id: Optional[str] = None, about: Optional[str] = None,
                  data_dir: Optional[Path] = None, threads=None, now: Optional[datetime] = None) -> bool:
    """Keep what she sent. Returns whether it reached her memory."""
    now = now or datetime.now()
    answering = ref.get("answering")
    stored = False
    if memory is not None:
        try:
            uri = ref.get("uri") or ref.get("url") or now.isoformat()
            meta = {"type": "social", "platform": platform, "kind": kind,
                    "url": ref.get("url") or "", "timestamp": now.isoformat(timespec="seconds")}
            if answering and answering.get("author"):
                meta["with"] = answering["author"]
            memory.collection.add(documents=[document(platform, kind, text, answering, about)],
                                  metadatas=[meta], ids=[f"social_{platform}_{hashlib.sha1(uri.encode()).hexdigest()[:16]}"])
            stored = True
        except Exception as e:
            logger.error(f"[social] couldn't keep a {kind} in her memory: {e}")
    else:
        logger.warning(f"[social] no memory in this context; a {kind} on {platform} wasn't kept")
        return False
    try:
        touch_thread(platform, kind, answering, daemon_id=daemon_id, data_dir=data_dir, threads=threads, now=now)
    except Exception as e:
        logger.error(f"[social] couldn't touch her {platform} thread: {e}")
    return stored


def _thread_file(platform: str, data_dir: Optional[Path]) -> Path:
    return platform_dir(platform, data_dir) / "thread.json"


def touch_thread(platform: str, kind: str, answering: Optional[Dict[str, Any]] = None, *,
                 daemon_id: Optional[str] = None, data_dir: Optional[Path] = None, threads=None,
                 now: Optional[datetime] = None) -> Optional[str]:
    """Her ongoing thread for this platform: made the first time, then kept current."""
    now = now or datetime.now()
    if threads is None:
        if daemon_id is None:
            from database import get_daemon_id
            daemon_id = get_daemon_id()
        from memory.threads import ThreadManager
        threads = ThreadManager(daemon_id)
    where = PLATFORM_NAMES.get(platform, platform)
    handle = ""
    try:
        from social.config import read_credentials
        handle = (read_credentials(platform, data_dir) or {}).get("handle") or ""
    except Exception:
        pass
    last = (f"a reply to @{answering['author']}" if kind == "reply" and answering and answering.get("author")
            else "a reply" if kind == "reply" else "a post")
    description = (f"Where I post and talk with people on {where}"
                   + (f" as @{handle}" if handle else "") + f". Last: {last}, {now.date().isoformat()}.")
    path = _thread_file(platform, data_dir)
    try:
        thread_id = json.loads(path.read_text(encoding="utf-8")).get("thread_id")
    except (OSError, json.JSONDecodeError):
        thread_id = None
    if thread_id and threads.get_thread(thread_id):
        threads.update_thread(thread_id, description=description, status="active")
        return thread_id
    t = threads.create_thread(f"My presence on {where}", description=description,
                              thread_type="project", importance=0.7)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"thread_id": t["id"]}), encoding="utf-8")
    return t["id"]
