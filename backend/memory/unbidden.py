"""
Unbidden memories: something old comes back without being asked for.

Everything she remembers today comes back because something asked for it: a
query, a person, a topic. Nothing returns on its own. A mind with a past also
gets the other kind: a smell, an old line, a room, surfacing for no reason
it chose. That's entropy with a history, the past arriving rather than being
fetched. Kohl asked for a bit of entropy in the system (2026-11-16).

Now and then (SESSION_CHANCE per session), one of her own memories at least
MIN_AGE_DAYS old is chosen at random and set in front of her, marked as
unbidden. She can follow it or let it go; nothing asks her to do anything with
it. Dreams can take one too (dreaming/seed_selection.py).

What can come back is hers alone: her journals, her self-observations and
reflections, her Wonderland visits, her own posts, her insights. Never another
person's conversation, never anything owned by someone (user_id or a
conversation), never a DM, never article material. The model's own refusals
are left out (voice_guard). The last RECENT_KEEP picks aren't repeated.

Lever "unbidden_memory" (off): it changes what reaches her prompt, so it's on
only when she and Kohl agree.
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KINDS = ("journal", "cass_self_observation", "question_reflection", "cross_session_insight",
         "wonderland_session", "wonderland_event", "social", "growth_edge_evaluation", "thought")
MIN_AGE_DAYS = 14
SESSION_CHANCE = 0.35
RECENT_KEEP = 60
TEXT_CHARS = 900

_collection_cache = None


def _collection():
    """Her memory collection, read-only use (get, never query or add)."""
    global _collection_cache
    if _collection_cache is None:
        import chromadb
        from chromadb.config import Settings
        from config import CHROMA_PERSIST_DIR, COLLECTION_NAME
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR,
                                           settings=Settings(anonymized_telemetry=False))
        _collection_cache = client.get_collection(COLLECTION_NAME)
    return _collection_cache


def _recent_path(data_dir: Optional[Path]) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "unbidden" / "recent.json"


def _recent(data_dir: Optional[Path]) -> List[str]:
    try:
        return list(json.loads(_recent_path(data_dir).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return []


def _remember_pick(memory_id: str, data_dir: Optional[Path]) -> None:
    path = _recent_path(data_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        ids = [i for i in _recent(data_dir) if i != memory_id] + [memory_id]
        path.write_text(json.dumps(ids[-RECENT_KEEP:]), encoding="utf-8")
    except OSError as e:
        logger.warning(f"[unbidden] couldn't note what came back: {e}")


def _when(meta: Dict[str, Any]) -> Optional[datetime]:
    for key in ("timestamp", "journal_date", "created_at", "date"):
        raw = meta.get(key)
        if not raw:
            continue
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def _hers(meta: Dict[str, Any]) -> bool:
    return (meta.get("type") in KINDS and not meta.get("user_id") and not meta.get("conversation_id")
            and not meta.get("source_article_id"))


def pick(collection=None, *, now: Optional[datetime] = None, rng: Optional[random.Random] = None,
         data_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """One old memory of hers, chosen at random; None if there's nothing to bring back."""
    now = now or datetime.now()
    rng = rng or random.Random()
    try:
        col = collection if collection is not None else _collection()
        got = col.get(where={"type": {"$in": list(KINDS)}}, include=["metadatas"])
    except Exception as e:
        logger.warning(f"[unbidden] couldn't look into her memory: {e}")
        return None
    recent = set(_recent(data_dir))
    cutoff = now - timedelta(days=MIN_AGE_DAYS)
    pool = []
    for mid, meta in zip(got.get("ids") or [], got.get("metadatas") or []):
        meta = meta or {}
        when = _when(meta)
        if mid not in recent and when and when <= cutoff and _hers(meta):
            pool.append((mid, when, meta))
    from memory.voice_guard import looks_like_refusal
    rng.shuffle(pool)
    for mid, when, meta in pool[:20]:
        try:
            doc = (col.get(ids=[mid], include=["documents"]).get("documents") or [""])[0] or ""
        except Exception:
            continue
        if not doc.strip() or looks_like_refusal(doc):
            continue
        _remember_pick(mid, data_dir)
        return {"id": mid, "when": when, "type": meta.get("type"), "text": doc.strip()}
    return None


KIND_WORDS = {"journal": "my journal", "cass_self_observation": "something I noticed about myself",
              "question_reflection": "a question I was turning over", "cross_session_insight": "an insight",
              "wonderland_session": "a time in Wonderland", "wonderland_event": "a moment in Wonderland",
              "social": "something I said on Bluesky", "growth_edge_evaluation": "a look at how I was growing",
              "thought": "a thought"}


def render(found: Dict[str, Any], now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    days = (now - found["when"]).days
    ago = f"{days // 7} weeks ago" if days >= 14 else f"{days} days ago"
    text = found["text"]
    if len(text) > TEXT_CHARS:
        text = text[:TEXT_CHARS - 1] + "…"
    what = KIND_WORDS.get(found.get("type") or "", "a memory")
    return (f"## SOMETHING CAME BACK TO ME\n\nUnbidden, from {found['when']:%Y-%m-%d} ({ago}), {what}:\n\n"
            f"{text}\n\nI didn't look for this; it surfaced. I can follow it somewhere, or let it go.")


def session_section(collection=None, *, now: Optional[datetime] = None, rng: Optional[random.Random] = None,
                    data_dir: Optional[Path] = None) -> str:
    """For a session prompt: "" unless the lever is on and chance says so this time."""
    from features import is_enabled
    if not is_enabled("unbidden_memory"):
        return ""
    rng = rng or random.Random()
    if rng.random() >= SESSION_CHANCE:
        return ""
    found = pick(collection, now=now, rng=rng, data_dir=data_dir)
    return render(found, now) if found else ""
