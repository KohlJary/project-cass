"""
One research queue, one runner (#60).

The queue is the wiki research queue (`research_tasks`, wiki.research.ResearchQueue).
The runner is ResearchRunner below: everything that runs research takes a task
off that queue and hands it to `ResearchRunner.execute()`, which

1. picks the task's step (red_link, question, deepening, exploration, or a
   research session with its engine),
2. resolves the model for each of the step's call sites through model routing
   (llm_config; an admin override wins, else the call site's default, which is
   the model that step ran before #60) and records it on the result,
3. runs the step's executor, and
4. completes the task in the queue (history, follow-up red links and
   explorations), as the wiki scheduler did.

What each step writes is unchanged: wiki steps write wiki pages; research
sessions write their research_sessions row, research notes (and their wiki
pages), the self-model observation and the research journal, all from inside
their session runner as before.

Old entry points are thin wrappers:

* wiki.scheduler.ResearchScheduler.run_single_task / run_batch /
  run_batch_by_type delegate here, so the autonomous_research job, the legacy
  loop, the research.* actions (spells, phase queue, Synkratos) and the wiki
  admin routes all run through this runner.
* Research sessions (admin "start", Cass's initiate_autonomous_research tool,
  approved session requests, the session.research action) enqueue a session
  task and run it at once through `start_session()` / `run_session()`.

Budget: the steps call the same call sites as before, so the budget gate
(scheduler/budget.py BUDGET_COUNTED_CALL_SITES) counts exactly what it counted.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from wiki.research import (
    ExplorationContext,
    ProgressReport,
    ResearchQueue,
    ResearchTask,
    TaskResult,
    TaskStatus,
    TaskType,
    create_task_id,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Step:
    name: str
    call_sites: Tuple[str, ...]
    description: str


# Every step and the call sites it makes LLM calls through. The defaults of
# these call sites (llm_config.CALL_SITES) are the models each step ran before
# #60: Ollama for the wiki steps, the session runner's model for sessions.
STEPS: Dict[str, Step] = {s.name: s for s in (
    Step("red_link", ("wiki.page_content",), "web search, then write the missing wiki page"),
    Step("question", (), "web search only; no LLM call"),
    Step("deepening", ("wiki.resynthesis", "wiki.resynthesis_validation"), "resynthesize a wiki page"),
    Step("exploration", ("wiki.page_content", "wiki.exploration_synthesis"),
         "write the related red-link pages, then synthesize an answer page"),
    Step("session.legacy", ("session.legacy",),
         "ResearchSessionRunner tool loop (Tavily search, notes, journal)"),
    Step("session.generic", ("session.generic",),
         "GenericSessionRunner research session (session.research action)"),
)}

SESSION_ENGINES = ("legacy", "generic")


def step_for(task: ResearchTask) -> Step:
    if task.task_type == TaskType.SESSION:
        engine = (task.params or {}).get("engine", "legacy")
        return STEPS[f"session.{engine}"]
    return STEPS[task.task_type.value]


def resolve_step_models(step: Step, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """call site -> "provider:model" that routing resolves for this step now."""
    # The same resolution llm_caller does for each call (override, else the
    # call site's default). Every name in STEPS is a registered call site
    # (tests/test_research_pipeline.py checks it).
    from llm_config import LLMConfigManager
    out = {}
    for site in step.call_sites:
        try:
            assignment = LLMConfigManager().resolve(site, (defaults or {}).get(site))
        except Exception as e:  # never let bookkeeping stop research
            logger.warning(f"research runner: could not resolve {site}: {e}")
            assignment = None
        out[site] = f"{assignment.provider}:{assignment.model_id}" if assignment else "skipped"
    return out


def _session_default(engine: str, runner: Any):
    """The model a session runner passes as its call site default (from_caller)."""
    from llm_config import ModelAssignment
    if runner is None:
        return None
    if engine == "legacy":
        if getattr(runner, "use_haiku", False):
            return ModelAssignment("anthropic", getattr(runner, "haiku_model", None) or "claude-haiku-4-5-20251001")
        if getattr(runner, "ollama_model", None):
            return ModelAssignment("ollama", runner.ollama_model)
        return None
    model = getattr(runner, "model", None)
    if isinstance(model, str) and model:
        return ModelAssignment("anthropic", model)
    return None


# Session task ids taken by a runner in this process and not yet completed.
# fail_interrupted_sessions() leaves these alone.
_LIVE_SESSION_TASKS: set = set()


def fail_interrupted_sessions(error: str = "interrupted by restart") -> Dict[str, list]:
    """For every daemon, fail session tasks left in_progress that no session
    in this process owns (called at startup: a restart mid-session leaves them
    in_progress forever). Returns daemon_id -> failed task ids."""
    from database import get_db
    with get_db() as conn:
        daemon_ids = [row[0] for row in conn.execute("SELECT id FROM daemons").fetchall()]
    out = {}
    for daemon_id in daemon_ids:
        failed = ResearchQueue(daemon_id=daemon_id).fail_interrupted_sessions(
            frozenset(_LIVE_SESSION_TASKS), error=error)
        if failed:
            out[daemon_id] = failed
    return out


# Automatic wiki research tasks per local day (RESEARCH_MAX_TASKS_PER_DAY overrides).
# 15 matches what the research budget share already allowed at the flat $0.10 a task.
DEFAULT_MAX_TASKS_PER_DAY = 15


class ResearchRunner:
    """Runs research tasks from the one queue. See the module docstring."""

    def __init__(self, queue: Optional[ResearchQueue] = None, wiki_scheduler=None):
        self.wiki_scheduler = wiki_scheduler
        if queue is None and wiki_scheduler is not None:
            queue = wiki_scheduler.queue
        self.queue = queue if queue is not None else ResearchQueue()
        self._watchers: set = set()

    # --- execution ------------------------------------------------------------

    async def execute(self, task: ResearchTask, *, session_runner: Any = None) -> TaskResult:
        """Run one task's step and return its result (the queue is not touched)."""
        step = step_for(task)
        if task.task_type == TaskType.SESSION:
            engine = step.name.split(".", 1)[1]
            models = resolve_step_models(step, {s: _session_default(engine, session_runner) for s in step.call_sites})
            result = TaskResult(success=False, error="session tasks run through start_session/run_session")
        else:
            models = resolve_step_models(step)
            if self.wiki_scheduler is None:
                result = TaskResult(success=False, error="wiki scheduler not available")
            else:
                logger.info(f"research runner: {step.name} [[{task.target}]] models={models}")
                result = await self.wiki_scheduler.execute_task(task)
        result.models = models
        return result

    async def run_task(self, task: ResearchTask) -> ProgressReport:
        """Execute a task already taken off the queue, then complete it there."""
        result = await self.execute(task)
        self.queue.complete(task.task_id, result)
        if (task.task_type == TaskType.DEEPENING and result.success
                and self.wiki_scheduler is not None):
            self.wiki_scheduler.detector.record_deepening(task.target)
        followups = self._queue_followups(task, result)
        return ProgressReport(
            report_id=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            created_at=datetime.now(),
            session_type="single",
            tasks_completed=1 if result.success else 0,
            tasks_failed=0 if result.success else 1,
            pages_created=result.pages_created,
            pages_updated=result.pages_updated,
            key_insights=result.insights,
            new_questions=result.questions_raised,
            connections_formed=result.connections_formed,
            followup_tasks_queued=followups,
            task_summaries=[{
                "task_id": task.task_id,
                "type": task.task_type.value,
                "target": task.target,
                "success": result.success,
                "summary": result.summary,
                "models": result.models,
            }],
        )

    def _queue_followups(self, task: ResearchTask, result: TaskResult) -> int:
        """New red links and follow-up explorations, as the wiki scheduler queued them."""
        followups = 0
        for red_link in result.new_red_links[:5]:
            if not self.queue.exists(red_link, TaskType.RED_LINK):
                self.queue.add(ResearchTask(
                    task_id=create_task_id(),
                    task_type=TaskType.RED_LINK,
                    target=red_link,
                    context=f"Generated from researching [[{task.target}]]",
                    priority=0.5,
                    source_page=task.target,
                    source_type="auto",
                ))
                followups += 1
        if task.task_type == TaskType.EXPLORATION and task.exploration and result.questions_raised:
            for follow_up_q in result.questions_raised[:2]:
                self.queue.add(ResearchTask(
                    task_id=create_task_id(),
                    task_type=TaskType.EXPLORATION,
                    target=follow_up_q[:80],
                    context=f"Follow-up from exploration of {task.exploration.question[:50]}",
                    priority=task.priority * 0.9,
                    source_type="exploration",
                    exploration=ExplorationContext(
                        question=follow_up_q,
                        rationale=f"This question emerged from exploring: {task.exploration.question}",
                        related_red_links=[],
                        source_pages=task.exploration.source_pages + result.pages_created[:2],
                        domain_tags=task.exploration.domain_tags,
                    ),
                ))
                followups += 1
        return followups

    # --- the wiki batch entry points (ResearchScheduler delegates here) --------

    def daily_cap_reached(self) -> bool:
        """True once today's automatic wiki tasks reach RESEARCH_MAX_TASKS_PER_DAY.

        The budget gate counts a flat estimate per task and nothing meters
        search-API credits (Tavily), so continuous mode needs a hard ceiling.
        0 or a negative value turns the cap off. Not capped: a task picked by
        id, session tasks, and approved proposals executed through the wiki
        routes (`execute`, which takes nothing off the queue).
        """
        try:
            cap = int(os.getenv("RESEARCH_MAX_TASKS_PER_DAY", str(DEFAULT_MAX_TASKS_PER_DAY)))
        except ValueError:
            cap = DEFAULT_MAX_TASKS_PER_DAY
        if cap <= 0:
            return False
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        started = self.queue.count_started_since(midnight)
        if started >= cap:
            logger.info(f"research runner: daily cap reached ({started}/{cap}); not starting another task")
            return True
        return False

    async def run_single_task(self, task_id: Optional[str] = None) -> Optional[ProgressReport]:
        # A task picked by id is someone's explicit choice; only automatic picks are capped.
        if not task_id and self.daily_cap_reached():
            return None
        task = self.queue.pop(task_id) if task_id else self.queue.pop_next()
        if not task:
            return None
        return await self.run_task(task)

    async def run_batch(self, max_tasks: int, delay: float = 0.0, graph_stats: Optional[dict] = None,
                        task_type: Optional[TaskType] = None, report_id: Optional[str] = None,
                        session_type: str = "batch") -> ProgressReport:
        reports = []
        for _ in range(max_tasks):
            if task_type is not None:
                if self.daily_cap_reached():
                    break
                task = self.queue.pop_next_by_type(task_type)
                report = await self.run_task(task) if task else None
            else:
                report = await self.run_single_task()
            if not report:
                break
            reports.append(report)
            await asyncio.sleep(delay)
        combined = ProgressReport(
            report_id=report_id or f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            created_at=datetime.now(),
            session_type=session_type,
            graph_stats=graph_stats() if callable(graph_stats) else graph_stats,
        )
        for r in reports:
            combined.task_summaries.extend(r.task_summaries)
            combined.pages_created.extend(r.pages_created)
            combined.pages_updated.extend(r.pages_updated)
            combined.key_insights.extend(r.key_insights)
            combined.new_questions.extend(r.new_questions)
            combined.connections_formed.extend(r.connections_formed)
            combined.followup_tasks_queued += r.followup_tasks_queued
            combined.tasks_completed += r.tasks_completed
            combined.tasks_failed += r.tasks_failed
        return combined

    # --- research sessions ------------------------------------------------------

    def enqueue_session(self, *, engine: str, focus: Optional[str], duration_minutes: int,
                        mode: str = "explore", trigger: str = "manual",
                        focus_item_id: Optional[str] = None, priority: float = 0.5,
                        extra: Optional[Dict[str, Any]] = None) -> ResearchTask:
        if engine not in SESSION_ENGINES:
            raise ValueError(f"unknown research session engine {engine!r}")
        params = {"engine": engine, "duration_minutes": duration_minutes, "mode": mode,
                  "trigger": trigger}
        if focus_item_id:
            params["focus_item_id"] = focus_item_id
        if extra:
            params.update(extra)
        task = ResearchTask(
            task_id=create_task_id(),
            task_type=TaskType.SESSION,
            target=(focus or "Open research")[:200],
            context=f"Research session ({trigger})",
            priority=priority,
            source_type=trigger,
            estimated_duration=f"{duration_minutes}m",
            params=params,
        )
        self.queue.add(task)
        return task

    def _take(self, task: ResearchTask) -> ResearchTask:
        taken = self.queue.pop(task.task_id)
        if taken is None:
            raise RuntimeError(f"research task {task.task_id} is no longer queued")
        return taken

    def _queue_session(self, task: Optional[ResearchTask], **enqueue_kwargs) -> Optional[ResearchTask]:
        """Enqueue (unless given) and take a session task. Queue bookkeeping
        never stops a session that ran before #60: on a queue error the session
        still runs, unrecorded, and the error is logged."""
        try:
            if task is None:
                task = self.enqueue_session(**enqueue_kwargs)
            taken = self._take(task)
            _LIVE_SESSION_TASKS.add(taken.task_id)
            return taken
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"research runner: could not queue research session: {e}")
            return None

    def _complete(self, task: Optional[ResearchTask], result: TaskResult) -> None:
        if task is None:
            return
        try:
            self.queue.complete(task.task_id, result)
        except Exception as e:
            logger.error(f"research runner: could not complete research task {task.task_id}: {e}")
        finally:
            _LIVE_SESSION_TASKS.discard(task.task_id)

    async def start_session(self, runner: Any, *, focus: Optional[str], duration_minutes: int,
                            mode: str = "explore", trigger: str = "manual",
                            focus_item_id: Optional[str] = None, task: Optional[ResearchTask] = None):
        """Queue a legacy research session and start it on `runner` now.

        Returns what runner.start_session returns (the session runs in the
        background as before); the queue task completes when the session ends.
        """
        task = self._queue_session(task, engine="legacy", focus=focus, duration_minutes=duration_minutes,
                                   mode=mode, trigger=trigger, focus_item_id=focus_item_id)
        models = resolve_step_models(STEPS["session.legacy"],
                                     {"session.legacy": _session_default("legacy", runner)})
        logger.info(f"research runner: session.legacy '{focus}' models={models}")
        kwargs = dict(duration_minutes=duration_minutes, focus=focus, mode=mode, trigger=trigger)
        if focus_item_id:
            kwargs["focus_item_id"] = focus_item_id
        try:
            session = await runner.start_session(**kwargs)
        except Exception as e:
            self._complete(task, TaskResult(success=False, error=str(e), models=models))
            raise
        session_id = getattr(session, "session_id", None) or getattr(session, "id", None)
        if task is None:
            return session
        if session_id:
            task.params["session_id"] = session_id
            try:
                self.queue.update(task)
            except Exception as e:
                logger.error(f"research runner: could not record session id on {task.task_id}: {e}")
        watcher = asyncio.ensure_future(self._finish_legacy_session(task, runner, session_id, models))
        self._watchers.add(watcher)
        watcher.add_done_callback(self._watchers.discard)
        return session

    async def _finish_legacy_session(self, task: ResearchTask, runner: Any,
                                     session_id: Optional[str], models: Dict[str, str]) -> None:
        loop_task = getattr(runner, "_current_task", None)
        if loop_task is not None:
            try:
                await asyncio.shield(loop_task)
            except BaseException:  # the session's own loop reports its errors
                pass
        data: Dict[str, Any] = {}
        manager = getattr(runner, "session_manager", None)
        if manager is not None and session_id:
            try:
                data = manager.get_session(session_id) or {}
            except Exception as e:
                logger.warning(f"research runner: could not read session {session_id}: {e}")
        status = data.get("status", "unknown")
        self._complete(task, TaskResult(
            success=status == "completed",
            summary=data.get("summary") or data.get("findings_summary"),
            insights=[data["findings_summary"]] if data.get("findings_summary") else [],
            error=None if status == "completed" else f"session ended with status {status}",
            models=models,
        ))

    async def run_session(self, run: Callable[[], Awaitable[Any]], *, runner: Any = None,
                          focus: Optional[str], duration_minutes: int, mode: str = "explore",
                          trigger: str = "action"):
        """Queue a generic-engine research session and run it to completion now.

        `run` is the session executor (session_handlers' GenericSessionRunner
        call); its return value (an ActionResult) is passed back unchanged.
        """
        task = self._queue_session(None, engine="generic", focus=focus,
                                   duration_minutes=duration_minutes, mode=mode, trigger=trigger)
        models = resolve_step_models(STEPS["session.generic"],
                                     {"session.generic": _session_default("generic", runner)})
        logger.info(f"research runner: session.generic '{focus}' models={models}")
        try:
            outcome = await run()
        except Exception as e:
            self._complete(task, TaskResult(success=False, error=str(e), models=models))
            raise
        success = bool(getattr(outcome, "success", False))
        self._complete(task, TaskResult(
            success=success,
            summary=getattr(outcome, "message", None),
            error=None if success else getattr(outcome, "message", "session failed"),
            models=models,
        ))
        return outcome

    async def run_due_session_requests(self, requests, runner: Any) -> list:
        """Start approved, due research session requests (research_scheduler.py).

        Before #60 nothing called check_and_trigger_due_sessions, so approved
        requests never ran. This runs the due research-type ones through the
        queue. Called by the autonomous_research job when the
        `research_session_requests` lever is on (default off).
        """
        started = []
        if runner is None or getattr(runner, "is_running", False):
            return started
        for schedule in requests.get_due_schedules():
            if getattr(schedule.session_type, "value", schedule.session_type) != "research":
                continue
            try:
                session = await self.start_session(
                    runner,
                    focus=schedule.focus_description,
                    duration_minutes=schedule.duration_minutes,
                    mode=schedule.mode,
                    trigger="scheduled",
                    focus_item_id=schedule.focus_item_id,
                )
            except Exception as e:
                logger.error(f"research runner: scheduled session {schedule.schedule_id} failed to start: {e}")
                continue
            session_id = getattr(session, "session_id", None) or getattr(session, "id", None)
            if session_id:
                requests.mark_session_started(schedule.schedule_id, session_id)
            started.append(schedule.schedule_id)
            break  # one session runner, one session at a time
        return started


_queue: Optional[ResearchQueue] = None


def get_research_pipeline(wiki_scheduler=None) -> ResearchRunner:
    """A runner on the shared queue (the wiki scheduler's, when it exists)."""
    global _queue
    if wiki_scheduler is None:
        try:
            import wiki
            wiki_scheduler = wiki.get_scheduler()
        except Exception:
            wiki_scheduler = None
    if wiki_scheduler is not None:
        return ResearchRunner(wiki_scheduler=wiki_scheduler)
    if _queue is None:
        _queue = ResearchQueue()
    return ResearchRunner(queue=_queue)


__all__ = [
    "Step", "STEPS", "SESSION_ENGINES", "step_for", "resolve_step_models",
    "ResearchRunner", "get_research_pipeline", "TaskStatus", "fail_interrupted_sessions",
]
