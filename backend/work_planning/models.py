"""
Work Planning Models - Cass's taskboard and calendar infrastructure.

These are Cass's own planning tools, not user-facing features.
WorkItems are units of work she plans to do, composed from atomic actions.
ScheduleSlots are when she plans to do that work.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class WorkStatus(Enum):
    """Status of a work item."""
    PLANNED = "planned"      # Created, not yet scheduled
    SCHEDULED = "scheduled"  # Has a schedule slot
    READY = "ready"          # Dependencies met, can run
    RUNNING = "running"      # Currently executing
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"        # Execution failed
    CANCELLED = "cancelled"  # Manually cancelled


class WorkPriority(Enum):
    """Priority levels for work items."""
    CRITICAL = 0   # Must happen (system health, user requests)
    HIGH = 1       # Important autonomous work
    NORMAL = 2     # Standard priority
    LOW = 3        # Background/fill work
    IDLE = 4       # Only when nothing else


class ApprovalStatus(Enum):
    """Approval status for work requiring human sign-off."""
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SlotStatus(Enum):
    """Status of a schedule slot."""
    SCHEDULED = "scheduled"
    EXECUTING = "executing"
    COMPLETED = "completed"
    SKIPPED = "skipped"  # Missed window or cancelled


@dataclass
class RecurrencePattern:
    """Pattern for recurring schedule slots."""
    type: str  # "daily", "weekly", "hourly", "cron"
    value: str  # "09:00" for daily, "Mon,Wed,Fri" for weekly, cron expression
    end_date: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "value": self.value,
            "end_date": self.end_date.isoformat() if self.end_date else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecurrencePattern":
        return cls(
            type=data["type"],
            value=data["value"],
            end_date=datetime.fromisoformat(data["end_date"]) if data.get("end_date") else None,
        )


@dataclass
class WorkItem:
    """
    A unit of work Cass plans to do.

    Composed from atomic actions, optionally linked to a goal,
    with scheduling constraints and approval tracking.
    """
    id: str
    title: str
    description: str = ""

    # Composition - what actions make up this work
    action_sequence: List[str] = field(default_factory=list)  # Ordered atomic action IDs

    # Context - what this work is for
    goal_id: Optional[str] = None  # What goal this serves
    category: str = "general"  # reflection, research, growth, etc.

    # Scheduling constraints
    priority: WorkPriority = WorkPriority.NORMAL
    estimated_duration_minutes: int = 30
    estimated_cost_usd: float = 0.0
    deadline: Optional[datetime] = None
    dependencies: List[str] = field(default_factory=list)  # Other work_item IDs that must complete first

    # Approval - for higher autonomy work
    requires_approval: bool = False
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None

    # Execution state
    status: WorkStatus = WorkStatus.PLANNED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    actual_cost_usd: float = 0.0
    result_summary: Optional[str] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "cass"  # Usually "cass", could be "synkratos" for auto-generated

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "action_sequence": self.action_sequence,
            "goal_id": self.goal_id,
            "category": self.category,
            "priority": self.priority.value,
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "estimated_cost_usd": self.estimated_cost_usd,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "dependencies": self.dependencies,
            "requires_approval": self.requires_approval,
            "approval_status": self.approval_status.value,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "actual_cost_usd": self.actual_cost_usd,
            "result_summary": self.result_summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkItem":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            action_sequence=data.get("action_sequence", []),
            goal_id=data.get("goal_id"),
            category=data.get("category", "general"),
            priority=WorkPriority(data.get("priority", 2)),
            estimated_duration_minutes=data.get("estimated_duration_minutes", 30),
            estimated_cost_usd=data.get("estimated_cost_usd", 0.0),
            deadline=datetime.fromisoformat(data["deadline"]) if data.get("deadline") else None,
            dependencies=data.get("dependencies", []),
            requires_approval=data.get("requires_approval", False),
            approval_status=ApprovalStatus(data.get("approval_status", "not_required")),
            approved_by=data.get("approved_by"),
            approved_at=datetime.fromisoformat(data["approved_at"]) if data.get("approved_at") else None,
            status=WorkStatus(data.get("status", "planned")),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            actual_cost_usd=data.get("actual_cost_usd", 0.0),
            result_summary=data.get("result_summary"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            created_by=data.get("created_by", "cass"),
        )


@dataclass
class ScheduleSlot:
    """
    When Cass plans to do work. Her calendar.

    Can be linked to a specific work item, or left open for ad-hoc work.
    Supports recurrence for regular patterns (daily reflection, etc.).
    """
    id: str
    work_item_id: Optional[str] = None  # Can be open slot for ad-hoc work

    # Timing
    start_time: Optional[datetime] = None  # None = flexible timing
    end_time: Optional[datetime] = None
    duration_minutes: int = 30

    # Recurrence for regular work patterns
    recurrence: Optional[RecurrencePattern] = None

    # Constraints
    priority: int = 2  # 0-4, matches WorkPriority values
    budget_allocation_usd: float = 0.0
    requires_idle: bool = False  # Only run when no user activity

    # State
    status: SlotStatus = SlotStatus.SCHEDULED
    executed_at: Optional[datetime] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "work_item_id": self.work_item_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_minutes": self.duration_minutes,
            "recurrence": self.recurrence.to_dict() if self.recurrence else None,
            "priority": self.priority,
            "budget_allocation_usd": self.budget_allocation_usd,
            "requires_idle": self.requires_idle,
            "status": self.status.value,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleSlot":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            work_item_id=data.get("work_item_id"),
            start_time=datetime.fromisoformat(data["start_time"]) if data.get("start_time") else None,
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            duration_minutes=data.get("duration_minutes", 30),
            recurrence=RecurrencePattern.from_dict(data["recurrence"]) if data.get("recurrence") else None,
            priority=data.get("priority", 2),
            budget_allocation_usd=data.get("budget_allocation_usd", 0.0),
            requires_idle=data.get("requires_idle", False),
            status=SlotStatus(data.get("status", "scheduled")),
            executed_at=datetime.fromisoformat(data["executed_at"]) if data.get("executed_at") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            notes=data.get("notes"),
        )
