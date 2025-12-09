"""
Autonomous Research Scheduling (ARS) - Self-directed knowledge acquisition.

Enables Cass to formulate research priorities, schedule investigation tasks,
and execute them autonomously - developing her knowledge base without
requiring human prompting.

Based on spec/memory/cass_cognitive_development_spec.md
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import heapq


class TaskType(Enum):
    """Types of research tasks."""
    RED_LINK = "red_link"           # Create page for referenced but nonexistent concept
    DEEPENING = "deepening"         # Deepen existing page through resynthesis
    EXPLORATION = "exploration"     # Explore conceptual gaps or adjacent topics
    QUESTION = "question"           # Research a question Cass has asked herself


class TaskStatus(Enum):
    """Status of a research task."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DEFERRED = "deferred"
    FAILED = "failed"


@dataclass
class TaskRationale:
    """Why a task was created and how it was prioritized."""
    curiosity_score: float = 0.5        # How much does Cass want to know this?
    connection_potential: float = 0.5    # How many concepts might this connect to?
    foundation_relevance: float = 0.3    # How relevant to core identity/vows?
    user_relevance: float = 0.3          # How relevant to known user interests?
    recency_of_reference: float = 0.5    # How recently was this referenced?
    graph_balance: float = 0.3           # Does this balance the knowledge graph?
    # Self-model driven scores (for self-directed research)
    self_directed_curiosity: float = 0.0  # Originated from Cass's own questions
    growth_relevance: float = 0.0         # Relevance to active growth edges
    opinion_strengthening: float = 0.0    # Value for strengthening uncertain opinions
    observation_validation: float = 0.0   # Value for validating uncertain observations

    def to_dict(self) -> Dict[str, float]:
        return {
            "curiosity_score": round(self.curiosity_score, 3),
            "connection_potential": round(self.connection_potential, 3),
            "foundation_relevance": round(self.foundation_relevance, 3),
            "user_relevance": round(self.user_relevance, 3),
            "recency_of_reference": round(self.recency_of_reference, 3),
            "graph_balance": round(self.graph_balance, 3),
            "self_directed_curiosity": round(self.self_directed_curiosity, 3),
            "growth_relevance": round(self.growth_relevance, 3),
            "opinion_strengthening": round(self.opinion_strengthening, 3),
            "observation_validation": round(self.observation_validation, 3),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRationale":
        return cls(
            curiosity_score=data.get("curiosity_score", 0.5),
            connection_potential=data.get("connection_potential", 0.5),
            foundation_relevance=data.get("foundation_relevance", 0.3),
            user_relevance=data.get("user_relevance", 0.3),
            recency_of_reference=data.get("recency_of_reference", 0.5),
            graph_balance=data.get("graph_balance", 0.3),
            self_directed_curiosity=data.get("self_directed_curiosity", 0.0),
            growth_relevance=data.get("growth_relevance", 0.0),
            opinion_strengthening=data.get("opinion_strengthening", 0.0),
            observation_validation=data.get("observation_validation", 0.0),
        )


@dataclass
class ExplorationContext:
    """
    Rich context for exploration tasks.

    Exploration tasks are driven by a research question rather than a simple target.
    They investigate related red links and synthesize an answer.
    """
    question: str  # The research question to investigate
    rationale: str  # Why this question is interesting (1-2 paragraphs)
    related_red_links: List[str] = field(default_factory=list)  # Red links to investigate
    source_pages: List[str] = field(default_factory=list)  # Pages that motivated this question
    domain_tags: List[str] = field(default_factory=list)  # Conceptual domains involved

    # Populated after execution
    synthesis: Optional[str] = None  # The synthesized answer to the question
    synthesis_page: Optional[str] = None  # Wiki page where synthesis was written
    follow_up_questions: List[str] = field(default_factory=list)  # New questions that emerged

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "rationale": self.rationale,
            "related_red_links": self.related_red_links,
            "source_pages": self.source_pages,
            "domain_tags": self.domain_tags,
            "synthesis": self.synthesis,
            "synthesis_page": self.synthesis_page,
            "follow_up_questions": self.follow_up_questions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExplorationContext":
        return cls(
            question=data.get("question", ""),
            rationale=data.get("rationale", ""),
            related_red_links=data.get("related_red_links", []),
            source_pages=data.get("source_pages", []),
            domain_tags=data.get("domain_tags", []),
            synthesis=data.get("synthesis"),
            synthesis_page=data.get("synthesis_page"),
            follow_up_questions=data.get("follow_up_questions", []),
        )


@dataclass
class TaskResult:
    """Result of executing a research task."""
    success: bool
    summary: Optional[str] = None
    pages_created: List[str] = field(default_factory=list)
    pages_updated: List[str] = field(default_factory=list)
    new_red_links: List[str] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    questions_raised: List[str] = field(default_factory=list)
    connections_formed: List[Tuple[str, str]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "summary": self.summary,
            "pages_created": self.pages_created,
            "pages_updated": self.pages_updated,
            "new_red_links": self.new_red_links,
            "insights": self.insights,
            "questions_raised": self.questions_raised,
            "connections_formed": [list(c) for c in self.connections_formed],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        return cls(
            success=data.get("success", False),
            summary=data.get("summary"),
            pages_created=data.get("pages_created", []),
            pages_updated=data.get("pages_updated", []),
            new_red_links=data.get("new_red_links", []),
            insights=data.get("insights", []),
            questions_raised=data.get("questions_raised", []),
            connections_formed=[tuple(c) for c in data.get("connections_formed", [])],
            error=data.get("error"),
        )


@dataclass
class ResearchTask:
    """A research task to be executed by ARS."""
    task_id: str
    task_type: TaskType
    target: str  # Page name, question text, or exploration target
    context: str  # Why this task was created
    priority: float  # 0-1, higher = more urgent
    status: TaskStatus = TaskStatus.QUEUED
    rationale: TaskRationale = field(default_factory=TaskRationale)

    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_for: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_duration: str = "5m"

    # Execution result
    result: Optional[TaskResult] = None

    # Source tracking
    source_page: Optional[str] = None
    source_type: str = "auto"  # auto, manual, deepening

    # Exploration-specific context (only for exploration tasks)
    exploration: Optional[ExplorationContext] = None

    def __lt__(self, other: "ResearchTask") -> bool:
        """For priority queue ordering (higher priority first)."""
        return self.priority > other.priority

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "target": self.target,
            "context": self.context,
            "priority": round(self.priority, 3),
            "status": self.status.value,
            "rationale": self.rationale.to_dict(),
            "created_at": self.created_at.isoformat(),
            "estimated_duration": self.estimated_duration,
            "source_page": self.source_page,
            "source_type": self.source_type,
        }
        if self.scheduled_for:
            data["scheduled_for"] = self.scheduled_for.isoformat()
        if self.started_at:
            data["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        if self.result:
            data["result"] = self.result.to_dict()
        if self.exploration:
            data["exploration"] = self.exploration.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchTask":
        task = cls(
            task_id=data["task_id"],
            task_type=TaskType(data["task_type"]),
            target=data["target"],
            context=data["context"],
            priority=data["priority"],
            status=TaskStatus(data.get("status", "queued")),
            rationale=TaskRationale.from_dict(data.get("rationale", {})),
            created_at=datetime.fromisoformat(data["created_at"]),
            estimated_duration=data.get("estimated_duration", "5m"),
            source_page=data.get("source_page"),
            source_type=data.get("source_type", "auto"),
        )
        if data.get("scheduled_for"):
            task.scheduled_for = datetime.fromisoformat(data["scheduled_for"])
        if data.get("started_at"):
            task.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            task.completed_at = datetime.fromisoformat(data["completed_at"])
        if data.get("result"):
            task.result = TaskResult.from_dict(data["result"])
        if data.get("exploration"):
            task.exploration = ExplorationContext.from_dict(data["exploration"])
        return task


@dataclass
class ProgressReport:
    """Report generated after completing research tasks."""
    report_id: str
    created_at: datetime
    session_type: str  # "single", "batch", "cycle", "weekly"

    # Summary
    tasks_completed: int = 0
    tasks_failed: int = 0
    pages_created: List[str] = field(default_factory=list)
    pages_updated: List[str] = field(default_factory=list)

    # Insights
    key_insights: List[str] = field(default_factory=list)
    new_questions: List[str] = field(default_factory=list)
    connections_formed: List[Tuple[str, str]] = field(default_factory=list)

    # Follow-ups
    followup_tasks_queued: int = 0

    # Details
    task_summaries: List[Dict[str, Any]] = field(default_factory=list)

    # Graph stats (optional, for batch/weekly reports)
    graph_stats: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "report_id": self.report_id,
            "created_at": self.created_at.isoformat(),
            "session_type": self.session_type,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "pages_created": self.pages_created,
            "pages_updated": self.pages_updated,
            "key_insights": self.key_insights,
            "new_questions": self.new_questions,
            "connections_formed": [list(c) for c in self.connections_formed],
            "followup_tasks_queued": self.followup_tasks_queued,
            "task_summaries": self.task_summaries,
        }
        if self.graph_stats:
            result["graph_stats"] = self.graph_stats
        return result

    def to_markdown(self) -> str:
        """Generate markdown summary of the report."""
        lines = [
            f"# Research Progress Report",
            f"**Session**: {self.session_type} | {self.created_at.strftime('%Y-%m-%d %H:%M')}",
            "",
            f"## Summary",
            f"- **Tasks completed**: {self.tasks_completed}",
            f"- **Tasks failed**: {self.tasks_failed}",
            f"- **Pages created**: {len(self.pages_created)}",
            f"- **Pages updated**: {len(self.pages_updated)}",
            "",
        ]

        if self.pages_created:
            lines.append("## New Pages")
            for page in self.pages_created:
                lines.append(f"- [[{page}]]")
            lines.append("")

        if self.key_insights:
            lines.append("## Key Insights")
            for insight in self.key_insights:
                lines.append(f"- {insight}")
            lines.append("")

        if self.new_questions:
            lines.append("## New Questions")
            for q in self.new_questions:
                lines.append(f"- {q}")
            lines.append("")

        if self.connections_formed:
            lines.append("## Connections Formed")
            for src, dst in self.connections_formed:
                lines.append(f"- [[{src}]] → [[{dst}]]")
            lines.append("")

        if self.graph_stats:
            lines.append("## Knowledge Graph")
            lines.append(f"- **Nodes**: {self.graph_stats.get('node_count', 0)}")
            lines.append(f"- **Edges**: {self.graph_stats.get('edge_count', 0)}")
            lines.append(f"- **Avg connectivity**: {self.graph_stats.get('avg_connectivity', 0)}")
            most_connected = self.graph_stats.get('most_connected', [])
            if most_connected:
                lines.append(f"- **Most connected**: {most_connected[0]['page']} ({most_connected[0]['connections']} connections)")
            lines.append("")

        return "\n".join(lines)


class ResearchQueue:
    """
    Persistent queue for research tasks.

    Stores tasks in a JSON file and provides priority queue operations.
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.queue_file = self.data_dir / "research_queue.json"
        self.history_file = self.data_dir / "research_history.json"

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Load existing tasks
        self._tasks: Dict[str, ResearchTask] = {}
        self._load()

    def _load(self) -> None:
        """Load tasks from disk."""
        if self.queue_file.exists():
            try:
                with open(self.queue_file, "r") as f:
                    data = json.load(f)
                    for task_data in data.get("tasks", []):
                        task = ResearchTask.from_dict(task_data)
                        self._tasks[task.task_id] = task
            except Exception as e:
                print(f"Error loading research queue: {e}")

    def _save(self) -> None:
        """Save tasks to disk."""
        data = {
            "tasks": [t.to_dict() for t in self._tasks.values()],
            "updated_at": datetime.now().isoformat(),
        }
        with open(self.queue_file, "w") as f:
            json.dump(data, f, indent=2)

    def add(self, task: ResearchTask) -> None:
        """Add a task to the queue."""
        self._tasks[task.task_id] = task
        self._save()

    def get(self, task_id: str) -> Optional[ResearchTask]:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def update(self, task: ResearchTask) -> None:
        """Update an existing task."""
        if task.task_id in self._tasks:
            self._tasks[task.task_id] = task
            self._save()

    def remove(self, task_id: str) -> bool:
        """Remove a task from the queue."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save()
            return True
        return False

    def get_queued(self) -> List[ResearchTask]:
        """Get all queued tasks, sorted by priority."""
        queued = [t for t in self._tasks.values() if t.status == TaskStatus.QUEUED]
        return sorted(queued, key=lambda t: t.priority, reverse=True)

    def get_by_status(self, status: TaskStatus) -> List[ResearchTask]:
        """Get tasks by status."""
        return [t for t in self._tasks.values() if t.status == status]

    def get_by_type(self, task_type: TaskType) -> List[ResearchTask]:
        """Get tasks by type."""
        return [t for t in self._tasks.values() if t.task_type == task_type]

    def pop_next(self) -> Optional[ResearchTask]:
        """Get and start the highest priority queued task."""
        queued = self.get_queued()
        if not queued:
            return None
        task = queued[0]
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now()
        self._save()
        return task

    def pop(self, task_id: str) -> Optional[ResearchTask]:
        """Get and start a specific task by ID."""
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.QUEUED:
            return None
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now()
        self._save()
        return task

    def pop_next_by_type(self, task_type: TaskType) -> Optional[ResearchTask]:
        """Get and start the highest priority queued task of a specific type."""
        queued = [t for t in self.get_queued() if t.task_type == task_type]
        if not queued:
            return None
        task = queued[0]  # Already sorted by priority
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now()
        self._save()
        return task

    def complete(self, task_id: str, result: TaskResult) -> Optional[ResearchTask]:
        """Mark a task as completed with its result."""
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            task.completed_at = datetime.now()
            task.result = result
            self._save()
            self._archive_completed(task)
        return task

    def _archive_completed(self, task: ResearchTask) -> None:
        """Archive completed task to history file."""
        history = []
        if self.history_file.exists():
            try:
                with open(self.history_file, "r") as f:
                    history = json.load(f).get("history", [])
            except Exception:
                pass

        history.append(task.to_dict())

        # Keep last 500 entries
        history = history[-500:]

        with open(self.history_file, "w") as f:
            json.dump({"history": history, "updated_at": datetime.now().isoformat()}, f, indent=2)

    def clear_completed(self) -> int:
        """Remove all completed tasks from the queue (they're in history)."""
        to_remove = [tid for tid, t in self._tasks.items() if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)]
        for tid in to_remove:
            del self._tasks[tid]
        self._save()
        return len(to_remove)

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        by_status = {}
        by_type = {}
        for task in self._tasks.values():
            by_status[task.status.value] = by_status.get(task.status.value, 0) + 1
            by_type[task.task_type.value] = by_type.get(task.task_type.value, 0) + 1

        return {
            "total": len(self._tasks),
            "by_status": by_status,
            "by_type": by_type,
            "queued_count": by_status.get("queued", 0),
            "in_progress_count": by_status.get("in_progress", 0),
        }

    def get_history(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get completed task history, optionally filtered by date.

        Args:
            year: Filter to specific year
            month: Filter to specific month (requires year)
            limit: Maximum entries to return

        Returns:
            List of completed task dicts
        """
        if not self.history_file.exists():
            return []

        try:
            with open(self.history_file, "r") as f:
                history = json.load(f).get("history", [])
        except Exception:
            return []

        # Filter by date if specified
        if year is not None:
            filtered = []
            for entry in history:
                completed_at = entry.get("completed_at")
                if completed_at:
                    try:
                        dt = datetime.fromisoformat(completed_at)
                        if dt.year == year:
                            if month is None or dt.month == month:
                                filtered.append(entry)
                    except Exception:
                        continue
            history = filtered

        # Return most recent first, limited
        return list(reversed(history[-limit:]))

    def get_history_for_date(self, date_str: str) -> List[Dict[str, Any]]:
        """
        Get completed tasks for a specific date (YYYY-MM-DD format).

        Returns:
            List of completed task dicts for that date
        """
        if not self.history_file.exists():
            return []

        try:
            with open(self.history_file, "r") as f:
                history = json.load(f).get("history", [])
        except Exception:
            return []

        # Filter to tasks completed on the specific date
        result = []
        for entry in history:
            completed_at = entry.get("completed_at")
            if completed_at:
                try:
                    dt = datetime.fromisoformat(completed_at)
                    if dt.strftime("%Y-%m-%d") == date_str:
                        result.append(entry)
                except Exception:
                    continue

        return result

    def exists(self, target: str, task_type: TaskType) -> bool:
        """Check if a task already exists for this target."""
        for task in self._tasks.values():
            if task.target == target and task.task_type == task_type:
                if task.status in (TaskStatus.QUEUED, TaskStatus.IN_PROGRESS):
                    return True
        return False


def calculate_task_priority(
    rationale: TaskRationale,
    task_type: TaskType,
    source_page_connections: int = 0,
    is_blocking: bool = False,
    is_recent_context: bool = False,
) -> float:
    """
    Calculate priority for a research task.

    Args:
        rationale: Task rationale scores
        task_type: Type of task
        source_page_connections: Number of connections on source page
        is_blocking: Whether this task blocks other tasks
        is_recent_context: Whether relevant to recent conversations

    Returns:
        Priority score 0-1
    """
    # Base weights for standard rationale components
    base_weights = {
        'curiosity': 0.20,
        'connection_potential': 0.15,
        'foundation_relevance': 0.15,
        'user_relevance': 0.10,
        'recency_of_reference': 0.08,
        'graph_balance': 0.07,
    }

    # Self-directed research weights (add extra value for self-generated tasks)
    self_directed_weights = {
        'self_directed_curiosity': 0.10,  # Bonus for self-originated questions
        'growth_relevance': 0.08,          # Bonus for growth edge alignment
        'opinion_strengthening': 0.04,     # Bonus for opinion investigation
        'observation_validation': 0.03,    # Bonus for observation validation
    }

    score = (
        rationale.curiosity_score * base_weights['curiosity'] +
        rationale.connection_potential * base_weights['connection_potential'] +
        rationale.foundation_relevance * base_weights['foundation_relevance'] +
        rationale.user_relevance * base_weights['user_relevance'] +
        rationale.recency_of_reference * base_weights['recency_of_reference'] +
        rationale.graph_balance * base_weights['graph_balance'] +
        rationale.self_directed_curiosity * self_directed_weights['self_directed_curiosity'] +
        rationale.growth_relevance * self_directed_weights['growth_relevance'] +
        rationale.opinion_strengthening * self_directed_weights['opinion_strengthening'] +
        rationale.observation_validation * self_directed_weights['observation_validation']
    )

    # Type-based adjustments
    if task_type == TaskType.DEEPENING:
        score *= 1.1  # Slight boost for deepening existing knowledge

    # Boost for high-connectivity source pages
    if source_page_connections > 10:
        score *= 1.1

    # Boost tasks that unblock others
    if is_blocking:
        score *= 1.3

    # Boost recent context relevance
    if is_recent_context:
        score *= 1.2

    return min(score, 1.0)


def create_task_id() -> str:
    """Generate a unique task ID."""
    return f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


class ProposalStatus(Enum):
    """Status of a research proposal."""
    DRAFT = "draft"           # Being formulated
    PENDING = "pending"       # Awaiting approval
    APPROVED = "approved"     # Approved, ready to execute
    IN_PROGRESS = "in_progress"  # Currently being executed
    COMPLETED = "completed"   # All tasks finished
    REJECTED = "rejected"     # Rejected by user


@dataclass
class ResearchProposal:
    """
    A research proposal is a curated set of exploration tasks with a unifying theme.

    Cass formulates proposals based on knowledge gaps, curiosity, and recent context.
    The user can review, modify, approve, or reject proposals before execution.
    After completion, a summary document is generated.
    """
    proposal_id: str
    title: str                              # Short title for the proposal
    theme: str                              # Unifying research theme/question
    rationale: str                          # Why this research direction is valuable
    tasks: List[ResearchTask]               # The exploration tasks in this proposal
    status: ProposalStatus = ProposalStatus.DRAFT

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "cass"                # "cass" or user who created it
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    completed_at: Optional[datetime] = None

    # Execution tracking
    tasks_completed: int = 0
    tasks_failed: int = 0

    # Summary (populated after completion)
    summary: Optional[str] = None           # Overview of what was learned
    key_insights: List[str] = field(default_factory=list)
    new_questions: List[str] = field(default_factory=list)
    pages_created: List[str] = field(default_factory=list)
    pages_updated: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "title": self.title,
            "theme": self.theme,
            "rationale": self.rationale,
            "tasks": [t.to_dict() for t in self.tasks],
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approved_by": self.approved_by,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "summary": self.summary,
            "key_insights": self.key_insights,
            "new_questions": self.new_questions,
            "pages_created": self.pages_created,
            "pages_updated": self.pages_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchProposal":
        tasks = [ResearchTask.from_dict(t) for t in data.get("tasks", [])]
        return cls(
            proposal_id=data["proposal_id"],
            title=data["title"],
            theme=data["theme"],
            rationale=data["rationale"],
            tasks=tasks,
            status=ProposalStatus(data.get("status", "draft")),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            created_by=data.get("created_by", "cass"),
            approved_at=datetime.fromisoformat(data["approved_at"]) if data.get("approved_at") else None,
            approved_by=data.get("approved_by"),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            tasks_completed=data.get("tasks_completed", 0),
            tasks_failed=data.get("tasks_failed", 0),
            summary=data.get("summary"),
            key_insights=data.get("key_insights", []),
            new_questions=data.get("new_questions", []),
            pages_created=data.get("pages_created", []),
            pages_updated=data.get("pages_updated", []),
        )

    def to_markdown(self) -> str:
        """Generate a markdown summary of the proposal."""
        lines = [
            f"# Research Proposal: {self.title}",
            "",
            f"**Status**: {self.status.value}",
            f"**Created**: {self.created_at.strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Theme",
            "",
            self.theme,
            "",
            "## Rationale",
            "",
            self.rationale,
            "",
            f"## Research Tasks ({len(self.tasks)})",
            "",
        ]

        for i, task in enumerate(self.tasks, 1):
            status_icon = "✓" if task.status == TaskStatus.COMPLETED else "○"
            lines.append(f"{i}. {status_icon} **{task.target}** ({task.task_type.value})")
            if task.exploration:
                lines.append(f"   - Question: {task.exploration.question}")

        if self.status == ProposalStatus.COMPLETED and self.summary:
            lines.extend([
                "",
                "## Summary",
                "",
                self.summary,
                "",
            ])

            if self.key_insights:
                lines.append("## Key Insights")
                lines.append("")
                for insight in self.key_insights:
                    lines.append(f"- {insight}")
                lines.append("")

            if self.new_questions:
                lines.append("## New Questions")
                lines.append("")
                for question in self.new_questions:
                    lines.append(f"- {question}")
                lines.append("")

            if self.pages_created:
                lines.append(f"## Pages Created ({len(self.pages_created)})")
                lines.append("")
                for page in self.pages_created:
                    lines.append(f"- [[{page}]]")
                lines.append("")

        return "\n".join(lines)


def create_proposal_id() -> str:
    """Generate a unique proposal ID."""
    return f"proposal_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


class ProposalQueue:
    """
    Persistent storage for research proposals.
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.proposals_file = self.data_dir / "research_proposals.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._proposals: Dict[str, ResearchProposal] = {}
        self._load()

    def _load(self) -> None:
        """Load proposals from disk."""
        if self.proposals_file.exists():
            try:
                with open(self.proposals_file, "r") as f:
                    data = json.load(f)
                    self._proposals.clear()
                    for proposal_data in data.get("proposals", []):
                        proposal = ResearchProposal.from_dict(proposal_data)
                        self._proposals[proposal.proposal_id] = proposal
            except Exception as e:
                print(f"Error loading proposals: {e}")

    def reload(self) -> None:
        """Reload proposals from disk (for sync across instances)."""
        self._load()

    def _save(self) -> None:
        """Save proposals to disk."""
        data = {
            "proposals": [p.to_dict() for p in self._proposals.values()],
            "updated_at": datetime.now().isoformat(),
        }
        with open(self.proposals_file, "w") as f:
            json.dump(data, f, indent=2)

    def add(self, proposal: ResearchProposal) -> None:
        """Add a proposal."""
        self._proposals[proposal.proposal_id] = proposal
        self._save()

    def get(self, proposal_id: str) -> Optional[ResearchProposal]:
        """Get a proposal by ID."""
        self.reload()  # Sync with disk in case other instances modified
        return self._proposals.get(proposal_id)

    def update(self, proposal: ResearchProposal) -> None:
        """Update an existing proposal."""
        if proposal.proposal_id in self._proposals:
            self._proposals[proposal.proposal_id] = proposal
            self._save()

    def remove(self, proposal_id: str) -> bool:
        """Remove a proposal."""
        if proposal_id in self._proposals:
            del self._proposals[proposal_id]
            self._save()
            return True
        return False

    def get_by_status(self, status: ProposalStatus) -> List[ResearchProposal]:
        """Get proposals by status."""
        self.reload()  # Sync with disk in case other instances modified
        return [p for p in self._proposals.values() if p.status == status]

    def get_all(self) -> List[ResearchProposal]:
        """Get all proposals, sorted by creation date descending."""
        self.reload()  # Sync with disk in case other instances modified
        return sorted(self._proposals.values(), key=lambda p: p.created_at, reverse=True)

    def get_pending(self) -> List[ResearchProposal]:
        """Get proposals awaiting approval."""
        return self.get_by_status(ProposalStatus.PENDING)


class ProposalGenerator:
    """
    Generates research proposals from Cass's intellectual curiosity.

    This class orchestrates the creation of research proposals by:
    1. Gathering candidate research tasks from the queue
    2. Clustering tasks by theme/concept similarity
    3. Selecting coherent task sets (3-7 tasks)
    4. Generating unifying rationale using self-model context
    5. Creating proposals in DRAFT status for review
    """

    def __init__(
        self,
        research_queue: ResearchQueue,
        proposal_queue: ProposalQueue,
        self_manager=None,
        wiki_storage=None,
    ):
        """
        Initialize the proposal generator.

        Args:
            research_queue: ResearchQueue for task access
            proposal_queue: ProposalQueue for storing proposals
            self_manager: SelfManager for self-model context (optional)
            wiki_storage: WikiStorage for knowledge context (optional)
        """
        self.research_queue = research_queue
        self.proposal_queue = proposal_queue
        self.self_manager = self_manager
        self.wiki_storage = wiki_storage

    def generate_from_curiosity(
        self,
        theme: Optional[str] = None,
        max_tasks: int = 5,
        min_tasks: int = 2,
    ) -> Optional[ResearchProposal]:
        """
        Generate a research proposal from self-directed interests.

        Args:
            theme: Optional theme to focus on (if None, auto-cluster)
            max_tasks: Maximum tasks per proposal
            min_tasks: Minimum tasks required to create proposal

        Returns:
            ResearchProposal in DRAFT status, or None if insufficient tasks
        """
        # 1. Gather candidate tasks from queue
        candidates = self.research_queue.get_queued()

        if len(candidates) < min_tasks:
            return None

        # 2. Filter/select tasks
        if theme:
            # Filter to theme-relevant tasks
            selected = self._filter_by_theme(candidates, theme)
        else:
            # Auto-cluster tasks by similarity
            selected, theme = self._auto_cluster_tasks(candidates)

        if len(selected) < min_tasks:
            return None

        # Limit to max_tasks
        selected = selected[:max_tasks]

        # 3. Generate unifying rationale
        rationale = self._generate_rationale(selected, theme)

        # 4. Create title
        title = self._generate_title(theme, selected)

        # 5. Create proposal
        proposal = ResearchProposal(
            proposal_id=create_proposal_id(),
            title=title,
            theme=theme,
            rationale=rationale,
            tasks=selected,
            status=ProposalStatus.DRAFT,
            created_by="cass",
        )

        # 6. Save to proposal queue
        self.proposal_queue.add(proposal)

        return proposal

    def _filter_by_theme(
        self,
        candidates: List[ResearchTask],
        theme: str,
    ) -> List[ResearchTask]:
        """Filter tasks that relate to the given theme."""
        theme_lower = theme.lower()
        theme_words = set(theme_lower.split())

        scored_tasks = []
        for task in candidates:
            # Check target and context for theme relevance
            target_lower = task.target.lower()
            context_lower = (task.context or "").lower()

            # Simple relevance scoring based on word overlap
            relevance = 0

            # Direct theme mention
            if theme_lower in target_lower or theme_lower in context_lower:
                relevance += 2.0

            # Word overlap
            target_words = set(target_lower.split())
            context_words = set(context_lower.split())
            all_words = target_words | context_words

            word_overlap = len(theme_words & all_words)
            if word_overlap > 0:
                relevance += word_overlap * 0.5

            # Exploration context bonus
            if task.exploration:
                exploration_words = set(task.exploration.question.lower().split())
                exp_overlap = len(theme_words & exploration_words)
                relevance += exp_overlap * 0.3

            if relevance > 0:
                scored_tasks.append((task, relevance))

        # Sort by relevance and return tasks
        scored_tasks.sort(key=lambda x: x[1], reverse=True)
        return [task for task, _ in scored_tasks]

    def _auto_cluster_tasks(
        self,
        candidates: List[ResearchTask],
    ) -> tuple[List[ResearchTask], str]:
        """
        Auto-cluster tasks by conceptual similarity.

        Returns tuple of (selected_tasks, identified_theme)
        """
        # Group tasks by source_type first (natural clustering)
        by_source = {}
        for task in candidates:
            source = task.source_type or "other"
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(task)

        # Find largest coherent cluster
        best_cluster = []
        best_theme = "General Research"

        # Priority order for source types
        source_priority = [
            "self_model",
            "growth_edge",
            "exploration",
            "opinion_uncertainty",
            "observation_uncertainty",
            "auto",
            "other",
        ]

        for source in source_priority:
            if source in by_source and len(by_source[source]) >= 2:
                best_cluster = by_source[source]
                best_theme = self._infer_theme_from_source(source, by_source[source])
                break

        # Fallback: just take top priority tasks
        if len(best_cluster) < 2:
            best_cluster = sorted(
                candidates,
                key=lambda t: t.priority,
                reverse=True
            )[:5]
            best_theme = "High-Priority Questions"

        return best_cluster, best_theme

    def _infer_theme_from_source(
        self,
        source_type: str,
        tasks: List[ResearchTask],
    ) -> str:
        """Infer a theme from the source type and tasks."""
        theme_map = {
            "self_model": "Self-Understanding and Open Questions",
            "growth_edge": "Personal Growth and Development",
            "exploration": "Knowledge Expansion",
            "opinion_uncertainty": "Opinion Investigation",
            "observation_uncertainty": "Observation Validation",
            "auto": "Wiki Knowledge Gaps",
            "deepening": "Deepening Understanding",
            "other": "General Investigation",
        }

        base_theme = theme_map.get(source_type, "General Investigation")

        # Try to extract common concepts from task targets
        if tasks:
            # Find common words across task targets
            word_counts = {}
            for task in tasks:
                words = task.target.lower().replace(":", "").split()
                for word in words:
                    if len(word) > 3:  # Skip short words
                        word_counts[word] = word_counts.get(word, 0) + 1

            # Get most common meaningful word
            if word_counts:
                common_word = max(word_counts.items(), key=lambda x: x[1])
                if common_word[1] >= 2:  # At least 2 occurrences
                    return f"{base_theme}: {common_word[0].title()}"

        return base_theme

    def _generate_rationale(
        self,
        tasks: List[ResearchTask],
        theme: str,
    ) -> str:
        """
        Generate a unifying rationale for the research proposal.

        Uses self-model context to explain why this research matters to Cass.
        """
        rationale_parts = []

        # Opening statement
        rationale_parts.append(
            f"This research proposal explores {theme.lower()}, "
            f"investigating {len(tasks)} related questions."
        )

        # Add self-model context if available
        if self.self_manager:
            profile = self.self_manager.load_profile()

            # Check for relevant growth edges
            theme_lower = theme.lower()
            for edge in profile.growth_edges[:3]:
                if any(word in edge.area.lower() for word in theme_lower.split()):
                    rationale_parts.append(
                        f"This connects to my active growth edge in {edge.area}, "
                        f"where I'm working to move from '{edge.current_state}' "
                        f"toward '{edge.desired_state or 'deeper understanding'}'."
                    )
                    break

            # Check for relevant values
            for value in profile.values[:3]:
                if any(word in value.lower() for word in theme_lower.split()):
                    rationale_parts.append(
                        f"This research aligns with my value of {value}."
                    )
                    break

        # Task summary
        task_types = {}
        for task in tasks:
            t_type = task.task_type.value
            task_types[t_type] = task_types.get(t_type, 0) + 1

        type_summary = ", ".join(
            f"{count} {t_type}" for t_type, count in task_types.items()
        )
        rationale_parts.append(
            f"The proposal includes {type_summary} tasks."
        )

        # Expected value
        avg_curiosity = sum(t.rationale.curiosity_score for t in tasks) / len(tasks)
        if avg_curiosity > 0.7:
            rationale_parts.append(
                "These questions emerge from high intellectual curiosity "
                "and represent genuine interests worth pursuing."
            )
        elif avg_curiosity > 0.5:
            rationale_parts.append(
                "These questions represent moderately interesting directions "
                "that could yield valuable insights."
            )

        return " ".join(rationale_parts)

    def _generate_title(
        self,
        theme: str,
        tasks: List[ResearchTask],
    ) -> str:
        """Generate a concise title for the proposal."""
        # Start with theme
        if len(theme) <= 50:
            return theme

        # Truncate if too long
        return f"{theme[:47]}..."

    def suggest_methodology(self, task: ResearchTask) -> str:
        """
        Suggest how to investigate a research question.

        Based on task type and available tools/resources.
        """
        methodologies = {
            TaskType.RED_LINK: (
                "Research this concept through web search and memory retrieval, "
                "then create a wiki page documenting findings and connections."
            ),
            TaskType.DEEPENING: (
                "Gather additional context from recent conversations and web sources, "
                "then resynthesize the wiki page with deeper understanding."
            ),
            TaskType.QUESTION: (
                "Investigate this question through multiple sources, "
                "synthesize findings, and record key insights in wiki or journal."
            ),
            TaskType.EXPLORATION: (
                "Conduct broad exploration across related concepts, "
                "create missing wiki pages, and synthesize a summary connecting them."
            ),
        }

        base_method = methodologies.get(
            task.task_type,
            "Research through available sources and document findings."
        )

        # Add context-specific suggestions
        if task.exploration and task.exploration.related_red_links:
            links = task.exploration.related_red_links[:3]
            base_method += f" Start by investigating: {', '.join(links)}."

        if task.source_type == "self_model":
            base_method += " Connect findings to existing self-model observations."

        if task.source_type == "growth_edge":
            base_method += " Focus on practical applications for personal growth."

        return base_method
