"""
Work Planning Package - Cass's taskboard and calendar infrastructure.

These are Cass's own planning tools for autonomous work, not user-facing features.
WorkItems are units of work she plans to do, composed from atomic actions.
ScheduleSlots are when she plans to do that work.
"""

from .models import (
    WorkItem,
    WorkStatus,
    WorkPriority,
    ApprovalStatus,
    ScheduleSlot,
    SlotStatus,
    RecurrencePattern,
)
from .work_manager import WorkItemManager
from .schedule_manager import ScheduleManager

__all__ = [
    # Models
    "WorkItem",
    "WorkStatus",
    "WorkPriority",
    "ApprovalStatus",
    "ScheduleSlot",
    "SlotStatus",
    "RecurrencePattern",
    # Managers
    "WorkItemManager",
    "ScheduleManager",
]
