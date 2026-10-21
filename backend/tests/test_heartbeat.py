"""
Heartbeat (#62): registry, cadence, budget gate, run log, off-loop execution,
and the migration rule (one trigger path per job), all on a fake clock.
"""
import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from heartbeat import (
    CONVERSATION, Cron, Every, FakeClock, Heartbeat, Once, RunLog, When, Work,
)
from scheduler.budget import BudgetConfig, BudgetManager, TaskCategory
from scheduler.handlers import HandlerResult


def runs(name=None):
    return list(reversed(RunLog().recent(limit=500, work_name=name)))


def make_hb(budget=None, idle=None, clock=None):
    return Heartbeat(budget_manager=budget, clock=clock or FakeClock(), idle_check=idle)


class Counter:
    def __init__(self, result=None):
        self.calls = 0
        self.result = result

    async def __call__(self, **kwargs):
        self.calls += 1
        return self.result


# ---------------------------------------------------------------------------
# Registry and cadence
# ---------------------------------------------------------------------------

class TestRegistryAndCadence:
    def test_duplicate_names_are_refused(self):
        hb = make_hb()
        hb.register(Work("job", Counter(), Every(60)))
        with pytest.raises(ValueError):
            hb.register(Work("job", Counter(), Every(60)))

    async def test_every_runs_once_per_interval(self):
        clock = FakeClock()
        hb = make_hb(clock=clock)
        job = Counter()
        hb.register(Work("job", job, Every(60)))

        assert await hb.tick() == []            # not due yet (first run after one interval)
        clock.advance(59)
        assert await hb.tick() == []
        clock.advance(1)
        assert await hb.tick() == ["job"]
        await hb.drain()
        assert await hb.tick() == []            # just ran
        clock.advance(60)
        await hb.tick()
        await hb.drain()
        assert job.calls == 2
        assert [r["status"] for r in runs("job")] == ["ok", "ok"]

    async def test_first_after_runs_early(self):
        clock = FakeClock()
        hb = make_hb(clock=clock)
        job = Counter()
        hb.register(Work("job", job, Every(3600, first_after=30)))
        clock.advance(30)
        await hb.tick()
        await hb.drain()
        assert job.calls == 1

    async def test_cron_runs_at_its_minute(self):
        clock = FakeClock(datetime(2026, 10, 20, 8, 58, tzinfo=timezone.utc))
        hb = make_hb(clock=clock)
        job = Counter()
        work = hb.register(Work("nine", job, Cron("0 9 * * *")))
        assert work.next_run == datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)

        clock.advance(minutes=1)
        await hb.tick()
        clock.advance(minutes=1)                # 09:00
        await hb.tick()
        await hb.drain()
        assert job.calls == 1
        assert work.next_run == datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)

    async def test_when_trigger_respects_condition_and_min_gap(self):
        clock = FakeClock()
        hb = make_hb(clock=clock)
        need = {"low": False}
        job = Counter()
        hb.register(Work("care", job, When(lambda: need["low"], min_interval_seconds=600)))

        await hb.tick()
        assert job.calls == 0
        need["low"] = True
        await hb.tick()
        await hb.drain()
        assert job.calls == 1
        clock.advance(300)
        await hb.tick()                         # still low, but inside the gap
        assert job.calls == 1
        clock.advance(300)
        await hb.tick()
        await hb.drain()
        assert job.calls == 2

    async def test_submitted_once_work_runs_once_and_leaves(self):
        hb = make_hb()
        job = Counter()
        hb.submit(Work("spell_step", job, Once()))
        await hb.tick()
        await hb.drain()
        await hb.tick()
        assert job.calls == 1
        assert "spell_step" not in hb.registry

    def test_submit_rejects_recurring_work(self):
        with pytest.raises(ValueError):
            make_hb().submit(Work("x", Counter(), Every(1)))

    async def test_no_double_run_while_in_flight(self):
        clock = FakeClock()
        hb = make_hb(clock=clock)
        release = asyncio.Event()
        calls = []

        async def slow(**kw):
            calls.append(1)
            await release.wait()

        hb.register(Work("slow", slow, Every(1, first_after=0)))
        await hb.tick()
        await asyncio.sleep(0)
        for _ in range(5):
            clock.advance(1)
            assert await hb.tick() == []        # still running: not dispatched again
        release.set()
        await hb.drain()
        assert len(calls) == 1

    async def test_idle_only_waits_for_quiet(self):
        clock = FakeClock()
        idle = {"v": False}
        hb = make_hb(clock=clock, idle=lambda: idle["v"])
        job = Counter()
        hb.register(Work("summarize", job, Every(60, first_after=0), idle_only=True))
        await hb.tick()
        assert job.calls == 0 and runs("summarize") == []   # deferred, not logged
        idle["v"] = True
        await hb.tick()
        await hb.drain()
        assert job.calls == 1

    async def test_lever_off_skips_work(self, levers):
        hb = make_hb()
        job = Counter()
        hb.register(Work("gh", job, Every(1, first_after=0),
                         lever=("scheduler", "job_github_metrics")))
        await hb.tick()                         # CASS_PROFILE=test: lever off
        assert job.calls == 0
        with levers(job_github_metrics=True):               # one of two levers on
            await hb.tick()
        assert job.calls == 0
        with levers(job_github_metrics=True, scheduler=True):
            await hb.tick()
            await hb.drain()
        assert job.calls == 1


