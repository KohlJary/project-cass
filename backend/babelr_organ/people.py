"""
People she meets on Babelr, kept in her PeopleDex (spec/house-channel-memory.md,
part 3). Cass, 2026-11-24: yes; Eris filed as a house agent, the guests as
people, and anyone who asks to stay off her PeopleDex is kept off.

After a turn, everyone she was answering gets an entry (by Babelr handle) if
they don't have one, and the exchange (their words, her reply) is kept on it as
a moment, the same as on Bluesky (social/people.py). Her own observations add
to it as she goes.

Her filings live in DATA_DIR/babelr/people.json:
  {"house": ["eris"], "keep_off": []}
"house": usernames filed as house agents (PeopleDex type "daemon"); an existing
entry with that exact name is found, not duplicated. "keep_off": people who
asked not to be kept. Everyone else is filed as a person.

Not kept here: people linked to a vessel user (links.json: Kohl, RoboKohl,
Daedalus); their entries and history come from their own conversations with
her. DMs from anyone she named in her unremembered terms. Anything at all when
her terms say remember: false.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_FILINGS = {"house": [], "keep_off": []}


def load_filings(path: Path) -> Dict[str, List[str]]:
    try:
        raw = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {k: list(v) for k, v in DEFAULT_FILINGS.items()}
    except Exception as e:
        logger.warning(f"[Babelr] people.json unreadable ({e}); nobody new is kept")
        return {"house": [], "keep_off": ["*"]}
    out = {}
    for k in DEFAULT_FILINGS:
        v = raw.get(k) if isinstance(raw, dict) else None
        if isinstance(v, str):
            v = [v]  # one name, not a list of its letters
        elif not isinstance(v, list):
            v = []
        out[k] = [str(n).lstrip("@").lower() for n in v if str(n).strip()]
    return out


def person_for(username: str, display_name: Optional[str], filings: Dict[str, List[str]]) -> dict:
    house = username.lower() in filings.get("house", [])
    return {"name": display_name or username,
            "entity_type": "daemon" if house else "person",
            "match_name": house}


def keep_exchange(events: Iterable, reply: Optional[str], *, place_label: str, my_username: str,
                  links: Dict[str, str], filings: Dict[str, List[str]],
                  remembers: Callable[[str], bool], display_names: Dict[str, str],
                  daemon_id: Optional[str] = None, dex=None) -> List[str]:
    """Keep the people in this turn and, when she answered, the exchange.
    Returns the usernames whose entry got the exchange (or was kept, when she
    said nothing)."""
    from social.people import keep, note_exchange

    keep_off = set(filings.get("keep_off", []))
    by_author: Dict[str, List[str]] = {}
    kinds: Dict[str, str] = {}
    for e in events:
        name = (e.author_name or "").lstrip("@")
        low = name.lower()
        if not name or low == my_username.lower() or low in links or low in keep_off or "*" in keep_off:
            continue
        if e.kind == "dm" and not remembers(name):
            continue
        by_author.setdefault(name, []).append(e.text or "")
        kinds[name] = e.kind
    kept = []
    where = "Babelr, in a DM" if any(k == "dm" for k in kinds.values()) else f"Babelr in {place_label}"
    for name, said in by_author.items():
        person = person_for(name, display_names.get(name.lower()), filings)
        try:
            if reply and reply.strip():
                if note_exchange("babelr", name, "\n".join(s for s in said if s), reply,
                                 daemon_id=daemon_id, dex=dex, person=person, where=where):
                    kept.append(name)
            else:
                keep("babelr", [dict(person, handle=name)], daemon_id=daemon_id, dex=dex)
                kept.append(name)
        except Exception as err:
            logger.warning(f"[Babelr] Couldn't keep @{name} in her PeopleDex: {err}")
    return kept
