"""
What Heartbeat runs, and the hooks the old schedulers call to hand work over.

Cutover rule (#62): with the `heartbeat` lever on, every autonomous job runs
through Heartbeat (one clock, one registry, one budget gate, one run log),
and each job has exactly one trigger path. main_sdk starts Heartbeat *before*
register_system_tasks; every old path (Synkratos system task, legacy asyncio
loop, Thymos's own tick loop, the day-phase loop, the Grimoire tick hook,
phase-queue dispatch to Synkratos, GoalOrchestrator's spawned tasks) asks
`owns(name)` and stands down only when a started Heartbeat has taken that
work. So with the lever off, or if Heartbeat fails to start, the old paths
run everything exactly as before.

What moves (lever on):

  recurring jobs (registered here)
    github_metrics, goal_refinement, idle_summarization, daily_journal,
    autonomous_research      the five Synkratos system jobs
    conversation_observation the 30-minute observation loop
    budget_sync              BudgetManager.sync_from_token_tracker, every 60 s
                             (was inside the Synkratos loop)
  adopted subsystems (their loops stop; Heartbeat drives them)
    thymos_tick              ThymosRunner's tick loop -> Every(tick_interval)
    day_phase                DayPhaseTracker's minute loop -> Every(60);
                             a phase change submits work requests
    spell.<name>             Grimoire TIMER spells -> Every; need/affect
                             threshold spells -> When; event spells -> Once
                             per matching event
    phase.<template>         phase-queue items -> Once (were Synkratos queue tasks)
    phase_email              the inbox check on phase changes and at boot -> Once
    goal_orchestrator.*      GoalOrchestrator's event handlers -> Once
    identity_bootstrap       the one-off boot identity snippet -> Once

Jobs that other paths also used to fire: an action that *is* a job's work
(journal.generate_daily is the daily journal, memory.summarize_idle_conversations
is idle summarization, research.run_batch / run_single are wiki research) runs
as a Once run *of that job* (same name, same concurrency group, same levers and
budget class) instead of inline, wherever it is called from: a phase-queued
daily_journal or memory_maintenance, a spell's TASK, a goal. So the journal,
summarization and research each have one path: their Heartbeat job.

Levers: every piece keeps the levers it had, checked at dispatch time (the
`scheduler` lever for the old Synkratos jobs and queues, `thymos` and the
grimoire_* levers for spells, and so on). The `heartbeat` lever itself is
read once at boot, so flipping it needs a restart.
"""
from __future__ import annotations

import logging
from functools import partial
from typing import Any, Callable, Dict, Optional

from features import is_enabled

from .core import Heartbeat, RefusedResult
from .registry import Cron, Every, Once, When, Work

logger = logging.getLogger(__name__)

# The recurring jobs register_jobs() can register (each only when its
# managers are available, the same condition Synkratos used).
HEARTBEAT_JOBS = frozenset({
    "github_metrics", "goal_refinement", "idle_summarization", "daily_journal",
    "autonomous_research", "conversation_observation", "budget_sync",
})

# Actions that are a job's work. Executing one with the job on Heartbeat runs
# it as a run of that job (see module docstring).
JOB_ACTIONS = {
    "journal.generate_daily": "daily_journal",
    "memory.summarize_idle_conversations": "idle_summarization",
    "research.run_batch": "autonomous_research",
    "research.run_single": "autonomous_research",
}

# How long a job's action (a spell's TASK, a phase item) waits for its turn
# before giving up: the job's own run can be long (a nightly journal + dream).
JOB_ACTION_START_TIMEOUT = 60 * 60

_heartbeat: Optional[Heartbeat] = None
# Subsystems Heartbeat drives that aren't (only) registry entries.
_adopted: set = set()


def owns(name: str) -> bool:
    """True when a started Heartbeat is the trigger path for this job or
    subsystem, so the old path must stand down."""
    if _heartbeat is None:
        return False
    return name in _adopted or name in _heartbeat.registry.names()


runs_job = owns  # alias used by the legacy-fallback guard in main_sdk


def get_heartbeat() -> Optional[Heartbeat]:
    return _heartbeat


def reset() -> None:
    """Tests: forget the started Heartbeat and everything it adopted."""
    global _heartbeat
    _heartbeat = None
    _adopted.clear()


# ---------------------------------------------------------------------------
# Recurring jobs
# ---------------------------------------------------------------------------

