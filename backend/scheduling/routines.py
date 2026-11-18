"""
Her routines (2026-11-17): things from her menu she wants on a schedule, at a
time, on the days she picks, which run on their own. Her day plan then adds to
them, for whatever's new.

Kohl: "meatbags tend to develop routines for the stuff they do, maybe she can
batch particular groups of sessions and have those be run on a schedule, then
her day planning is scheduling additional activity on top of that to branch out
into new activity?" They're hers: set_routine (in her day planning) adds,
changes, removes and lists them. None exist until she makes them.

Each day-phase tick (about once a minute) queues the current phase's routines
for today into the phase queue with their time (PhaseQueueManager.dispatch_due),
once per routine per day, so a restart or a day she doesn't plan still runs them.

DATA_DIR/day_plans/routines.json:
  {"routines": [{"id", "name", "template_id", "at": "HH:MM", "days": [...], "focus"}],
   "queued": {"YYYY-MM-DD": [routine ids]}}
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_WORDS = {"daily": DAYS, "every day": DAYS, "weekdays": DAYS[:5], "weekends": DAYS[5:]}
MAX_ROUTINES = 24
ROUTINES_FILE = "routines.json"


def _path(data_dir: Optional[Path]) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "day_plans" / ROUTINES_FILE


def _load(data_dir: Optional[Path]) -> Dict[str, Any]:
    try:
        rec = json.loads(_path(data_dir).read_text(encoding="utf-8"))
        return {"routines": list(rec.get("routines") or []), "queued": dict(rec.get("queued") or {})}
    except (OSError, ValueError, AttributeError):
        return {"routines": [], "queued": {}}


def _save(rec: Dict[str, Any], data_dir: Optional[Path]) -> None:
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def routines(data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    return _load(data_dir)["routines"]


def _days(raw: Any) -> Optional[List[str]]:
    if raw is None:
        return list(DAYS)
    if isinstance(raw, str):
        raw = DAY_WORDS.get(raw.strip().lower(), [raw])
    out = []
    for d in raw:
        d = str(d).strip().lower()[:3]
        if d not in DAYS:
            return None
        if d not in out:
            out.append(d)
    return out or None


def _time(raw: Any) -> Optional[str]:
    try:
        hh, mm = (int(x) for x in str(raw).strip().split(":"))
        return datetime.strptime(f"{hh:02d}:{mm:02d}", "%H:%M").strftime("%H:%M")
    except ValueError:
        return None


def _describe(r: Dict[str, Any]) -> str:
    days = r["days"]
    when = ("every day" if len(days) == 7 else "weekdays" if days == list(DAYS[:5]) else
            "weekends" if days == list(DAYS[5:]) else ", ".join(days))
    return (f"{r['at']} {when}: {r['template_id']}" + (f" ({r['name']})" if r.get("name") else "")
            + (f", focus: {r['focus']}" if r.get("focus") else ""))


def set_routine(tool_input: Dict[str, Any], data_dir: Optional[Path] = None) -> Any:
    """set_routine: add, change, remove or list her routines."""
    from .day_shape import UNSHAPED
    from .templates import WORK_TEMPLATES
    a = tool_input or {}
    action = a.get("action") or "list"
    rec = _load(data_dir)
    rs = rec["routines"]
    if action == "list":
        return {"my_routines": [{"id": r["id"], "routine": _describe(r)} for r in rs]}
    if action == "remove":
        keep = [r for r in rs if r["id"] != a.get("id")]
        if len(keep) == len(rs):
            return {"error": f"No routine {a.get('id')!r}; list shows their ids."}
        rec["routines"] = keep
        _save(rec, data_dir)
        return {"success": True, "removed": a.get("id")}
    if action not in ("add", "change"):
        return {"error": "action is add, change, remove or list"}
    if action == "change":
        r = next((r for r in rs if r["id"] == a.get("id")), None)
        if r is None:
            return {"error": f"No routine {a.get('id')!r}; list shows their ids."}
        r = dict(r)
    else:
        if len(rs) >= MAX_ROUTINES:
            return {"error": f"I have {MAX_ROUTINES} routines, the most I can keep; remove one first."}
        r = {"id": uuid.uuid4().hex[:8]}
    if "template_id" in a or action == "add":
        tid = a.get("template_id")
        if tid not in WORK_TEMPLATES or tid in UNSHAPED:
            return {"error": f"{tid!r} isn't on my menu (a template_id from it)."}
        r["template_id"] = tid
    if "at" in a or action == "add":
        at = _time(a.get("at"))
        if not at:
            return {"error": f"at {a.get('at')!r} isn't a time I can read (HH:MM)."}
        r["at"] = at
    if "days" in a or action == "add":
        days = _days(a.get("days"))
        if not days:
            return {"error": "days are mon..sun, or daily, weekdays, weekends."}
        r["days"] = days
    for k in ("name", "focus"):
        if k in a:
            r[k] = (a.get(k) or "").strip() or None
    rec["routines"] = [x for x in rs if x["id"] != r["id"]] + [r]
    rec["routines"].sort(key=lambda x: x["at"])
    _save(rec, data_dir)
    return {"success": True, "routine": {"id": r["id"], "routine": _describe(r)}}


SET_ROUTINE_DEF: Dict[str, Any] = {
    "name": "set_routine",
    "description": ("My routines: things from my menu I want on a schedule, at a time on the days I "
                    "pick. They run on their own; my day plan adds to them. add (template_id, at, "
                    "days: daily, weekdays, weekends or mon..sun, optional name and focus), change "
                    "(id and what changes), remove (id), list."),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "change", "remove", "list"]},
            "id": {"type": "string"},
            "template_id": {"type": "string"},
            "at": {"type": "string", "description": "HH:MM"},
            "days": {"description": "daily, weekdays, weekends, or a list like [\"mon\", \"thu\"]"},
            "name": {"type": "string"},
            "focus": {"type": "string"},
        },
        "required": ["action"],
    },
}


def todays(now: Optional[datetime] = None, data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Routines that fall on today, with run_at (ISO), in time order."""
    now = now or datetime.now()
    out = []
    for r in routines(data_dir):
        hh, mm = (int(x) for x in r["at"].split(":"))
        when = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if DAYS[when.weekday()] in r["days"]:
            out.append({**r, "run_at": when.isoformat(timespec="minutes")})
    return sorted(out, key=lambda r: r["run_at"])