# ---------------------------------------------------------------------------
# Budget gate
# ---------------------------------------------------------------------------

def exhausted_budget():
    budget = BudgetManager(BudgetConfig(daily_budget_usd=1.0))
    budget.record_spend(TaskCategory.RESEARCH, 1.0)    # whole day spent
    return budget


class TestBudgetGate:
    async def test_refuses_budgeted_job_and_logs_it(self):
        clock = FakeClock()
        hb = make_hb(budget=exhausted_budget(), clock=clock)
        job = Counter()
        hb.register(Work("research", job, Every(300, first_after=0),
                         budget_class=TaskCategory.RESEARCH, estimated_cost_usd=0.10))
        await hb.tick()
        await hb.drain()
        assert job.calls == 0
        rows = runs("research")
        assert [r["status"] for r in rows] == ["refused_budget"]
        assert "over budget" in rows[0]["error"]
        # Refused work waits for its next occurrence instead of retrying every tick.
        assert await hb.tick() == [] and len(runs("research")) == 1

    async def test_never_refuses_a_conversation(self):
        hb = make_hb(budget=exhausted_budget())
        turn = Counter()
        hb.submit(Work("conversation_turn", turn, Once(),
                       budget_class=CONVERSATION, estimated_cost_usd=5.0))
        await hb.tick()
        await hb.drain()
        assert turn.calls == 1
        assert [r["status"] for r in runs("conversation_turn")] == ["ok"]

    async def test_conversation_runs_even_with_no_budget_manager(self):
        hb = make_hb(budget=None)
        turn = Counter()
        hb.submit(Work("conversation_turn", turn, Once(), budget_class=CONVERSATION,
                       estimated_cost_usd=1.0))
        await hb.tick()
        await hb.drain()
        assert turn.calls == 1

    async def test_spend_is_charged_to_the_shared_budget(self):
        budget = BudgetManager(BudgetConfig(daily_budget_usd=10.0))
        hb = make_hb(budget=budget)
        reported = Counter(HandlerResult(success=True, message="", cost_usd=0.25))
        estimated = Counter(None)
        hb.submit(Work("a", reported, Once(), budget_class=TaskCategory.RESEARCH,
                       estimated_cost_usd=0.10))
        hb.submit(Work("b", estimated, Once(), budget_class=TaskCategory.RESEARCH,
                       estimated_cost_usd=0.10))
        await hb.tick()
        await hb.drain()
        assert budget._spend_by_category[TaskCategory.RESEARCH] == pytest.approx(0.35)
        logged = {r["work_name"]: r["cost_usd"] for r in runs()}
        assert logged == {"a": pytest.approx(0.25), "b": pytest.approx(0.10)}

    async def test_conversation_spend_is_not_charged(self):
        budget = BudgetManager(BudgetConfig(daily_budget_usd=10.0))
        hb = make_hb(budget=budget)
        hb.submit(Work("turn", Counter(HandlerResult(True, "", cost_usd=0.5)), Once(),
                       budget_class=CONVERSATION))
        await hb.tick()
        await hb.drain()
        assert sum(budget._spend_by_category.values()) == 0


# ---------------------------------------------------------------------------
# Run log and execution
# ---------------------------------------------------------------------------

