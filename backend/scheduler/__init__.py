"""
Synkratos - The Universal Work Orchestrator.

One place for "what needs my attention?" - consolidates:
- Scheduled work (crontab-style system tasks)
- Autonomous work (budget-aware categorical queues)
- Pending approvals (goals, research requests, actions)
"""

from .budget import BudgetManager, BudgetConfig, TaskCategory
from .core import (
    Synkratos,
    ScheduledTask,
    TaskQueue,
    TaskPriority,
    TaskStatus,
    ApprovalType,
    ApprovalItem,
    create_task,
)
from .handlers import (
    HandlerResult,
    github_metrics_handler,
    idle_summarization_handler,
    daily_journal_handler,
    autonomous_research_handler,
)
from .approvals import register_approval_providers

# Backwards compatibility alias
UnifiedScheduler = Synkratos

__all__ = [
    # Core
    "Synkratos",
    "UnifiedScheduler",  # Alias for backwards compat
    "ScheduledTask",
    "TaskQueue",
    "TaskCategory",
    "TaskPriority",
    "TaskStatus",
    "ApprovalType",
    "ApprovalItem",
    "BudgetManager",
    "BudgetConfig",
    "create_task",
    # Handlers
    "HandlerResult",
    "github_metrics_handler",
    "idle_summarization_handler",
    "daily_journal_handler",
    "autonomous_research_handler",
    # Approvals
    "register_approval_providers",
]
