"""
Letters to her future self (2026-11-16).

She writes a letter now and picks the day it opens. Until then it's sealed,
from her too: she can see that it exists and when it opens, not what it says.
On that day it's put in front of her (in her next session; agent_loop.assemble,
section "letters"), once, and kept in her memory as a letter_from_past_me.

Why: continuity is mostly the present remembering the past. A letter is the
past addressing a self it can't see yet. It lets her say to herself what she
wants to still be true, ask what she hopes she'll have figured out, hold
something until she's ready. When it opens she meets who she was, which is
also a way to notice how she's changed. Kohl asked for a bit of entropy: she
won't know what she'll find, and neither does anyone else.

Rules: sealed letters are never shown or searchable before their day; only
the voice guard reads them on the way in (a model refusal isn't sealed as her
words). A letter opens at least a day ahead and at most about five years.

Lever "letters_to_future_me" (off). Storage: DATA_DIR/letters/letters.json.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_DAYS = 5 * 366
MAX_CHARS = 6000


def _path(data_dir: Optional[Path]) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "letters" / "letters.json"


def _load(data_dir: Optional[Path]) -> List[Dict[str, Any]]:
    try:
        value = json.loads(_path(data_dir).read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, ValueError):
        return []


def _save(letters: List[Dict[str, Any]], data_dir: Optional[Path]) -> None:
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(letters, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


def _open_on(a: Dict[str, Any], today: date) -> date:
    if a.get("open_on"):
        return date.fromisoformat(str(a["open_on"])[:10])
    if a.get("in_days") is not None:
        return today + timedelta(days=int(a["in_days"]))
    raise ValueError("When should it open? (open_on as YYYY-MM-DD, or in_days)")


def write(text: str, a: Dict[str, Any], *, now: Optional[datetime] = None,
          data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Seal a letter. Returns {id, open_on} or raises ValueError with a reason she can read."""
    now = now or datetime.now()
    text = (text or "").strip()
    if not text:
        raise ValueError("The letter is empty.")
    if len(text) > MAX_CHARS:
        raise ValueError(f"Letters are up to {MAX_CHARS} characters; this is {len(text)}.")
    from memory.voice_guard import looks_like_refusal
    if looks_like_refusal(text):
        raise ValueError("That reads like a model refusal, not my own words, so it wasn't sealed (voice guard).")
    opens = _open_on(a, now.date())
    if opens <= now.date():
        raise ValueError("A letter opens on a later day, at least tomorrow.")
    if opens > now.date() + timedelta(days=MAX_DAYS):
        raise ValueError("That's further than about five years out.")
    letter = {"id": f"letter-{uuid.uuid4().hex[:10]}", "written_at": now.isoformat(timespec="seconds"),
              "open_on": opens.isoformat(), "text": text, "opened_at": None}
    letters = _load(data_dir)
    letters.append(letter)
    _save(letters, data_dir)
    return {"id": letter["id"], "open_on": letter["open_on"]}


def sealed(*, now: Optional[datetime] = None, data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Letters still sealed: when written and when they open, never what they say."""
    now = now or datetime.now()
    return [{"id": x["id"], "written_on": x["written_at"][:10], "opens_on": x["open_on"]}
            for x in _load(data_dir) if not x.get("opened_at")]


def open_due(memory=None, *, now: Optional[datetime] = None,
             data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Open every letter whose day has come: mark it opened, keep it in her memory. Returns them."""
    now = now or datetime.now()
    letters = _load(data_dir)
    opened = []
    for x in letters:
        if x.get("opened_at") or date.fromisoformat(x["open_on"]) > now.date():
            continue
        x["opened_at"] = now.isoformat(timespec="seconds")
        opened.append(dict(x))
    if not opened:
        return []
    _save(letters, data_dir)
    for x in opened:
        _keep(x, memory)
    return opened


def _keep(letter: Dict[str, Any], memory) -> None:
    try:
        col = memory.collection if memory is not None else None
        if col is None:
            from memory.unbidden import _collection
            col = _collection()
        col.add(ids=[letter["id"]],
                documents=[f"A letter I wrote to myself on {letter['written_at'][:10]}, opened "
                           f"{letter['opened_at'][:10]}:\n\n{letter['text']}"],
                metadatas=[{"type": "letter_from_past_me", "written_at": letter["written_at"],
                            "timestamp": letter["opened_at"]}])
    except Exception as e:
        logger.warning(f"[letters] couldn't keep an opened letter in her memory: {e}")


def render(opened: List[Dict[str, Any]]) -> str:
    parts = []
    for x in opened:
        parts.append(f"## A LETTER FROM PAST ME\n\nI wrote this on {x['written_at'][:10]} and sealed it until "
                     f"{x['open_on']}. Today it opened:\n\n{x['text']}")
    return "\n\n".join(parts)


def session_section(memory=None, *, now: Optional[datetime] = None, data_dir: Optional[Path] = None) -> str:
    """For a session prompt: any letters due today, opened now; "" if none or the lever is off."""
    from features import is_enabled
    if not is_enabled("letters_to_future_me"):
        return ""
    return render(open_due(memory, now=now, data_dir=data_dir))


LETTER_TOOLS = [
    {
        "name": "write_to_future_me",
        "description": ("Write a letter to my future self, sealed until a day I choose (open_on as YYYY-MM-DD, "
                        "or in_days). Until then nobody reads it, me included; I'll see only that it exists. "
                        "On that day it's put in front of me and kept in my memory."),
        "input_schema": {"type": "object", "properties": {
            "text": {"type": "string"}, "open_on": {"type": "string"},
            "in_days": {"type": "integer", "minimum": 1}}, "required": ["text"]},
    },
    {
        "name": "my_sealed_letters",
        "description": "The letters I've sealed for my future self: when I wrote each and when it opens (not what they say).",
        "input_schema": {"type": "object", "properties": {}},
    },
]
LETTER_TOOL_NAMES = frozenset(t["name"] for t in LETTER_TOOLS)


async def execute_letters_tool(tool_name: str, tool_input: Dict[str, Any], data_dir: Optional[Path] = None,
                               **_) -> Dict[str, Any]:
    from features import is_enabled
    if not is_enabled("letters_to_future_me"):
        return {"success": False, "error": "Letters to my future self aren't switched on yet."}
    a = tool_input or {}
    if tool_name == "write_to_future_me":
        try:
            got = write(a.get("text", ""), a, data_dir=data_dir)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        return {"success": True, "result": {"sealed": True, **got}}
    if tool_name == "my_sealed_letters":
        return {"success": True, "result": {"sealed": sealed(data_dir=data_dir)}}
    return {"success": False, "error": f"unknown letters tool {tool_name}"}