def job_work(managers: Dict[str, Any]) -> Dict[str, Work]:
    """The jobs as Work, keyed by name, for whichever managers are present."""
    from scheduler.budget import TaskCategory
    from scheduler import handlers

    jobs: Dict[str, Work] = {}

    gm = managers.get("github_metrics_manager")
    if gm is not None:
        jobs["github_metrics"] = Work(
            name="github_metrics",
            run=partial(handlers.github_metrics_handler, github_metrics_manager=gm),
            trigger=Every(6 * 60 * 60),
            lever=("scheduler", "job_github_metrics"),
            budget_class=TaskCategory.SYSTEM,
            estimated_cost_usd=0.01,
        )

    if managers.get("conversation_manager") and managers.get("memory"):
        jobs["idle_summarization"] = Work(
            name="idle_summarization",
            run=partial(handlers.idle_summarization_handler,
                        conversation_manager=managers["conversation_manager"],
                        memory=managers["memory"],
                        token_tracker=managers.get("token_tracker")),
            trigger=Every(60 * 60),
            lever=("scheduler", "job_idle_summarization"),
            budget_class=TaskCategory.SYSTEM,
            estimated_cost_usd=0.05,
            idle_only=True,
            group="job:idle_summarization",
        )

    if managers.get("generate_missing_journals"):
        jobs["daily_journal"] = Work(
            name="daily_journal",
            run=partial(handlers.daily_journal_handler,
                        generate_missing_journals_func=managers.get("generate_missing_journals"),
                        generate_nightly_dream_func=managers.get("generate_nightly_dream"),
                        self_manager=managers.get("self_manager"),
                        data_dir=managers.get("data_dir"),
                        conversation_manager=managers.get("conversation_manager")),
            trigger=Cron("5 0 * * *"),
            lever=("scheduler", "job_daily_journal"),
            budget_class=TaskCategory.SYSTEM,
            estimated_cost_usd=0.20,
            group="job:daily_journal",
        )

    if managers.get("research_scheduler"):
        jobs["autonomous_research"] = Work(
            name="autonomous_research",
            run=partial(handlers.autonomous_research_handler,
                        scheduler=managers["research_scheduler"],
                        mode=None,  # read live from scheduler.config.mode
                        max_tasks=5,
                        session_requests=managers.get("research_session_requests"),
                        session_runner_getter=managers.get("research_session_runner_getter")),
            trigger=Every(5 * 60),
            lever=("scheduler", "job_autonomous_research"),
            budget_class=TaskCategory.RESEARCH,
            estimated_cost_usd=0.10,
            group="job:autonomous_research",
        )

    jobs["goal_refinement"] = Work(
        name="goal_refinement",
        # async def with only blocking SQLite inside: run it off the loop.
        run=partial(handlers.goal_refinement_handler, daemon_id=managers.get("daemon_id")),
        offload=True,
        trigger=Cron("0 9 * * *"),
        lever=("scheduler", "job_goal_refinement"),
        budget_class=TaskCategory.SYSTEM,
        estimated_cost_usd=0.0,
    )

    if (managers.get("conversation_manager") and managers.get("memory")
            and managers.get("self_manager")):
        from background_tasks import ConversationObservationJob
        jobs["conversation_observation"] = Work(
            name="conversation_observation",
            run=ConversationObservationJob(managers["conversation_manager"],
                                           managers["memory"], managers["self_manager"]),
            # The loop waited 120 s after boot, then ran every 30 min.
            trigger=Every(30 * 60, first_after=120),
            lever="conversation_observation",
            budget_class=TaskCategory.REFLECTION,
            estimated_cost_usd=0.05,
        )

    budget = managers.get("budget_manager")
    if budget is not None:
        jobs["budget_sync"] = Work(
            name="budget_sync",
            run=budget.sync_from_token_tracker,   # sync: runs in a worker thread
            trigger=Every(60, first_after=0),
            log_runs=False,
        )
    return jobs


def register_jobs(hb: Heartbeat, managers: Dict[str, Any]) -> None:
    for work in job_work(managers).values():
        hb.register(work)


register_migrated_jobs = register_jobs  # #87's name


async def start_heartbeat(
    budget_manager,
    managers: Dict[str, Any],
    idle_check: Optional[Callable[[], bool]] = None,
) -> Optional[Heartbeat]:
    """Build, register and start Heartbeat if its lever is on. Returns it."""
    global _heartbeat
    if not is_enabled("heartbeat"):
        return None
    if _heartbeat is not None:
        return _heartbeat
    hb = Heartbeat(budget_manager=budget_manager, idle_check=idle_check)
    register_jobs(hb, {**managers, "budget_manager": budget_manager})
    await hb.start()
    _heartbeat = hb  # only after a confirmed start: owns() depends on it
    return hb


