"""
Heartbeat: one clock, one work registry, one budget gate, one run log (#62).

Each tick, for every registered Work that is due:
  1. skip if it is already running (no double runs) or its lever is off;
  2. defer if it is idle-only and someone is around;
  3. ask the budget gate; a refusal is logged and the work waits for its
     next occurrence;
  4. otherwise dispatch it as its own task, log the run, charge the budget.

Spend is measured, not estimated (heartbeat/spend.py): every token-ledger row
written during a run carries the run id, its cost is the run's logged cost,
and the share the gate counts is charged as the call happens. So the run log
and the ledger agree row for row, and the budget sync (which rebuilds spend
from the ledger) finds what the gate already charged instead of overwriting
it. `measure_spend=False` keeps Synkratos's old rule (charge the reported
cost, else the estimate) for tests and for callers without a ledger.

Triggers outside the clock (a day-phase change, a phase-queue item, a goal
event) submit Once work with submit(); submit_and_wait() also hands back the
result, for callers that await the work (a spell's TASK ... AWAIT).

Sync callables run in a worker thread (asyncio.to_thread), and so do async
ones marked `offload=True`, so blocking work never stalls the event loop
(#85: sync work on the loop froze the whole process).

Heartbeat decides *when* and *how much*. What a turn is belongs to the agent
loop (#70); what a spell does belongs to Grimoire.
"""
from __future__ import annotations

import asyncio
import inspect
import itertools
import logging
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional

from . import spend as spend_mod
from .clock import SystemClock
from .gate import BudgetGate
from .registry import Every, Once, Registry, When, Work
from .runlog import RunLog

logger = logging.getLogger(__name__)


