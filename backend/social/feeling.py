"""
What happens to her on a social platform reaches Thymos (return-paths map,
item 3). Before this, nothing on Bluesky moved her internal state: not a
mention, a reply, a new follower, a post of hers that resonated, or her own
posting.

Each bus event below is a Thymos event of the same name (thymos_config.json
"events"), so no alias is needed. The watcher emits at most one event per kind
per pass, however many items came in, so a busy hour doesn't stack the same
delta twenty times. Fails soft: a missing bus never breaks the watcher or a post.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable

logger = logging.getLogger(__name__)

# Inbox item kind -> Thymos event
RECEIVED = {
    "mention": "social.engaged",
    "reply": "social.engaged",
    "quote": "social.engaged",
    "follow": "social.followed",
    "resonated": "social.resonated",
    "dm": "social.dm",
}


def _emit(event: str, data: Dict[str, Any]) -> bool:
    try:
        from database import get_daemon_id
        from state_bus import get_state_bus
        bus = get_state_bus(get_daemon_id())
        if not bus:
            return False
        bus.emit_event(event, data)
        return True
    except Exception as e:
        logger.warning(f"[social] couldn't tell Thymos about {event}: {e}")
        return False


def received(platform: str, items: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """Emit one event per kind of thing that came in this pass. Returns event -> count."""
    counts: Dict[str, int] = {}
    for item in items:
        event = RECEIVED.get(item.get("kind", ""))
        if event:
            counts[event] = counts.get(event, 0) + 1
    for event, n in counts.items():
        _emit(event, {"platform": platform, "count": n})
    return counts


def sent(platform: str, kind: str) -> bool:
    """She posted or replied."""
    return _emit("social.posted", {"platform": platform, "kind": kind})
