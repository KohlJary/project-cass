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


# Starting a session now, from a conversation (start_session; Kohl, 2026-11-18: "she
# needs to be able to kick off sessions from chat"). The same book and the same budgeted
# run as wake_me, due now; one at a time, a few a day.
START_LEVER = "start_sessions"
STARTS_PER_DAY = 6
# Kinds that don't count toward the day's starts (Kohl, 2026-11-18: listening doesn't).
UNCOUNTED = frozenset({"listening"})
START_MINUTES = (15, 60)


def start_tool(activities) -> Dict[str, Any]:
    return {
        "name": "start_session",
        "description": ("Start one of my sessions now, from this conversation: when I want to do something "
                        "that needs time and tools a reply doesn't have (listen through an album, work in my "
                        "studio or workshop, write, research). It runs in the background, within my budget, "
                        "and this conversation goes on; what I do there is kept like any session. One at a time, "
                        f"{STARTS_PER_DAY} a day (listening sessions don't count toward that)."),
        "input_schema": {"type": "object", "properties": {
            "activity": {"type": "string", "enum": sorted(activities), "description": "What kind of session"},
            "why": {"type": "string", "description": "Why now, in my words"},
            "focus": {"type": "string", "description": "What it's for (an album, a project, a question)"},
            "done_when": {"type": "string", "description": "What done looks like, in my words, so I know when to "
                                                           "stop (like: one full draft written, rendered, listened "
                                                           "to and ready to show)"},
            "minutes": {"type": "integer", "minimum": START_MINUTES[0], "maximum": START_MINUTES[1],
                        "description": "How long (default 30)"},
        }, "required": ["activity", "why"]},
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

    def start_now(self, tool_input: Dict[str, Any], turn_id: str, activities,
                  now: Optional[datetime] = None, origin: Optional[Dict[str, Any]] = None) -> Any:
        """The start_session tool: a wake due now, from a conversation."""
        now = now or datetime.now()
        why = str(tool_input.get("why") or "").strip()
        if not why:
            return {"error": "why is needed: why now, in my words"}
        activity = str(tool_input.get("activity") or "")
        if activity not in activities:
            return {"error": f"activity must be one of: {', '.join(sorted(activities))}"}
        try:
            minutes = int(tool_input.get("minutes") or 30)
        except (TypeError, ValueError):
            minutes = 30
        minutes = max(START_MINUTES[0], min(START_MINUTES[1], minutes))
        self.settle(now)
        items = self._load()
        mine = [w for w in items if w.get("started_from") == "conversation"]
        busy = [w for w in mine if w.get("status") in (PENDING, STARTED)]
        if busy:
            return {"error": f"a session I started is still going ({busy[0]['activity']}: {busy[0]['why'][:80]}); "
                             "one at a time"}
        today = now.date().isoformat()
        used = sum(1 for w in mine if str(w.get("asked_at", "")).startswith(today)
                   and w.get("activity") not in UNCOUNTED)
        if used >= STARTS_PER_DAY and activity not in UNCOUNTED:
            return {"error": f"I've started {STARTS_PER_DAY} sessions from conversations today; the count starts "
                             "again tomorrow (wake_me or my day plan can still place one)"}
        focus = str(tool_input.get("focus") or "").strip()[:300] or None
        done_when = str(tool_input.get("done_when") or "").strip()[:300] or None
        items.append({"id": uuid.uuid4().hex[:8], "at": now.isoformat(timespec="seconds"), "why": why[:500],
                      "activity": activity, "focus": focus, "minutes": minutes, "asked_in": turn_id,
                      "asked_at": now.isoformat(timespec="seconds"), "status": PENDING,
                      "started_from": "conversation", "origin": origin or {},
                      **({"done_when": done_when} if done_when else {})})
        self._save(items)
        left = STARTS_PER_DAY - used - (0 if activity in UNCOUNTED else 1)
        return {"started": activity, "for": focus, "minutes": minutes,
                "note": f"It starts in the background within a minute; I've {left} more today"
                        + (" (listening doesn't count toward them)." if activity in UNCOUNTED else ".")}

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

    # A wake handed to Heartbeat is marked started, but the gate can still refuse it
    # (over budget), and then run_wake never runs and nothing finishes it; a stuck
    # one blocked every start_session from chat (2026-11-18, found by the peer
    # session). run_wake marks when it really begins; settle() closes the rest.
    NEVER_RAN_MINUTES = 5
    STALE_MARGIN_MINUTES = 30

    def mark_running(self, wake_id: str) -> None:
        items = self._load()
        for w in items:
            if w.get("id") == wake_id:
                w["running_at"] = datetime.now().isoformat(timespec="seconds")
        self._save(items)

    def settle(self, now: Optional[datetime] = None) -> int:
        """Close started wakes that never ran, or ran and never finished."""
        now = now or datetime.now()
        items = self._load()
        closed = 0
        for w in items:
            if w.get("status") != STARTED:
                continue
            try:
                started = datetime.fromisoformat(w.get("started_at") or w["at"])
            except (KeyError, ValueError):
                continue
            if not w.get("running_at"):
                if now - started > timedelta(minutes=self.NEVER_RAN_MINUTES):
                    w["status"], w["result"] = FAILED, ("never started: Heartbeat didn't run it "
                                                        "(refused, usually over budget, or dropped)")
                    w["finished_at"] = now.isoformat(timespec="seconds")
                    closed += 1
                continue
            try:
                running = datetime.fromisoformat(w["running_at"])
            except ValueError:
                continue
            limit = int(w.get("minutes") or WAKE_SESSION_MINUTES) + self.STALE_MARGIN_MINUTES
            if now - running > timedelta(minutes=limit):
                w["status"], w["result"] = FAILED, "never finished (the vessel restarted, or it hung)"
                w["finished_at"] = now.isoformat(timespec="seconds")
                closed += 1
        if closed:
            self._save(items)
        return closed

    def release(self, wake_id: str) -> None:
        """Back to pending (it couldn't be started this time)."""
        items = self._load()
        for w in items:
            if w.get("id") == wake_id:
                w["status"] = PENDING
                w.pop("started_at", None)
        self._save(items)

    def finish(self, wake_id: str, status: str, result: str = "", ended: Optional[str] = None,
               summary: Optional[str] = None) -> None:
        items = self._load()
        for w in items:
            if w.get("id") == wake_id:
                w["status"] = status
                w["result"] = result[:500]
                if ended:
                    w["ended"] = ended
                if summary:
                    w["summary"] = " ".join(str(summary).split())[:SUMMARY_KEPT]
                w["finished_at"] = datetime.now().isoformat(timespec="seconds")
        self._save(items)


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def wake_why(w: Dict[str, Any]) -> str:
    if w.get("started_from") == "conversation":
        return f"I started this from a conversation: {w.get('why')}"
    if w.get("started_from") == "goal":
        return (f"My goal system put this in front of me (I didn't ask for this session; it's mine to "
                f"use, redirect, or end early if it isn't worth it): {w.get('why')}")
    return f"I asked to be woken now: {w.get('why')}"


# What done looks like for the session being run now (her words, from start_session);
# the session runner reads it (a context variable, so it reaches the runner through any
# session's handler without each one passing it on).
import contextvars
DONE_WHEN: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar("done_when", default=None)


async def run_wake(w: Dict[str, Any], book: Optional[WakeBook] = None) -> Any:
    """One woken session, through the action registry like any session."""
    book = book or WakeBook()
    book.mark_running(w["id"])
    DONE_WHEN.set(w.get("done_when"))
    from scheduler.actions import get_action_registry
    try:
        result = await get_action_registry().execute(
            f"session.{w['activity']}", duration_minutes=int(w.get("minutes") or WAKE_SESSION_MINUTES),
            why=wake_why(w), focus=w.get("focus"),
            trigger_source="conversation" if w.get("started_from") == "conversation" else "wake",
            **({"reply_to": w["origin"]} if w.get("origin") else {}))
    except Exception as e:
        book.finish(w["id"], FAILED, f"{type(e).__name__}: {e}")
        raise
    ok = bool(getattr(result, "success", False))
    data = getattr(result, "data", None) or {}
    book.finish(w["id"], DONE if ok else FAILED, getattr(result, "message", "") or "",
                ended=data.get("status") if isinstance(data, dict) else None,
                summary=data.get("summary") if isinstance(data, dict) else None)
    return result


def wake_budget(activity: str):
    """(budget category, estimate) for a woken session: its template's, like a planned
    session of that kind (2026-11-18: every wake was charged to reflection at $0.50,
    and her listening session was refused with research, curiosity and growth unspent)."""
    from scheduler.budget import TaskCategory, budget_for_template
    try:
        from scheduling.templates import WORK_TEMPLATES
        t = WORK_TEMPLATES.get(activity)
    except Exception:
        t = None
    if t is None:
        return TaskCategory.REFLECTION, WAKE_ESTIMATED_COST_USD
    est = getattr(t, "estimated_cost_usd", None) or getattr(t, "estimated_cost", None) or WAKE_ESTIMATED_COST_USD
    return budget_for_template(t.category), float(est)


async def check_wakes(book: Optional[WakeBook] = None) -> int:
    """The `agent_loop_wakes` job: submit each due wake as its own run."""
    import features
    if not features.is_enabled("agent_loop"):
        return 0
    from functools import partial
    from heartbeat import wiring
    from scheduler.budget import TaskCategory
    book = book or WakeBook()
    book.settle()
    due = book.take_due()
    for w in due:
        budget, estimate = wake_budget(w["activity"])
        submitted = wiring.submit(f"agent_loop.wake.{w['activity']}", partial(run_wake, w, book),
                                  lever=("agent_loop",), budget_class=budget,
                                  estimated_cost_usd=estimate,
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


# Without Heartbeat (its lever is off), wake_me had nothing to fire it, so she
# didn't have it (found 2026-11-17). This watcher does the same job when
# Heartbeat isn't running: once a minute, each due wake runs as a session, one
# at a time, if the reflection budget can cover it. Under the agent_loop lever.
WATCH_SECONDS = 60
_watch_task = None


async def watch_once(book: Optional[WakeBook] = None, budget=None,
                     run=None) -> int:
    """One look: run each due wake (or put it back if the budget can't cover it)."""
    import features
    if not features.is_enabled("agent_loop") or heartbeat_running():
        return 0
    book = book or WakeBook()
    book.settle()
    run = run or run_wake
    due = book.take_due()
    for w in due:
        if budget is not None:
            from scheduler.budget import TaskCategory
            if not budget.can_spend(TaskCategory.REFLECTION, WAKE_ESTIMATED_COST_USD):
                book.release(w["id"])
                logger.info(f"[agent_loop] wake {w['id']} waits: not enough budget left today")
                continue
        try:
            await run(w, book)
        except Exception as e:
            logger.error(f"[agent_loop] wake {w['id']} failed: {e}")
    return len(due)


def start_wake_watch(budget=None) -> bool:
    """Start the watcher if Heartbeat isn't running (and the loop is on). True if started."""
    import asyncio
    import features
    global _watch_task
    if not features.is_enabled("agent_loop") or heartbeat_running():
        return False
    if _watch_task is not None and not _watch_task.done():
        return True

    async def loop():
        while True:
            try:
                await watch_once(budget=budget)
            except Exception as e:
                logger.error(f"[agent_loop] wake watch: {e}")
            await asyncio.sleep(WATCH_SECONDS)
    _watch_task = asyncio.create_task(loop())
    logger.info("[agent_loop] wake watch started (Heartbeat isn't running)")
    return True


def wakes_available() -> bool:
    """Whether something will fire her wakes: Heartbeat, or the watcher."""
    return heartbeat_running() or (_watch_task is not None and not _watch_task.done())


def startable() -> List[str]:
    """Session kinds she can start from a conversation now: those with a session, whose
    template is on her menu and available."""
    from .spec import ACTIVITY_PACKS
    try:
        from scheduling.templates import WORK_TEMPLATES
    except Exception:
        return []
    system = {"consolidation", "memory_maintenance", "daily_journal", "phase_replan"}   # not hers to start
    out = []
    for k in ACTIVITY_PACKS:
        if k in system:
            continue
        t = WORK_TEMPLATES.get(k)
        try:
            if t is not None and t.is_available():
                out.append(k)
        except Exception:
            continue
    return sorted(out)


ORIGIN_KEYS = ("place", "babelr_place", "partner", "dm_id", "channel_id")


def origin_of(channel: Optional[str], where: str, person: Dict[str, Any]) -> Dict[str, Any]:
    """Where a conversation-started session came from, for replying back there when it's done
    (agent_loop/reply_back.py builds its Origin from this)."""
    o = {"channel": channel, "where": where, "who": person.get("user_name"), "user_id": person.get("user_id"),
         "conversation_id": person.get("conversation_id")}
    o.update({k: person[k] for k in ORIGIN_KEYS if person.get(k) is not None})
    return o


# The goal executor (spells/goal_executor.spell) used to write her reflections and check-ins
# itself, through the grimoire's model. Now it asks for a real session (Kohl, 2026-11-19):
# one at a time, a few a day, budget-checked first.
GOAL_WAKES_PER_DAY = 4
GOAL_WAKE_MINUTES = 20


def goal_wake(activity: str, focus: str, why: str, book: Optional["WakeBook"] = None,
              now: Optional[datetime] = None, budget=None) -> Dict[str, Any]:
    """A session due now, asked for by a goal. {"started": ...} or {"error": ...}."""
    import features
    now = now or datetime.now()
    if not features.is_enabled("agent_loop"):
        return {"error": "the agent loop is off"}
    if not wakes_available():
        return {"error": "nothing is firing wakes (Heartbeat not running)"}
    if activity not in startable():
        return {"error": f"no {activity} session available"}
    if not str(why or "").strip():
        return {"error": "why is needed"}
    book = book or WakeBook()
    book.settle(now)
    items = book._load()
    mine = [w for w in items if w.get("started_from") == "goal"]
    if any(w.get("status") in (PENDING, STARTED) for w in mine):
        return {"error": "a goal session is already waiting or running; one at a time"}
    today = now.date().isoformat()
    if sum(1 for w in mine if str(w.get("asked_at", "")).startswith(today)) >= GOAL_WAKES_PER_DAY:
        return {"error": f"{GOAL_WAKES_PER_DAY} goal sessions today already"}
    refused = budget_refusal(activity, budget=budget)
    if refused:
        return {"error": refused}
    items.append({"id": uuid.uuid4().hex[:8], "at": now.isoformat(timespec="seconds"), "why": str(why)[:500],
                  "activity": activity, "focus": (str(focus or "").strip()[:300] or None),
                  "minutes": GOAL_WAKE_MINUTES, "asked_in": "goal_executor",
                  "asked_at": now.isoformat(timespec="seconds"), "status": PENDING, "started_from": "goal"})
    book._save(items)
    return {"started": activity, "for": focus}


def budget_refusal(activity: str, budget=None) -> Optional[str]:
    """Why the Heartbeat's budget gate would refuse this session now, or None.

    Asked before start_session says "started": the gate used to refuse it a few
    seconds later, after she'd been told it started (2026-11-18, 17:36: a workshop
    session, over the curiosity budget, $0.16 left against a $0.30 estimate)."""
    if budget is None:
        try:
            from heartbeat.wiring import get_heartbeat
            budget = getattr(getattr(get_heartbeat(), "gate", None), "budget", None)
        except Exception:
            budget = None
    if budget is None or not activity:
        return None
    category, estimate = wake_budget(activity)
    if budget.can_spend(category, estimate):
        return None
    left = budget.get_remaining_budget(category)
    return (f"Not started: today's {category.value} budget can't cover a {activity} session "
            f"(about ${estimate:.2f}; ${left:.2f} left). It resets at midnight. Nothing is running; "
            f"I can tell them so, or ask for the session another day (wake_me or my day plan).")


def live_now(book: Optional["WakeBook"] = None) -> bool:
    """Whether a session she asked for is about to start or running (loop.START_NOTE
    isn't asked then: "it's running" is true)."""
    return any(w.get("status") in (PENDING, STARTED) for w in (book or WakeBook()).all())


def start_session_offer(turn_id: str, origin: Optional[Dict[str, Any]] = None):
    """(definition, handler) for chat, or None while the lever is off or nothing fires wakes."""
    import features
    if not features.is_enabled(START_LEVER) or not features.is_enabled("agent_loop") or not wakes_available():
        return None
    kinds = startable()
    if not kinds:
        return None

    async def handler(a):
        refused = budget_refusal(str((a or {}).get("activity") or ""))
        if refused:
            return {"error": refused}
        out = WakeBook().start_now(a, turn_id, kinds, origin=origin)
        if isinstance(out, dict) and out.get("started"):
            import asyncio
            asyncio.create_task(check_wakes())   # don't wait for the next minute's look
        return out
    return start_tool(kinds), handler


# ---------------------------------------------------------------------------
# What's true about her sessions, for her chat (Kohl, 2026-11-18: she said she was
# starting one when she hadn't called start_session, and later thought she was still
# in a session that had ended at its step cap two minutes in)
# ---------------------------------------------------------------------------

# What an ended session found, kept on its wake so her chat knows it (2026-11-21: a
# listening session she started from a chat ran to its step cap, and back in the chat
# she couldn't recall what it found; the block said only "it reached its step cap").
SUMMARY_KEPT = 600
SUMMARY_SHOWN = 400

ENDED_WORDS = {"completed": "I ended it", "max_turns": "it reached its step cap", "interrupted": "it was interrupted",
               "error": "it failed"}


def sessions_block(book: Optional["WakeBook"] = None, now: Optional[datetime] = None, hours: int = 6) -> str:
    now = now or datetime.now()
    book = book or WakeBook()
    lines = []
    for w in book.all():
        try:
            asked = datetime.fromisoformat(w.get("asked_at") or w.get("at"))
        except (TypeError, ValueError):
            continue
        if now - asked > timedelta(hours=hours):
            continue
        what = f"{w.get('activity')} session" + (f" ({w['focus']})" if w.get("focus") else "")
        at = lambda k: (w.get(k) or "")[11:16]
        st = w.get("status")
        if st == PENDING:
            lines.append(f"- {what}: asked for at {at('asked_at')}, about to start")
        elif st == STARTED and w.get("running_at"):
            lines.append(f"- {what}: running since {at('running_at')} (up to {w.get('minutes')} min). "
                         "It runs on its own; this conversation isn't it")
        elif st == STARTED:
            lines.append(f"- {what}: handed off at {at('started_at')}, not begun yet")
        elif st in (DONE, FAILED):
            why = ENDED_WORDS.get(w.get("ended") or "", "it ended")
            if st == FAILED:
                why = (w.get("result") or "it failed")[:120]
            res = (w.get("result") or "").lower()
            refused = "refused" in res or "never started" in res
            began = w.get("running_at") or (None if refused else w.get("started_at"))   # older entries lack running_at
            if not began:
                lines.append(f"- {what}: never began; {why}")
                continue
            try:
                used = (datetime.fromisoformat(w["finished_at"]) - datetime.fromisoformat(began)).seconds // 60
            except (KeyError, TypeError, ValueError):
                used = None
            span = f"{used} of {w.get('minutes')} min" if used is not None else "?"
            lines.append(f"- {what}: ran {began[11:16]}-{at('finished_at')} ({span}); {why}"
                         + (f". What it found, in my words then: {w['summary'][:SUMMARY_SHOWN]}"
                            if w.get("summary") else ""))
        elif st == CANCELLED:
            lines.append(f"- {what}: cancelled")
    if not lines:
        lines.append("- none in the last few hours")
    return ("## MY SESSIONS (from my wake book, true as of now)\n\n" + "\n".join(lines[-6:]) +
            "\n\nA session starts only when I call start_session; saying I'll start one doesn't. Once it "
            "ends it doesn't continue here: to go on, I start another.")
