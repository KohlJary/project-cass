"""
Her social inbox: what came in, queued for her social sessions (plan "Cass on
Bluesky and Tumblr", phase 5). She chose (2026-11-16): queue what comes in, don't
interrupt; she answers in her social sessions, and wants to know when
something she said resonated.

The watcher (social/watch.py) calls poll(); nothing here posts or wakes her.

    DATA_DIR/social/<platform>/inbox.json
        {"items": [...], "seen": [notification uris], "flagged": [her post uris],
         "dm_seen": {convo id: last message id}, "last_poll": iso}

An item: {id, kind, at, from, text, url, uri, status, note}
    kind: mention | reply | quote | follow | resonated | dm
    status: new | later | done
A DM item carries who and how many unread, never the text: what a DM says
is read in the session, under the consent line (social/dms.py).
"""
from __future__ import annotations

import logging

import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from social import limits
from social.config import platform_dir

logger = logging.getLogger(__name__)

QUEUED_REASONS = ("mention", "reply", "quote", "follow")
SEEN_KEEP = 1000        # notification uris remembered, so nothing is queued twice
ITEMS_KEEP = 400        # done items beyond this are dropped, oldest first
STATS_POSTS = 20        # her recent posts and replies looked at for engagement
# A post resonated when its engagement is well above her own usual: at least
# RESONANCE_FLOOR, and RESONANCE_RATIO times the median of her other recent posts.
RESONANCE_FLOOR = 5
RESONANCE_RATIO = 3


def engagement(stats: Dict[str, int]) -> int:
    """Replies, reposts and quotes are someone taking it further; likes count once."""
    return (2 * stats.get("replies", 0) + 2 * stats.get("reposts", 0)
            + 2 * stats.get("quotes", 0) + stats.get("likes", 0))


def _path(platform: str, data_dir: Optional[Path]) -> Path:
    return platform_dir(platform, data_dir) / "inbox.json"


def load(platform: str, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    try:
        state = json.loads(_path(platform, data_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    state.setdefault("items", [])
    state.setdefault("seen", [])
    state.setdefault("flagged", [])
    state.setdefault("dm_seen", {})
    return state


def save(platform: str, state: Dict[str, Any], data_dir: Optional[Path] = None) -> None:
    done = [i for i in state["items"] if i.get("status") == "done"]
    if len(state["items"]) > ITEMS_KEEP and done:
        drop = {id(i) for i in done[:len(state["items"]) - ITEMS_KEEP]}
        state["items"] = [i for i in state["items"] if id(i) not in drop]
    state["seen"] = state["seen"][-SEEN_KEEP:]
    state["flagged"] = state["flagged"][-SEEN_KEEP:]
    path = _path(platform, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _item(kind: str, **fields) -> Dict[str, Any]:
    return {"kind": kind, "status": "new", **fields}


async def poll(platform: str, client, data_dir: Optional[Path] = None, *, dms: bool = False,
               now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Queue what's new; returns the items added."""
    now = now or datetime.now()
    state = load(platform, data_dir)
    seen = set(state["seen"])
    added: List[Dict[str, Any]] = []

    for n in reversed(await client.notifications(50)):   # oldest first, so the queue reads in order
        uri = n.get("uri")
        if not uri or uri in seen:
            continue
        seen.add(uri)
        state["seen"].append(uri)
        if n.get("reason") not in QUEUED_REASONS:
            continue   # likes and reposts are counted per post below, not queued one by one
        added.append(_item(n["reason"], id=uri, uri=uri, at=n.get("at"), **{"from": n.get("author")},
                           name=n.get("name"), text=n.get("text", ""), url=n.get("url")))

    # Each part fails on its own: a refused DM listing (an app password made
    # without DM access says "Bad token method") used to throw away the
    # mentions and replies already fetched in this pass.
    for part in (lambda: _resonance(platform, client, state, data_dir),
                 (lambda: _dms(client, state)) if dms else None):
        if part is None:
            continue
        try:
            added += await part()
        except Exception as e:
            logger.warning(f"[social] part of the {platform} poll failed; the rest is kept: {e}")

    state["items"].extend(added)
    state["last_poll"] = now.isoformat(timespec="seconds")
    save(platform, state, data_dir)
    return added


async def _resonance(platform: str, client, state: Dict[str, Any], data_dir) -> List[Dict[str, Any]]:
    mine = [r for r in limits.posted(platform, data_dir) if r.get("kind") in ("post", "reply") and r.get("uri")]
    mine = mine[-STATS_POSTS:]
    if not mine or not hasattr(client, "post_stats"):
        return []
    stats = await client.post_stats([r["uri"] for r in mine])
    scores = {uri: engagement(s) for uri, s in stats.items()}
    out = []
    for rec in mine:
        uri = rec["uri"]
        if uri in state["flagged"] or uri not in scores:
            continue
        others = [v for u, v in scores.items() if u != uri]
        usual = statistics.median(others) if others else 0
        if scores[uri] >= max(RESONANCE_FLOOR, RESONANCE_RATIO * usual):
            state["flagged"].append(uri)
            out.append(_item("resonated", id=f"resonated:{uri}", uri=uri, url=rec.get("url"),
                             at=datetime.now().isoformat(timespec="seconds"), text=rec.get("text", ""),
                             stats=stats[uri], usual=usual))
    return out


async def _dms(client, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for c in await client.conversations(50):
        last = (c.get("last") or {})
        if not c.get("unread") or not last.get("id") or last.get("from") == "me":
            continue
        if state["dm_seen"].get(c["id"]) == last["id"]:
            continue
        state["dm_seen"][c["id"]] = last["id"]
        out.append(_item("dm", id=f"dm:{c['id']}:{last['id']}", convo=c["id"], at=last.get("at"),
                         unread=c.get("unread"), **{"from": c.get("with")}))
    return out


def pending(platform: str, data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    return [i for i in load(platform, data_dir)["items"] if i.get("status") in ("new", "later")]


def mark(platform: str, ids: List[str], status: str, note: Optional[str] = None,
         data_dir: Optional[Path] = None) -> List[str]:
    """Mark items done or later; returns the ids that matched."""
    if status not in ("done", "later", "new"):
        raise ValueError("status is done, later or new")
    state = load(platform, data_dir)
    wanted, hit = set(ids), []
    for i in state["items"]:
        if i.get("id") in wanted:
            i["status"] = status
            if note:
                i["note"] = note
            hit.append(i["id"])
    if hit:
        save(platform, state, data_dir)
    return hit


def answered(platform: str, post_uri: Optional[str], data_dir: Optional[Path] = None) -> None:
    """She replied to this post: the item it came in as is done."""
    if not post_uri:
        return
    state = load(platform, data_dir)
    changed = False
    for i in state["items"]:
        if i.get("uri") == post_uri and i.get("status") != "done":
            i["status"] = "done"
            changed = True
    if changed:
        save(platform, state, data_dir)
