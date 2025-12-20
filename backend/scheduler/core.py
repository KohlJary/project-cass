"""
Synkratos - The Universal Work Orchestrator.

Named for one who brings together (syn + kratos). Consolidates all work:
- Scheduled work (crontab-style system tasks)
- Autonomous work (budget-aware categorical queues)
- Pending approvals (goals, research requests, actions)

The name carries intent - not "yet another scheduler" but the orchestrator
that coordinates everything Cass does autonomously.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Callable, Optional, Any, Dict, List, Awaitable
import asyncio
import logging
import uuid
import re

from .budget import BudgetManager, TaskCategory

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Priority levels for scheduled tasks."""
    CRITICAL = 0    # Must run (system health) - bypasses budget
    HIGH = 1        # Important autonomous work
    NORMAL = 2      # Standard priority
    LOW = 3         # Background/fill tasks
    IDLE = 4        # Only when nothing else to do


class TaskStatus(Enum):
    """Status of a scheduled task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BUDGET_BLOCKED = "budget_blocked"


class ApprovalType(Enum):
    """Types of items that require approval."""
    GOAL = "goal"                    # Goal proposals from Cass
    RESEARCH = "research"            # Research session requests
    ACTION = "action"                # Proposed actions (future)
    USER = "user"                    # User registration (if enabled)


@dataclass
class ApprovalItem:
    """
    A unified approval item that wraps different approvable types.

    Provides a single interface for Kohl to see "what needs my attention?"
    across goals, research proposals, actions, etc.
    """
    approval_id: str
    approval_type: ApprovalType
    title: str
    description: str

    # Reference to the original item
    source_id: str                   # ID in the source system (goal_id, proposal_id, etc.)
    source_data: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "cass"         # Who proposed this
    priority: TaskPriority = TaskPriority.NORMAL

    # Resolution
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    approved: Optional[bool] = None  # None = pending, True = approved, False = rejected
    resolution_note: Optional[str] = None


@dataclass
class ScheduledTask:
    """A task that can be scheduled for execution."""
    task_id: str
    name: str
    category: TaskCategory
    priority: TaskPriority
    handler: Callable[..., Awaitable[Any]]

    # Scheduling options (for system tasks)
    cron: Optional[str] = None              # "0 * * * *" = hourly
    interval_seconds: Optional[int] = None  # Alternative: fixed interval

    # Execution state
    status: TaskStatus = TaskStatus.PENDING
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0

    # Cost tracking
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0

    # Dependencies
    requires_idle: bool = False     # Only run when no user activity
    max_concurrent: int = 1         # Max instances of this task

    # Handler context (passed to handler)
    context: Dict[str, Any] = field(default_factory=dict)

    # Execution metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.next_run is None and self.interval_seconds:
            self.next_run = datetime.now(timezone.utc) + timedelta(seconds=self.interval_seconds)


@dataclass
class TaskQueue:
    """A queue of tasks for a specific category."""
    category: TaskCategory
    max_concurrent: int = 1
    budget_allocation: float = 0.3  # Share of daily budget

    pending: List[ScheduledTask] = field(default_factory=list)
    running: List[ScheduledTask] = field(default_factory=list)
    paused: bool = False

    def add(self, task: ScheduledTask) -> None:
        """Add a task to the queue, sorted by priority then creation time."""
        self.pending.append(task)
        self.pending.sort(key=lambda t: (t.priority.value, t.created_at))

    def pop_next(self) -> Optional[ScheduledTask]:
        """Get the next task to run, if slots available."""
        if self.paused:
            return None
        if len(self.running) >= self.max_concurrent:
            return None
        if not self.pending:
            return None

        task = self.pending.pop(0)
        task.status = TaskStatus.RUNNING
        self.running.append(task)
        return task

    def complete(self, task_id: str, success: bool, error: Optional[str] = None) -> None:
        """Mark a task as completed."""
        for i, task in enumerate(self.running):
            if task.task_id == task_id:
                self.running.pop(i)
                task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
                task.error_message = error
                break


class CronParser:
    """Simple cron expression parser for scheduling."""

    @staticmethod
    def parse_next_run(cron_expr: str, from_time: datetime = None) -> Optional[datetime]:
        """
        Parse a cron expression and return the next run time.

        Supports: minute hour day month weekday
        Example: "0 23 * * *" = 23:00 daily
        """
        if not cron_expr:
            return None

        from_time = from_time or datetime.now(timezone.utc)
        parts = cron_expr.split()
        if len(parts) != 5:
            logger.warning(f"Invalid cron expression: {cron_expr}")
            return None

        try:
            minute, hour, day, month, weekday = parts

            # Simple implementation: find next matching time
            # Start from next minute
            candidate = from_time.replace(second=0, microsecond=0) + timedelta(minutes=1)

            for _ in range(60 * 24 * 7):  # Search up to 1 week ahead
                if CronParser._matches(candidate, minute, hour, day, month, weekday):
                    return candidate
                candidate += timedelta(minutes=1)

            return None
        except Exception as e:
            logger.warning(f"Error parsing cron expression '{cron_expr}': {e}")
            return None

    @staticmethod
    def _matches(dt: datetime, minute: str, hour: str, day: str, month: str, weekday: str) -> bool:
        """Check if datetime matches cron fields."""
        if minute != "*" and dt.minute != int(minute):
            return False
        if hour != "*" and dt.hour != int(hour):
            return False
        if day != "*" and dt.day != int(day):
            return False
        if month != "*" and dt.month != int(month):
            return False
        if weekday != "*" and dt.weekday() != int(weekday):
            return False
        return True


class Synkratos:
    """
    The Universal Work Orchestrator.

    One place for "what needs my attention?" - consolidates:
    - Scheduled work (crontab-style system tasks)
    - Autonomous work (budget-aware categorical queues)
    - Pending approvals (goals, research requests, actions)

    Features:
    - Single event loop (1-second tick)
    - Budget-aware execution with category allocations
    - Priority-based queue management
    - Idle detection for low-priority tasks
    - Unified approval queue across subsystems
    """

    TICK_INTERVAL = 1.0  # Check every second

    def __init__(
        self,
        budget_manager: BudgetManager,
        token_tracker=None,
        idle_threshold_seconds: int = 300,  # 5 minutes of no activity = idle
    ):
        self.budget = budget_manager
        self.token_tracker = token_tracker
        self.idle_threshold = idle_threshold_seconds

        # System tasks (crontab-style, recurring)
        self.system_tasks: Dict[str, ScheduledTask] = {}

        # Categorical queues for autonomous work
        self.queues: Dict[TaskCategory, TaskQueue] = {}
        self._init_default_queues()

        # State
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self._last_activity: datetime = datetime.now(timezone.utc)
        self._last_budget_sync: Optional[datetime] = None

        # Execution history (last N completed tasks)
        self._history: List[Dict[str, Any]] = []
        self._max_history = 100

        # Approval queue - unified view of pending approvals
        self._approval_providers: Dict[ApprovalType, Callable[[], List[ApprovalItem]]] = {}
        self._approval_handlers: Dict[ApprovalType, Dict[str, Callable]] = {}

    def _init_default_queues(self) -> None:
        """Initialize default task queues."""
        queue_configs = {
            TaskCategory.RESEARCH: {"max_concurrent": 1, "budget_allocation": 0.30},
            TaskCategory.REFLECTION: {"max_concurrent": 1, "budget_allocation": 0.20},
            TaskCategory.GROWTH: {"max_concurrent": 1, "budget_allocation": 0.15},
            TaskCategory.CURIOSITY: {"max_concurrent": 1, "budget_allocation": 0.15},
        }

        for category, config in queue_configs.items():
            self.queues[category] = TaskQueue(
                category=category,
                max_concurrent=config["max_concurrent"],
                budget_allocation=config["budget_allocation"],
            )

    def init_autonomous_queues(self, configs: Dict[str, Dict[str, Any]]) -> None:
        """
        Initialize or reconfigure autonomous queues.

        Args:
            configs: Dict mapping queue names to config dicts
                     e.g., {"research": {"max_concurrent": 1, "budget_share": 0.3}}
        """
        for name, config in configs.items():
            try:
                category = TaskCategory(name)
                self.queues[category] = TaskQueue(
                    category=category,
                    max_concurrent=config.get("max_concurrent", 1),
                    budget_allocation=config.get("budget_share", 0.1),
                )
                logger.info(f"Initialized queue: {name} with config {config}")
            except ValueError:
                logger.warning(f"Unknown category: {name}")

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        self._loop_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Synkratos started")

    async def stop(self) -> None:
        """Gracefully stop the scheduler."""
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        logger.info("Synkratos stopped")

    def record_activity(self) -> None:
        """Record user activity (call this on user messages)."""
        self._last_activity = datetime.now(timezone.utc)

    def is_idle(self) -> bool:
        """Check if the system is idle (no recent user activity)."""
        elapsed = (datetime.now(timezone.utc) - self._last_activity).total_seconds()
        return elapsed >= self.idle_threshold

    def register_system_task(self, task: ScheduledTask) -> None:
        """
        Register a crontab-style system task.

        Args:
            task: ScheduledTask with cron or interval_seconds set
        """
        if task.cron:
            task.next_run = CronParser.parse_next_run(task.cron)
        elif task.interval_seconds:
            task.next_run = datetime.now(timezone.utc) + timedelta(seconds=task.interval_seconds)

        self.system_tasks[task.task_id] = task
        logger.info(f"Registered system task: {task.name} (next run: {task.next_run})")

    def submit_task(self, task: ScheduledTask) -> str:
        """
        Submit a task to the appropriate queue.

        Args:
            task: Task to submit

        Returns:
            Task ID
        """
        if task.category not in self.queues:
            raise ValueError(f"No queue for category: {task.category}")

        self.queues[task.category].add(task)
        logger.debug(f"Submitted task {task.task_id} to {task.category.value} queue")
        return task.task_id

    def pause_queue(self, category: TaskCategory) -> None:
        """Pause a queue - no new tasks will be started."""
        if category in self.queues:
            self.queues[category].paused = True
            logger.info(f"Paused queue: {category.value}")

    def resume_queue(self, category: TaskCategory) -> None:
        """Resume a paused queue."""
        if category in self.queues:
            self.queues[category].paused = False
            logger.info(f"Resumed queue: {category.value}")

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop - check and dispatch tasks."""
        logger.info("Scheduler loop started")

        while self._running:
            try:
                now = datetime.now(timezone.utc)

                # Sync budget from token tracker every 60 seconds
                if (self._last_budget_sync is None or
                    (now - self._last_budget_sync).total_seconds() >= 60):
                    self.budget.sync_from_token_tracker()
                    self._last_budget_sync = now

                # Check system tasks
                await self._check_system_tasks(now)

                # Check queue tasks
                await self._check_queue_tasks(now)

                await asyncio.sleep(self.TICK_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Back off on error

        logger.info("Scheduler loop ended")

    async def _check_system_tasks(self, now: datetime) -> None:
        """Check and dispatch due system tasks."""
        for task_id, task in list(self.system_tasks.items()):
            if task.status == TaskStatus.RUNNING:
                continue

            if task.next_run and now >= task.next_run:
                # Check idle requirement
                if task.requires_idle and not self.is_idle():
                    continue

                # Check budget (unless CRITICAL)
                if task.priority != TaskPriority.CRITICAL:
                    if not self.budget.can_spend(task.category, task.estimated_cost_usd):
                        logger.debug(f"Budget blocked: {task.name}")
                        continue

                # Dispatch task
                asyncio.create_task(self._run_system_task(task))

    async def _run_system_task(self, task: ScheduledTask) -> None:
        """Execute a system task."""
        task.status = TaskStatus.RUNNING
        task.last_run = datetime.now(timezone.utc)
        start_time = datetime.now(timezone.utc)

        try:
            logger.info(f"Running system task: {task.name}")
            result = await task.handler(**task.context)

            task.status = TaskStatus.COMPLETED
            task.run_count += 1

            # Record cost if tracked
            if self.token_tracker and hasattr(result, 'cost_usd'):
                task.actual_cost_usd = result.cost_usd
                self.budget.record_spend(task.category, result.cost_usd)
            elif task.estimated_cost_usd > 0:
                self.budget.record_spend(task.category, task.estimated_cost_usd)

            logger.info(f"Completed system task: {task.name}")

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            logger.error(f"System task failed: {task.name} - {e}", exc_info=True)

        finally:
            # Schedule next run
            if task.cron:
                task.next_run = CronParser.parse_next_run(task.cron, task.last_run)
            elif task.interval_seconds:
                task.next_run = task.last_run + timedelta(seconds=task.interval_seconds)

            # Record to history
            self._record_history(task, start_time)

    async def _check_queue_tasks(self, now: datetime) -> None:
        """Check and dispatch queue tasks."""
        for category, queue in self.queues.items():
            if queue.paused:
                continue

            task = queue.pop_next()
            if not task:
                continue

            # Check idle requirement
            if task.requires_idle and not self.is_idle():
                task.status = TaskStatus.PENDING
                queue.pending.insert(0, task)  # Put it back
                queue.running.remove(task)
                continue

            # Check budget (unless CRITICAL)
            if task.priority != TaskPriority.CRITICAL:
                if not self.budget.can_spend(category, task.estimated_cost_usd):
                    task.status = TaskStatus.BUDGET_BLOCKED
                    queue.running.remove(task)
                    logger.debug(f"Budget blocked task: {task.name}")
                    continue

            # Dispatch task
            asyncio.create_task(self._run_queue_task(queue, task))

    async def _run_queue_task(self, queue: TaskQueue, task: ScheduledTask) -> None:
        """Execute a queue task."""
        start_time = datetime.now(timezone.utc)

        try:
            logger.info(f"Running queue task: {task.name} ({queue.category.value})")
            result = await task.handler(**task.context)

            queue.complete(task.task_id, success=True)
            task.run_count += 1

            # Record cost
            if self.token_tracker and hasattr(result, 'cost_usd'):
                task.actual_cost_usd = result.cost_usd
                self.budget.record_spend(queue.category, result.cost_usd)
            elif task.estimated_cost_usd > 0:
                self.budget.record_spend(queue.category, task.estimated_cost_usd)

            logger.info(f"Completed queue task: {task.name}")

        except Exception as e:
            queue.complete(task.task_id, success=False, error=str(e))
            logger.error(f"Queue task failed: {task.name} - {e}", exc_info=True)

        finally:
            self._record_history(task, start_time)

    def _record_history(self, task: ScheduledTask, start_time: datetime) -> None:
        """Record task execution to history."""
        end_time = datetime.now(timezone.utc)
        entry = {
            "task_id": task.task_id,
            "name": task.name,
            "category": task.category.value,
            "priority": task.priority.value,
            "status": task.status.value,
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "estimated_cost_usd": task.estimated_cost_usd,
            "actual_cost_usd": task.actual_cost_usd,
            "error": task.error_message,
        }
        self._history.append(entry)

        # Trim history
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status for monitoring."""
        return {
            "running": self._running,
            "is_idle": self.is_idle(),
            "last_activity": self._last_activity.isoformat(),
            "system_tasks": {
                task_id: {
                    "name": task.name,
                    "status": task.status.value,
                    "last_run": task.last_run.isoformat() if task.last_run else None,
                    "next_run": task.next_run.isoformat() if task.next_run else None,
                    "run_count": task.run_count,
                }
                for task_id, task in self.system_tasks.items()
            },
            "queues": {
                cat.value: {
                    "pending": len(queue.pending),
                    "running": len(queue.running),
                    "paused": queue.paused,
                    "max_concurrent": queue.max_concurrent,
                }
                for cat, queue in self.queues.items()
            },
            "budget": self.budget.get_budget_status(),
        }

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent task execution history."""
        return self._history[-limit:]

    # ============== Approval Queue Methods ==============

    def register_approval_provider(
        self,
        approval_type: ApprovalType,
        provider: Callable[[], List[ApprovalItem]],
        approve_handler: Callable[[str, str], bool] = None,
        reject_handler: Callable[[str, str, str], bool] = None,
    ) -> None:
        """
        Register an approval provider for a specific type.

        Args:
            approval_type: Type of approvals this provider handles
            provider: Function that returns list of pending ApprovalItems
            approve_handler: Function(source_id, approved_by) -> success
            reject_handler: Function(source_id, rejected_by, reason) -> success
        """
        self._approval_providers[approval_type] = provider
        self._approval_handlers[approval_type] = {
            "approve": approve_handler,
            "reject": reject_handler,
        }
        logger.info(f"Registered approval provider: {approval_type.value}")

    def get_pending_approvals(self, approval_type: ApprovalType = None) -> List[ApprovalItem]:
        """
        Get all pending approvals, optionally filtered by type.

        This is the unified "what needs my attention?" view.
        """
        approvals = []

        providers = (
            {approval_type: self._approval_providers[approval_type]}
            if approval_type and approval_type in self._approval_providers
            else self._approval_providers
        )

        for atype, provider in providers.items():
            try:
                items = provider()
                approvals.extend(items)
            except Exception as e:
                logger.error(f"Error fetching approvals from {atype.value}: {e}")

        # Sort by priority then creation time
        approvals.sort(key=lambda a: (a.priority.value, a.created_at))
        return approvals

    def get_approval_counts(self) -> Dict[str, int]:
        """Get count of pending approvals by type."""
        counts = {}
        for atype, provider in self._approval_providers.items():
            try:
                items = provider()
                counts[atype.value] = len(items)
            except Exception as e:
                logger.error(f"Error counting approvals from {atype.value}: {e}")
                counts[atype.value] = 0
        counts["total"] = sum(counts.values())
        return counts

    async def approve_item(
        self,
        approval_type: ApprovalType,
        source_id: str,
        approved_by: str = "admin",
    ) -> Dict[str, Any]:
        """
        Approve an item through the unified interface.

        Delegates to the registered handler for that approval type.
        """
        if approval_type not in self._approval_handlers:
            return {"success": False, "error": f"No handler for {approval_type.value}"}

        handler = self._approval_handlers[approval_type].get("approve")
        if not handler:
            return {"success": False, "error": f"No approve handler for {approval_type.value}"}

        try:
            # Handler might be sync or async
            if asyncio.iscoroutinefunction(handler):
                result = await handler(source_id, approved_by)
            else:
                result = handler(source_id, approved_by)

            return {"success": bool(result), "approved_by": approved_by}
        except Exception as e:
            logger.error(f"Error approving {approval_type.value}/{source_id}: {e}")
            return {"success": False, "error": str(e)}

    async def reject_item(
        self,
        approval_type: ApprovalType,
        source_id: str,
        rejected_by: str = "admin",
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        Reject an item through the unified interface.

        Delegates to the registered handler for that approval type.
        """
        if approval_type not in self._approval_handlers:
            return {"success": False, "error": f"No handler for {approval_type.value}"}

        handler = self._approval_handlers[approval_type].get("reject")
        if not handler:
            return {"success": False, "error": f"No reject handler for {approval_type.value}"}

        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(source_id, rejected_by, reason)
            else:
                result = handler(source_id, rejected_by, reason)

            return {"success": bool(result), "rejected_by": rejected_by, "reason": reason}
        except Exception as e:
            logger.error(f"Error rejecting {approval_type.value}/{source_id}: {e}")
            return {"success": False, "error": str(e)}


def create_task(
    name: str,
    category: TaskCategory,
    handler: Callable[..., Awaitable[Any]],
    priority: TaskPriority = TaskPriority.NORMAL,
    estimated_cost_usd: float = 0.0,
    requires_idle: bool = False,
    context: Dict[str, Any] = None,
    cron: str = None,
    interval_seconds: int = None,
) -> ScheduledTask:
    """Factory function to create a ScheduledTask."""
    return ScheduledTask(
        task_id=str(uuid.uuid4())[:8],
        name=name,
        category=category,
        priority=priority,
        handler=handler,
        estimated_cost_usd=estimated_cost_usd,
        requires_idle=requires_idle,
        context=context or {},
        cron=cron,
        interval_seconds=interval_seconds,
    )
