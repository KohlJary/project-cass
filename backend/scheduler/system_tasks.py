"""
System Task Registration - Crontab-style periodic tasks.

Registers all system-level tasks with Synkratos.
"""

import logging
from typing import Any, Dict
from functools import partial

from .core import ScheduledTask, TaskPriority, create_task
from .budget import TaskCategory
from .handlers import (
    github_metrics_handler,
    idle_summarization_handler,
    daily_journal_handler,
    rhythm_phase_handler,
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
            - rhythm_manager
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

    # GitHub metrics - every 6 hours
    if managers.get("github_metrics_manager"):
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
    if managers.get("conversation_manager") and managers.get("memory"):
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
    if managers.get("generate_missing_journals"):
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
            ),
            cron="5 0 * * *",  # 00:05 daily
            estimated_cost_usd=0.20,
        ))
        logger.info("Registered: daily_journal (00:05 daily)")

    # Rhythm phase monitor - every 5 minutes
    if managers.get("rhythm_manager"):
        scheduler.register_system_task(create_task(
            name="rhythm_phase_check",
            category=TaskCategory.SYSTEM,
            priority=TaskPriority.NORMAL,
            handler=partial(
                rhythm_phase_handler,
                rhythm_manager=managers["rhythm_manager"],
                runners=managers.get("runners", {}),
                self_model_graph=managers.get("self_model_graph"),
            ),
            interval_seconds=5 * 60,  # 5 minutes
            estimated_cost_usd=0.0,  # Check is free, sessions track their own cost
        ))
        logger.info("Registered: rhythm_phase_check (every 5 minutes)")

    # Autonomous research - only register if not in supervised mode
    if managers.get("research_scheduler"):
        # Try to get mode from config, default to supervised if not available
        research_sched = managers["research_scheduler"]
        mode = None
        if hasattr(research_sched, 'config') and hasattr(research_sched.config, 'mode'):
            mode = research_sched.config.mode
        mode_value = mode.value if mode else "supervised"

        if mode_value == "supervised":
            logger.info("Skipping autonomous_research registration (supervised mode - manual only)")
        else:
            scheduler.register_system_task(create_task(
                name="autonomous_research",
                category=TaskCategory.RESEARCH,
                priority=TaskPriority.LOW,
                handler=partial(
                    autonomous_research_handler,
                    scheduler=managers["research_scheduler"],
                    mode=mode_value,
                    max_tasks=5,
                ),
                interval_seconds=5 * 60,  # 5 minutes
                estimated_cost_usd=0.10,
            ))
            logger.info(f"Registered: autonomous_research (every 5 min, mode: {mode_value})")

    # Goal refinement - daily at 09:00
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
        "rhythm_phase_check": {
            "description": "Monitor and trigger rhythm phase sessions",
            "interval": "every 5 minutes",
            "estimated_cost": "$0.00-0.50 (varies by session)",
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
