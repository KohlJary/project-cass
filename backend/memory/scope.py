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


def recallable_with(user_id: Optional[str], metadata: Dict, agents: Iterable[str],
                    owners: Callable[[Optional[str]], Optional[str]], *, episodic: bool) -> bool:
    """May this memory come up while she's with `user_id` (None: nobody known)?

    Episodic memories (conversations, summary chunks) need an owner: the
    person she's with, or a house agent. Other memories (her journals,
    reflections, notes) come up anywhere, unless they're tagged with
    someone, in which case the same rule applies.
    """
    owner = owner_of(metadata, owners)
    if owner is None:
        return not episodic
    return owner == user_id or owner in set(agents)
