"""
Heartbeat cutover (#62): every autonomous job runs through Heartbeat with the
`heartbeat` lever on, each job has exactly one trigger path, and spend is
measured from the token ledger so the run log and the budget agree with it.

Done-when (from the issue): a fake-LLM run over a simulated day with the
lever on, where the run log and the budget ledger match exactly
(TestSimulatedDay), and each job has exactly one trigger path
(TestOneTriggerPath). TestLeverOff checks the old registration is unchanged
with the lever off.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from functools import partial

import pytest

from heartbeat import Every, FakeClock, Heartbeat, Once, RunLog, Work, wiring
from scheduler.budget import (
    BudgetConfig, BudgetManager, TaskCategory, budget_category_for, counts_toward_budget,
)

SYNKRATOS_JOBS = ("github_metrics", "idle_summarization", "daily_journal",
                  "autonomous_research", "goal_refinement")
JOB_LEVERS = dict(scheduler=True, job_github_metrics=True, job_idle_summarization=True,
                  job_daily_journal=True, job_goal_refinement=True,
                  job_autonomous_research=True, conversation_observation=True)


class Obj:
    """A stand-in manager (register_system_tasks / job_work only check truthiness)."""


def system_managers(**extra):
    managers = {
        "github_metrics_manager": Obj(), "conversation_manager": Obj(), "memory": Obj(),
        "self_manager": Obj(), "generate_missing_journals": Obj(),
        "research_scheduler": Obj(), "daemon_id": "cass",
    }
    managers.update(extra)
    return managers


@pytest.fixture
def clean_wiring():
    wiring.reset()
    yield wiring
    wiring.reset()


def install(hb):
    """Make `hb` the started Heartbeat the old paths consult."""
    wiring._heartbeat = hb


async def settle(hb, rounds=400):
    """Tick, without moving the clock, until nothing is in flight or waiting.

    Unlike drain(), this keeps ticking, so work that waits on other work it
    submitted (a phase item running the daily journal job) can finish."""
    for _ in range(rounds):
        await hb.tick()
        await asyncio.sleep(0.002)
        now = hb.clock.now()
        pending = [w for w in hb.registry.all()
                   if isinstance(w.trigger, Once) and w.next_run and w.next_run <= now]
        if not hb._running and not pending:
            return
    raise AssertionError(f"Heartbeat did not settle; in flight: {list(hb._running)}")


def ledger():
    from database import get_db
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT call_site, category, estimated_cost_usd, heartbeat_run_id "
            "FROM token_usage_records ORDER BY rowid").fetchall()]


def run_log():
    return list(reversed(RunLog().recent(limit=10000)))


@pytest.fixture
def llm(request):
    """The fake LLM (needs the anthropic SDK to patch, so not in the fast job)."""
    pytest.importorskip("anthropic")
    return request.getfixturevalue("fake_llm")


async def spend(call_site: str):
    """One real routed LLM call (answered by the fake), so one ledger row."""
    from llm_caller import call_llm
    resp = await call_llm(call_site, system_prompt="s", user_prompt="u", max_tokens=50)
    assert resp.error is None, resp.error


class LastDayTracker:
    """The real ledger read over the last 24 h. sync_from_token_tracker's own
    window is UTC midnight against local timestamps (strict xfail in
    tests/test_budget_routing.py, a decision for Kohl); this keeps these tests
    independent of the hour they run at."""

    def __init__(self):
        from token_tracker import TokenUsageTracker
        self._t = TokenUsageTracker()

    def get_records(self, start_date=None, end_date=None, **kw):
        return self._t.get_records(start_date=datetime.now() - timedelta(days=1), **kw)


def counted_by_bucket(rows):
    buckets = {}
    for r in rows:
        cat = budget_category_for(r["category"])
        if cat is not None and counts_toward_budget(r["call_site"]):
            buckets[cat] = buckets.get(cat, 0.0) + (r["estimated_cost_usd"] or 0.0)
    return buckets


def nonzero(spend_by_category):
    return {k: v for k, v in spend_by_category.items() if v}


# ---------------------------------------------------------------------------
# Measured spend
# ---------------------------------------------------------------------------

class TestMeasuredSpend:
    async def test_ledger_rows_carry_the_run_and_the_run_logs_their_cost(self, llm):
        budget = BudgetManager(BudgetConfig(daily_budget_usd=50.0))
        hb = Heartbeat(budget_manager=budget, clock=FakeClock())

        async def journal():
            await spend("memory.journal_entry")       # counted by the budget
            await spend("dreaming.the_dreaming")      # in the ledger, not counted

        hb.submit(Work("journal", journal, Once(), budget_class=TaskCategory.SYSTEM,
                       estimated_cost_usd=0.20))
        await hb.tick()
        await hb.drain()

        (run,) = run_log()
        rows = ledger()
        assert len(rows) == 2
        assert {r["heartbeat_run_id"] for r in rows} == {run["id"]}
        total = sum(r["estimated_cost_usd"] or 0.0 for r in rows)
        assert total > 0
        assert run["cost_usd"] == pytest.approx(total)
        # The budget is charged only what it counts, in the sync's buckets.
        assert nonzero(budget._spend_by_category) == pytest.approx(counted_by_bucket(rows))
        assert sum(budget._spend_by_category.values()) < total

    async def test_sync_from_the_ledger_keeps_what_the_gate_charged(self, llm):
        # #87's review note: the 60 s sync replaced in-process spend with the
        # ledger's, wiping what the gate had charged (estimates). Measured
        # charges are the ledger's own rows, so the sync finds the same spend.
        budget = BudgetManager(BudgetConfig(daily_budget_usd=50.0), LastDayTracker())
        hb = Heartbeat(budget_manager=budget, clock=FakeClock())

        async def work():
            await spend("memory.summary_chunk")
            await spend("research_journal")

        for name, cls in (("a", TaskCategory.SYSTEM), ("b", TaskCategory.RESEARCH)):
            hb.submit(Work(name, work, Once(), budget_class=cls, estimated_cost_usd=0.1))
        await hb.tick()
        await hb.drain()

        charged = nonzero(budget._spend_by_category)
        assert charged
        budget.sync_from_token_tracker()
        assert nonzero(budget._spend_by_category) == pytest.approx(charged)

    async def test_a_run_without_llm_calls_costs_nothing(self):
        budget = BudgetManager(BudgetConfig(daily_budget_usd=50.0))
        hb = Heartbeat(budget_manager=budget, clock=FakeClock())

        async def metrics():
            return None

        hb.submit(Work("github_metrics", metrics, Once(), budget_class=TaskCategory.SYSTEM,
                       estimated_cost_usd=0.01))
        await hb.tick()
        await hb.drain()
        assert run_log()[0]["cost_usd"] == 0
        assert sum(budget._spend_by_category.values()) == 0

    async def test_spend_after_the_run_ends_is_still_attributed(self, llm):
        budget = BudgetManager(BudgetConfig(daily_budget_usd=50.0))
        hb = Heartbeat(budget_manager=budget, clock=FakeClock())
        release = asyncio.Event()
        stray = []

        async def spawns_a_task():
            async def later():
                await release.wait()
                await spend("memory.journal_entry")
            stray.append(asyncio.create_task(later()))

        hb.submit(Work("spawner", spawns_a_task, Once(), budget_class=TaskCategory.SYSTEM,
                       estimated_cost_usd=0.1))
        await hb.tick()
        await hb.drain()
        assert run_log()[0]["cost_usd"] == 0
        release.set()
        await stray[0]

        (run,) = run_log()
        (row,) = ledger()
        assert row["heartbeat_run_id"] == run["id"]
        assert run["cost_usd"] == pytest.approx(row["estimated_cost_usd"])
        assert sum(budget._spend_by_category.values()) == pytest.approx(row["estimated_cost_usd"])

    async def test_housekeeping_work_is_not_logged(self):
        hb = Heartbeat(clock=FakeClock())
        calls = []
        hb.register(Work("budget_sync", lambda: calls.append(1), Every(60, first_after=0),
                         log_runs=False))
        await hb.tick()
        await hb.drain()
        assert calls == [1] and run_log() == []


# ---------------------------------------------------------------------------
# Core additions the cutover needs
# ---------------------------------------------------------------------------

class TestCoreAdditions:
    async def test_one_run_at_a_time_per_group(self):
        hb = Heartbeat(clock=FakeClock())
        release = asyncio.Event()
        started = []

        async def item(n):
            started.append(n)
            await release.wait()

        for n in (1, 2):
            hb.submit(Work(f"phase.{n}", partial(item, n), Once(), group="queue:research"))
        hb.submit(Work("phase.other", partial(item, 3), Once(), group="queue:growth"))
        for _ in range(3):
            await hb.tick()
            await asyncio.sleep(0)
        assert sorted(started) == [1, 3]          # 2 waits for 1 (same queue)
        release.set()
        await settle(hb)
        assert sorted(started) == [1, 2, 3]

    async def test_once_work_with_its_lever_off_is_dropped_and_its_waiter_told(self, levers):
        hb = Heartbeat(clock=FakeClock())
        ran = []

        async def work():
            ran.append(1)

        waiter = asyncio.create_task(hb.submit_and_wait(
            Work("phase.x", work, Once(), lever="scheduler")))
        await asyncio.sleep(0)
        await hb.tick()                           # CASS_PROFILE=test: lever off
        result = await waiter
        assert result.success is False and "lever off" in result.message
        assert ran == [] and len(hb.registry) == 0

    async def test_a_refused_threshold_backs_off(self):
        from heartbeat import When
        spent = BudgetManager(BudgetConfig(daily_budget_usd=1.0))
        spent.record_spend(TaskCategory.GROWTH, 1.0)
        clock = FakeClock()
        hb = Heartbeat(budget_manager=spent, clock=clock)
        hb.register(Work("spell.social_care", lambda: None,
                         When(lambda: True, min_interval_seconds=60),
                         budget_class=TaskCategory.GROWTH, estimated_cost_usd=0.05))
        for _ in range(20):                       # 20 minutes, threshold crossed throughout
            await hb.tick()
            clock.advance(60)
        statuses = [r["status"] for r in run_log()]
        assert statuses == ["refused_budget", "refused_budget"]   # at 0 and 15 min


class TestReviewFixes:
    """Momus's review of #104."""

    async def test_stop_releases_a_waiter_whose_work_never_started(self, levers):
        hb = Heartbeat(clock=FakeClock())
        await hb.start()
        waiter = asyncio.create_task(hb.submit_and_wait(
            Work("journal", partial(asyncio.sleep, 0), Once(delay_seconds=3600))))
        await asyncio.sleep(0)
        await hb.stop()
        result = await asyncio.wait_for(waiter, 1)
        assert result.success is False and "stopped" in result.message
        assert len(hb.registry) == 0
        # After stop, nothing new is accepted to wait on.
        late = await hb.submit_and_wait(Work("x", partial(asyncio.sleep, 0), Once()))
        assert late.success is False

    async def test_loop_death_releases_waiters(self):
        hb = Heartbeat(clock=FakeClock())

        async def broken_sleep(seconds):
            raise RuntimeError("clock broke")

        hb.clock.sleep = broken_sleep
        waiter = asyncio.create_task(hb.submit_and_wait(
            Work("journal", partial(asyncio.sleep, 0), Once(delay_seconds=3600))))
        await asyncio.sleep(0)
        await hb.start()
        result = await asyncio.wait_for(waiter, 1)
        assert result.success is False and "loop ended" in result.message

    async def test_a_waiter_gives_up_if_its_work_has_not_started(self):
        hb = Heartbeat(clock=FakeClock())
        result = await hb.submit_and_wait(
            Work("journal", partial(asyncio.sleep, 0), Once()), start_timeout=0.01)
        assert result.success is False and "not started" in result.message
        assert len(hb.registry) == 0

    async def test_a_refused_timer_spell_retries_soon_instead_of_losing_its_cycle(self):
        spent = BudgetManager(BudgetConfig(daily_budget_usd=1.0))
        spent.record_spend(TaskCategory.CURIOSITY, 1.0)
        clock = FakeClock()
        hb = Heartbeat(budget_manager=spent, clock=clock)
        work = hb.register(Work("spell.art_study", partial(asyncio.sleep, 0),
                                Every(6 * 3600, first_after=0),
                                budget_class=TaskCategory.CURIOSITY, estimated_cost_usd=0.05))
        await hb.tick()
        assert run_log()[-1]["status"] == "refused_budget"
        assert work.next_run == clock.now() + timedelta(seconds=Heartbeat.REFUSED_BACKOFF_SECONDS)
        spent._spend_by_category[TaskCategory.CURIOSITY] = 0.0   # budget frees up
        clock.advance(Heartbeat.REFUSED_BACKOFF_SECONDS)
        await hb.tick()
        await hb.drain()
        assert run_log()[-1]["status"] == "ok"                     # 15 min later, not 6 h
        assert work.next_run == clock.now() + timedelta(hours=6)

    async def test_a_refused_cron_job_retries_after_the_backoff(self):
        from heartbeat import Cron
        spent = BudgetManager(BudgetConfig(daily_budget_usd=1.0))
        spent.record_spend(TaskCategory.SYSTEM, 1.0)
        clock = FakeClock(datetime(2026, 10, 21, 0, 4, tzinfo=timezone.utc))
        hb = Heartbeat(budget_manager=spent, clock=clock)
        work = hb.register(Work("daily_journal", partial(asyncio.sleep, 0), Cron("5 0 * * *"),
                                budget_class=TaskCategory.SYSTEM, estimated_cost_usd=0.2))
        clock.advance(60)
        await hb.tick()
        assert work.next_run == clock.now() + timedelta(minutes=15)   # not tomorrow

    async def test_phase_items_in_one_queue_run_in_priority_order(self, levers, clean_wiring):
        from scheduling.day_phase import DayPhase
        from scheduling.phase_queue import PhaseQueueManager, QueuedWorkUnit
        from scheduling.templates import WORK_TEMPLATES
        from scheduler.actions import ActionRegistry

        hb = Heartbeat(budget_manager=BudgetManager(BudgetConfig()), clock=FakeClock())
        install(hb)
        wiring.adopt("phase_queue")
        registry = ActionRegistry()
        registry.load_definitions()
        order = []

        async def action(context):
            order.append(context["focus"])
            return {"success": True}

        registry.register_handler("session.reflection", action)
        pq = PhaseQueueManager(synkratos=None, action_registry=registry)
        # Submitted lowest priority first; all in the reflection queue.
        for priority in (3, 1, 2):
            unit = WORK_TEMPLATES["reflection_block"].instantiate(focus=f"p{priority}")
            assert await pq._dispatch_work(QueuedWorkUnit(
                work_unit=unit, target_phase=DayPhase.EVENING, priority=priority))
        with levers(scheduler=True):
            await settle(hb)
        assert order == ["p1", "p2", "p3"]

    async def test_adopt_thymos_leaves_the_old_loop_if_registering_fails(
            self, levers, clean_wiring, monkeypatch):
        from thymos.shadow_runner import ThymosRunner

        hb = Heartbeat(clock=FakeClock())
        install(hb)
        runner = ThymosRunner(daemon_id="cass")
        with levers(thymos=True):
            await runner.start()
        try:
            def boom(work):
                raise RuntimeError("registry broke")
            monkeypatch.setattr(hb, "register", boom)
            with pytest.raises(RuntimeError):
                wiring.adopt_thymos(runner)
            assert runner._tick_task is not None and not wiring.owns("thymos_tick")
        finally:
            await runner.stop()

    async def test_adopt_grimoire_is_all_or_nothing(self, levers, clean_wiring, monkeypatch):
        from pathlib import Path
        from grimoire import GrimoireManager
        from thymos.shadow_runner import ThymosRunner

        hb = Heartbeat(clock=FakeClock())
        install(hb)
        runner = ThymosRunner(daemon_id="cass")
        with levers(thymos=True):
            await runner.start()
        try:
            assert wiring.adopt_thymos(runner)
            manager = GrimoireManager(spells_directory=Path(__file__).parents[1] / "spells")
            manager._caster = object()
            real_register, calls = hb.register, []

            def flaky(work):
                calls.append(work.name)
                if len(calls) == 3:
                    raise RuntimeError("registry broke mid-way")
                return real_register(work)

            monkeypatch.setattr(hb, "register", flaky)
            assert not wiring.adopt_grimoire(manager, runner)
            assert not runner.spells_on_heartbeat           # spells stay on the tick
            assert not any(n.startswith("spell.") for n in hb.registry.names())
            assert not wiring.owns("grimoire_spells")
        finally:
            await runner.stop()

    async def test_actions_run_inline_if_heartbeat_cannot_be_asked(self, monkeypatch, clean_wiring):
        from scheduler.actions import ActionRegistry

        def broken(action_id):
            raise RuntimeError("heartbeat import broke")

        monkeypatch.setattr(wiring, "job_for_action", broken)
        registry = ActionRegistry()
        registry.load_definitions()
        ran = []

        async def handler(context):
            ran.append(1)
            return {"success": True}

        registry.register_handler("journal.generate_daily", handler)
        assert (await registry.execute("journal.generate_daily")).success
        assert ran == [1]

    def test_ledger_writes_survive_a_broken_heartbeat(self, monkeypatch):
        from heartbeat import spend as spend_mod
        from token_tracker import TokenUsageTracker

        def broken(*a, **k):
            raise RuntimeError("heartbeat broke")

        monkeypatch.setattr(spend_mod, "current_run_id", broken)
        monkeypatch.setattr(spend_mod, "note_ledger_row", broken)
        TokenUsageTracker().record(category="journal", operation="t", provider="anthropic",
                                   model="claude-haiku-4-5-20251001", input_tokens=10,
                                   output_tokens=5, call_site="memory.journal_entry")
        rows = ledger()
        assert len(rows) == 1 and rows[0]["heartbeat_run_id"] is None


