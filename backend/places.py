"""
Places: where her conversations happen (spec/house-channel-memory.md).

A place is one conversation space on one platform: a Babelr channel, a DM, a
Mastodon thread. Each is registered with the vessel conversation it's
recorded in and how visible it is, so what she can recall, and where, follows
the place and not who happened to wake her. Cass, 2026-11-24: "the boundary
should be location-based, not filing-based. House channels are recallable in
house contexts. External stays private unless I'm directly with that person."

visibility:
  house   a space only the house is in (a channel on Chapter House, a
          private server). Recallable in any house context: with Kohl, in a
          housemate's DM, in her own sessions. Never in public context.
  person  a space with one person (a DM). Recalled with that person, as
          memory/scope.py already does by owner.
  public  a space outsiders can be in (a public server's channel, a Mastodon
          thread). Not recalled in private context unless she's with its
          owner; the platform that registers it decides more later.

Babelr is the first platform to register places; Mastodon and the rest
register theirs the same way. Read-only lookups fail soft (an older database
without the table has no places).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

VISIBILITIES = ("house", "person", "public")
KINDS = ("channel", "dm", "thread")


def register(platform: str, place_key: str, *, kind: str, visibility: str,
             conversation_id: Optional[str], label: Optional[str] = None,
             person_user_id: Optional[str] = None) -> None:
    """Record (or update) a place and the conversation it's kept in."""
    if visibility not in VISIBILITIES:
        raise ValueError(f"unknown visibility {visibility!r}")
    if kind not in KINDS:
        raise ValueError(f"unknown place kind {kind!r}")
    from database import get_db
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO places (platform, place_key, kind, visibility, label,
                                   conversation_id, person_user_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(platform, place_key) DO UPDATE SET
                 kind = excluded.kind, visibility = excluded.visibility,
                 label = COALESCE(excluded.label, places.label),
                 conversation_id = COALESCE(excluded.conversation_id, places.conversation_id),
                 person_user_id = COALESCE(excluded.person_user_id, places.person_user_id),
                 updated_at = excluded.updated_at""",
            (platform, place_key, kind, visibility, label, conversation_id, person_user_id, now, now))
        conn.commit()


def _rows(where: str = "", args: tuple = ()) -> List[Dict]:
    try:
        from database import get_db
        with get_db() as conn:
            cur = conn.execute(
                "SELECT platform, place_key, kind, visibility, label, conversation_id, person_user_id, "
                "created_at, updated_at FROM places " + where, args)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.debug(f"[places] lookup failed: {e}")
        return []


def by_conversation(conversation_id: Optional[str]) -> Optional[Dict]:
    if not conversation_id:
        return None
    rows = _rows("WHERE conversation_id = ?", (conversation_id,))
    return rows[0] if rows else None


def house_conversation_ids() -> Set[str]:
    """Conversations kept for house places: recallable in any house context."""
    return {r["conversation_id"] for r in _rows("WHERE visibility = 'house'") if r["conversation_id"]}


def house_members() -> Set[str]:
    """Vessel users who are in the house: the people linked to her on Babelr
    (DATA_DIR/babelr/links.json: Kohl, RoboKohl, Daedalus). House places come up
    with them, and with nobody else who has an account. Empty if unknown, so
    house places then come up only where she's with nobody in particular."""
    try:
        import json
        from babelr_organ.config import load_config
        data = json.loads(load_config().links_path.read_text())
        return {str(v) for v in data.values() if isinstance(v, str) and v}
    except Exception as e:
        logger.debug(f"[places] no house members: {e}")
        return set()


def all_places(platform: Optional[str] = None, visibility: Optional[str] = None) -> List[Dict]:
    clauses, args = [], []
    if platform:
        clauses.append("platform = ?")
        args.append(platform)
    if visibility:
        clauses.append("visibility = ?")
        args.append(visibility)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return _rows(where + " ORDER BY created_at", tuple(args))
