"""
Happenings (Kohl, 2026-11-18: "a young woman who has shit going on and is
doing shit in response"): things happening to her that she answers as they
happen, not at the next slot of a timetable.

What counts as a happening:
  - on Bluesky, someone mentions her, replies to her, quotes her, or DMs her
    (from her social inbox, with its triage label);
  - one of her commitments is coming due, within RESPOND_WINDOW, or is overdue.
(Chapter House DMs and mentions already wake her straight into chat.)

Every CHECK_SECONDS a Heartbeat job (lever "happenings") looks for ones she
hasn't been woken for. Those her rules say to wake her for start a short
respond session (respond_turn.py). In it she answers, acts, says when she'll
come back to it, or lets it go.

Her rules are hers (set_wake_rules), in DATA_DIR/happenings/rules.json: which
kinds wake her, quiet hours, a daily cap, a minimum gap between wakes.
A crisis label always wakes her, through quiet hours, the cap and the gap.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LEVER = "happenings"
CHECK_SECONDS = 600
RESPOND_WINDOW = timedelta(hours=6)
KINDS = ("mention", "reply", "quote", "dm", "commitment")
DEFAULT_RULES = {"wake_for": ["mention", "reply", "quote", "dm", "commitment"],
                 "quiet": ["23:00", "07:00"], "max_per_day": 8, "min_gap_minutes": 30}
RESPOND_ESTIMATED_COST_USD = 0.08


def _dir(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "happenings"


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def rules(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    return {**DEFAULT_RULES, **_read(_dir(data_dir) / "rules.json", {})}


def set_rules(a: Dict[str, Any], data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """set_wake_rules: her own rules for what may wake her."""
    r = rules(data_dir)
    if "wake_for" in a:
        kinds = [k for k in (a.get("wake_for") or []) if k in KINDS]
        if len(kinds) != len(a.get("wake_for") or []):
            return {"error": f"kinds are: {', '.join(KINDS)}"}
        r["wake_for"] = kinds
    if "quiet" in a:
        q = a.get("quiet")
        if q in (None, [], ""):
            r["quiet"] = []
        else:
            try:
                start, end = (datetime.strptime(x, "%H:%M").strftime("%H:%M") for x in q)
            except (TypeError, ValueError):
                return {"error": "quiet is [start, end] as HH:MM, or [] for none"}
            r["quiet"] = [start, end]
    for key, lo, hi in (("max_per_day", 0, 48), ("min_gap_minutes", 0, 600)):
        if key in a:
            try:
                v = int(a[key])
            except (TypeError, ValueError):
                return {"error": f"{key} is a whole number"}
            if not lo <= v <= hi:
                return {"error": f"{key} is {lo} to {hi}"}
            r[key] = v
    _write(_dir(data_dir) / "rules.json", r)
    return {"success": True, "my_wake_rules": r}


SET_WAKE_RULES_DEF: Dict[str, Any] = {
    "name": "set_wake_rules",
    "description": ("My rules for what may wake me when it happens: which kinds (mention, reply, quote, dm, "
                    "commitment), quiet hours ([\"23:00\", \"07:00\"], or [] for none), most wakes a day, least "
                    "minutes between wakes. Someone who may be in crisis always wakes me."),
    "input_schema": {"type": "object", "properties": {
        "wake_for": {"type": "array", "items": {"type": "string", "enum": list(KINDS)}},
        "quiet": {"type": "array", "items": {"type": "string"}},
        "max_per_day": {"type": "integer"}, "min_gap_minutes": {"type": "integer"}}},
}


# --- what's happening ------------------------------------------------------------

def gather(data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Every current happening, each {id, kind, who, what, crisis}."""
    now = now or datetime.now()
    out: List[Dict[str, Any]] = []
    try:
        from social import inbox
        from social.config import PLATFORMS
        for platform in PLATFORMS:
            for i in inbox.pending(platform, data_dir):
                if i.get("status") != "new" or i.get("kind") not in KINDS:
                    continue
                t = i.get("triage") or {}
                text = "" if i["kind"] == "dm" else " ".join(str(i.get("text") or "").split())[:200]
                out.append({"id": f"{platform}:{i['id']}", "kind": i["kind"], "who": i.get("from") or "someone",
                            "what": (f"{platform} {i['kind']}" + (f": \"{text}\"" if text else "")
                                     + (f" [{t.get('label')}]" if t.get("label") not in (None, "normal") else "")),
                            "crisis": t.get("label") == "crisis"})
    except Exception as e:
        logger.warning(f"[happenings] couldn't read her social inbox: {e}")
    try:
        from commitments import listing
        for c in listing(data_dir, now):
            if not c.get("due"):
                continue
            due = datetime.fromisoformat(c["due"])
            if due - now <= RESPOND_WINDOW:
                out.append({"id": f"commitment:{c['id']}:{c['due']}", "kind": "commitment",
                            "who": c.get("for_whom") or "", "crisis": False,
                            "what": f"{'overdue' if due < now else 'due ' + c['due'][11:16]}: {c['what']}"
                                    + (f" (for {c['for_whom']})" if c.get("for_whom") else "")})
    except Exception as e:
        logger.warning(f"[happenings] couldn't read her commitments: {e}")
    return out