# ---------------------------------------------------------------------------
# Done-when: a simulated day
# ---------------------------------------------------------------------------

class TestSimulatedDay:
    async def test_run_log_and_budget_match_the_ledger_over_a_day(
            self, llm, levers, clean_wiring, monkeypatch):
        """A fake-LLM day on the real Heartbeat wiring, lever on.

        The production job set (wiring.register_jobs) with each job's work
        replaced by fake-LLM calls through llm_caller, plus the evening's
        phase-queued work: a reflection block (Once work through the gate),
        and a phase-queued daily journal, which must run as the daily_journal
        job (not a second path). Then, for the whole day:
          - every ledger row belongs to a logged run;
          - each run's logged cost equals its ledger rows exactly;
          - the budget's in-process spend equals the counted ledger spend
            bucket for bucket, and a sync from the ledger leaves it unchanged.
        """
        from scheduler import handlers
        from scheduler.handlers import HandlerResult
        import background_tasks

        calls = {"journal": 0, "research": 0, "summarize": 0, "observe": 0}

        async def fake_journal(**kw):
            calls["journal"] += 1
            await spend("memory.journal_entry")
            await spend("dreaming.the_dreaming")
            return HandlerResult(True, "journal + dream")

        async def fake_research(**kw):
            calls["research"] += 1
            await spend("wiki.research_and_create")   # local model: $0 in the ledger
            await spend("research_journal")
            return HandlerResult(True, "one task")

        async def fake_summarize(**kw):
            calls["summarize"] += 1
            await spend("memory.summary_chunk")
            return HandlerResult(True, "summarized")

        async def fake_metrics(**kw):
            return HandlerResult(True, "no llm")

        async def fake_observe(cm, mem, sm, analyzed, limit=10):
            calls["observe"] += 1
            await spend("self_observation_extraction.conversation")
            return analyzed

        monkeypatch.setattr(handlers, "daily_journal_handler", fake_journal)
        monkeypatch.setattr(handlers, "autonomous_research_handler", fake_research)
        monkeypatch.setattr(handlers, "idle_summarization_handler", fake_summarize)
        monkeypatch.setattr(handlers, "github_metrics_handler", fake_metrics)
        monkeypatch.setattr(background_tasks, "observe_recent_conversations", fake_observe)
        monkeypatch.setattr(background_tasks, "get_active_daemon_activity_mode", lambda: "active")

        budget = BudgetManager(BudgetConfig(daily_budget_usd=100.0), LastDayTracker())
        # What the gate charges, kept apart from the budget_sync job (which
        # rebuilds the budget from the ledger every minute and would hide a
        # gate that charged nothing).
        gate_charged = {}
        real_record_spend = budget.record_spend

        def record_spend(category, usd):
            gate_charged[category] = gate_charged.get(category, 0.0) + usd
            real_record_spend(category, usd)

        budget.record_spend = record_spend
        clock = FakeClock(datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc))
        hb = Heartbeat(budget_manager=budget, clock=clock, idle_check=lambda: True)
        wiring.register_jobs(hb, system_managers(budget_manager=budget))
        install(hb)

        # The evening phase queue: one ordinary item, and a daily_journal item,
        # whose journal.generate_daily action is the daily journal job's work.
        from scheduler.actions import ActionRegistry
        from scheduling.day_phase import DayPhase
        from scheduling.phase_queue import PhaseQueueManager, QueuedWorkUnit
        from scheduling.templates import WORK_TEMPLATES

        registry = ActionRegistry()
        registry.load_definitions()

        async def reflect_action(context):
            await spend("open_question_reflection")
            return {"success": True}

        async def journal_action(context):
            calls["journal"] += 1
            await spend("memory.journal_entry")
            return {"success": True}

        registry.register_handler("session.reflection", reflect_action)
        registry.register_handler("journal.generate_daily", journal_action)
        phase_queue = PhaseQueueManager(synkratos=None, action_registry=registry)
        wiring.adopt("phase_queue")

        with levers(heartbeat=True, **JOB_LEVERS):
            end = clock.now() + timedelta(days=1)
            evening_done = False
            while clock.now() < end:
                await settle(hb)
                if not evening_done and clock.now().hour == 21:
                    for template in ("reflection_block", "daily_journal"):
                        unit = WORK_TEMPLATES[template].instantiate()
                        assert await phase_queue._dispatch_work(
                            QueuedWorkUnit(work_unit=unit, target_phase=DayPhase.EVENING))
                    await settle(hb)
                    evening_done = True
                clock.advance(60)

        runs = run_log()
        rows = ledger()
        by_name = {}
        for r in runs:
            by_name.setdefault(r["work_name"], []).append(r)

        # The day happened (00:00 up to, not including, 24:00): the cron journal
        # at 00:05 plus the phase-queued one, research every 5 minutes from
        # 00:05, summarization hourly from 01:00, observation at 00:02 and
        # every 30 minutes after.
        assert calls["journal"] == 2
        assert len(by_name["daily_journal"]) == 2          # both as the job
        assert len(by_name["autonomous_research"]) == 287
        assert len(by_name["idle_summarization"]) == 23
        assert len(by_name["conversation_observation"]) == 48
        assert len(by_name["goal_refinement"]) == 1
        assert len(by_name["phase.reflection_block"]) == 1
        assert len(by_name["phase.daily_journal"]) == 1
        assert {r["status"] for r in runs} == {"ok"}

        # 1. Every ledger row belongs to a logged run.
        run_ids = {r["id"] for r in runs}
        assert rows and all(r["heartbeat_run_id"] in run_ids for r in rows)

        # 2. Each run's logged cost is exactly its ledger rows.
        ledger_cost = {}
        for row in rows:
            ledger_cost[row["heartbeat_run_id"]] = (
                ledger_cost.get(row["heartbeat_run_id"], 0.0) + (row["estimated_cost_usd"] or 0.0))
        for r in runs:
            assert r["cost_usd"] == pytest.approx(ledger_cost.get(r["id"], 0.0), abs=1e-12), r
        day_total = sum(row["estimated_cost_usd"] or 0.0 for row in rows)
        assert day_total > 0
        assert sum(r["cost_usd"] for r in runs) == pytest.approx(day_total)
        # The phase item that ran the journal spent nothing itself: the
        # journal job's run carries it.
        assert by_name["phase.daily_journal"][0]["cost_usd"] == 0

        # 3. The budget: what the gate charged equals the counted ledger
        # spend, bucket for bucket, and a sync from the ledger changes nothing.
        counted = counted_by_bucket(rows)
        assert counted and nonzero(gate_charged) == pytest.approx(counted)
        charged = nonzero(budget._spend_by_category)
        assert charged == pytest.approx(counted)
        budget.sync_from_token_tracker()
        assert nonzero(budget._spend_by_category) == pytest.approx(charged)


