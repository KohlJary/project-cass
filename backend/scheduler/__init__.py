"""
Unified Scheduler - Centralized Task Orchestration for Cass Vessel.

Consolidates all background task management:
- Crontab-style scheduling for system tasks
- Categorical queues with priority for autonomous work
- Global budget awareness and enforcement
"""

from .budget import BudgetManager, BudgetConfig, TaskCategory
from .core import (
    UnifiedScheduler,
    ScheduledTask,
    TaskQueue,
    TaskPriority,
    TaskStatus,
    create_task,
)
from .handlers import (
    HandlerResult,
    github_metrics_handler,
    idle_summarization_handler,
    daily_journal_handler,
    rhythm_phase_handler,
    autonomous_research_handler,
)

__all__ = [
    # Core
    "UnifiedScheduler",
    "ScheduledTask",
    "TaskQueue",
    "TaskCategory",
    "TaskPriority",
    "TaskStatus",
    "BudgetManager",
    "BudgetConfig",
    "create_task",
    # Handlers
    "HandlerResult",
    "github_metrics_handler",
    "idle_summarization_handler",
    "daily_journal_handler",
    "rhythm_phase_handler",
    "autonomous_research_handler",
]
