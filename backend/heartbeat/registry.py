"""
The work registry: what Heartbeat can run, and what wakes each piece of work.

A `Work` is data: a name, a callable, a trigger, the lever that switches it,
the budget class it spends from, and whether it waits for an idle moment.

Triggers say *when*; they never run anything themselves:
  Every(seconds)       fixed cadence, measured from the start of the last run
                       (seconds may be a callable, for an admin-adjustable cadence)
  Cron("5 0 * * *")    cron expression on the one clock (CASS_TIMEZONE or UTC)
  When(predicate)      a condition checked each tick (a need threshold, say),
                       with a minimum gap between runs
  Once()               a one-off request (submitted work: a spell step, a
                       phase-queue item, a conversation turn)
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Union

# Budget class for a person talking to her. The gate never refuses it
# (Kohl's rule: conversations are never refused for budget).
CONVERSATION = "conversation"


@dataclass(frozen=True)
class Every:
    # Seconds, or a callable returning them (read each time, so a cadence an
    # admin can change at runtime, like the Thymos tick, takes effect).
    seconds: Union[float, Callable[[], float]]
    # Delay before the first run; None = one full interval (Synkratos's rule).
    first_after: Optional[float] = None

    @property
    def interval(self) -> float:
        return float(self.seconds() if callable(self.seconds) else self.seconds)

    def first(self, now: datetime) -> datetime:
        delay = self.interval if self.first_after is None else self.first_after
        return now + timedelta(seconds=delay)

    def next_after(self, started: datetime, now: datetime) -> datetime:
        return started + timedelta(seconds=self.interval)

    def describe(self) -> str:
        return f"every {self.interval:g}s"


@dataclass(frozen=True)
class Cron:
    expr: str

    def first(self, now: datetime) -> Optional[datetime]:
        from scheduler.core import CronParser
        return CronParser.parse_next_run(self.expr, now)

    def next_after(self, started: datetime, now: datetime) -> Optional[datetime]:
        from scheduler.core import CronParser
        return CronParser.parse_next_run(self.expr, max(started, now))

    def describe(self) -> str:
        return f"cron {self.expr}"


@dataclass(frozen=True)
class When:
    predicate: Callable[[], bool]
    min_interval_seconds: float = 0.0
    label: str = "condition"

    def first(self, now: datetime) -> datetime:
        return now

    def next_after(self, started: datetime, now: datetime) -> datetime:
        return started + timedelta(seconds=self.min_interval_seconds)

    def describe(self) -> str:
        return f"when {self.label}"


@dataclass(frozen=True)
class Once:
    # Run no earlier than this many seconds after submission.
    delay_seconds: float = 0.0

    def first(self, now: datetime) -> datetime:
        return now + timedelta(seconds=self.delay_seconds)

    def next_after(self, started: datetime, now: datetime) -> None:
        return None

    def describe(self) -> str:
        return "once"


Trigger = Union[Every, Cron, When, Once]


@dataclass
class Work:
    name: str
    run: Callable[..., Any]
    trigger: Trigger
    # Lever(s) (features.py) checked at dispatch time; all must be on.
    # A name, a tuple of names, or None (no lever of its own).
    lever: Any = None
    # A scheduler.budget.TaskCategory, CONVERSATION, or None (spends nothing).
    budget_class: Any = None
    estimated_cost_usd: float = 0.0
    idle_only: bool = False
    # Run an `async def` that does blocking work in a worker thread with its
    # own event loop. Plain (sync) callables always run in a worker thread.
    offload: bool = False
    kwargs: Dict[str, Any] = field(default_factory=dict)
    # At most one run in flight per group (Synkratos ran one task at a time
    # per category queue; phase-queue work keeps that with group="queue:<cat>").
    group: Optional[str] = None
    # Lower runs first when several due works compete for one group slot
    # (phase-queue items keep their queue priority, as Synkratos's queues
    # ordered by priority, then submission). Ties keep submission order.
    priority: int = 0
    # False for housekeeping that runs every minute and spends nothing (the
    # Thymos tick, the day-phase check, the budget sync): no run-log row, and
    # no spend attribution, so an LLM call made inside one shows up unattributed.
    log_runs: bool = True

    # Scheduling state (owned by Heartbeat)
    # Registry key: the name for recurring work, name#n for submitted Once work
    # (several requests with one name can be pending at once).
    key: Optional[str] = None
    next_run: Optional[datetime] = None
    last_started: Optional[datetime] = None
    run_count: int = 0

    @property
    def is_async(self) -> bool:
        fn = self.run
        while hasattr(fn, "func"):  # functools.partial
            fn = fn.func
        return (inspect.iscoroutinefunction(fn)
                or inspect.iscoroutinefunction(getattr(fn, "__call__", None)))

    @property
    def levers(self) -> tuple:
        if not self.lever:
            return ()
        return (self.lever,) if isinstance(self.lever, str) else tuple(self.lever)

    @property
    def budget_label(self) -> Optional[str]:
        bc = self.budget_class
        return getattr(bc, "value", bc)


class Registry:
    def __init__(self):
        self._work: Dict[str, Work] = {}

    def add(self, work: Work) -> Work:
        key = work.key or work.name
        if key in self._work:
            raise ValueError(f"Heartbeat work already registered: {key}")
        work.key = key
        self._work[key] = work
        return work

    def remove(self, key: str) -> Optional[Work]:
        return self._work.pop(key, None)

    def get(self, key: str) -> Optional[Work]:
        return self._work.get(key)

    def all(self):
        return list(self._work.values())

    def names(self) -> set:
        """Names of registered recurring work (submitted Once work excluded)."""
        return {w.name for w in self._work.values() if not isinstance(w.trigger, Once)}

    def __contains__(self, key: str) -> bool:
        return key in self._work

    def __len__(self) -> int:
        return len(self._work)