# ---------------------------------------------------------------------------
# Submitting work from triggers
# ---------------------------------------------------------------------------

def submit(name: str, run: Callable, *, lever=None, budget_class=None,
           estimated_cost_usd: float = 0.0, group: Optional[str] = None,
           delay_seconds: float = 0.0, offload: bool = False, priority: int = 0) -> bool:
    """Submit one-off work to the started Heartbeat. False when there is none
    (the caller then runs it the old way)."""
    hb = _heartbeat
    if hb is None:
        return False
    hb.submit(Work(name=name, run=run, trigger=Once(delay_seconds), lever=lever,
                   budget_class=budget_class, estimated_cost_usd=estimated_cost_usd,
                   group=group, offload=offload, priority=priority))
    return True


def job_for_action(action_id: str) -> Optional[str]:
    """The Heartbeat job an action belongs to, when that job runs on Heartbeat."""
    job = JOB_ACTIONS.get(action_id)
    return job if job and owns(job) else None


async def run_as_job(job: str, run: Callable) -> Any:
    """Run `run` (an async callable) as a one-off run of a registered job:
    same name, concurrency group, levers and budget class, so it never
    overlaps the job's own run and shows up in the run log under its name.
    Returns its result, or a RefusedResult when the gate or a lever said no."""
    hb = _heartbeat
    work = hb.registry.get(job) if hb else None
    if work is None:
        return await run()
    return await hb.submit_and_wait(Work(
        name=job, run=run, trigger=Once(), lever=work.lever,
        budget_class=work.budget_class, estimated_cost_usd=work.estimated_cost_usd,
        group=work.group or f"job:{job}",
    ), start_timeout=JOB_ACTION_START_TIMEOUT)


# ---------------------------------------------------------------------------
# Adopting subsystems
# ---------------------------------------------------------------------------

def adopt_thymos(runner) -> bool:
    """Drive the Thymos tick from Heartbeat instead of its own loop."""
    hb = _heartbeat
    if hb is None or runner is None or not getattr(runner, "running", False):
        return False
    if owns("thymos_tick"):
        return True
    # Register first: if that fails, Thymos's own loop is still running.
    work = hb.register(Work(
        name="thymos_tick",
        run=runner.heartbeat_tick,
        trigger=Every(lambda: runner.tick_interval),
        lever="thymos",
        log_runs=False,
    ))
    try:
        runner.use_external_clock()
    except Exception:
        hb.registry.remove(work.key)
        raise
    _adopted.add("thymos_tick")
    return True


def spell_budget(spell):
    """(budget class, estimate) for a spell's runs, from its tags."""
    from scheduler.budget import TaskCategory
    tags = {t.lower() for t in (spell.metadata.tags or [])}
    if "routine" in tags or "scheduling" in tags:
        return None, 0.0                           # phase spells only QUEUE work
    if "research" in tags or "rss" in tags:
        return TaskCategory.RESEARCH, 0.05
    if tags & {"creative", "art", "music"}:
        return TaskCategory.CURIOSITY, 0.05
    if tags & {"reflection", "values", "rest"}:
        return TaskCategory.REFLECTION, 0.05
    return TaskCategory.GROWTH, 0.05


def _while_ticking(runner, run):
    """Spells ran inside the Thymos tick, so a paused or stopped Thymos ran
    none; keep that."""
    async def guarded(**kwargs):
        if not runner.is_ticking():
            return {"success": True, "message": "Thymos paused or stopped"}
        return await run(**kwargs)
    return guarded


