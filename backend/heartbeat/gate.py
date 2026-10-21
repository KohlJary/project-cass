"""
The one budget gate.

Wraps the existing scheduler.budget.BudgetManager (the same instance Synkratos
uses, so spend is counted in one place). Rules:

- CONVERSATION work is always admitted. A person talking to her is never
  refused for budget (Kohl's rule), and chat spend is not charged to the
  autonomous budget (BudgetManager.sync_from_token_tracker leaves chat out).
- Work with no budget class, or an estimate of 0, is admitted.
- Everything else asks BudgetManager.can_spend(category, estimate).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .registry import CONVERSATION, Work

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""


class BudgetGate:
    def __init__(self, budget_manager=None):
        self.budget = budget_manager

    def check(self, work: Work) -> Decision:
        if work.budget_class == CONVERSATION:
            return Decision(True, "conversation")
        if work.budget_class is None or work.estimated_cost_usd <= 0:
            return Decision(True, "free")
        if self.budget is None:
            # No ledger wired: refuse spend we can't count rather than run blind.
            return Decision(False, "no budget manager")
        if self.budget.can_spend(work.budget_class, work.estimated_cost_usd):
            return Decision(True, "within budget")
        return Decision(False, f"over budget for {work.budget_label} "
                               f"(estimate ${work.estimated_cost_usd:.2f})")

    def record(self, work: Work, cost_usd: Optional[float]) -> float:
        """Charge a finished run. Returns what was charged."""
        if work.budget_class in (None, CONVERSATION) or self.budget is None:
            return 0.0
        charged = cost_usd if cost_usd is not None else work.estimated_cost_usd
        if charged > 0:
            self.budget.record_spend(work.budget_class, charged)
        return charged