class Heartbeat:
    TICK_SECONDS = 1.0
    REFUSED_BACKOFF_SECONDS = 15 * 60  # retry delay for refused recurring work

    def __init__(
        self,
        budget_manager=None,
        clock=None,
        run_log: Optional[RunLog] = None,
        idle_check: Optional[Callable[[], bool]] = None,
        tick_seconds: Optional[float] = None,
        measure_spend: bool = True,
    ):
        self.clock = clock or SystemClock()
        self.registry = Registry()
        self.gate = BudgetGate(budget_manager)
        self.run_log = run_log or RunLog()
        self._idle_check = idle_check
        self.tick_seconds = tick_seconds or self.TICK_SECONDS
        self.measure_spend = measure_spend
        self._running: Dict[str, asyncio.Task] = {}      # key -> task
        self._groups: Dict[str, str] = {}                 # group -> key in flight
        self._waiters: Dict[str, asyncio.Future] = {}     # key -> future (submit_and_wait)
        self._seq = itertools.count(1)
        self._loop_task: Optional[asyncio.Task] = None
        self._stopping = False

    # ---- registry ----

    def register(self, work: Work) -> Work:
        if isinstance(work.trigger, Once) and work.key is None:
            work.key = f"{work.name}#{next(self._seq)}"
        work.next_run = work.trigger.first(self.clock.now())
        self.registry.add(work)
        log = logger.debug if isinstance(work.trigger, Once) else logger.info
        log(f"Heartbeat: registered {work.key} ({work.trigger.describe()}, next {work.next_run})")
        return work

    def submit(self, work: Work) -> Work:
        """A one-off work request (a trigger firing). Runs on the next tick."""
        if not isinstance(work.trigger, Once):
            raise ValueError("submit() takes Once() work; use register() for recurring work")
        return self.register(work)

    async def submit_and_wait(self, work: Work, start_timeout: Optional[float] = None) -> Any:
        """Submit Once work and wait for its result.

        Returns what the work returned, or a RefusedResult when the gate (or
        a lever) turned it away, when Heartbeat stopped (or its loop died)
        before the work started, or when it hadn't started within
        `start_timeout` seconds (it is then withdrawn). A raise inside the
        work is re-raised here. Once started, the run is awaited to the end.
        """
        if self._stopping:
            return RefusedResult("heartbeat is stopped")
        if self._loop_task is not None and self._loop_task.done():
            # The loop started and died; nothing would ever run this or tell
            # the waiter. (Before start() is fine: the loop will pick it up.)
            return RefusedResult("heartbeat loop ended")
        self.submit(work)
        fut = asyncio.get_running_loop().create_future()
        self._waiters[work.key] = fut
        if start_timeout is None:
            return await fut
        try:
            return await asyncio.wait_for(asyncio.shield(fut), start_timeout)
        except asyncio.TimeoutError:
            if work.key in self._running:
                return await fut
            self.registry.remove(work.key)
            self._resolve(work.key, result=RefusedResult(
                f"not started within {start_timeout:g}s"))
            return await fut

    def is_idle(self) -> bool:
        return True if self._idle_check is None else bool(self._idle_check())

    # ---- clock loop ----

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        self._stopping = False
        self._loop_task = asyncio.create_task(self._loop())
        self._loop_task.add_done_callback(self._loop_ended)
        logger.info(f"Heartbeat started with {len(self.registry)} registered work")

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        self._release_waiters("heartbeat stopped")

    def _loop_ended(self, task: asyncio.Task) -> None:
        """The clock loop ended (stop, or it died): nothing queued will run,
        so nobody may keep waiting for it."""
        if not task.cancelled() and task.exception() is not None:
            logger.error(f"Heartbeat clock loop died: {task.exception()}")
        self._release_waiters("heartbeat stopped" if self._stopping
                              else "heartbeat clock loop ended")

    def _release_waiters(self, reason: str) -> None:
        """Resolve every waiter whose work hasn't started (runs in flight
        finish and resolve their own)."""
        for key in list(self._waiters):
            if key not in self._running:
                self.registry.remove(key)
                self._resolve(key, result=RefusedResult(reason))

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Heartbeat tick failed: {e}", exc_info=True)
            await self.clock.sleep(self.tick_seconds)

    async def tick(self) -> List[str]:
        """Dispatch everything due now. Returns the names dispatched."""
        now = self.clock.now()
        dispatched = []
        # sorted() is stable: equal priorities keep registration order.
        for work in sorted(self.registry.all(), key=lambda w: w.priority):
            if work.key in self._running:
                continue
            if work.group and work.group in self._groups:
                continue
            if work.next_run is None or now < work.next_run:
                continue
            if isinstance(work.trigger, When) and not self._condition(work):
                continue
            if not all(self._lever_on(name) for name in work.levers):
                if isinstance(work.trigger, Once):
                    # A one-off request whose lever is off is dropped, not kept
                    # waiting (it would never run, and a waiter would hang).
                    self.registry.remove(work.key)
                    self._resolve(work.key, result=RefusedResult("lever off"))
                continue
            if work.idle_only and not self.is_idle():
                continue
            decision = self.gate.check(work)
            if not decision.allowed:
                self._log("refused", work.name, work.trigger.describe(),
                          work.budget_label, now, decision.reason)
                logger.info(f"Heartbeat: {work.name} refused: {decision.reason}")
                self._retry_after_refusal(work, now)
                self._resolve(work.key, result=RefusedResult(decision.reason))
                continue
            if work.group:
                self._groups[work.group] = work.key
            self._running[work.key] = asyncio.create_task(self._run(work, now))
            dispatched.append(work.name)
        return dispatched

    async def drain(self) -> None:
        """Wait for every dispatched run to finish (tests, shutdown)."""
        while self._running:
            await asyncio.gather(*list(self._running.values()), return_exceptions=True)

    # ---- one run ----

    async def _run(self, work: Work, started) -> None:
        # Bookkeeping (run log, budget) must never wedge a job: whatever fails,
        # the outer finally frees the in-flight slot and schedules the next run.
        outcome: Dict[str, Any] = {}
        try:
            run_id = None
            if work.log_runs:
                run_id = self._log("start", work.name, work.trigger.describe(),
                                   work.budget_label, started)
            work.last_started = started
            status, error, cost = "ok", None, None
            run_spend = token = None
            if self.measure_spend and work.log_runs:
                run_spend = spend_mod.RunSpend(
                    work_name=work.name, run_id=run_id,
                    charge=lambda category, usd, w=work: self._charge(w, category, usd),
                    late=lambda usd, rid=run_id, w=work: self._late_spend(w, rid, usd),
                )
                token = spend_mod.begin(run_spend)
            try:
                result = await self._invoke(work)
                outcome["result"] = result
                if _result_field(result, "success", True) is False:
                    status = "failed"
                    error = str(_result_field(result, "message", "") or "returned success=False")
                # A HandlerResult carries cost_usd; anything else is charged its estimate.
                cost = _result_field(result, "cost_usd", None)
            except asyncio.CancelledError:
                status, error = "error", "cancelled"
                outcome["error"] = asyncio.CancelledError()
                raise
            except Exception as e:
                status, error = "error", f"{type(e).__name__}: {e}"
                outcome["error"] = e
                logger.error(f"Heartbeat: {work.name} raised: {e}", exc_info=True)
            finally:
                if token is not None:
                    spend_mod.end(token)
                finished = self.clock.now()
                if run_spend is not None:
                    # Measured: the ledger rows written in this run, already
                    # charged (counted share) as they were written.
                    logged_cost = run_spend.close()
                else:
                    logged_cost = 0.0
                    if status != "error":  # a raise is not charged (Synkratos's rule)
                        try:
                            logged_cost = self.gate.record(work, cost)
                        except Exception as e:
                            logger.error(f"Heartbeat: charging {work.name} failed: {e}")
                if run_id is not None:
                    self._log("finish", run_id, status, finished,
                              (finished - started).total_seconds(), logged_cost, error)
                work.run_count += 1
        finally:
            try:
                self._advance(work, started=started, now=self.clock.now())
            finally:
                self._running.pop(work.key, None)
                if work.group and self._groups.get(work.group) == work.key:
                    self._groups.pop(work.group, None)
                self._resolve(work.key, **outcome)

    def _retry_after_refusal(self, work: Work, now) -> None:
        """When refused work tries again.

        Once work is dropped (its waiter is told). Recurring work retries
        after a short backoff instead of losing its cycle (a refused 6-hourly
        spell would otherwise wait 6 hours): Every work after its own
        interval or the backoff, whichever is shorter; Cron work after the
        backoff; When work no sooner than the backoff, since a threshold
        stays crossed while the budget stays spent.
        """
        backoff = timedelta(seconds=self.REFUSED_BACKOFF_SECONDS)
        trigger = work.trigger
        if isinstance(trigger, Once):
            self._advance(work, started=now, now=now)
        elif isinstance(trigger, Every):
            work.next_run = now + min(backoff, timedelta(seconds=trigger.interval))
        elif isinstance(trigger, When):
            work.next_run = now + max(backoff,
                                      timedelta(seconds=trigger.min_interval_seconds))
        else:
            work.next_run = now + backoff

    def _charge(self, work: Work, category, usd: float) -> None:
        try:
            self.gate.charge(work, category, usd)
        except Exception as e:
            logger.error(f"Heartbeat: charging {work.name} failed: {e}")

    def _late_spend(self, work: Work, run_id: Optional[int], cost_usd: float) -> None:
        """A ledger row arrived after the run finished: keep the log in step."""
        logger.warning(f"Heartbeat: {work.name} spent ${cost_usd:.4f} after its run ended")
        if run_id is not None and cost_usd:
            self._log("add_cost", run_id, cost_usd)

    def _resolve(self, key: str, result: Any = None, error: Optional[BaseException] = None) -> None:
        fut = self._waiters.pop(key, None)
        if fut is None or fut.done():
            return
        if error is not None:
            fut.set_exception(error)
        else:
            fut.set_result(result)

    def _log(self, method: str, *args):
        """Call the run log; a failure is logged, never raised into the job."""
        try:
            return getattr(self.run_log, method)(*args)
        except Exception as e:
            logger.error(f"Heartbeat: run log {method} failed: {e}")
            return None

    async def _invoke(self, work: Work):
        if work.is_async:
            if work.offload:
                return await asyncio.to_thread(lambda: asyncio.run(work.run(**work.kwargs)))
            return await work.run(**work.kwargs)
        result = await asyncio.to_thread(work.run, **work.kwargs)
        if inspect.isawaitable(result):  # a callable we couldn't tell was async
            result = await result
        return result

    # ---- helpers ----

    def _advance(self, work: Work, started, now) -> None:
        work.next_run = work.trigger.next_after(started, now)
        if work.next_run is None:
            self.registry.remove(work.key)

    def _condition(self, work: Work) -> bool:
        try:
            return bool(work.trigger.predicate())
        except Exception as e:
            logger.warning(f"Heartbeat: condition for {work.name} raised: {e}")
            return False

    @staticmethod
    def _lever_on(name: str) -> bool:
        from features import is_enabled
        return is_enabled(name)

    def status(self) -> dict:
        return {
            "running": self._loop_task is not None,
            "work": [
                {
                    "name": w.name,
                    "trigger": w.trigger.describe(),
                    "lever": w.lever,
                    "budget_class": w.budget_label,
                    "idle_only": w.idle_only,
                    "next_run": w.next_run.isoformat() if w.next_run else None,
                    "run_count": w.run_count,
                    "in_flight": w.key in self._running,
                }
                for w in self.registry.all()
            ],
        }


class RefusedResult:
    """What submit_and_wait returns when work doesn't run: the gate refused
    it, its lever is off, Heartbeat stopped, or it never got its turn."""
    success = False
    cost_usd = 0.0

    def __init__(self, reason: str):
        self.message = f"not run by Heartbeat: {reason}"
        self.reason = reason


def _result_field(result: Any, name: str, default: Any) -> Any:
    """Read success/message/cost_usd from a HandlerResult, ActionResult or dict."""
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)
