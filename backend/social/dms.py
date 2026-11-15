"""
Who has said she may remember their DMs (the PeopleDex consent line Cass
and Kohl agreed: public exchanges are kept; DMs only after she asks).
Nobody is on the list until she asks them and records their yes herself
with social_dm_remember; she can take someone off it the same way.

Until someone says yes, a DM with them is read and answered but not kept:
not in the stored session record (agent_loop/loop.py keeps only that a DM
was read), not in the sent log's text, and they aren't added to PeopleDex.

    DATA_DIR/social/<platform>/dm.json   {"remembered": ["handle", ...]}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from social.config import platform_dir

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