class TestRunLog:
    async def test_rows_record_status_duration_and_error(self):
        clock = FakeClock()
        hb = make_hb(clock=clock)

        async def ok(**kw):
            clock.advance(2.5)

        async def boom(**kw):
            raise RuntimeError("kaput")

        hb.submit(Work("ok", ok, Once()))
        hb.submit(Work("boom", boom, Once()))
        hb.submit(Work("soft", Counter(HandlerResult(False, "no manager")), Once()))
        await hb.tick()
        await hb.drain()

        by_name = {r["work_name"]: r for r in runs()}
        assert by_name["ok"]["status"] == "ok"
        assert by_name["ok"]["duration_seconds"] == pytest.approx(2.5)
        assert by_name["ok"]["finished_at"] and by_name["ok"]["started_at"]
        assert by_name["boom"]["status"] == "error"
        assert "kaput" in by_name["boom"]["error"]
        assert by_name["soft"]["status"] == "failed"
        assert by_name["soft"]["error"] == "no manager"

    async def test_a_raising_job_keeps_its_schedule(self):
        clock = FakeClock()
        hb = make_hb(clock=clock)

        async def boom(**kw):
            raise RuntimeError("x")

        hb.register(Work("flaky", boom, Every(60, first_after=0)))
        await hb.tick()
        await hb.drain()
        clock.advance(60)
        await hb.tick()
        await hb.drain()
        assert [r["status"] for r in runs("flaky")] == ["error", "error"]


class TestRunLogFailure:
    async def test_run_log_errors_do_not_wedge_a_job(self):
        class BrokenLog(RunLog):
            def start(self, *a, **k):
                raise RuntimeError("database is locked")

            def finish(self, *a, **k):
                raise RuntimeError("database is locked")

            def refused(self, *a, **k):
                raise RuntimeError("database is locked")

        clock = FakeClock()
        hb = Heartbeat(clock=clock, run_log=BrokenLog())
        job = Counter()
        work = hb.register(Work("job", job, Every(60, first_after=0)))
        await hb.tick()
        await hb.drain()
        assert job.calls == 1
        assert "job" not in hb._running                      # slot freed
        assert work.next_run == clock.now() + timedelta(seconds=60)
        clock.advance(60)
        assert await hb.tick() == ["job"]                    # and it runs again
        await hb.drain()
        assert job.calls == 2

    async def test_budget_refusal_survives_a_broken_run_log(self):
        class BrokenLog(RunLog):
            def refused(self, *a, **k):
                raise RuntimeError("disk full")

        clock = FakeClock()
        hb = Heartbeat(budget_manager=exhausted_budget(), clock=clock, run_log=BrokenLog())
        hb.register(Work("r", Counter(), Every(60, first_after=0),
                         budget_class=TaskCategory.RESEARCH, estimated_cost_usd=0.1))
        assert await hb.tick() == []
        assert hb.registry.get("r").next_run == clock.now() + timedelta(seconds=60)


class TestOffLoop:
    async def test_sync_work_runs_in_a_thread_and_does_not_block_the_loop(self):
        hb = make_hb()
        seen = {}

        def blocking(**kw):
            seen["thread"] = threading.current_thread() is not threading.main_thread()
            time.sleep(0.3)

        hb.submit(Work("blocking", blocking, Once()))
        ticks = 0

        async def other_work():
            nonlocal ticks
            for _ in range(10):
                await asyncio.sleep(0.01)
                ticks += 1

        await hb.tick()
        await asyncio.gather(other_work(), hb.drain())
        assert seen["thread"] is True
        assert ticks == 10                      # the loop kept serving while it ran
        assert runs("blocking")[0]["status"] == "ok"

    async def test_offload_runs_async_work_in_a_thread(self):
        hb = make_hb()
        seen = {}

        async def blocking_inside(**kw):
            seen["thread"] = threading.current_thread() is not threading.main_thread()
            time.sleep(0.05)
            return HandlerResult(True, "fine")

        hb.submit(Work("offloaded", blocking_inside, Once(), offload=True))
        await hb.tick()
        await hb.drain()
        assert seen["thread"] is True

    async def test_start_and_stop_drive_the_clock_loop(self):
        clock = FakeClock()
        hb = Heartbeat(clock=clock, tick_seconds=30)
        job = Counter()
        hb.register(Work("job", job, Every(60)))
        await hb.start()
        for _ in range(20):
            await asyncio.sleep(0)
        await hb.stop()
        await hb.drain()
        assert job.calls >= 1


