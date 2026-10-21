"""
Which jobs Heartbeat owns, and the registration hook main_sdk calls.

Migration rule: a job has exactly one trigger path. When the `heartbeat`
lever is on, the jobs in HEARTBEAT_JOBS register here and the old path
(Synkratos system task, legacy asyncio loop) skips them. When it is off,
nothing here runs and the old path is unchanged.

The lever is read once at boot: both sides of the decision are made in the
same startup pass, so flipping it needs a restart.
"""
from __future__ import annotations

import logging
from functools import partial
from typing import Any, Callable, Dict, Optional

from features import is_enabled

from .core import Heartbeat
from .registry import Cron, Every, Work

logger = logging.getLogger(__name__)

# Migrated so far: low-stakes jobs with no LLM spend.
HEARTBEAT_JOBS = frozenset({"github_metrics", "goal_refinement"})

_heartbeat: Optional[Heartbeat] = None


def owns(job_name: str) -> bool:
    """True when Heartbeat, not the old scheduler, runs this job."""
    return job_name in HEARTBEAT_JOBS and is_enabled("heartbeat")


def runs_job(job_name: str) -> bool:
    """True when a started Heartbeat has this job registered (legacy-loop guard)."""
    return _heartbeat is not None and job_name in _heartbeat.registry


def get_heartbeat() -> Optional[Heartbeat]:
    return _heartbeat


def register_migrated_jobs(hb: Heartbeat, managers: Dict[str, Any]) -> None:
    from scheduler.budget import TaskCategory
    from scheduler.handlers import github_metrics_handler, goal_refinement_handler

    gm = managers.get("github_metrics_manager")
    if gm is not None:
        hb.register(Work(
            name="github_metrics",
            run=partial(github_metrics_handler, github_metrics_manager=gm),
            trigger=Every(6 * 60 * 60),
            lever="job_github_metrics",
            budget_class=TaskCategory.SYSTEM,
            estimated_cost_usd=0.01,
        ))

    hb.register(Work(
        name="goal_refinement",
        # async def with only blocking SQLite inside: run it off the loop.
        run=partial(goal_refinement_handler, daemon_id=managers.get("daemon_id")),
        offload=True,
        trigger=Cron("0 9 * * *"),
        lever="job_goal_refinement",
        budget_class=TaskCategory.SYSTEM,
        estimated_cost_usd=0.0,
    ))


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
    register_migrated_jobs(hb, managers)
    await hb.start()
    _heartbeat = hb
    return hb
