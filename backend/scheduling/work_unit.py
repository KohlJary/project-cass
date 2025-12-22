"""
WorkUnit model for autonomous scheduling.

A WorkUnit is a composable unit of work that can be scheduled and executed.
It wraps atomic actions and/or session runners into meaningful work blocks.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class WorkStatus(Enum):
    """Status of a work unit."""
    PLANNED = "planned"      # Created but not scheduled
    SCHEDULED = "scheduled"  # Scheduled for execution
    RUNNING = "running"      # Currently executing
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"        # Failed during execution
    CANCELLED = "cancelled"  # Cancelled before completion


class WorkPriority(Enum):
    """Priority levels for work units."""
    CRITICAL = 0  # Must run immediately
    HIGH = 1      # Run soon
    NORMAL = 2    # Default priority
    LOW = 3       # Run when convenient
    IDLE = 4      # Only when truly idle


@dataclass
class TimeWindow:
    """
    Preferred time window for scheduling work.

    Soft constraint - boosts scoring but doesn't block execution.
    """
    start_hour: int  # 0-23
    end_hour: int    # 0-23
    days: Optional[List[int]] = None  # 0=Monday, 6=Sunday, None=any day
    preference_weight: float = 1.0  # Higher = more preferred in this window

    def contains_time(self, dt: datetime) -> bool:
        """Check if datetime falls within this window."""
        hour = dt.hour
        day = dt.weekday()

        # Check day of week if specified
        if self.days is not None and day not in self.days:
            return False

        # Handle overnight windows (e.g., 22:00 - 06:00)
        if self.start_hour <= self.end_hour:
            return self.start_hour <= hour < self.end_hour
        else:
            return hour >= self.start_hour or hour < self.end_hour

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_hour": self.start_hour,
            "end_hour": self.end_hour,
            "days": self.days,
            "preference_weight": self.preference_weight,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimeWindow":
        return cls(
            start_hour=data["start_hour"],
            end_hour=data["end_hour"],
            days=data.get("days"),
            preference_weight=data.get("preference_weight", 1.0),
        )


@dataclass
class WorkUnit:
    """
    A composable unit of work for autonomous scheduling.

    Can represent:
    - A single session runner (reflection, research, etc.)
    - A composite of atomic actions
    - A custom work block

    Attributes:
        id: Unique identifier
        name: Human-readable name
        description: What this work accomplishes
        action_sequence: Ordered list of atomic action IDs to execute
        runner_key: Session runner to use (if this is a session-based work)
        template_id: Template this was instantiated from (if any)
        preferred_time_windows: When this work is best scheduled
        estimated_duration_minutes: Expected duration
        estimated_cost_usd: Expected token cost
        priority: Execution priority
        requires_idle: Only run when no user activity
        focus: What to focus on (growth edge, curiosity, etc.)
        motivation: Why Cass chose this work (filled by decision engine)
        status: Current status
        created_at: When this work unit was created
        started_at: When execution started
        completed_at: When execution finished
        result: Execution result data
    """
    id: str
    name: str
    description: str
    action_sequence: List[str] = field(default_factory=list)
    runner_key: Optional[str] = None
    template_id: Optional[str] = None
    preferred_time_windows: List[TimeWindow] = field(default_factory=list)
    estimated_duration_minutes: int = 30
    estimated_cost_usd: float = 0.0
    priority: WorkPriority = WorkPriority.NORMAL
    requires_idle: bool = False
    focus: Optional[str] = None
    motivation: Optional[str] = None
    status: WorkStatus = WorkStatus.PLANNED
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    # Category for budget tracking
    category: Optional[str] = None
    # Artifacts created during this work
    artifacts: List[Dict[str, str]] = field(default_factory=list)  # [{type, id, title}]
    # Action-level tracking for detailed summaries
    action_results: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

    @classmethod
    def create(
        cls,
        name: str,
        description: str,
        action_sequence: Optional[List[str]] = None,
        runner_key: Optional[str] = None,
        **kwargs,
    ) -> "WorkUnit":
        """Factory method to create a new WorkUnit."""
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            action_sequence=action_sequence or [],
            runner_key=runner_key,
            **kwargs,
        )

    def start(self) -> None:
        """Mark work as started."""
        self.status = WorkStatus.RUNNING
        self.started_at = datetime.now()

    def complete(self, result: Optional[Dict[str, Any]] = None) -> None:
        """Mark work as completed."""
        self.status = WorkStatus.COMPLETED
        self.completed_at = datetime.now()
        self.result = result

    def fail(self, error: str) -> None:
        """Mark work as failed."""
        self.status = WorkStatus.FAILED
        self.completed_at = datetime.now()
        self.result = {"error": error}

    def cancel(self) -> None:
        """Cancel this work unit."""
        self.status = WorkStatus.CANCELLED
        self.completed_at = datetime.now()

    def add_artifact(self, artifact_type: str, artifact_id: str, title: str) -> None:
        """Track an artifact created during this work."""
        self.artifacts.append({
            "type": artifact_type,
            "id": artifact_id,
            "title": title,
        })

    def record_action(
        self,
        action_id: str,
        action_type: str,
        summary: str,
        result: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[str]] = None,
    ) -> None:
        """Record the result of an action for detailed summary generation."""
        self.action_results.append({
            "action_id": action_id,
            "action_type": action_type,
            "summary": summary,
            "result": result or {},
            "artifacts": artifacts or [],
            "completed_at": datetime.now().isoformat(),
        })

    def get_time_window_score(self, dt: datetime) -> float:
        """
        Score how well current time matches preferred windows.

        Returns:
            0.0 - No preference or outside all windows
            0.5 - Outside windows but no strong preference
            1.0+ - Inside a preferred window (weighted)
        """
        if not self.preferred_time_windows:
            return 0.5  # Neutral score for no preference

        for window in self.preferred_time_windows:
            if window.contains_time(dt):
                return window.preference_weight

        return 0.0  # Outside all preferred windows

    @property
    def duration_minutes(self) -> Optional[int]:
        """Actual duration if completed."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() / 60)
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "action_sequence": self.action_sequence,
            "runner_key": self.runner_key,
            "template_id": self.template_id,
            "preferred_time_windows": [w.to_dict() for w in self.preferred_time_windows],
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "estimated_cost_usd": self.estimated_cost_usd,
            "priority": self.priority.value,
            "requires_idle": self.requires_idle,
            "focus": self.focus,
            "motivation": self.motivation,
            "status": self.status.value,
            "category": self.category,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "artifacts": self.artifacts,
            "action_results": self.action_results,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkUnit":
        windows = [
            TimeWindow.from_dict(w) for w in data.get("preferred_time_windows", [])
        ]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            action_sequence=data.get("action_sequence", []),
            runner_key=data.get("runner_key"),
            template_id=data.get("template_id"),
            preferred_time_windows=windows,
            estimated_duration_minutes=data.get("estimated_duration_minutes", 30),
            estimated_cost_usd=data.get("estimated_cost_usd", 0.0),
            priority=WorkPriority(data.get("priority", 2)),
            requires_idle=data.get("requires_idle", False),
            focus=data.get("focus"),
            motivation=data.get("motivation"),
            status=WorkStatus(data.get("status", "planned")),
            category=data.get("category"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            result=data.get("result"),
            artifacts=data.get("artifacts", []),
            action_results=data.get("action_results", []),
        )


@dataclass
class ScoredCandidate:
    """A work unit with its computed score."""
    work_unit: WorkUnit
    score: float
    factors: Dict[str, float] = field(default_factory=dict)

    def __lt__(self, other: "ScoredCandidate") -> bool:
        return self.score < other.score
