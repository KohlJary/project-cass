"""
Slots through her waking day (plan "Cass plans her own day", phase 4; Cass agreed both, 2026-11-16).

Her waking day, 06:00-22:00, is cut into 90-minute slots (11 of them). A planned item
runs at its slot instead of all at the phase's start: one she gave a time keeps it; one
she gave only a phase is spread across that phase's free slots. One session runs at a
time, so an item whose slot comes while another is running starts when that one ends
(phase_queue.dispatch_due). Night isn't slotted: it stays housekeeping plus anything she
puts there, and overflow from the day doesn't roll into it.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Sequence

DAY_START = time(6, 0)
DAY_END = time(22, 0)
SLOT_MINUTES = 90


def slot_times(day: Optional[datetime] = None) -> List[datetime]:
    """Every slot start of `day`'s waking day: 06:00, 07:30 ... 21:00."""
    day = day or datetime.now()
    t = datetime.combine(day.date(), DAY_START)
    end = datetime.combine(day.date(), DAY_END)
    out = []
    while t < end:
        out.append(t)
        t += timedelta(minutes=SLOT_MINUTES)
    return out


def phase_of(when: datetime) -> str:
    """The phase name a time falls in (the day-phase windows)."""
    from .day_phase import DEFAULT_PHASE_WINDOWS
    for w in DEFAULT_PHASE_WINDOWS:
        if w.contains_hour(when.hour):
            return w.phase.value
    return "night"


def slots_left(now: Optional[datetime] = None, phase: Optional[str] = None) -> List[datetime]:
    """Slots still to come today (a slot already started doesn't count), optionally in one phase."""
    now = now or datetime.now()
    return [s for s in slot_times(now) if s > now and (phase is None or phase_of(s) == phase)]


def _taken(at: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(at)) if at else None
    except ValueError:
        return None


def spread(chosen: Dict[str, List[Dict[str, Any]]], now: Optional[datetime] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Give each day-phase item that has no time the next free slot in its phase.

    A slot is taken by an item already timed within it. When a phase has more items than
    free slots, the extra ones take the phase's last slot and wait their turn there (one
    session at a time); they never spill into the next phase or into the night. Night
    items stay as they are. Returns `chosen`, changed in place."""
    now = now or datetime.now()
    for phase, items in chosen.items():
        free = slots_left(now, phase)
        if not free:
            continue
        timed = [t for t in (_taken(i.get("at")) for i in items) if t]
        open_slots = [s for s in free
                      if not any(s <= t < s + timedelta(minutes=SLOT_MINUTES) for t in timed)]
        for item in items:
            if item.get("at"):
                continue
            slot = open_slots.pop(0) if open_slots else free[-1]
            item["at"] = slot.isoformat(timespec="minutes")
            item["slotted"] = True
    return chosen


def fits_text(chosen: Dict[str, List[Dict[str, Any]]], costs: Dict[str, float], budget_left: float,
              now: Optional[datetime] = None) -> str:
    """What a plan would take, by the menu's own estimates: slots and money. Never a refusal."""
    now = now or datetime.now()
    n_day = sum(len(v) for k, v in chosen.items() if k != "night")
    left = len(slots_left(now))
    cost = sum(costs.get(i["template_id"], 0.0) for v in chosen.values() for i in v)
    parts = [f"{n_day} in the waking day's slots, {left} slot(s) left today"]
    if n_day > left:
        parts.append(f"{n_day - left} will wait their turn after another ends")
    parts.append(f"about ${cost:.2f} by my menu's estimates, of ${budget_left:.2f} left")
    return "This plan: " + "; ".join(parts) + "."


def menu_line(now: Optional[datetime] = None, budget_left: Optional[float] = None,
              costs: Sequence[float] = ()) -> str:
    """The menu's line about slots: how many are left, and when the next one is."""
    now = now or datetime.now()
    left = slots_left(now)
    if not left:
        return "No slots left in today's waking day (06:00-22:00); anything I plan now waits for tonight or tomorrow."
    by_phase: Dict[str, int] = {}
    for s in left:
        by_phase[phase_of(s)] = by_phase.get(phase_of(s), 0) + 1
    line = (f"My waking day runs in {SLOT_MINUTES}-minute slots, one session at a time. Slots left today: "
            f"{len(left)} ({', '.join(f'{p} {n}' for p, n in by_phase.items())}), the next at {left[0]:%H:%M}. "
            "Something I give a time runs then; something I give only a phase takes that phase's next free slot.")
    if costs and budget_left is not None:
        avg = sum(costs) / len(costs)
        line += (f" A slot of something from my menu costs about ${avg:.2f} on average, so filling every slot "
                 f"left would be about ${avg * len(left):.2f} of the ${budget_left:.2f} left.")
    return line
