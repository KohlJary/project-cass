"""Agent-loop sessions count in the budget, in their own bucket (2026-11-17)."""
from heartbeat import spend
from scheduler.budget import TaskCategory, budget_category_for, counts_toward_budget


def test_session_spend_counts():
    assert counts_toward_budget("session.generic")


def test_a_session_in_a_heartbeat_run_files_under_its_budget_class():
    from agent_loop.session import ledger_category
    for cls in TaskCategory:
        token = spend.begin(spend.RunSpend(work_name="phase.x", budget_class=cls))
        try:
            got = ledger_category()
        finally:
            spend.end(token)
        assert got == cls.value
        if cls is not TaskCategory.MESSAGE:
            assert budget_category_for(got) is cls


def test_outside_a_run_a_session_files_under_reflection():
    from agent_loop.session import ledger_category
    assert ledger_category() == "reflection"
    assert budget_category_for("reflection") is TaskCategory.REFLECTION


def test_a_run_with_no_budget_class_files_under_reflection():
    from agent_loop.session import ledger_category
    token = spend.begin(spend.RunSpend(work_name="day_phase"))
    try:
        assert ledger_category() == "reflection"
    finally:
        spend.end(token)


def test_old_session_rows_stay_out_of_the_budget():
    assert budget_category_for("session") is None
