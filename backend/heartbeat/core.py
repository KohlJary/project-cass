"""
Heartbeat: one clock, one work registry, one budget gate, one run log (#62).

Each tick, for every registered Work that is due:
  1. skip if it is already running (no double runs) or its lever is off;
  2. defer if it is idle-only and someone is around;
  3. ask the budget gate; a refusal is logged and the work waits for its
     next occurrence;
  4. otherwise dispatch it as its own task, log the run, charge the budget.

Sync callables run in a worker thread (asyncio.to_thread), and so do async
ones marked `offload=True`, so blocking work never stalls the event loop
(#85: sync work on the loop froze the whole process).

Heartbeat decides *when* and *how much*. What a turn is belongs to the agent
loop (#70); what a spell does belongs to Grimoire.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Callable, Dict, List, Optional

from .clock import SystemClock
from .gate import BudgetGate
from .registry import Once, Registry, When, Work
from .runlog import RunLog

logger = logging.getLogger(__name__)


class Heartbeat:
    TICK_SECONDS = 1.0

    def __init__(
        self,
        budget_manager=None,
        clock=None,
        run_log: Optional[RunLog] = None,
        idle_check: Optional[Callable[[], bool]] = None,
        tick_seconds: Optional[float] = None,
    ):
        self.clock = clock or SystemClock()
        self.registry = Registry()
        self.gate = BudgetGate(budget_manager)
        self.run_log = run_log or RunLog()
        self._idle_check = idle_check
        self.tick_seconds = tick_seconds or self.TICK_SECONDS
        self._running: Dict[str, asyncio.Task] = {}
        self._loop_task: Optional[asyncio.Task] = None
        self._stopping = False

    # ---- registry ----

    def register(self, work: Work) -> Work:
        work.next_run = work.trigger.first(self.clock.now())
        self.registry.add(work)
        logger.info(f"Heartbeat: registered {work.name} ({work.trigger.describe()}, "
                    f"next {work.next_run})")
        return work

    def submit(self, work: Work) -> Work:
        """A one-off work request (a trigger firing). Runs on the next tick."""
        if not isinstance(work.trigger, Once):
            raise ValueError("submit() takes Once() work; use register() for recurring work")
        return self.register(work)

    def is_idle(self) -> bool:
        return True if self._idle_check is None else bool(self._idle_check())

    # ---- clock loop ----

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        self._stopping = False
        self._loop_task = asyncio.create_task(self._loop())
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
        for work in self.registry.all():
            if work.name in self._running:
                continue
            if work.next_run is None or now < work.next_run:
                continue
            if isinstance(work.trigger, When) and not self._condition(work):
                continue
            if work.lever and not self._lever_on(work.lever):
                continue
            if work.idle_only and not self.is_idle():
                continue
            decision = self.gate.check(work)
            if not decision.allowed:
                self.run_log.refused(work.name, work.trigger.describe(), work.budget_label,
                                     now, decision.reason)
                logger.info(f"Heartbeat: {work.name} refused: {decision.reason}")
                self._advance(work, started=now, now=now)
                continue
            self._running[work.name] = asyncio.create_task(self._run(work, now))
            dispatched.append(work.name)
        return dispatched

    async def drain(self) -> None:
        """Wait for every dispatched run to finish (tests, shutdown)."""
        while self._running:
            await asyncio.gather(*list(self._running.values()), return_exceptions=True)

    # ---- one run ----

    async def _run(self, work: Work, started) -> None:
        run_id = self.run_log.start(work.name, work.trigger.describe(), work.budget_label, started)
        work.last_started = started
        status, error, cost = "ok", None, None
        try:
            result = await self._invoke(work)
            if getattr(result, "success", True) is False:
                status = "failed"
                error = str(getattr(result, "message", "") or "returned success=False")
            # A HandlerResult carries cost_usd; anything else is charged its estimate.
            cost = getattr(result, "cost_usd", None)
        except asyncio.CancelledError:
            status, error = "error", "cancelled"
            raise
        except Exception as e:
            status, error = "error", f"{type(e).__name__}: {e}"
            logger.error(f"Heartbeat: {work.name} raised: {e}", exc_info=True)
        finally:
            finished = self.clock.now()
            charged = 0.0
            if status != "error":  # a raise is not charged (Synkratos's rule)
                charged = self.gate.record(work, cost)
            self.run_log.finish(run_id, status, finished,
                                (finished - started).total_seconds(), charged, error)
            work.run_count += 1
            self._advance(work, started=started, now=finished)
            self._running.pop(work.name, None)

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
            self.registry.remove(work.name)

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
                    "in_flight": w.name in self._running,
                }
                for w in self.registry.all()
            ],
        }
