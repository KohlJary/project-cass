"""
The Synkratos budget gate counts what it counted before #64 routed every LLM
call into the token ledger (scheduler/budget.py, BUDGET_COUNTED_CALL_SITES).

Newly recorded spend (dreams, sessions, art study, ...) is in the ledger and
on the admin page but must not defer system tasks such as idle_summarization
and daily_journal until Kohl turns COUNT_ALL_LEDGER_SPEND on.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("anthropic")  # the scheduler package needs the runtime deps

from scheduler import budget as budget_mod
from scheduler.budget import BudgetConfig, BudgetManager, TaskCategory
from token_tracker import TokenUsageTracker


class _LastDayTracker:
    """The real ledger, read over the last 24 hours.

    sync_from_token_tracker's own window has a timezone mismatch (see the
    xfail test below); this keeps these tests about *what* is counted.
    """

    def __init__(self):
        self._t = TokenUsageTracker()

    def get_records(self, start_date=None, end_date=None, **kw):
        return self._t.get_records(start_date=datetime.now() - timedelta(days=1), **kw)


def _system_tasks():
    """The real daily_journal and idle_summarization task definitions."""
    import features
    from scheduler.system_tasks import register_system_tasks

    class Capture:
        tasks = {}

        def register_system_task(self, task):
            self.tasks[task.name] = task

    cap = Capture()
    managers = {"conversation_manager": object(), "memory": object(),
                "generate_missing_journals": lambda *a, **k: None}
    with features.override(job_idle_summarization=True, job_daily_journal=True):
        register_system_tasks(cap, managers, enabled=True)
    return cap.tasks["daily_journal"], cap.tasks["idle_summarization"]


def _spend(call_site, category, usd):
    """One ledger row costing about `usd` (Sonnet output pricing $15/M)."""
    from llm_caller import record_usage
    record_usage(call_site, "anthropic", "claude-sonnet-4-6",
                 output_tokens=int(usd / 15.0 * 1_000_000), category=category)


def _gate(tracker=None):
    mgr = BudgetManager(BudgetConfig(), tracker or _LastDayTracker())
    mgr.sync_from_token_tracker()
    return mgr


@pytest.mark.unit
def test_new_routed_spend_does_not_defer_daily_journal_or_idle_summarization():
    # $2 of spend the ledger only sees since #64: dreams, a session, art study.
    _spend("dreaming.the_dreaming", "dreaming", 0.80)
    _spend("session.generic", "session", 0.70)
    _spend("art_study.deep_analysis", "art_study", 0.50)

    daily_journal, idle_summarization = _system_tasks()
    gate = _gate()
    assert sum(gate._spend_by_category.values()) == 0.0
    for task in (daily_journal, idle_summarization):
        assert gate.can_spend(task.category, task.estimated_cost_usd), task.name


@pytest.mark.unit
def test_spend_the_gate_counted_before_still_counts():
    # Rows written directly (no call site) and call sites that recorded
    # before #64 count as they did: $2 of summarization uses up SYSTEM.
    TokenUsageTracker().record(category="internal", operation="something_old",
                               provider="anthropic", model="claude-sonnet-4-6",
                               output_tokens=int(1.0 / 15.0 * 1_000_000))
    _spend("memory.summary_chunk", "summarization", 1.0)

    daily_journal, idle_summarization = _system_tasks()
    gate = _gate()
    assert gate._spend_by_category[TaskCategory.SYSTEM] == pytest.approx(2.0, rel=0.01)
    assert not gate.can_spend(daily_journal.category, daily_journal.estimated_cost_usd)


@pytest.mark.unit
def test_count_all_switch_counts_everything(monkeypatch):
    _spend("dreaming.the_dreaming", "dreaming", 2.0)
    monkeypatch.setattr(budget_mod, "COUNT_ALL_LEDGER_SPEND", True)
    daily_journal, _ = _system_tasks()
    gate = _gate()
    assert gate._spend_by_category[TaskCategory.SYSTEM] == pytest.approx(2.0, rel=0.01)
    assert not gate.can_spend(daily_journal.category, daily_journal.estimated_cost_usd)


@pytest.mark.unit
def test_counted_call_sites_are_registered():
    from llm_config import CALL_SITES
    assert budget_mod.BUDGET_COUNTED_CALL_SITES <= set(CALL_SITES)


@pytest.mark.unit
@pytest.mark.xfail(strict=True, reason=(
    "Pre-existing (not #64): sync_from_token_tracker starts the day at UTC "
    "midnight but the ledger stores naive local timestamps, so after UTC "
    "midnight and before local midnight (e.g. 20:00-24:00 EDT) the gate "
    "counts none of the day's spend. Left as is: fixing it changes budget "
    "behaviour, which is Kohl's call."))
def test_budget_window_timezone(monkeypatch):
    from database import get_db
    # 21:00 local on Oct 20 in UTC-4 is 01:00 UTC on Oct 21: same instant.
    tracker = TokenUsageTracker()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO token_usage_records (id, daemon_id, timestamp, provider, model, category, "
            "operation, input_tokens, output_tokens, total_tokens, estimated_cost_usd) "
            "VALUES (?, ?, ?, 'anthropic', 'm', 'internal', 'x', 0, 0, 0, 1.0)",
            (str(uuid.uuid4()), tracker._daemon_id, "2026-10-20T21:00:00"))

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            utc = datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc)
            return utc if tz else datetime(2026, 10, 20, 21, 0)

    monkeypatch.setattr(budget_mod, "datetime", FrozenDatetime)
    gate = BudgetManager(BudgetConfig(), tracker)
    gate.sync_from_token_tracker()
    assert gate._spend_by_category[TaskCategory.SYSTEM] == pytest.approx(1.0)
