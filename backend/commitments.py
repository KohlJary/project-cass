"""
Her commitments (Kohl, 2026-11-18: "a young woman who has shit going on and
is doing shit in response"): what she said she'd do, for whom, by when.

When she tells someone she'll do something, in chat or in a session, she
keeps it here. As it nears, it comes up: in her day plan's recap, as a
happening that can wake her (happenings.py), in Kohl's record. Missed ones
show as missed. Her word, kept visible, and her follow-through with it.

DATA_DIR/commitments/commitments.json: [{id, what, for_whom, due, status,
created, done_at, note}]. status: open | done | dropped.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STATUSES = ("open", "done", "dropped")
SOON = timedelta(days=2)


def _path(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "commitments" / "commitments.json"


def load(data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    try:
        return json.loads(_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(items: List[Dict[str, Any]], data_dir: Optional[Path]) -> None:
    p = _path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _due(raw: Any, now: datetime) -> Optional[str]:
    """An ISO due time from 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM', 'today', 'tomorrow' or 'in N days'."""
    s = str(raw or "").strip().lower()
    if not s:
        return None
    if s == "today":
        return now.replace(hour=23, minute=59, second=0, microsecond=0).isoformat(timespec="minutes")
    if s == "tomorrow":
        return (now + timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0).isoformat(timespec="minutes")
    if s.startswith("in ") and s.endswith(("day", "days")):
        try:
            n = int(s.split()[1])
            return (now + timedelta(days=n)).replace(hour=23, minute=59, second=0, microsecond=0).isoformat(timespec="minutes")
        except (ValueError, IndexError):
            return None
    try:
        t = datetime.fromisoformat(s.upper() if "t" in s else s)
    except ValueError:
        return None
    if len(s) == 10:
        t = t.replace(hour=23, minute=59)
    return t.isoformat(timespec="minutes")


def state_of(c: Dict[str, Any], now: Optional[datetime] = None) -> str:
    """open, due soon, overdue, done or dropped."""
    if c["status"] != "open":
        return c["status"]
    if not c.get("due"):
        return "open"
    now = now or datetime.now()
    due = datetime.fromisoformat(c["due"])
    if due < now:
        return "overdue"
    return "due soon" if due - now <= SOON else "open"


def add(what: str, for_whom: str = "", due: Any = None, note: str = "",
        data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now()
    if not (what or "").strip():
        return {"error": "what did I say I'd do?"}
    when = _due(due, now)
    if due and not when:
        return {"error": f"{due!r} isn't a date I can read (YYYY-MM-DD, today, tomorrow, in 3 days)"}
    item = {"id": uuid.uuid4().hex[:8], "what": what.strip(), "for_whom": (for_whom or "").strip(),
            "due": when, "status": "open", "created": now.isoformat(timespec="seconds"),
            "done_at": None, "note": (note or "").strip()}
    items = load(data_dir)
    items.append(item)
    _save(items, data_dir)
    return {"success": True, "commitment": item}


def _find(cid: str, items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return next((c for c in items if c["id"] == (cid or "").strip()), None)


def set_status(cid: str, status: str, note: str = "", data_dir: Optional[Path] = None,
               now: Optional[datetime] = None) -> Dict[str, Any]:
    if status not in ("done", "dropped"):
        return {"error": "a commitment is done or dropped"}
    items = load(data_dir)
    c = _find(cid, items)
    if c is None:
        return {"error": f"no commitment {cid!r}; list shows their ids"}
    if status == "dropped" and not (note or "").strip():
        return {"error": "dropping one says why, and whether I've told them"}
    c["status"], c["done_at"] = status, (now or datetime.now()).isoformat(timespec="seconds")
    if note:
        c["note"] = note.strip()
    _save(items, data_dir)
    return {"success": True, "commitment": c}


def change(cid: str, due: Any = None, what: Optional[str] = None, note: Optional[str] = None,
           data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    items = load(data_dir)
    c = _find(cid, items)
    if c is None:
        return {"error": f"no commitment {cid!r}"}
    if due:
        when = _due(due, now or datetime.now())
        if not when:
            return {"error": f"{due!r} isn't a date I can read"}
        c["due"] = when
    if what:
        c["what"] = what.strip()
    if note is not None:
        c["note"] = note.strip()
    _save(items, data_dir)
    return {"success": True, "commitment": c}


def listing(data_dir: Optional[Path] = None, now: Optional[datetime] = None,
            include_closed: bool = False) -> List[Dict[str, Any]]:
    now = now or datetime.now()
    out = [{**c, "state": state_of(c, now)} for c in load(data_dir)
           if include_closed or c["status"] == "open"]
    return sorted(out, key=lambda c: (c.get("due") or "9999", c["created"]))


def pressing(data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Open commitments that are overdue or due soon."""
    return [c for c in listing(data_dir, now) if c["state"] in ("overdue", "due soon")]


def lines(data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> List[str]:
    """For her recap: what she's promised that's pressing, in a line each."""
    out = []
    for c in pressing(data_dir, now):
        who = f" for {c['for_whom']}" if c["for_whom"] else ""
        out.append(f"- [{c['id']}] {c['state'].upper()}: {c['what']}{who} (due {c['due'].replace('T', ' ')})")
    return out


COMMITMENT_TOOLS = [{
    "name": "commitment",
    "description": ("What I've said I'll do, for whom, by when. When I tell someone I'll do something, I keep it "
                    "here, and it comes back to me as it nears; missed ones show as missed. action: add (what, "
                    "for_whom, due: YYYY-MM-DD, today, tomorrow, in N days), list (closed too: all), done (id, "
                    "note), drop (id, why: and whether I've told them), change (id, due/what/note)."),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "list", "done", "drop", "change"]},
            "id": {"type": "string"}, "what": {"type": "string"}, "for_whom": {"type": "string"},
            "due": {"type": "string"}, "note": {"type": "string"}, "all": {"type": "boolean"},
        },
        "required": ["action"],
    },
}]


async def execute_commitment_tool(tool_name: str, tool_input: Dict[str, Any], **_) -> Dict[str, Any]:
    a = tool_input or {}
    action = a.get("action")
    if action == "add":
        out = add(a.get("what") or "", a.get("for_whom") or "", a.get("due"), a.get("note") or "")
    elif action == "list":
        out = {"commitments": listing(include_closed=bool(a.get("all")))}
    elif action == "done":
        out = set_status(a.get("id") or "", "done", a.get("note") or "")
    elif action == "drop":
        out = set_status(a.get("id") or "", "dropped", a.get("note") or "")
    elif action == "change":
        out = change(a.get("id") or "", a.get("due"), a.get("what"), a.get("note"))
    else:
        out = {"error": "action is add, list, done, drop or change"}
    if "error" in out:
        return {"success": False, "error": out["error"]}
    return {"success": True, "result": out}
