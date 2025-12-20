"""
Budget Manager - Global spend tracking for autonomous activities.

Tracks and enforces spending limits across all task categories,
integrating with TokenTracker for actual spend data.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TaskCategory(Enum):
    """Categories of scheduled tasks."""
    SYSTEM = "system"           # Crontab-style recurring (github, summarization)
    RESEARCH = "research"       # Wiki research, exploration
    REFLECTION = "reflection"   # Solo contemplation, synthesis
    GROWTH = "growth"           # Growth edge work
    CURIOSITY = "curiosity"     # Self-directed questions
    TRIGGERED = "triggered"     # Event-driven (future)
    MESSAGE = "message"         # Chat handling (future)


@dataclass
class BudgetConfig:
    """Configuration for budget management."""
    daily_budget_usd: float = 5.0
    emergency_reserve: float = 0.5  # Always keep this available for critical tasks

    # Category allocations (should sum to ≤1.0)
    # Remaining budget after allocations goes to emergency reserve
    allocations: Dict[TaskCategory, float] = field(default_factory=lambda: {
        TaskCategory.SYSTEM: 0.10,      # 10% for system tasks
        TaskCategory.RESEARCH: 0.30,    # 30% for research
        TaskCategory.REFLECTION: 0.20,  # 20% for reflection
        TaskCategory.GROWTH: 0.15,      # 15% for growth
        TaskCategory.CURIOSITY: 0.15,   # 15% for curiosity
        TaskCategory.TRIGGERED: 0.05,   # 5% for triggered
        TaskCategory.MESSAGE: 0.05,     # 5% for messages
    })


class BudgetManager:
    """
    Tracks and enforces spending across all autonomous activities.

    Integrates with TokenTracker for actual spend data.
    Resets daily at midnight UTC.
    """

    def __init__(self, config: BudgetConfig = None, token_tracker=None):
        self.config = config or BudgetConfig()
        self.tracker = token_tracker

        # Daily spend tracking by category
        self._spend_by_category: Dict[TaskCategory, float] = {
            cat: 0.0 for cat in TaskCategory
        }
        self._last_reset: Optional[datetime] = None
        self._reset_if_new_day()

    def _reset_if_new_day(self) -> bool:
        """Reset spend tracking if it's a new day (UTC). Returns True if reset occurred."""
        now = datetime.now(timezone.utc)
        today = now.date()

        if self._last_reset is None or self._last_reset.date() < today:
            self._spend_by_category = {cat: 0.0 for cat in TaskCategory}
            self._last_reset = now
            logger.info(f"Budget reset for new day: {today}")
            return True
        return False

    def get_category_budget(self, category: TaskCategory) -> float:
        """Get the total daily budget for a category."""
        allocation = self.config.allocations.get(category, 0.0)
        return self.config.daily_budget_usd * allocation

    def get_remaining_budget(self, category: TaskCategory) -> float:
        """Get remaining budget for a category today."""
        self._reset_if_new_day()
        total = self.get_category_budget(category)
        spent = self._spend_by_category.get(category, 0.0)
        return max(0.0, total - spent)

    def get_total_remaining(self) -> float:
        """Get total remaining budget across all categories."""
        self._reset_if_new_day()
        total_spent = sum(self._spend_by_category.values())
        return max(0.0, self.config.daily_budget_usd - total_spent)

    def can_spend(self, category: TaskCategory, estimated_usd: float) -> bool:
        """
        Check if a task can be run within budget.

        Args:
            category: The task category
            estimated_usd: Estimated cost of the task

        Returns:
            True if the task can be run within category and global budgets
        """
        self._reset_if_new_day()

        # Check category budget
        remaining = self.get_remaining_budget(category)
        if estimated_usd > remaining:
            logger.debug(
                f"Budget check failed for {category.value}: "
                f"estimated ${estimated_usd:.4f} > remaining ${remaining:.4f}"
            )
            return False

        # Check global budget (with emergency reserve)
        available = self.get_total_remaining() - self.config.emergency_reserve
        if estimated_usd > available:
            logger.debug(
                f"Global budget check failed: "
                f"estimated ${estimated_usd:.4f} > available ${available:.4f}"
            )
            return False

        return True

    def record_spend(self, category: TaskCategory, actual_usd: float) -> None:
        """
        Record actual spend after task completion.

        Args:
            category: The task category
            actual_usd: Actual cost incurred
        """
        self._reset_if_new_day()
        self._spend_by_category[category] = (
            self._spend_by_category.get(category, 0.0) + actual_usd
        )
        logger.debug(
            f"Recorded spend: ${actual_usd:.4f} for {category.value}, "
            f"total today: ${self._spend_by_category[category]:.4f}"
        )

    def get_budget_status(self) -> Dict[str, Any]:
        """
        Get full budget status for monitoring.

        Returns:
            Dict with daily budget, spend by category, remaining amounts
        """
        self._reset_if_new_day()
        # Sync from token tracker to get latest spend data
        self.sync_from_token_tracker()

        status = {
            "daily_budget_usd": self.config.daily_budget_usd,
            "emergency_reserve": self.config.emergency_reserve,
            "last_reset": self._last_reset.isoformat() if self._last_reset else None,
            "total_spent": sum(self._spend_by_category.values()),
            "total_remaining": self.get_total_remaining(),
            "by_category": {},
        }

        for category in TaskCategory:
            cat_budget = self.get_category_budget(category)
            cat_spent = self._spend_by_category.get(category, 0.0)
            status["by_category"][category.value] = {
                "budget": cat_budget,
                "spent": cat_spent,
                "remaining": max(0.0, cat_budget - cat_spent),
                "allocation_pct": self.config.allocations.get(category, 0.0) * 100,
            }

        return status

    def use_emergency_reserve(self, amount_usd: float) -> bool:
        """
        Use emergency reserve for critical tasks.

        Should only be called for CRITICAL priority tasks.
        Returns True if reserve was available and used.
        """
        if amount_usd > self.config.emergency_reserve:
            return False

        # Record against SYSTEM category but allow exceeding normal limits
        self._spend_by_category[TaskCategory.SYSTEM] = (
            self._spend_by_category.get(TaskCategory.SYSTEM, 0.0) + amount_usd
        )
        logger.warning(f"Used ${amount_usd:.4f} from emergency reserve")
        return True

    def sync_from_token_tracker(self) -> None:
        """
        Sync spend data from token_tracker for today.

        Only counts autonomous activities (NOT chat).
        Maps token_tracker categories to TaskCategory.
        """
        if not self.tracker:
            return

        self._reset_if_new_day()

        # Get today's summary from token tracker
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        try:
            summary = self.tracker.get_summary(start_date=today_start)
            by_category = summary.get("by_category", {})

            # Map token_tracker categories to TaskCategory
            # NOTE: "chat" is explicitly excluded - it's user-driven, not autonomous
            category_mapping = {
                "research": TaskCategory.RESEARCH,
                "reflection": TaskCategory.REFLECTION,
                "summarization": TaskCategory.SYSTEM,
                "internal": TaskCategory.SYSTEM,
                "synthesis": TaskCategory.REFLECTION,
                "growth_edge": TaskCategory.GROWTH,
                "curiosity": TaskCategory.CURIOSITY,
                "dream": TaskCategory.SYSTEM,
                "journal": TaskCategory.SYSTEM,
            }

            # Reset and repopulate from token tracker
            new_spend = {cat: 0.0 for cat in TaskCategory}

            for tracker_cat, data in by_category.items():
                # Skip chat - that's user activity, not autonomous budget
                if tracker_cat == "chat":
                    continue

                task_cat = category_mapping.get(tracker_cat)
                if task_cat:
                    new_spend[task_cat] += data.get("cost", 0.0)
                else:
                    # Unknown category goes to SYSTEM
                    if tracker_cat not in ("unknown",):
                        new_spend[TaskCategory.SYSTEM] += data.get("cost", 0.0)

            self._spend_by_category = new_spend

            total = sum(new_spend.values())
            if total > 0:
                logger.debug(f"Synced spend from token_tracker: ${total:.4f}")

        except Exception as e:
            logger.warning(f"Failed to sync from token_tracker: {e}")
