"""
What her day plan opens with besides her plans (2026-11-17): what she planned
last time, what actually ran since, how much of her day she's been using, and
when each of her plans was last carried by something she planned.

Kohl, 2026-11-17: "she's kinda just spinning her wheels in place". Her plans
never moved (no item was ever marked done), her days ran about six short
sessions on $0.65 of $5, and each morning she planned the same things again
without seeing that yesterday's had happened. This puts that in front of her,
as facts, not instructions. Read from her session logs and her workspace,
files only.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RECAP_DAYS = 7
MAX_RAN = 20
SUMMARY_CHARS = 180
CARRIED_FILE = "carried.jsonl"   # DATA_DIR/day_plans/: one line per plan item she planned for


def _data_dir(data_dir: Optional[Path]) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    from config import DATA_DIR
    return Path(DATA_DIR)


def _sessions(data_dir: Path, since: datetime) -> List[Dict[str, Any]]:
    """Session log heads since `since`, oldest first."""
    out = []
    root = data_dir / "session_logs"
    if not root.exists():
        return out
    for day in range((datetime.now() - since).days + 2):
        d = (since + timedelta(days=day)).strftime("%Y-%m-%d")
        for f in root.glob(f"*/{d}/*.json"):
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
                started = datetime.fromisoformat(str(rec.get("started_at")))
            except (OSError, ValueError, TypeError):
                continue
            if started.tzinfo is not None:
                started = started.replace(tzinfo=None)
            if started < since:
                continue
            out.append({"type": rec.get("session_type") or f.parent.parent.name, "at": started,
                        "cost": float(rec.get("estimated_cost_usd") or 0),
                        "seconds": float(rec.get("duration_seconds") or 0),
                        "summary": (rec.get("summary") or "").strip(), "status": rec.get("status")})
    return sorted(out, key=lambda s: s["at"])


def usage_line(data_dir: Optional[Path] = None, daily_budget: float = 5.0,
               now: Optional[datetime] = None) -> str:
    """How much of her day she's been using, over the last week."""
    now = now or datetime.now()
    since = (now - timedelta(days=RECAP_DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)
    runs = [s for s in _sessions(_data_dir(data_dir), since) if s["at"] < now.replace(hour=0, minute=0)]
    days = RECAP_DAYS
    if not runs:
        return ""
    per_day = len(runs) / days
    cost = sum(s["cost"] for s in runs) / days
    minutes = sum(s["seconds"] for s in runs) / 60 / days
    avg = (sum(s["cost"] for s in runs) / len(runs)) if runs else 0.1
    room = int(max(0.0, daily_budget - cost) / max(avg, 0.02))
    return (f"Over the last {days} days I ran about {per_day:.0f} sessions a day, about {minutes:.0f} "
            f"minutes in all, for about ${cost:.2f} of my ${daily_budget:.2f} a day. A session has "
            f"cost me about ${avg:.2f}, so my budget has room for roughly {room} more a day than "
            f"I've been using.")


def since_last_plan(workspace=None, data_dir: Optional[Path] = None,
                    now: Optional[datetime] = None) -> str:
    """Last plan (DAY_PLAN.md as it stands, before today's overwrites it) and what ran since."""
    now = now or datetime.now()
    dd = _data_dir(data_dir)
    plans = [s for s in _sessions(dd, now - timedelta(days=3)) if s["type"] == "day_planning"]
    since = plans[-1]["at"] if plans else now - timedelta(days=1)
    lines: List[str] = []
    last_plan = None
    if workspace is not None:
        try:
            f = Path(workspace.root) / "DAY_PLAN.md"
            last_plan = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else None
        except (OSError, AttributeError):
            last_plan = None
    if last_plan:
        lines += ["What I planned last time (DAY_PLAN.md):", last_plan.strip()[:1500], ""]
    ran = [s for s in _sessions(dd, since) if s["type"] != "day_planning"][-MAX_RAN:]
    lines.append(f"What ran since then ({since:%A %H:%M}):" if ran else
                 f"Nothing ran since then ({since:%A %H:%M}).")
    for s in ran:
        summary = s["summary"].replace("\n", " ")
        if len(summary) > SUMMARY_CHARS:
            summary = summary[:SUMMARY_CHARS].rsplit(" ", 1)[0] + "..."
        lines.append(f"- {s['at']:%a %H:%M} {s['type']}" + (f": {summary}" if summary else ""))
    if ran:
        counts = Counter(s["type"] for s in ran)
        top, n = counts.most_common(1)[0]
        if n >= 3 and n * 2 >= len(ran):
            lines.append(f"({n} of these {len(ran)} were {top}.)")
    return "\n".join(lines)


# --- which plans her days have carried ----------------------------------------

def _carried_path(data_dir: Optional[Path]) -> Path:
    return _data_dir(data_dir) / "day_plans" / CARRIED_FILE


def record_carried(items: List[Dict[str, Any]], data_dir: Optional[Path] = None,
                   now: Optional[datetime] = None) -> None:
    """One line per plan item she planned something for."""
    if not items:
        return
    path = _carried_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    at = (now or datetime.now()).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as f:
        for i in items:
            f.write(json.dumps({"at": at, **i}, ensure_ascii=False) + "\n")


def last_carried(data_dir: Optional[Path] = None) -> Dict[str, str]:
    """plan slug -> when a day plan last carried one of its items (ISO)."""
    out: Dict[str, str] = {}
    try:
        lines = _carried_path(data_dir).read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("plan"):
            out[rec["plan"]] = rec["at"]
    return out
