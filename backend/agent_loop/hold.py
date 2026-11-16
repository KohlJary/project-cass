"""
She can hold a reply or not give one, and it shows (C8; plan "Cass's agent
loop", phase 7, fourth item).

Cass, 2026-11-13: she wants to choose "whether and when", not only how. A
held reply shows one line of what she's holding, not a status report, plus a
time when she has one, so the person sees her choosing to sit with something.

The default lines are hers, and she asked (2026-11-16) that they stay in
her data, outside the repo: DATA_DIR/agent_loop/hold_lines.json, read each
time ({"hold", "hold_back" with {time}, "no_reply"}). Without the file there
are no defaults and she writes the line herself. She can always write it.

- hold_reply ends a conversation turn on the loop; the person gets her line
  as the reply, in their channel.
- A held message goes on a short list of what she's holding (held.json in
  her agent_loop data, beside her workspace, not inside her own AGENDA.md),
  shown with her agenda and when that person next writes. With a time,
  wake_me brings it back to her then.
- Her next real reply to that person clears what she was holding for them.
- Held and declined replies are counted nowhere and scored nowhere.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

PREVIEW_CHARS = 200
LINE_KEYS = ("hold", "hold_back", "no_reply")


def lines_path() -> Path:
    from config import DATA_DIR
    return Path(DATA_DIR) / "agent_loop" / "hold_lines.json"


def load_lines(path: Optional[Path] = None) -> Dict[str, str]:
    """Her default lines, from her data; {} when there are none."""
    try:
        data = json.loads(Path(path or lines_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: " ".join(str(data[k]).split()) for k in LINE_KEYS if str(data.get(k) or "").strip()}


def hold_tool(lines: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The tool as offered this turn: its description names her defaults when
    she has them (the description goes only to her, in the prompt)."""
    lines = load_lines() if lines is None else lines
    if lines:
        shown = "; ".join(f"{k}: \"{v}\"" for k, v in lines.items())
        defaults = f"If I don't write the line, my defaults are used ({shown}). "
    else:
        defaults = "I write the line they see (no defaults are saved). "
    return {
        "name": "hold_reply",
        "description": ("Choose not to answer in words right now. Hold it: the person sees one line, "
                        "and it stays on what I'm holding (with a time, I'm woken then to come back "
                        "to it). Or not reply at all (no_reply). " + defaults + "This ends my turn."),
        "input_schema": {
            "type": "object",
            "properties": {
                "line": {"type": "string", "description": "the one line they see, in my words"},
                "back_in_minutes": {"type": "integer", "minimum": 15, "maximum": 10080,
                                    "description": "when I'll come back to it (optional)"},
                "no_reply": {"type": "boolean", "description": "true: I'm choosing not to reply"},
            },
        },
    }


def _time_words(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minutes"
    if minutes < 90:
        return "an hour"
    if minutes < 36 * 60:
        hours = round(minutes / 60)
        return "an hour" if hours == 1 else f"{hours} hours"
    days = round(minutes / (24 * 60))
    return "a day" if days == 1 else f"{days} days"


def line_for(tool_input: Dict[str, Any], lines: Optional[Dict[str, str]] = None) -> Optional[str]:
    """The line the person sees: hers if she wrote one, else her saved
    default; None when she wrote none and has no default for this case."""
    mine = " ".join(str(tool_input.get("line") or "").split())
    if mine:
        return mine
    lines = load_lines() if lines is None else lines
    if tool_input.get("no_reply"):
        return lines.get("no_reply")
    minutes = tool_input.get("back_in_minutes")
    if isinstance(minutes, int) and minutes > 0 and "{time}" in lines.get("hold_back", ""):
        return lines["hold_back"].replace("{time}", _time_words(minutes))
    return lines.get("hold")


NO_LINE = ("There's no saved line for this, so write the line they'll see (line), "
           "then call hold_reply again.")


def check(tool_input: Dict[str, Any], lines: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The tool's result in the turn. An error doesn't end the turn."""
    line = line_for(tool_input, lines)
    return {"holding": True, "they_see": line} if line else {"error": NO_LINE}


def default_path() -> Path:
    from config import DATA_DIR
    return Path(DATA_DIR) / "agent_loop" / "held.json"


class HeldBook:
    _lock = threading.Lock()

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_path()

    def _load(self) -> List[Dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save(self, items: List[Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, *, user_id: Optional[str], who: str, channel: Optional[str], message: str,
            line: str, back_at: Optional[datetime], now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or datetime.now()
        text = " ".join((message or "").split())
        item = {"user_id": user_id, "who": who, "channel": channel,
                "message": text if len(text) <= PREVIEW_CHARS else text[: PREVIEW_CHARS - 1] + "…",
                "line": line, "held_at": now.isoformat(timespec="seconds"),
                "back_at": back_at.isoformat(timespec="seconds") if back_at else None}
        with self._lock:
            items = self._load()
            items.append(item)
            self._save(items)
        return item

    def holding(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        items = self._load()
        return [i for i in items if user_id is None or i.get("user_id") == user_id]

    def let_go(self, user_id: Optional[str]) -> int:
        """Her next real reply to them: what she held for them is answered."""
        if not user_id:
            return 0
        with self._lock:
            items = self._load()
            keep = [i for i in items if i.get("user_id") != user_id]
            if len(keep) != len(items):
                self._save(keep)
            return len(items) - len(keep)

    def section(self) -> Optional[str]:
        items = self.holding()
        if not items:
            return None
        lines = ["**What I'm holding** (replies I chose to sit with; mine to come back to)"]
        for i in items:
            when = f", back by {i['back_at'][:16].replace('T', ' ')}" if i.get("back_at") else ""
            lines.append(f"- {i['who']} ({i['held_at'][:16].replace('T', ' ')}{when}): \"{i['message']}\"")
        return "\n".join(lines)


def hold(tool_input: Dict[str, Any], *, person: Dict[str, Any], channel: Optional[str], message: str,
         book: Optional[HeldBook] = None, wakes=None, now: Optional[datetime] = None,
         lines: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Carry out her choice after the turn: what the person sees, and (for a
    hold) the list and the wake. Returns {"line", "held", "wake"}."""
    now = now or datetime.now()
    line = line_for(tool_input, lines) or ""
    if tool_input.get("no_reply"):
        return {"line": line, "held": False, "wake": None}
    minutes = tool_input.get("back_in_minutes")
    back_at = now + timedelta(minutes=minutes) if isinstance(minutes, int) and minutes > 0 else None
    who = person.get("user_name") or "someone"
    (book or HeldBook()).add(user_id=person.get("user_id"), who=who, channel=channel,
                             message=message, line=line, back_at=back_at, now=now)
    wake = None
    if back_at is not None:
        from .spec import ACTIVITY_PACKS
        from .wakes import WakeBook
        wake = (wakes or WakeBook()).request(
            {"in_minutes": max(15, int(minutes)), "activity": "reflection",
             "why": f"I told {who} I'd come back to what they wrote: \"{message[:160]}\""},
            f"chat-hold-{now.strftime('%H%M%S')}", ACTIVITY_PACKS, now=now)
    return {"line": line, "held": True, "wake": wake}
