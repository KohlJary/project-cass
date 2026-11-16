"""
The social watcher: every few minutes, queue what came in on each platform
she's on into her inbox (social/inbox.py). She chose (2026-11-16) to have what
comes in queued rather than interrupting her. Nothing here posts, replies or wakes her; her social
sessions read the queue.

Lever "social_watch" (on by default, but it acts only on a platform whose own
lever is on and whose credentials are placed). DMs are queued only when the
"bluesky_dms" lever is on, and only as who and how many, never the text.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Callable, Dict, Optional

from social import config, inbox

logger = logging.getLogger(__name__)

WATCH_MINUTES = 5
WATCHED = ("bluesky",)   # Tumblr's activity feed isn't queued yet; she started on Bluesky

_task: Optional[asyncio.Task] = None


async def watch_once(data_dir: Optional[Path] = None, client_for: Optional[Callable] = None) -> Dict[str, int]:
    """One pass over every watched platform that's usable. Returns platform -> items queued."""
    if client_for is None:
        from social.tools import client_for
    out: Dict[str, int] = {}
    for platform in WATCHED:
        if config.availability(platform, data_dir):
            continue
        try:
            client = client_for(platform, data_dir)
            added = await inbox.poll(platform, client, data_dir,
                                     dms=platform == "bluesky" and config.lever_on("bluesky_dms"))
            out[platform] = len(added)
            if added:
                logger.info(f"[social] {len(added)} new in her {platform} inbox")
        except Exception as e:
            logger.warning(f"[social] watching {platform} failed this pass: {e}")
    return out


async def run(data_dir: Optional[Path] = None, minutes: float = WATCH_MINUTES) -> None:
    while True:
        await watch_once(data_dir)
        await asyncio.sleep(minutes * 60)


def start_social_watch(data_dir: Optional[Path] = None) -> Optional[asyncio.Task]:
    """Start the watcher if its lever is on and she's on a watched platform; else None."""
    global _task
    from features import is_enabled
    if not is_enabled("social_watch"):
        logger.info("[social] lever 'social_watch' is off; watcher not started")
        return None
    if not any(config.lever_on(p) for p in WATCHED):
        logger.info("[social] no watched platform is switched on; watcher not started")
        return None
    if _task and not _task.done():
        return _task
    _task = asyncio.create_task(run(data_dir))
    return _task
