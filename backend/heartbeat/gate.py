"""
The one budget gate.

Wraps the existing scheduler.budget.BudgetManager, the same instance Synkratos
uses.

What it charges: with measured spend (Heartbeat's default), each token-ledger
row written during a run is charged as it is written, but only rows the
budget counts (scheduler.budget.counts_toward_budget: no call site, or one in
BUDGET_COUNTED_CALL_SITES, or all rows if COUNT_ALL_LEDGER_SPEND), and in the
bucket the sync uses (budget_category_for). That is exactly what
BudgetManager.sync_from_token_tracker rebuilds from the ledger every 60 s, so
the sync no longer wipes what the gate charged (#87's review note): before a
sync and after it, the gate sees the same spend. Two
caveats stay open as decisions for Kohl, unchanged here: which ledger rows
count (COUNT_ALL_LEDGER_SPEND stays False), and the budget day, which resets
at UTC midnight while ledger timestamps are local (pinned by a strict xfail in
tests/test_budget_routing.py). Rules:

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

    def charge(self, work: Work, category, usd: float) -> float:
        """Charge one measured ledger row's counted spend, in the budget bucket
        the sync puts it in (`category`, from budget_category_for), so the
        gate and the sync agree. The work's own budget class decides
        admission (check); conversation work is never charged."""
        if work.budget_class == CONVERSATION or self.budget is None or usd <= 0:
            return 0.0
        self.budget.record_spend(category, usd)
        return usd

    def record(self, work: Work, cost_usd: Optional[float]) -> float:
        """Unmeasured mode: charge a finished run its reported cost, else its
        estimate (Synkratos's rule). Returns what was charged."""
        if work.budget_class in (None, CONVERSATION) or self.budget is None:
            return 0.0
        charged = cost_usd if cost_usd is not None else work.estimated_cost_usd
        if charged > 0:
            self.budget.record_spend(work.budget_class, charged)
        return charged
