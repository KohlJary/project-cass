"""
System Task Registration - Crontab-style periodic tasks.

Registers all system-level tasks with Synkratos.
"""

import logging
from typing import Any, Dict
from functools import partial

from features import is_enabled

from .core import ScheduledTask, TaskPriority, create_task
from .budget import TaskCategory
from .handlers import (
    github_metrics_handler,
    idle_summarization_handler,
    daily_journal_handler,
    autonomous_research_handler,
    goal_refinement_handler,
)

logger = logging.getLogger(__name__)


def register_system_tasks(
    scheduler,
    managers: Dict[str, Any],
    enabled: bool = False,  # Start disabled by default
) -> None:
    """
    Register all system-level periodic tasks.

    Args:
        scheduler: Synkratos instance
        managers: Dict of manager instances needed by handlers:
            - github_metrics_manager
            - conversation_manager
            - memory
            - token_tracker
            - runners (dict of activity runners)
            - self_model_graph
            - generate_missing_journals (function)
            - generate_nightly_dream (function)
            - self_manager
            - data_dir
            - research_scheduler
        enabled: Whether to actually run these tasks (feature flag)
    """
    if not enabled:
        logger.info("System tasks registration skipped (feature flag disabled)")
        return

    # Each job also has its own feature lever (features.py, job_*), so a test
    # battery or CASS_PROFILE can switch single jobs off.

    # GitHub metrics - every 6 hours
    if managers.get("github_metrics_manager") and is_enabled("job_github_metrics"):
        scheduler.register_system_task(create_task(
            name="github_metrics",
            category=TaskCategory.SYSTEM,
            priority=TaskPriority.LOW,
            handler=partial(
                github_metrics_handler,
                github_metrics_manager=managers["github_metrics_manager"]
            ),
            interval_seconds=6 * 60 * 60,  # 6 hours
            estimated_cost_usd=0.01,
        ))
        logger.info("Registered: github_metrics (every 6 hours)")

    # Idle summarization - every hour
    if managers.get("conversation_manager") and managers.get("memory") and is_enabled("job_idle_summarization"):
        scheduler.register_system_task(create_task(
            name="idle_summarization",
            category=TaskCategory.SYSTEM,
            priority=TaskPriority.NORMAL,
            handler=partial(
                idle_summarization_handler,
                conversation_manager=managers["conversation_manager"],
                memory=managers["memory"],
                token_tracker=managers.get("token_tracker"),
            ),
            interval_seconds=60 * 60,  # 1 hour
            requires_idle=True,
            estimated_cost_usd=0.05,
        ))
        logger.info("Registered: idle_summarization (every hour, idle-only)")

    # Daily journal - 00:05 daily (5 minutes after midnight)
    if managers.get("generate_missing_journals") and is_enabled("job_daily_journal"):
        scheduler.register_system_task(create_task(
            name="daily_journal",
            category=TaskCategory.SYSTEM,
            priority=TaskPriority.HIGH,
            handler=partial(
                daily_journal_handler,
                generate_missing_journals_func=managers.get("generate_missing_journals"),
                generate_nightly_dream_func=managers.get("generate_nightly_dream"),
                self_manager=managers.get("self_manager"),
                data_dir=managers.get("data_dir"),
                conversation_manager=managers.get("conversation_manager"),
            ),
            cron="5 0 * * *",  # 00:05 daily
            estimated_cost_usd=0.20,
        ))
        logger.info("Registered: daily_journal (00:05 daily)")

    # Autonomous research. Always registered; the handler reads the wiki
    # scheduler's mode on every run, so supervised mode is a no-op and
    # switching mode from the admin UI takes effect without a restart.
    # (It used to read the mode once here, from the wrong scheduler class,
    # so it was never registered at all.)
    if managers.get("research_scheduler") and is_enabled("job_autonomous_research"):
        scheduler.register_system_task(create_task(
            name="autonomous_research",
            category=TaskCategory.RESEARCH,
            priority=TaskPriority.LOW,
            handler=partial(
                autonomous_research_handler,
                scheduler=managers["research_scheduler"],
                mode=None,  # read live from scheduler.config.mode
                max_tasks=5,
            ),
            interval_seconds=5 * 60,  # 5 minutes
            estimated_cost_usd=0.10,
        ))
        logger.info("Registered: autonomous_research (every 5 min, mode read each run)")

    # Goal refinement - daily at 09:00
    if not is_enabled("job_goal_refinement"):
        return
    scheduler.register_system_task(create_task(
        name="goal_refinement",
        category=TaskCategory.SYSTEM,
        priority=TaskPriority.LOW,
        handler=partial(
            goal_refinement_handler,
            daemon_id=managers.get("daemon_id"),
        ),
        cron="0 9 * * *",  # 09:00 daily
        estimated_cost_usd=0.0,  # Just scans, doesn't generate
    ))
    logger.info("Registered: goal_refinement (09:00 daily)")


def get_system_task_config() -> Dict[str, Dict[str, Any]]:
    """
    Get the configuration for all system tasks.

    Useful for admin UI to show task schedules.
    """
    return {
        "github_metrics": {
            "description": "Fetch GitHub repository metrics",
            "interval": "every 6 hours",
            "estimated_cost": "$0.01",
            "category": "system",
        },
        "idle_summarization": {
            "description": "Summarize idle conversations",
            "interval": "every hour (when idle)",
            "estimated_cost": "$0.01-0.10",
            "category": "system",
        },
        "daily_journal": {
            "description": "Generate daily journal and nightly dream",
            "interval": "00:05 daily",
            "estimated_cost": "$0.10-0.20",
            "category": "system",
        },
        "autonomous_research": {
            "description": "Run autonomous wiki research",
            "interval": "every 5 minutes",
            "estimated_cost": "$0.10-0.50",
            "category": "research",
        },
        "goal_refinement": {
            "description": "Check for goals needing detailed descriptions/criteria",
            "interval": "09:00 daily",
            "estimated_cost": "$0.00 (scan only)",
            "category": "system",
        },
    }