# ---------------------------------------------------------------------------
# One trigger path per job
# ---------------------------------------------------------------------------

class FakeSynkratos:
    def __init__(self):
        self.names = []
        self.submitted = []

    def register_system_task(self, task):
        self.names.append(task.name)

    def submit_task(self, task):
        self.submitted.append(task.name)


def synkratos_jobs():
    from scheduler.system_tasks import register_system_tasks
    synk = FakeSynkratos()
    register_system_tasks(synk, system_managers(), enabled=True)
    return synk.names


LEGACY_LOOPS = {   # main_sdk's fallback: job -> loop it would start
    "daily_journal": "daily_journal_task",
    "autonomous_research": "autonomous_research_task",
    "github_metrics": "github_metrics_task",
    "idle_summarization": "idle_summarization_task",
    "conversation_observation": "periodic_conversation_observation_task",
}


def trigger_paths(job, on_heartbeat, on_synkratos, fallback):
    """Where `job` can be triggered from. Synkratos and the legacy fallback
    are exclusive (the fallback runs only when Synkratos init fails), so a
    job with neither Heartbeat nor Synkratos has the fallback as its path."""
    paths = []
    if job in on_heartbeat:
        paths.append("heartbeat")
    if job in on_synkratos:
        paths.append("synkratos")
    if fallback and job in LEGACY_LOOPS and not wiring.runs_job(job):
        paths.append("legacy")
    return paths


