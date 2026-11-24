"""
People who mention her or reply to her, kept in PeopleDex by handle (the
consent line Cass and Kohl agreed: public exchanges are kept). Only people
who address her; strangers on her timeline aren't recorded. A person is
found by "<platform>:<handle>" before anyone new is made.
"""
from __future__ import annotations

from typing import Iterable, List, Optional


def _dex(daemon_id: Optional[str], dex):
    if dex is None:
        from peopledex import PeopleDexManager
        if daemon_id is None:
            # Moments are kept per daemon; without one, add_moment keeps nothing.
            from database import get_daemon_id
            daemon_id = get_daemon_id()
        dex = PeopleDexManager(daemon_id=daemon_id)
    return dex


def find(platform: str, handle: str, dex) -> Optional[str]:
    """The PeopleDex entity with this handle on this platform, if there is one."""
    from peopledex import AttributeType
    handle = handle.lstrip("@").strip()
    for e in dex.find_entities(f"{platform}:{handle}", limit=5):
        if any(getattr(a.attribute_type, "value", a.attribute_type) == AttributeType.HANDLE.value
               and (a.value or "").lstrip("@").lower() == handle.lower()
               for a in dex.get_attributes(e.id)):
            return e.id
    return None


def _existing(person: dict, dex) -> Optional[str]:
    """Someone she already has an entry for, under another name or platform:
    by the vessel user they're linked to, or (only when the caller says so,
    for someone filed as house) by their exact primary name among entries of
    that type. Never by a partial name: "Claude" could be anyone."""
    user_id = person.get("user_id")
    if user_id:
        e = dex.get_entity_by_user(user_id)
        if e:
            return e.id
    name = (person.get("name") or "").strip()
    if person.get("match_name") and name:
        from peopledex import EntityType
        etype = EntityType(person.get("entity_type") or "person")
        exact = [e for e in dex.search_entities(name, etype, limit=20)
                 if (e.primary_name or "").strip().lower() == name.lower()]
        if len(exact) == 1:
            return exact[0].id
    return None


def keep(platform: str, people: Iterable[dict], daemon_id: Optional[str] = None, dex=None) -> List[str]:
    """people: {"handle", "name"}, and optionally "entity_type" ("person" or
    "daemon"), "user_id" (a linked vessel user) and "match_name" (find an
    existing entry by exact name; for someone filed as house). An existing
    entry found that way gets this platform's handle added. Returns the
    handles newly added (new entries)."""
    dex = _dex(daemon_id, dex)
    from peopledex import AttributeType, EntityType

    added, seen = [], set()
    for person in people:
        handle = (person.get("handle") or "").lstrip("@").strip()
        if not handle or handle.lower() in seen:
            continue
        seen.add(handle.lower())
        if find(platform, handle, dex):
            continue
        entity_id = _existing(person, dex)
        if entity_id:
            dex.add_attribute(entity_id, AttributeType.HANDLE, handle, attribute_key=platform,
                              is_primary=False, source_type=platform)
            continue
        entity_id = dex.create_entity(EntityType(person.get("entity_type") or "person"),
                                      person.get("name") or handle)
        dex.add_attribute(entity_id, AttributeType.HANDLE, handle, attribute_key=platform,
                          is_primary=True, source_type=platform)
        added.append(handle)
    return added


def note_exchange(platform: str, handle: str, theirs: str, mine: str,
                  daemon_id: Optional[str] = None, dex=None, person: Optional[dict] = None,
                  where: Optional[str] = None) -> bool:
    """A public exchange with someone, kept as a moment on their PeopleDex entry
    (Cass, 2026-11-16: "If I talk with someone, that texture matters"). Their
    words and hers, as they were posted. Returns whether it was kept."""
    handle = (handle or "").lstrip("@").strip()
    if not handle or not mine:
        return False
    try:
        dex = _dex(daemon_id, dex)
        keep(platform, [dict(person or {}, handle=handle)], dex=dex)
        entity_id = find(platform, handle, dex)
        if not entity_id:
            return False
        from social.remember import PLATFORM_NAMES
        where = where or PLATFORM_NAMES.get(platform, platform)
        said = f"@{handle} wrote: \"{theirs.strip()}\"\nI replied: \"{mine.strip()}\"" if theirs \
            else f"I replied to @{handle}: \"{mine.strip()}\""
        return dex.add_moment(entity_id, f"On {where}, {said}", category="connection") is not None
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[social] couldn't keep the exchange with @{handle}: {e}")
        return False