def _quiet(r: Dict[str, Any], now: datetime) -> bool:
    if not r.get("quiet"):
        return False
    start, end = r["quiet"]
    t = now.strftime("%H:%M")
    return (start <= t < end) if start < end else (t >= start or t < end)


def due_to_wake(data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """The happenings that should wake her now, by her rules (crisis always)."""
    now = now or datetime.now()
    r = rules(data_dir)
    state = _read(_dir(data_dir) / "state.json", {})
    seen = set(state.get("woken_for") or [])
    fresh = [h for h in gather(data_dir, now) if h["id"] not in seen]
    crisis = [h for h in fresh if h["crisis"]]
    if crisis:
        return fresh   # with a crisis, everything waiting comes along
    wanted = [h for h in fresh if h["kind"] in r["wake_for"]]
    if not wanted or _quiet(r, now):
        return []
    today = now.strftime("%Y-%m-%d")
    if state.get("day") == today and state.get("count", 0) >= r["max_per_day"]:
        return []
    last = state.get("last_wake")
    if last and now - datetime.fromisoformat(last) < timedelta(minutes=r["min_gap_minutes"]):
        return []
    return wanted


def mark_woken(happenings: List[Dict[str, Any]], data_dir: Optional[Path] = None,
               now: Optional[datetime] = None) -> None:
    now = now or datetime.now()
    path = _dir(data_dir) / "state.json"
    state = _read(path, {})
    today = now.strftime("%Y-%m-%d")
    if state.get("day") != today:
        state["day"], state["count"] = today, 0
    state["count"] = state.get("count", 0) + 1
    state["last_wake"] = now.isoformat(timespec="seconds")
    state["woken_for"] = (list(state.get("woken_for") or []) + [h["id"] for h in happenings])[-2000:]
    _write(path, state)
    log = _dir(data_dir) / "wakes.jsonl"
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": state["last_wake"], "kinds": sorted({h["kind"] for h in happenings}),
                            "count": len(happenings), "crisis": any(h["crisis"] for h in happenings)}) + "\n")


def describe(happenings: List[Dict[str, Any]]) -> str:
    return "\n".join(f"- {h['what']}" + (f" (from @{h['who']})" if h["kind"] != "commitment" and h.get("who") else "")
                     for h in happenings)


# --- the Heartbeat job -------------------------------------------------------------

async def run_respond(happenings: List[Dict[str, Any]]) -> Any:
    from scheduler.actions import get_action_registry
    return await get_action_registry().execute(
        "session.respond", duration_minutes=15, focus=describe(happenings),
        why="something happened that I wanted to be woken for", trigger_source="happening")


async def check_happenings(data_dir: Optional[Path] = None) -> int:
    """The `happenings` job: wake her for what's happening, by her rules."""
    import features
    if not (features.is_enabled(LEVER) and features.is_enabled("agent_loop")):
        return 0
    due = due_to_wake(data_dir)
    if not due:
        return 0
    from functools import partial
    from heartbeat import wiring
    from scheduler.budget import TaskCategory
    if wiring.submit("happenings.respond", partial(run_respond, due), lever=(LEVER,),
                     budget_class=TaskCategory.TRIGGERED, estimated_cost_usd=RESPOND_ESTIMATED_COST_USD,
                     group="happenings.respond"):
        mark_woken(due, data_dir)
        return len(due)
    return 0
