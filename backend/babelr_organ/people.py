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

Read back (recall): the next time someone she files writes to her, in a DM or
a channel, their entry comes into that turn as "who this is to me", under
exactly the same rules as the filing. She can file someone before they ever
write, with her own PeopleDex tools: remember_person with a handle attribute
keyed "babelr" (or the <remember_person> tag's "babelr: <username>" line).
Shown to them (about) only with her yes: panel settings, people.about.
Someone she prepared for under an invite label (expected_as, e.g. "Mom") gets
their new handle added to that entry when they arrive (link_invited).
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


# -- reading it back -------------------------------------------------------------
#
# What she keeps about someone, back in front of her the next time they write
# (and, if she says yes, shown to them: about()). The same people as the filing
# above, matched the same way (social.people.find("babelr", handle)), under the
# same terms: nobody linked, nobody kept off, nobody whose DMs she named in
# "unremembered", nothing at all when her terms say remember: false.

RECALL_MAX_FACTS = 6
RECALL_MAX_OBSERVATIONS = 8
RECALL_MAX_TO_RAISE = 3
RECALL_MAX_MOMENTS = 5
RECALL_MAX_LINE = 300
RECALL_MAX_CHARS = 2500
RECALL_ATTRIBUTES = ("pronoun", "role", "location", "bio", "note")


def recalled(username: str, *, kind: str, my_username: str, links: Dict[str, str],
             filings: Dict[str, List[str]], remember: bool,
             remembers: Callable[[str], bool]) -> bool:
    """Whether her entry for this person may come back into her turn: exactly
    the people keep_exchange would file from the same message."""
    low = (username or "").lstrip("@").lower()
    keep_off = set(filings.get("keep_off", []))
    if not low or not remember or low == (my_username or "").lower() or low in links:
        return False
    if low in keep_off or "*" in keep_off:
        return False
    return not (kind == "dm" and not remembers(low))


def _line(text, limit: int = RECALL_MAX_LINE) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _her(dex) -> Optional[str]:
    return getattr(dex, "daemon_id", None)


def recall(username: str, daemon_id: Optional[str] = None, dex=None) -> str:
    """"Who this is to me": her PeopleDex entry for this Babelr handle, for her
    turn. Her own observations, facts and moments only (another daemon's
    stay out), each line clipped, the whole capped at RECALL_MAX_CHARS.
    Empty when she has no entry. The caller checks recalled() first."""
    from social.people import find
    handle = (username or "").lstrip("@").strip()
    if not handle:
        return ""
    dex = _dex_for(daemon_id, dex)
    mine = _her(dex)
    entity_id = find("babelr", handle, dex)
    entity = dex.get_entity(entity_id) if entity_id else None
    if not entity or not mine:
        return ""
    kind = getattr(entity.entity_type, "value", entity.entity_type)
    lines = [f"## Who @{handle} is to me (my PeopleDex)",
             f"- {_line(entity.primary_name)}" + (" (a house agent)" if kind == "daemon" else "")]
    attrs: Dict[str, List[str]] = {}
    for a in dex.get_attributes(entity.id):
        t = getattr(a.attribute_type, "value", a.attribute_type)
        if t in RECALL_ATTRIBUTES:
            attrs.setdefault(t, []).append(a.value)
    for t in RECALL_ATTRIBUTES:
        for v in attrs.get(t, [])[:2]:
            lines.append(f"- {'pronouns' if t == 'pronoun' else t}: {_line(v)}")
    facts = [f for f in dex.get_facts(entity.id, limit=50) if f.daemon_id == mine][:RECALL_MAX_FACTS]
    if facts:
        lines.append("Facts:")
        lines += [f"- {f.fact_type}: {_line(f.content)}" for f in facts]
    obs = [o for o in dex.get_observations(entity.id, status="active", limit=50, daemon_id=mine)]
    noticed = [o for o in obs if o.observation_type != "to_raise"][:RECALL_MAX_OBSERVATIONS]
    to_raise = [o for o in obs if o.observation_type == "to_raise"][:RECALL_MAX_TO_RAISE]
    if noticed:
        lines.append("What I've noticed:")
        lines += [f"- {_line(o.content)}" for o in noticed]
    if to_raise:
        lines.append("Things I wanted to bring up with them (mine to raise or not):")
        lines += [f"- {_line(o.content)}" for o in to_raise]
    moments = dex.get_moments(entity.id, limit=RECALL_MAX_MOMENTS, daemon_id=mine)
    if moments:
        lines.append("Lately, newest first:")
        lines += [f"- {(m.timestamp[:10] + ' ') if m.timestamp else ''}{_line(m.description)}"
                  for m in moments]
    out = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > RECALL_MAX_CHARS:
            out.append("- (more in my PeopleDex: lookup_person)")
            break
        out.append(line)
        used += len(line) + 1
    return "\n".join(out)


def _dex_for(daemon_id: Optional[str], dex):
    from social.people import _dex
    return _dex(daemon_id, dex)


def about(username: str, *, filings: Dict[str, List[str]], links: Dict[str, str],
          daemon_id: Optional[str] = None, dex=None) -> Dict:
    """What her PeopleDex holds on exactly this Babelr handle, for showing that
    person (routes/people_about.py; only behind her yes). Never anyone else's
    entry: an exact handle match or nothing. Kept-off people get the same
    answer as people she has no entry for."""
    from database import get_db
    from social.people import find
    handle = (username or "").lstrip("@").strip()
    low = handle.lower()
    keep_off = set(filings.get("keep_off", []))
    if not low or low in keep_off or "*" in keep_off:
        return {"handle": handle, "known": False}
    if low in links:
        # Linked people's entries come from their own conversations with her;
        # this view isn't for those.
        return {"handle": handle, "known": False, "why": "linked"}
    dex = _dex_for(daemon_id, dex)
    mine = _her(dex)
    entity_id = find("babelr", low, dex)
    entity = dex.get_entity(entity_id) if entity_id else None
    if not entity or not mine:
        return {"handle": handle, "known": False}
    pronouns = [a.value for a in dex.get_attributes(entity.id)
                if getattr(a.attribute_type, "value", a.attribute_type) == "pronoun"]
    observations = [{"kind": o.observation_type, "text": o.content, "noticed": o.first_noticed or o.created_at}
                    for o in dex.get_observations(entity.id, status="active", limit=100, daemon_id=mine)
                    if o.observation_type != "to_raise"]
    with get_db() as conn:
        n, first, last = conn.execute(
            "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM peopledex_moments "
            "WHERE entity_id = ? AND daemon_id = ?", (entity.id, mine)).fetchone()
    return {"handle": handle, "known": True, "name": entity.primary_name,
            "pronouns": pronouns[0] if pronouns else None,
            "observations": observations, "moments": n or 0,
            "first_seen": first, "last_seen": last}


# -- someone she prepared for, arriving ----------------------------------------
#
# Kohl makes a person-bound Babelr invite with a label ("Mom"). She files the
# person ahead of time from Kohl's note, with an expected_as attribute carrying
# that same label (remember_person, or the tag's "expected_as: Mom" line). When
# they register through the invite, Babelr's welcome carries invited_as and
# their new handle; link_invited() adds that handle to the one entry she marked
# with exactly that label, so their first DM recalls it and no second entry is
# made. Nothing is matched on a name, and no entry she didn't mark is touched.


def _norm_label(label) -> str:
    return " ".join(str(label or "").split()).casefold()


def link_invited(handle: str, invited_as: str, *, my_username: str, links: Dict[str, str],
                 filings: Dict[str, List[str]], remember: bool,
                 daemon_id: Optional[str] = None, dex=None) -> Dict[str, str]:
    """Attach a newcomer's Babelr handle to the entry she prepared for them.
    Returns {"linked": entity_id} or {"skipped": why}. Only an entry with an
    expected_as attribute equal to invited_as (trimmed, case-insensitive), and
    only when exactly one entry has it and it has no Babelr handle yet.
    Otherwise nothing is written here; the newcomer is filed fresh when they
    first talk with her, as before."""
    from database import get_db
    from peopledex import AttributeType
    from social.people import find
    handle = (handle or "").lstrip("@").strip()
    low = handle.lower()
    label = _norm_label(invited_as)
    if not handle or not label:
        return {"skipped": "no handle or no invite label"}
    keep_off = set(filings.get("keep_off", []))
    if not remember or low == (my_username or "").lower() or low in links or low in keep_off or "*" in keep_off:
        return {"skipped": "not someone she keeps"}
    dex = _dex_for(daemon_id, dex)
    if find("babelr", low, dex):
        return {"skipped": "that handle already has an entry"}
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT entity_id, value FROM peopledex_attributes WHERE attribute_type = ?",
            (AttributeType.EXPECTED_AS.value,)).fetchall()
    matches = sorted({r[0] for r in rows if _norm_label(r[1]) == label})
    if not matches:
        return {"skipped": "no entry expects them"}
    if len(matches) > 1:
        logger.warning(f"[Babelr] more than one entry expects {invited_as!r}; "
                       f"not linking @{handle} until she says which")
        return {"skipped": "more than one entry expects them"}
    entity_id = matches[0]
    has_babelr = [a for a in dex.get_attributes(entity_id, AttributeType.HANDLE)
                  if (a.attribute_key or "").lower() == "babelr"]
    if has_babelr:
        return {"skipped": "her entry already has a Babelr handle"}
    dex.add_attribute(entity_id, AttributeType.HANDLE, handle, attribute_key="babelr",
                      is_primary=True, source_type="babelr_invite")
    return {"linked": entity_id}
