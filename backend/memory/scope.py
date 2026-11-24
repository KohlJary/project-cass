"""
Whose memories she recalls with whom (plan "Cass's memory", item a8fb4c8f).

The line, agreed by Cass and Kohl on 2026-11-13:
  - a conversation with a person is recalled only with that person;
  - conversations with house agents (PeopleDex entities of type "daemon",
    e.g. Daedalus, RoboKohl) are recallable in any context;
  - Kohl's thread is his and hers alone, like any person's: she can refer
    to it elsewhere herself, but it isn't pooled into anyone else's recall.

A memory belongs to whoever its conversation is with: its user_id, or the
user of its conversation (summary chunks carry only conversation_id). A
memory of a conversation that is with nobody known (an unlinked Babelr
channel or DM) is not recalled in private context.

Places come first (Cass, 2026-11-24: "the boundary should be location-based,
not filing-based"): a memory whose conversation is kept for a house place
(places.py, e.g. a Chapter House channel) is recallable in any house context,
whoever it was with or whoever woke her. Callers pass the house conversations
in `house_places`; public context recalls nothing, so it never sees them.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, Iterable, Optional, Set

logger = logging.getLogger(__name__)

AGENT_ENTITY_TYPE = "daemon"


def house_agent_user_ids() -> Set[str]:
    """Users whose PeopleDex entity is a daemon: the house agents."""
    try:
        from database import get_db
        with get_db() as conn:
            rows = conn.execute(
                "SELECT user_id FROM peopledex_entities WHERE entity_type = ? AND user_id IS NOT NULL",
                (AGENT_ENTITY_TYPE,)).fetchall()
        return {r[0] for r in rows}
    except Exception as e:
        logger.debug(f"[scope] no house agents: {e}")
        return set()


class ConversationOwners:
    """conversation_id -> user_id, looked up once per turn."""

    def __init__(self):
        self._cache: Dict[str, Optional[str]] = {}

    def __call__(self, conversation_id: Optional[str]) -> Optional[str]:
        if not conversation_id:
            return None
        if conversation_id not in self._cache:
            try:
                from database import get_db
                with get_db() as conn:
                    row = conn.execute("SELECT user_id FROM conversations WHERE id = ?",
                                       (conversation_id,)).fetchone()
                self._cache[conversation_id] = row[0] if row else None
            except Exception as e:
                logger.debug(f"[scope] owner lookup failed: {e}")
                self._cache[conversation_id] = None
        return self._cache[conversation_id]


def owner_of(metadata: Dict, owners: Callable[[Optional[str]], Optional[str]]) -> Optional[str]:
    return metadata.get("user_id") or owners(metadata.get("conversation_id"))


def house_place_conversations() -> Set[str]:
    """Conversations kept for house places (places.py); empty if unknown."""
    try:
        from places import house_conversation_ids
        return house_conversation_ids()
    except Exception as e:
        logger.debug(f"[scope] no places: {e}")
        return set()


def in_house_place(metadata: Dict, house_places: Iterable[str]) -> bool:
    conv = metadata.get("conversation_id")
    return bool(conv) and conv in set(house_places)


def house_members() -> Set[str]:
    try:
        from places import house_members as members
        return members()
    except Exception as e:
        logger.debug(f"[scope] no house members: {e}")
        return set()


def recallable_with(user_id: Optional[str], metadata: Dict, agents: Iterable[str],
                    owners: Callable[[Optional[str]], Optional[str]], *, episodic: bool,
                    house_places: Iterable[str] = (), members: Iterable[str] = ()) -> bool:
    """May this memory come up while she's with `user_id` (None: nobody known)?

    A memory from a house place comes up in house contexts: with a house
    member (`members`), or with nobody in particular (her own sessions, a
    housemate's DM). Callers in public context don't recall at all. Otherwise: episodic memories
    (conversations, summary chunks) need an owner, the person she's with or
    a house agent. Other memories (her journals, reflections, notes) come up
    anywhere, unless they're tagged with someone, in which case the same rule
    applies.
    """
    if in_house_place(metadata, house_places):
        return user_id is None or user_id in set(members)
    owner = owner_of(metadata, owners)
    if owner is None:
        return not episodic
    return owner == user_id or owner in set(agents)