# ---------------------------------------------------------------------------
# Migration rule: one trigger path per job
# ---------------------------------------------------------------------------

class FakeSynkratos:
    def __init__(self):
        self.names = []

    def register_system_task(self, task):
        self.names.append(task.name)


def _register(levers_on):
    from scheduler.system_tasks import register_system_tasks
    synk = FakeSynkratos()
    register_system_tasks(synk, {
        "github_metrics_manager": object(),
        "conversation_manager": object(),
        "memory": object(),
        "generate_missing_journals": object(),
        "research_scheduler": object(),
    }, enabled=True)
    return synk.names


JOB_LEVERS = dict(job_github_metrics=True, job_idle_summarization=True,
                  job_daily_journal=True, job_goal_refinement=True,
                  job_autonomous_research=True)


@pytest.fixture
def clean_wiring():
    from heartbeat import wiring
    wiring._heartbeat = None
    yield wiring
    wiring._heartbeat = None


class TestMigration:
    def test_lever_off_leaves_synkratos_registrations_untouched(self, levers, clean_wiring):
        with levers(**JOB_LEVERS):
            names = _register(True)
        assert names == ["github_metrics", "idle_summarization", "daily_journal",
                         "autonomous_research", "goal_refinement"]

    async def test_started_heartbeat_takes_migrated_jobs_without_double_registration(
            self, levers, clean_wiring):
        wiring = clean_wiring
        with levers(heartbeat=True, **JOB_LEVERS):
            hb = await wiring.start_heartbeat(None, {"github_metrics_manager": object()})
            try:
                names = _register(True)
            finally:
                await hb.stop()
        heartbeat_names = {w.name for w in hb.registry.all()}
        assert heartbeat_names == set(wiring.HEARTBEAT_JOBS)
        assert not heartbeat_names & set(names)                 # never both
        assert names == ["idle_summarization", "daily_journal", "autonomous_research"]

    async def test_heartbeat_failing_to_start_leaves_jobs_on_synkratos(
            self, levers, clean_wiring, monkeypatch):
        wiring = clean_wiring

        async def boom(self):
            raise RuntimeError("heartbeat start failed")

        monkeypatch.setattr(Heartbeat, "start", boom)
        with levers(heartbeat=True, **JOB_LEVERS):
            with pytest.raises(RuntimeError):
                await wiring.start_heartbeat(None, {"github_metrics_manager": object()})
            names = _register(True)
        assert wiring.get_heartbeat() is None
        assert not wiring.owns("github_metrics") and not wiring.runs_job("github_metrics")
        assert names == ["github_metrics", "idle_summarization", "daily_journal",
                         "autonomous_research", "goal_refinement"]

    async def test_start_heartbeat_does_nothing_when_lever_off(self, levers, clean_wiring):
        wiring = clean_wiring
        assert await wiring.start_heartbeat(None, {}) is None
        assert wiring.get_heartbeat() is None
        assert wiring.owns("github_metrics") is False
        assert wiring.runs_job("github_metrics") is False

    async def test_migrated_jobs_respect_the_scheduler_lever(self, levers):
        from heartbeat import wiring
        clock = FakeClock(datetime(2026, 10, 20, 8, 59, 30, tzinfo=timezone.utc))
        hb = make_hb(clock=clock)
        wiring.register_migrated_jobs(hb, {})
        clock.advance(30)
        with levers(heartbeat=True, job_goal_refinement=True, scheduler=False):
            assert await hb.tick() == []
        assert runs("goal_refinement") == []

    async def test_migrated_goal_refinement_runs_and_logs(self, levers):
        from heartbeat import wiring
        clock = FakeClock(datetime(2026, 10, 20, 8, 59, 30, tzinfo=timezone.utc))
        hb = make_hb(budget=BudgetManager(BudgetConfig()), clock=clock)
        wiring.register_migrated_jobs(hb, {})
        clock.advance(30)
        with levers(scheduler=True, job_goal_refinement=True):
            assert await hb.tick() == ["goal_refinement"]
            await hb.drain()
        row = runs("goal_refinement")[0]
        assert row["status"] == "ok", row["error"]
        assert row["trigger"] == "cron 0 9 * * *"
        assert row["budget_class"] == "system"