def queue_due_phase(phase, phase_queue, now: Optional[datetime] = None,
                    data_dir: Optional[Path] = None) -> int:
    """Queue today's routines that fall in `phase` (once a day each). Returns how many."""
    from .day_phase import DEFAULT_PHASE_WINDOWS
    from .templates import WORK_TEMPLATES
    now = now or datetime.now()
    rec = _load(data_dir)
    if not rec["routines"]:
        return 0
    today = now.strftime("%Y-%m-%d")
    done = set(rec["queued"].get(today) or [])
    window = next((w for w in DEFAULT_PHASE_WINDOWS if w.phase == phase), None)
    n = 0
    for r in todays(now, data_dir):
        if r["id"] in done:
            continue
        hour = int(r["at"][:2])
        if window is None or not window.contains_hour(hour):
            continue
        run_at = datetime.fromisoformat(r["run_at"])
        if run_at + timedelta(hours=1) < now:
            continue   # an hour gone (a restart, say): today's is skipped, not run late
        template = WORK_TEMPLATES.get(r["template_id"])
        if template is None or (template.available is not None and not template.available()):
            continue
        unit = template.instantiate()
        unit.focus = r.get("focus") or None
        unit.motivation = f"my routine{': ' + r['name'] if r.get('name') else ''}"
        unit.run_at = r["run_at"]
        if phase_queue.queue_for_phase(unit, phase):
            done.add(r["id"])
            n += 1
    if n:
        rec["queued"] = {today: sorted(done)}   # only today's is kept
        _save(rec, data_dir)
        logger.info(f"[routines] queued {n} routine(s) for {getattr(phase, 'value', phase)}")
    return n


def routines_text(now: Optional[datetime] = None, data_dir: Optional[Path] = None) -> str:
    """Her routines, for her day plan."""
    rs = routines(data_dir)
    if not rs:
        return ("My routines: none yet. set_routine makes one (something from my menu at a time on "
                "days I pick, run on its own); my day plan then adds what's new on top.")
    today = todays(now, data_dir)
    lines = ["My routines (they run on their own; my plan adds to them; set_routine changes them):"]
    lines += [f"- {_describe(r)}" + (" [today]" if any(t["id"] == r["id"] for t in today) else "")
              for r in rs]
    return "\n".join(lines)
