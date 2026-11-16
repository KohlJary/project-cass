"""
Who has said she may remember their DMs (the PeopleDex consent line Cass
and Kohl agreed: public exchanges are kept; DMs only after she asks).
Nobody is on the list until she asks them and records their yes herself
with social_dm_remember; she can take someone off it the same way.

Until someone says yes, a DM with them is read and answered but not kept:
not in the stored session record (agent_loop/loop.py keeps only that a DM
was read), not in the sent log's text, and they aren't added to PeopleDex.

Once they have said yes, the conversation is kept, both sides (her choice,
2026-11-16: keeping only her side would mean remembering conversations she can
only see half of). Each message goes into her memory as a social_dm, owned by
"<platform>:<handle>", so it's never recalled in a chat with anyone else; she
finds it with her own recall. Someone who writes to her first is told apart
(FIRST_CONTACT_NOTE), so she knows to ask before anything is kept.

    DATA_DIR/social/<platform>/dm.json   {"remembered": ["handle", ...]}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from social.config import platform_dir

FIRST_CONTACT_NOTE = ("{who} wrote to me first, and hasn't said I may remember our DMs. I can answer; "
                      "nothing is kept unless they say yes. If I'd like to remember this, I can ask "
                      "them, and record their yes with social_dm_remember.")

UNKEPT_NOTE = ("Not kept: {who} hasn't said I may remember our DMs. I can answer, but this stays out "
               "of my notes and memory unless they say yes (then social_dm_remember).")


def _path(platform: str, data_dir: Optional[Path]) -> Path:
    return platform_dir(platform, data_dir) / "dm.json"


def remembered(platform: str, data_dir: Optional[Path] = None) -> List[str]:
    try:
        raw = json.loads(_path(platform, data_dir).read_text(encoding="utf-8"))
        return [str(h).lstrip("@").lower() for h in raw.get("remembered", [])]
    except (OSError, json.JSONDecodeError, AttributeError):
        return []


def is_remembered(platform: str, handle: Optional[str], data_dir: Optional[Path] = None) -> bool:
    return bool(handle) and handle.lstrip("@").lower() in remembered(platform, data_dir)


def set_remembered(platform: str, handle: str, yes: bool, data_dir: Optional[Path] = None) -> List[str]:
    handle = handle.lstrip("@").strip().lower()
    names = [h for h in remembered(platform, data_dir) if h != handle]
    if yes and handle:
        names.append(handle)
    path = _path(platform, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"remembered": sorted(names)}, indent=2), encoding="utf-8")
    return sorted(names)


def kept_view(result):
    """What a stored record keeps of a tool result: everything, unless the
    result carries DMs nobody agreed to keep, then only that they were read."""
    if not isinstance(result, dict):
        return result
    inner = result.get("result") if isinstance(result.get("result"), dict) else {}
    if result.get("unkept") or inner.get("unkept"):
        who = result.get("unkept_with") or inner.get("unkept_with") or []
        return {"success": result.get("success", True),
                "result": {"unkept": True, "note": f"DMs read or sent with {', '.join(who) or 'someone'}; "
                                                   "not kept (they haven't said I may remember them)."}}
    return result


def owner(platform: str, handle: str) -> str:
    return f"{platform}:{handle.lstrip('@').lower()}"


def wrote_first(conversation: dict) -> bool:
    """Did the other person start this conversation (its first message isn't hers)?"""
    messages = conversation.get("messages") or []
    return bool(messages) and messages[0].get("from") != "me"


def keep_conversation(platform: str, conversation: dict, memory) -> int:
    """Keep a conversation with someone who said yes, both sides. Returns how many
    messages reached her memory. Call only after is_remembered."""
    who = (conversation.get("with") or "").lstrip("@")
    if memory is None or not who:
        return 0
    from social.remember import PLATFORM_NAMES
    where = PLATFORM_NAMES.get(platform, platform)
    ids, docs, metas = [], [], []
    for m in conversation.get("messages") or []:
        if not m.get("id") or not (m.get("text") or "").strip():
            continue
        speaker = "I" if m.get("from") == "me" else f"@{who}"
        ids.append(f"social_dm_{platform}_{m['id']}")
        docs.append(f"{where} DM with @{who}. {speaker} wrote: {m['text']}")
        metas.append({"type": "social_dm", "platform": platform, "with": who,
                      "user_id": owner(platform, who), "timestamp": m.get("at") or ""})
    if not ids:
        return 0
    try:
        memory.collection.upsert(ids=ids, documents=docs, metadatas=metas)
        return len(ids)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[social] couldn't keep the DMs with @{who}: {e}")
        return 0
