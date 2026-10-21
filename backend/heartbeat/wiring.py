"""
Which jobs Heartbeat owns, and the registration hook main_sdk calls.

Migration rule: a job has exactly one trigger path. main_sdk starts Heartbeat
*before* register_system_tasks; the old path (Synkratos system task, legacy
asyncio loop) skips a job only when a started Heartbeat has it registered
(`owns`). So if the `heartbeat` lever is off, or Heartbeat fails to start, the
old path runs everything exactly as before.

Migrated jobs keep their old levers: the `scheduler` lever (which gated the
Synkratos loop they ran on) and their own `job_*` lever, both checked at
dispatch time.

The `heartbeat` lever is read once at boot, so flipping it needs a restart.
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
    """True when a started Heartbeat runs this job, so the old path must skip it."""
    return _heartbeat is not None and job_name in _heartbeat.registry


runs_job = owns  # alias used by the legacy-fallback guard in main_sdk


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
            lever=("scheduler", "job_github_metrics"),
            budget_class=TaskCategory.SYSTEM,
            estimated_cost_usd=0.01,
        ))

    hb.register(Work(
        name="goal_refinement",
        # async def with only blocking SQLite inside: run it off the loop.
        run=partial(goal_refinement_handler, daemon_id=managers.get("daemon_id")),
        offload=True,
        trigger=Cron("0 9 * * *"),
        lever=("scheduler", "job_goal_refinement"),
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
    _heartbeat = hb  # only after a confirmed start: owns() depends on it
    return hb
