"""
People who mention her or reply to her, kept in PeopleDex by handle (the
consent line Cass and Kohl agreed: public exchanges are kept). Only people
who address her; strangers on her timeline aren't recorded. A person is
found by "<platform>:<handle>" before anyone new is made.
"""
from __future__ import annotations

from typing import Iterable, List, Optional


def keep(platform: str, people: Iterable[dict], daemon_id: Optional[str] = None, dex=None) -> List[str]:
    """people: {"handle", "name"}. Returns the handles newly added."""
    if dex is None:
        from peopledex import PeopleDexManager
        dex = PeopleDexManager(daemon_id=daemon_id)
    from peopledex import AttributeType, EntityType

    added, seen = [], set()
    for person in people:
        handle = (person.get("handle") or "").lstrip("@").strip()
        if not handle or handle.lower() in seen:
            continue
        seen.add(handle.lower())
        exact = [e for e in dex.find_entities(f"{platform}:{handle}", limit=5)
                 if any(getattr(a.attribute_type, "value", a.attribute_type) == AttributeType.HANDLE.value
                        and (a.value or "").lstrip("@").lower() == handle.lower()
                        for a in dex.get_attributes(e.id))]
        if exact:
            continue
        entity_id = dex.create_entity(EntityType.PERSON, person.get("name") or handle)
        dex.add_attribute(entity_id, AttributeType.HANDLE, handle, attribute_key=platform,
                          is_primary=True, source_type=platform)
        added.append(handle)
    return added