class TestOneTriggerPath:
    async def test_each_job_has_exactly_one_trigger_path_with_the_lever_on(
            self, levers, clean_wiring):
        with levers(heartbeat=True, **JOB_LEVERS):
            hb = await wiring.start_heartbeat(BudgetManager(BudgetConfig()), system_managers())
            try:
                on_heartbeat = hb.registry.names()
                on_synkratos = set(synkratos_jobs())
            finally:
                await hb.stop()

        assert set(SYNKRATOS_JOBS) | {"conversation_observation", "budget_sync"} == on_heartbeat
        for job in on_heartbeat:
            # Normal boot (Synkratos up) and the fallback (Synkratos init failed):
            assert trigger_paths(job, on_heartbeat, on_synkratos, fallback=False) == ["heartbeat"]
            assert trigger_paths(job, on_heartbeat, set(), fallback=True) == ["heartbeat"]

    async def test_a_jobs_action_runs_as_that_job_not_inline(self, levers, clean_wiring):
        # journal.generate_daily (phase queue), memory.summarize_idle_conversations
        # (memory_maintenance) and research.run_batch/run_single (spells, goals)
        # are the jobs' own work: with the job on Heartbeat they run as its run.
        from scheduler.actions import ActionRegistry

        hb = Heartbeat(budget_manager=BudgetManager(BudgetConfig()), clock=FakeClock())
        wiring.register_jobs(hb, system_managers())
        install(hb)
        registry = ActionRegistry()
        registry.load_definitions()
        ran = []
        for action_id in wiring.JOB_ACTIONS:
            async def handler(context, action_id=action_id):
                ran.append(action_id)
                return {"success": True, "message": action_id}
            registry.register_handler(action_id, handler)

        with levers(heartbeat=True, research=True, **JOB_LEVERS):
            for action_id, job in wiring.JOB_ACTIONS.items():
                task = asyncio.create_task(registry.execute(action_id))
                await asyncio.sleep(0)
                assert not task.done()            # waiting for its job's turn
                await settle(hb)
                result = await task
                assert result.success, result.message
                assert ran[-1] == action_id
                assert run_log()[-1]["work_name"] == job

    async def test_job_action_waits_for_the_jobs_own_run(self, levers, clean_wiring):
        hb = Heartbeat(clock=FakeClock())
        release = asyncio.Event()
        order = []

        async def job_run():
            order.append("job start")
            await release.wait()
            order.append("job end")

        hb.register(Work("daily_journal", job_run, Every(3600, first_after=0),
                         group="job:daily_journal"))
        install(hb)
        await hb.tick()                           # the cron run is in flight

        async def action():
            order.append("action")
            return {"success": True}

        waiter = asyncio.create_task(wiring.run_as_job("daily_journal", action))
        for _ in range(5):
            await hb.tick()
            await asyncio.sleep(0)
        assert order == ["job start"]             # never alongside the job's run
        release.set()
        await settle(hb)
        await waiter
        assert order == ["job start", "job end", "action"]

    async def test_a_refused_job_action_reports_failure(self, levers, clean_wiring):
        from scheduler.actions import ActionRegistry

        spent = BudgetManager(BudgetConfig(daily_budget_usd=1.0))
        spent.record_spend(TaskCategory.SYSTEM, 1.0)
        hb = Heartbeat(budget_manager=spent, clock=FakeClock())
        wiring.register_jobs(hb, system_managers())
        install(hb)
        registry = ActionRegistry()
        registry.load_definitions()
        ran = []

        async def handler(context):
            ran.append(1)
            return {"success": True}

        registry.register_handler("journal.generate_daily", handler)
        with levers(heartbeat=True, **JOB_LEVERS):
            task = asyncio.create_task(registry.execute("journal.generate_daily"))
            await asyncio.sleep(0)
            await settle(hb)
            result = await task
        assert not result.success and "budget" in result.message
        assert ran == []
        assert run_log()[-1]["status"] == "refused_budget"

    async def test_phase_queue_items_go_to_heartbeat_not_synkratos(self, levers, clean_wiring):
        from scheduling.day_phase import DayPhase
        from scheduling.phase_queue import PhaseQueueManager, QueuedWorkUnit
        from scheduling.templates import WORK_TEMPLATES

        hb = Heartbeat(clock=FakeClock())
        install(hb)
        wiring.adopt("phase_queue")
        synk = FakeSynkratos()
        pq = PhaseQueueManager(synkratos=synk)
        unit = WORK_TEMPLATES["reflection_block"].instantiate()
        assert await pq._dispatch_work(QueuedWorkUnit(work_unit=unit,
                                                      target_phase=DayPhase.MORNING))
        assert synk.submitted == []
        (work,) = hb.registry.all()
        assert work.name == "phase.reflection_block"
        assert work.budget_class == TaskCategory.REFLECTION
        assert work.group == "queue:reflection" and work.levers == ("scheduler",)

    async def test_thymos_tick_and_its_spells_move_to_heartbeat(self, levers, clean_wiring):
        from pathlib import Path
        from grimoire import GrimoireManager
        from thymos.shadow_runner import ThymosRunner

        hb = Heartbeat(clock=FakeClock())
        install(hb)
        runner = ThymosRunner(daemon_id="cass")
        with levers(thymos=True):
            await runner.start()
        assert runner._tick_task is not None      # its own loop, before adoption
        manager = GrimoireManager(spells_directory=Path(__file__).parents[1] / "spells")
        try:
            assert wiring.adopt_thymos(runner)
            assert runner._tick_task is None      # own loop stopped
            assert not wiring.adopt_grimoire(manager, runner)   # not attached yet
            assert not runner.spells_on_heartbeat
            manager._caster = object()            # attach_grimoire would set this
            assert wiring.adopt_grimoire(manager, runner)
            names = hb.registry.names()
            assert "thymos_tick" in names
            timer = {f"spell.{s.metadata.name}" for s, _ in manager.registry.get_timer_spells()}
            threshold = {f"spell.{s.metadata.name}" for s in manager.threshold_spells()}
            assert timer and threshold and (timer | threshold) <= names
            assert runner.spells_on_heartbeat     # the tick no longer runs them

            # The tick on Heartbeat no longer calls the Grimoire tick hook.
            hook_calls = []

            async def hook(affects, needs):
                hook_calls.append(1)

            runner._grimoire_on_tick = hook
            with levers(thymos=True):
                await runner.heartbeat_tick()
            assert hook_calls == []
        finally:
            await runner.stop()

    async def test_day_phase_checks_move_to_heartbeat(self, levers, clean_wiring):
        from scheduling.day_phase import DayPhaseTracker

        hb = Heartbeat(clock=FakeClock())
        install(hb)
        tracker = DayPhaseTracker()
        assert wiring.adopt_day_phases(tracker)
        await tracker.start(own_loop=False)
        try:
            assert tracker._loop_task is None
            assert "day_phase" in hb.registry.names()
            seen = []
            tracker.on_phase_change(lambda t: seen.append(t.to_phase))
            tracker._current_phase = None if tracker._current_phase is None else \
                [p for p in type(tracker._current_phase) if p != tracker._current_phase][0]
            await tracker.check_phase()
            assert seen == [tracker.current_phase]
        finally:
            await tracker.stop()

    async def test_goal_orchestrator_events_become_heartbeat_work(self, levers, clean_wiring):
        from goal_orchestrator import GoalOrchestrator

        hb = Heartbeat(budget_manager=BudgetManager(BudgetConfig()), clock=FakeClock())
        install(hb)
        wiring.adopt("goal_orchestrator")
        orch = GoalOrchestrator.__new__(GoalOrchestrator)   # handlers only
        ran = []

        async def handled(event_type, data):
            ran.append(event_type)

        orch._handle_need_depleted = handled
        orch._handle_need_depleted_sync("need.depleted", {"need": "rest"})
        (work,) = hb.registry.all()
        assert work.name == "goal_orchestrator.need"
        assert work.levers == ("goal_orchestrator",)
        with levers(goal_orchestrator=True):
            await settle(hb)
        assert ran == ["need.depleted"]