def adopt_grimoire(manager, runner) -> bool:
    """Run Grimoire's spells as Heartbeat work instead of inside the Thymos tick.

    TIMER spells become Every work, need/affect threshold spells When work,
    and event spells Once work per matching event (create_grimoire_hooks).
    Each spell keeps its cooldown, and the levers it had: `thymos` (spells ran
    inside its tick) plus grimoire_timer_spells / grimoire_need_spells.

    All or nothing: every spell is registered first, and only then does the
    tick stop running them (spells_on_heartbeat). If any registration fails,
    the ones made are removed and the spells stay on the tick, so no spell
    can run from both. Needs Grimoire's services attached (attach_grimoire,
    in heavy init); until then it returns False, and main_sdk calls it again
    right after attaching.
    """
    import time

    hb = _heartbeat
    if hb is None or manager is None or runner is None:
        return False
    if owns("grimoire_spells"):
        return True
    if not owns("thymos_tick"):
        return False  # spells ride the Thymos tick; without it, leave them there
    if getattr(manager, "_caster", None) is None:
        logger.info("Heartbeat: Grimoire not attached yet; spells stay on the Thymos tick for now")
        return False

    works = []
    for spell, trigger in manager.registry.get_timer_spells():
        name = spell.metadata.name
        if trigger.interval_minutes is not None:
            interval = trigger.interval_minutes * 60.0
            last = manager._timer_last_run.get(name, 0)
            # Same rule as GrimoireManager._is_timer_due: never run -> now,
            # else when the interval since the persisted last run is up.
            first = 0.0 if not last else max(0.0, interval - (time.time() - last))
            when = Every(interval, first_after=first)
        elif trigger.cron_expr is not None:
            when = Cron(trigger.cron_expr)
        else:
            continue
        budget_class, estimate = spell_budget(spell)
        works.append(Work(
            name=f"spell.{name}",
            run=_while_ticking(runner, partial(manager.run_timer_spell, name)),
            trigger=when,
            lever=("thymos", "grimoire_timer_spells"),
            budget_class=budget_class, estimated_cost_usd=estimate,
        ))

    for spell in manager.threshold_spells():
        name = spell.metadata.name
        budget_class, estimate = spell_budget(spell)
        works.append(Work(
            name=f"spell.{name}",
            run=_while_ticking(runner, partial(manager.run_threshold_spell, name,
                                               runner.current_affects, runner.current_needs)),
            # Checked every Heartbeat tick, at most once a minute (the Thymos
            # tick it used to ride); the spell's own cooldown also applies.
            trigger=When(partial(_threshold_due, runner, manager, name),
                         min_interval_seconds=60, label=f"{name} threshold"),
            lever=("thymos", "grimoire_need_spells"),
            budget_class=budget_class, estimated_cost_usd=estimate,
        ))

    registered = []
    try:
        for work in works:
            registered.append(hb.register(work))
    except Exception as e:
        for work in registered:
            hb.registry.remove(work.key)
        logger.error(f"Heartbeat: adopting Grimoire failed; spells stay on the Thymos tick: {e}")
        return False

    runner.spells_on_heartbeat = True
    _adopted.add("grimoire_spells")
    return True


def _threshold_due(runner, manager, name) -> bool:
    return runner.is_ticking() and manager.threshold_due(
        name, runner.current_affects, runner.current_needs)


def submit_event_spell(manager, match) -> bool:
    """An event spell matched: run it as Once work (adopted Grimoire only)."""
    if not owns("grimoire_spells"):
        return False
    budget_class, estimate = spell_budget(match.spell)
    return submit(f"spell.{match.spell.metadata.name}",
                  partial(manager.execute_matches, [match], "event"),
                  lever="thymos", budget_class=budget_class, estimated_cost_usd=estimate)


def adopt_day_phases(tracker) -> bool:
    """Check for day-phase changes on the Heartbeat clock instead of the
    tracker's own minute loop. A change still emits day_phase.* events and
    calls the tracker's callbacks; those submit work (phase queue)."""
    hb = _heartbeat
    if hb is None or tracker is None:
        return False
    hb.register(Work(
        name="day_phase",
        run=tracker.check_phase,
        trigger=Every(tracker.CHECK_INTERVAL_SECONDS),
        lever="day_phases",
        log_runs=False,
    ))
    _adopted.add("day_phase")
    return True


def adopt(name: str) -> bool:
    """Record that Heartbeat is the trigger path for a submit-only subsystem
    (phase_queue, phase_email, goal_orchestrator, identity_bootstrap)."""
    if _heartbeat is None:
        return False
    _adopted.add(name)
    return True


__all__ = [
    "HEARTBEAT_JOBS", "JOB_ACTIONS", "owns", "runs_job", "get_heartbeat", "reset",
    "job_work", "register_jobs", "start_heartbeat", "submit", "job_for_action",
    "run_as_job", "adopt_thymos", "spell_budget", "adopt_grimoire",
    "submit_event_spell", "adopt_day_phases", "adopt", "RefusedResult",
]
