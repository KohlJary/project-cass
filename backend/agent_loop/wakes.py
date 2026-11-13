"""
wake_me: she asks to be woken later to continue something (phase 4 of
docs/design/agent-loop.md; Heartbeat, #62).

A request is stored in DATA_DIR/agent_loop/wakes.json, so a restart keeps
it. The Heartbeat job `agent_loop_wakes` looks once a minute; for each
request that's due it submits one session run as its own Heartbeat work, with
a budget class, so the budget gate and the run log see it like any other
autonomous session. The session's "Why now" is her own reason.

Limits (Daedalus's, not hers; change them when she asks): at least 15
minutes ahead, at most 7 days, at most 3 pending at once.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MIN_MINUTES = 15
MAX_MINUTES = 7 * 24 * 60
MAX_PENDING = 3
WAKE_SESSION_MINUTES = 30
WAKE_ESTIMATED_COST_USD = 0.50

PENDING, STARTED, DONE, FAILED, CANCELLED = "pending", "started", "done", "failed", "cancelled"


def wake_tool(activities) -> Dict[str, Any]:
    return {
        "name": "wake_me",
        "description": ("Ask to be woken later to continue something. I'll wake into a session "
                        "with my reason as the why-now, and my agenda will be there. At least 15 "
                        "minutes ahead, at most 7 days, 3 pending at a time."),
        "input_schema": {"type": "object", "properties": {
            "in_minutes": {"type": "integer", "minimum": MIN_MINUTES, "maximum": MAX_MINUTES,
                           "description": "How long from now, in minutes (60 = an hour, 1440 = a day)"},
            "why": {"type": "string", "description": "What I want to pick up, in my words"},
            "activity": {"type": "string", "enum": sorted(activities),
                         "description": "What kind of session to wake into (default: reflection)"},
        }, "required": ["in_minutes", "why"]},
    }


def default_path() -> Path:
    from config import DATA_DIR
    return Path(DATA_DIR) / "agent_loop" / "wakes.json"


class WakeBook:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_path()

    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[wake_me] couldn't read {self.path}: {e}")
            return []

    def _save(self, items: List[Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def all(self) -> List[Dict[str, Any]]:
        return self._load()

    def pending(self) -> List[Dict[str, Any]]:
        return [w for w in self._load() if w.get("status") == PENDING]

    def request(self, tool_input: Dict[str, Any], session_id: str, activities,
                now: Optional[datetime] = None) -> Any:
        """The wake_me tool. Returns text, or {"error": ...}."""
        now = now or datetime.now()
        try:
            minutes = int(tool_input.get("in_minutes"))
        except (TypeError, ValueError):
            return {"error": "in_minutes must be a whole number of minutes"}
        if not MIN_MINUTES <= minutes <= MAX_MINUTES:
            return {"error": f"in_minutes must be between {MIN_MINUTES} and {MAX_MINUTES} (7 days)"}
        why = str(tool_input.get("why") or "").strip()
        if not why:
            return {"error": "why is needed: what I want to pick up"}
        activity = str(tool_input.get("activity") or "reflection")
        if activity not in activities:
            return {"error": f"activity must be one of: {', '.join(sorted(activities))}"}
        items = self._load()
        pending = [w for w in items if w.get("status") == PENDING]
        if len(pending) >= MAX_PENDING:
            whens = ", ".join(w["at"] for w in pending)
            return {"error": f"I already have {MAX_PENDING} wakes pending ({whens}); "
                             "one has to pass first, or put this in my agenda"}
        at = now + timedelta(minutes=minutes)
        items.append({"id": uuid.uuid4().hex[:8], "at": at.isoformat(timespec="seconds"),
                      "why": why[:500], "activity": activity, "asked_in": session_id,
                      "asked_at": now.isoformat(timespec="seconds"), "status": PENDING})
        self._save(items)
        return f"I'll be woken at {at.strftime('%A %H:%M')} ({activity}): {why[:200]}"

    def take_due(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Due pending wakes, marked started (so a second look can't run them twice)."""
        now = now or datetime.now()
        items = self._load()
        due, changed = [], False
        for w in items:
            if w.get("status") != PENDING:
                continue
            try:
                at = datetime.fromisoformat(w["at"])
            except (KeyError, ValueError):
                w["status"], w["result"], changed = FAILED, "unreadable time", True
                continue
            if at <= now:
                w["status"] = STARTED
                w["started_at"] = now.isoformat(timespec="seconds")
                due.append(dict(w))
                changed = True
        if changed:
            self._save(items)
        return due

    def release(self, wake_id: str) -> None:
        """Back to pending (it couldn't be started this time)."""
        items = self._load()
        for w in items:
            if w.get("id") == wake_id:
                w["status"] = PENDING
                w.pop("started_at", None)
        self._save(items)

    def finish(self, wake_id: str, status: str, result: str = "") -> None:
        items = self._load()
        for w in items:
            if w.get("id") == wake_id:
                w["status"] = status
                w["result"] = result[:500]
                w["finished_at"] = datetime.now().isoformat(timespec="seconds")
        self._save(items)


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def wake_why(w: Dict[str, Any]) -> str:
    return f"I asked to be woken now: {w.get('why')}"


async def run_wake(w: Dict[str, Any], book: Optional[WakeBook] = None) -> Any:
    """One woken session, through the action registry like any session."""
    book = book or WakeBook()
    from scheduler.actions import get_action_registry
    try:
        result = await get_action_registry().execute(
            f"session.{w['activity']}", duration_minutes=WAKE_SESSION_MINUTES,
            why=wake_why(w), trigger_source="wake")
    except Exception as e:
        book.finish(w["id"], FAILED, f"{type(e).__name__}: {e}")
        raise
    ok = bool(getattr(result, "success", False))
    book.finish(w["id"], DONE if ok else FAILED, getattr(result, "message", "") or "")
    return result


async def check_wakes(book: Optional[WakeBook] = None) -> int:
    """The `agent_loop_wakes` job: submit each due wake as its own run."""
    import features
    if not features.is_enabled("agent_loop"):
        return 0
    from functools import partial
    from heartbeat import wiring
    from scheduler.budget import TaskCategory
    book = book or WakeBook()
    due = book.take_due()
    for w in due:
        submitted = wiring.submit(f"agent_loop.wake.{w['activity']}", partial(run_wake, w, book),
                                  lever=("agent_loop",), budget_class=TaskCategory.REFLECTION,
                                  estimated_cost_usd=WAKE_ESTIMATED_COST_USD,
                                  group="agent_loop.wake")
        if not submitted:  # Heartbeat stopped: leave it for the next look
            book.release(w["id"])
    return len(due)


def heartbeat_running() -> bool:
    try:
        from heartbeat import wiring
        return wiring.get_heartbeat() is not None
    except Exception:
        return False
