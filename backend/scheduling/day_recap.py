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
                        "summary": (rec.get("summary") or "").strip(), "status": rec.get("status"),
                        "pick_up_next": rec.get("pick_up_next"), "at_cap": bool(rec.get("summarized_at_cap"))})
    return sorted(out, key=lambda s: s["at"])


def usage_line(data_dir: Optional[Path] = None, daily_budget: Optional[float] = None,
               now: Optional[datetime] = None) -> str:
    """How much of her day she's been using, over the last week.

    The cap is the one the budget gate uses (DAILY_BUDGET_USD, as main_sdk reads it).
    """
    if daily_budget is None:
        import os
        daily_budget = float(os.getenv("DAILY_BUDGET_USD", "5.0"))
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


def _refused(since: datetime) -> List[Dict[str, Any]]:
    from heartbeat.runlog import RunLog
    return RunLog().refused_since(since)


def _sent(since: datetime, data_dir: Path) -> List[Dict[str, Any]]:
    """What she sent out since `since`: reach-outs to Kohl, and her social posts and replies."""
    out: List[Dict[str, Any]] = []
    from reach_out import ReachOutManager, find_primary_partner
    from database import get_daemon_id
    daemon_id = get_daemon_id()
    partner = find_primary_partner(daemon_id)
    for r in (ReachOutManager(daemon_id).history(partner, limit=50) if partner else []):
        try:
            at = datetime.fromisoformat(str(r.created_at)).replace(tzinfo=None)
        except ValueError:
            continue
        if at >= since:
            via = ", ".join(sorted({str(v.get("channel")) for v in (r.delivered_via or []) if v.get("ok", True)}))
            out.append({"at": at, "what": f"to Kohl ({r.kind})" + (f" via {via}" if via else "")
                        + ("" if r.delivered else f", NOT delivered: {r.error}"), "text": r.body})
    from social.limits import posted
    for rec in posted("bluesky", data_dir, since=since):
        if rec.get("kind") in ("post", "reply"):
            out.append({"at": datetime.fromisoformat(rec["at"]), "what": f"Bluesky {rec['kind']}",
                        "text": rec.get("text", "")})
    return sorted(out, key=lambda r: r["at"])


def since_last_plan(workspace=None, data_dir: Optional[Path] = None,
                    now: Optional[datetime] = None, refused=None, sent=None, didnt=None) -> str:
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
        lines.append(f"- {s['at']:%a %H:%M} {s['type']}" + (" (ran out of steps; summary written at the cap)" if s.get("at_cap") else "")
                     + (f": {summary}" if summary else ""))
    # Her ask (2026-11-18): planned work the gate refused is named, with why,
    # not just absent; and what she actually sent, so narration and reality meet.
    try:
        refusals = (refused or _refused)(since)
    except Exception as e:
        logger.warning(f"[day_recap] couldn't read refusals: {e}")
        refusals = []
    if refusals:
        lines.append("Planned but refused (not run):")
        for r in refusals:
            at = str(r.get("started_at") or "")[11:16]
            name = str(r.get("work_name") or "").replace("phase.", "")
            lines.append(f"- {at} {name}: {r.get('error') or 'refused'}")
    try:
        sends = (sent or (lambda s: _sent(s, dd)))(since)
    except Exception as e:
        logger.warning(f"[day_recap] couldn't read what she sent: {e}")
        sends = None
    if sends is not None:
        if sends:
            lines.append("What I actually sent out since then:")
            for s in sends:
                text = (s.get("text") or "").replace("\n", " ")
                if len(text) > SUMMARY_CHARS:
                    text = text[:SUMMARY_CHARS].rsplit(" ", 1)[0] + "..."
                lines.append(f"- {s['at']:%a %H:%M} {s['what']}" + (f": \"{text}\"" if text else ""))
        else:
            lines.append("I sent nothing out since then (no message to Kohl, no post).")
    try:   # what didn't go out, and why (her ask, 2026-11-18; reach_out.note_decision)
        from reach_out import decisions_since, _OUTCOME_WORDS, _TRIGGER_WORDS
        held = (didnt or decisions_since)(since)
    except Exception as e:
        logger.warning(f"[day_recap] couldn't read what didn't go out: {e}")
        held = []
    if held:
        lines.append("What didn't go out since then:")
        for d in held:
            why = f": {d['reason']}" if d.get("reason") else ""
            lines.append(f"- {datetime.fromisoformat(d['at']):%a %H:%M} "
                         f"{_TRIGGER_WORDS.get(d.get('trigger'), d.get('trigger'))}, "
                         f"{_OUTCOME_WORDS.get(d.get('outcome'), d.get('outcome'))}{why}")
    try:   # what she's promised that's pressing (commitments.py)
        from commitments import lines as commitment_lines
        promised = commitment_lines(dd, now)
    except Exception as e:
        logger.warning(f"[day_recap] couldn't read her commitments: {e}")
        promised = []
    if promised:
        lines.append("What I've promised that's pressing:")
        lines += promised
    left = [s for s in ran if s.get("pick_up_next")]
    if left:   # what she left herself (session_complete pick_up_next, or written at the cap)
        lines.append("What I said I'd pick up next:")
        lines += [f"- from {s['type']} ({s['at']:%a %H:%M}): {s['pick_up_next']}" for s in left]
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