# ---------------------------------------------------------------------------
# Lever off: the old paths, unchanged
# ---------------------------------------------------------------------------

class TestLeverOff:
    async def test_legacy_registration_is_unchanged(self, levers, clean_wiring):
        with levers(**JOB_LEVERS):
            assert await wiring.start_heartbeat(None, system_managers()) is None
            assert synkratos_jobs() == list(SYNKRATOS_JOBS)
        for name in (*SYNKRATOS_JOBS, "conversation_observation", "budget_sync",
                     "thymos_tick", "day_phase", "grimoire_spells", "phase_queue",
                     "phase_email", "goal_orchestrator", "identity_bootstrap"):
            assert not wiring.owns(name), name

    async def test_job_actions_run_inline(self, levers, clean_wiring):
        from scheduler.actions import ActionRegistry
        registry = ActionRegistry()
        registry.load_definitions()
        ran = []

        async def handler(context):
            ran.append(1)
            return {"success": True}

        registry.register_handler("journal.generate_daily", handler)
        assert wiring.job_for_action("journal.generate_daily") is None
        assert (await registry.execute("journal.generate_daily")).success
        assert ran == [1] and run_log() == []

    async def test_phase_queue_submits_to_synkratos(self, clean_wiring):
        from scheduling.day_phase import DayPhase
        from scheduling.phase_queue import PhaseQueueManager, QueuedWorkUnit
        from scheduling.templates import WORK_TEMPLATES

        synk = FakeSynkratos()
        pq = PhaseQueueManager(synkratos=synk)
        unit = WORK_TEMPLATES["reflection_block"].instantiate()
        assert await pq._dispatch_work(QueuedWorkUnit(work_unit=unit,
                                                      target_phase=DayPhase.MORNING))
        assert synk.submitted == ["[Phase] Reflection Block"]

    async def test_thymos_and_day_phase_keep_their_own_loops(self, levers, clean_wiring):
        from scheduling.day_phase import DayPhaseTracker
        from thymos.shadow_runner import ThymosRunner

        runner = ThymosRunner(daemon_id="cass")
        tracker = DayPhaseTracker()
        assert not wiring.adopt_thymos(runner) and not wiring.adopt_day_phases(tracker)
        with levers(thymos=True):
            await runner.start()
        await tracker.start()
        try:
            assert runner._tick_task is not None
            assert tracker._loop_task is not None
            assert runner.spells_on_heartbeat is False
        finally:
            await runner.stop()
            await tracker.stop()

    async def test_goal_orchestrator_spawns_a_task(self, clean_wiring):
        from goal_orchestrator import GoalOrchestrator

        orch = GoalOrchestrator.__new__(GoalOrchestrator)
        ran = []

        async def handled(event_type, data):
            ran.append(event_type)

        orch._handle_need_depleted = handled
        orch._handle_need_depleted_sync("need.depleted", {})
        await asyncio.sleep(0)
        assert ran == ["need.depleted"]
