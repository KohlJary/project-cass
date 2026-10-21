"""
The work registry: what Heartbeat can run, and what wakes each piece of work.

A `Work` is data: a name, a callable, a trigger, the lever that switches it,
the budget class it spends from, and whether it waits for an idle moment.

Triggers say *when*; they never run anything themselves:
  Every(seconds)       fixed cadence, measured from the start of the last run
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
    seconds: float
    # Delay before the first run; None = one full interval (Synkratos's rule).
    first_after: Optional[float] = None

    def first(self, now: datetime) -> datetime:
        delay = self.seconds if self.first_after is None else self.first_after
        return now + timedelta(seconds=delay)

    def next_after(self, started: datetime, now: datetime) -> datetime:
        return started + timedelta(seconds=self.seconds)

    def describe(self) -> str:
        return f"every {self.seconds:g}s"


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
    def first(self, now: datetime) -> datetime:
        return now

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
    # Lever (features.py) checked at dispatch time; None = no lever of its own.
    lever: Optional[str] = None
    # A scheduler.budget.TaskCategory, CONVERSATION, or None (spends nothing).
    budget_class: Any = None
    estimated_cost_usd: float = 0.0
    idle_only: bool = False
    # Run an `async def` that does blocking work in a worker thread with its
    # own event loop. Plain (sync) callables always run in a worker thread.
    offload: bool = False
    kwargs: Dict[str, Any] = field(default_factory=dict)

    # Scheduling state (owned by Heartbeat)
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
    def budget_label(self) -> Optional[str]:
        bc = self.budget_class
        return getattr(bc, "value", bc)


class Registry:
    def __init__(self):
        self._work: Dict[str, Work] = {}

    def add(self, work: Work) -> Work:
        if work.name in self._work:
            raise ValueError(f"Heartbeat work already registered: {work.name}")
        self._work[work.name] = work
        return work

    def remove(self, name: str) -> Optional[Work]:
        return self._work.pop(name, None)

    def get(self, name: str) -> Optional[Work]:
        return self._work.get(name)

    def all(self):
        return list(self._work.values())

    def __contains__(self, name: str) -> bool:
        return name in self._work

    def __len__(self) -> int:
        return len(self._work)
