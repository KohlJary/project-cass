"""
Spend attribution: which Heartbeat run an LLM call was made in.

While a run is in progress, a context variable holds its RunSpend. Every row
the token ledger writes (token_tracker.TokenUsageTracker.record, which every
routed LLM call reaches through llm_caller) does two things with it:

  - stores the run id in token_usage_records.heartbeat_run_id, so the ledger
    and the run log can be joined row by row;
  - adds its cost to the run, which becomes the run's logged cost, and
    charges the budget as the call happens: only rows the budget counts
    (scheduler.budget.counts_toward_budget), in the bucket the budget sync
    would put them in (scheduler.budget.budget_category_for). So what the gate
    charges is exactly what the next sync rebuilds from the ledger.

The context variable follows the run into worker threads (asyncio.to_thread
copies the context) and into tasks the run spawns. A row written after the
run finished (a task it spawned outlived it) is still attributed: the run log
row's cost is topped up and the budget charged, so the two never drift.

Outside a run, both are no-ops: with the `heartbeat` lever off nothing here
ever runs, and the ledger column stays NULL.
"""
from __future__ import annotations

import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable, Optional

_current: ContextVar[Optional["RunSpend"]] = ContextVar("heartbeat_run_spend", default=None)


@dataclass
class RunSpend:
    work_name: str
    run_id: Optional[int] = None
    cost_usd: float = 0.0           # every ledger row in this run
    counted_usd: float = 0.0        # the part the budget gate counts
    rows: int = 0
    closed: bool = False
    # charge(budget_category, counted_usd): called for every counted row, in
    # or after the run. budget_category is the TaskCategory the budget sync
    # puts that row in (scheduler.budget.budget_category_for).
    charge: Optional[Callable[[object, float], None]] = None
    # late(cost_usd): called for a row written after the run closed.
    late: Optional[Callable[[float], None]] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, cost_usd: float, counted_usd: float, budget_category=None) -> None:
        with self._lock:
            late = self.closed
            if not late:
                self.cost_usd += cost_usd
                self.counted_usd += counted_usd
                self.rows += 1
        if counted_usd and budget_category is not None and self.charge:
            self.charge(budget_category, counted_usd)
        if late and self.late:
            self.late(cost_usd)

    def close(self) -> float:
        with self._lock:
            self.closed = True
            return self.cost_usd


def begin(spend: RunSpend):
    """Make `spend` the current run for this context. Returns a reset token."""
    return _current.set(spend)


def end(token) -> None:
    _current.reset(token)


def current() -> Optional[RunSpend]:
    return _current.get()


def current_run_id() -> Optional[int]:
    spend = _current.get()
    return spend.run_id if spend is not None else None


def note_ledger_row(cost_usd: Optional[float], call_site: Optional[str],
                    category: Optional[str] = None) -> None:
    """Called by the token ledger for every row it writes."""
    spend = _current.get()
    if spend is None:
        return
    cost = float(cost_usd or 0.0)
    from scheduler.budget import budget_category_for, counts_toward_budget
    counted = cost if counts_toward_budget(call_site) else 0.0
    spend.add(cost, counted, budget_category_for(category))
