"""
recall: her own queries over her memory (plan "Cass's memory", phase 8,
"She asks her own memory"). Kohl, 2026-11-16: her memory in conversation
was too rigid; she shaped the tool the same night.

She composes the query: what it's about (by meaning, optional), which kinds
of memory, with whom, between which dates, from where, in what order. With
no `about`, results are filtered and ordered by date (the arc of something
over time). recall_open reads one result in full with what came around it.

Scope (Cass proposed, Kohl agreed, 2026-11-16): she can recall anyone's
conversations when she asks; what comes up on its own each turn stays scoped
(continuous_context._scoped_recall, unchanged). Results from a conversation
with someone other than the person she's with carry a note: hers to be aware
of, not to quote or attribute. That's her commitment, not something code can
enforce. What was never kept (Vigil, DMs without a yes) or was deleted on
request isn't in her memory to find.

Tone or stance ("where I pushed back") is matched by meaning only; nothing
in her memory is labelled by tone.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Sequence

# What she calls each part of her memory -> the stored types.
KINDS: Dict[str, Sequence[str]] = {
    "conversations": ("conversation",),
    "summaries": ("summary",),
    "journals": ("journal", "per_user_journal"),
    "reflections": ("question_reflection", "growth_edge_evaluation", "cross_session_insight"),
    "self_observations": ("cass_self_observation",),
    "people": ("user_observation",),
    "notes": ("research_note",),
    "social": ("social",),
}
ALL_TYPES = tuple(t for ts in KINDS.values() for t in ts)
KIND_OF = {t: k for k, ts in KINDS.items() for t in ts}
SOURCES = ("chat", "babelr", "discord", "bluesky")
MAX_LIMIT = 25
SCAN = 3000          # memories looked through for a query with no `about`
OVERFETCH = 8        # candidates per result for a query by meaning
THEIRS_NOTE = ("from your conversation with someone else: yours to be aware of, "
               "not to quote or attribute")


def _types(kinds: Optional[Iterable[str]]) -> List[str]:
    if not kinds:
        return list(ALL_TYPES)
    out: List[str] = []
    for k in kinds:
        out += list(KINDS.get(k, ()))
    return out


def _source(meta: Dict[str, Any]) -> str:
    if meta.get("type") == "social":
        return meta.get("platform") or "bluesky"
    return meta.get("source") or "chat"


def _in_range(meta: Dict[str, Any], between: Optional[Dict[str, str]]) -> bool:
    if not between:
        return True
    day = (meta.get("timestamp") or meta.get("journal_date") or "")[:10]
    if not day:
        return False
    lo, hi = (between.get("from") or "")[:10], (between.get("to") or "")[:10]
    return (not lo or day >= lo) and (not hi or day <= hi)


class People:
    """Who `with` names: their user ids (conversations) and handles (Bluesky)."""

    def __init__(self, names: Optional[Sequence[str]], dex=None, daemon_id: Optional[str] = None):
        self.user_ids: set = set()
        self.handles: set = set()
        self.unknown: List[str] = []
        self.wanted = bool(names)
        for name in names or ():
            n = name.strip().lstrip("@")
            if not n:
                continue
            found = False
            if "." in n:   # a handle
                self.handles.add(n.lower())
                found = True
            if dex is None:
                try:
                    from peopledex import PeopleDexManager
                    dex = PeopleDexManager(daemon_id=daemon_id)
                except Exception:
                    dex = False
            if dex:
                for e in dex.find_entities(n, limit=5):
                    if getattr(e, "user_id", None):
                        self.user_ids.add(e.user_id)
                        found = True
            if not found:
                self.unknown.append(name)

    def match(self, meta: Dict[str, Any], owner: Optional[str]) -> bool:
        if not self.wanted:
            return True
        if owner and owner in self.user_ids:
            return True
        return (meta.get("with") or "").lower() in self.handles


def _owners():
    from memory.scope import ConversationOwners, house_agent_user_ids
    return ConversationOwners(), house_agent_user_ids()


def _entry(mid: str, doc: str, meta: Dict[str, Any], owner: Optional[str], current: Optional[str],
           agents: set, full: bool = False) -> Dict[str, Any]:
    text = doc if full else (meta.get("gist") or doc)
    if not full and len(text) > 700:
        text = text[:699] + "…"
    out = {"id": mid, "kind": KIND_OF.get(meta.get("type"), meta.get("type")),
           "date": (meta.get("timestamp") or meta.get("journal_date") or "")[:16],
           "from": _source(meta), "text": text}
    if meta.get("with"):
        out["with"] = meta["with"]
    if owner and owner != current and owner not in agents:
        out["note"] = THEIRS_NOTE
    return out


def recall(memory, *, about: Optional[str] = None, kinds: Optional[Sequence[str]] = None,
           with_people: Optional[Sequence[str]] = None, between: Optional[Dict[str, str]] = None,
           from_sources: Optional[Sequence[str]] = None, order: str = "relevance", limit: int = 10,
           by_month: bool = False, current_user_id: Optional[str] = None,
           daemon_id: Optional[str] = None, dex=None, owners=None, agents=None) -> Dict[str, Any]:
    limit = max(1, min(int(limit or 10), MAX_LIMIT))
    types = _types(kinds)
    unknown_kinds = [k for k in (kinds or ()) if k not in KINDS]
    if not types:
        return {"error": f"I don't keep memories of that kind; kinds are {', '.join(KINDS)}."}
    if owners is None or agents is None:
        owners, agents = _owners()
    people = People(with_people, dex=dex, daemon_id=daemon_id)
    sources = {s.lower() for s in from_sources or ()}
    where = {"type": {"$in": types}} if len(types) > 1 else {"type": types[0]}

    if about and about.strip():
        found = memory.retrieve_where(about.strip(), limit * OVERFETCH, where)
        candidates = [(m.get("id") or "", m["content"], m.get("metadata") or {}) for m in found]
    else:
        got = memory.collection.get(where=where, include=["documents", "metadatas"], limit=SCAN)
        candidates = list(zip(got.get("ids") or [], got.get("documents") or [], got.get("metadatas") or []))
        if order == "relevance":
            order = "newest"

    from memory.scope import owner_of
    results = []
    for mid, doc, meta in candidates:
        if not _in_range(meta, between):
            continue
        if sources and _source(meta) not in sources:
            continue
        owner = owner_of(meta, owners)
        if not people.match(meta, owner):
            continue
        results.append(_entry(mid, doc, meta, owner, current_user_id, set(agents)))

    if order in ("newest", "oldest"):
        results.sort(key=lambda r: r["date"], reverse=(order == "newest"))
    results = results[:limit]

    out: Dict[str, Any] = {"count": len(results)}
    if by_month:
        grouped: "OrderedDict[str, list]" = OrderedDict()
        for r in sorted(results, key=lambda r: r["date"]):
            grouped.setdefault(r["date"][:7] or "undated", []).append(r)
        out["by_month"] = grouped
    else:
        out["results"] = results
    if people.unknown:
        out["not_found"] = people.unknown
    if unknown_kinds:
        out["unknown_kinds"] = unknown_kinds
    if about and any(w in about.lower() for w in ("felt", "feeling", "uncertain", "pushed back", "excited", "tone")):
        out["about_tone"] = "Tone is matched by meaning only; nothing in my memory is labelled by tone."
    return out


def recall_open(memory, memory_id: str, *, around: int = 3, current_user_id: Optional[str] = None,
                owners=None, agents=None) -> Dict[str, Any]:
    got = memory.collection.get(ids=[memory_id], include=["documents", "metadatas"])
    if not got.get("ids"):
        return {"error": "I don't have a memory with that id (it comes from recall's results)."}
    doc, meta = got["documents"][0], got["metadatas"][0]
    if owners is None or agents is None:
        owners, agents = _owners()
    from memory.scope import owner_of
    owner = owner_of(meta, owners)
    out = {"memory": _entry(memory_id, doc, meta, owner, current_user_id, set(agents), full=True)}
    cid = meta.get("conversation_id")
    if cid and around:
        thread = memory.get_by_conversation(cid)
        idx = next((i for i, e in enumerate(thread) if e.get("id") == memory_id), None)
        if idx is not None:
            def view(e):
                return _entry(e["id"], e["content"], e["metadata"], owner, current_user_id, set(agents), full=True)
            out["before"] = [view(e) for e in thread[max(0, idx - around):idx]]
            out["after"] = [view(e) for e in thread[idx + 1: idx + 1 + around]]
    return out
