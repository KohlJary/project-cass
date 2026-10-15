"""
Regression tests for the "silent breakage" fixes (CAPABILITIES.md, cards 03-05).

Each of these paths used to fail quietly: an AttributeError or a None manager
caught by a broad except and logged. These tests pin the fixed behaviour.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# 1. Nightly journal pipeline reads the live managers
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_managers(monkeypatch):
    """Install fake managers the way main_sdk's init_admin_managers does."""
    import routes.admin as admin_state
    mem, users, selfm, tracker = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(admin_state, "memory", mem)
    monkeypatch.setattr(admin_state, "users", users)
    monkeypatch.setattr(admin_state, "self_manager", selfm)
    monkeypatch.setattr(admin_state, "token_usage_tracker", tracker)
    return SimpleNamespace(memory=mem, users=users, self_manager=selfm, tracker=tracker)


def test_admin_api_reexport_is_stale_but_pipeline_reads_live_managers(admin_managers):
    # admin_api copied routes.admin.memory at import time (None) - that's the
    # trap. The pipeline modules must not read from it.
    import journal_generation
    import journal_tasks
    import research_integration

    mem, tracker, selfm, users = journal_generation._get_dependencies()
    assert (mem, tracker, selfm, users) == (
        admin_managers.memory, admin_managers.tracker,
        admin_managers.self_manager, admin_managers.users)
    assert journal_tasks._get_dependencies() == (admin_managers.memory, admin_managers.self_manager)
    assert research_integration._get_dependencies() == (
        admin_managers.memory, admin_managers.tracker, admin_managers.self_manager)


def test_init_managers_reaches_pipeline():
    import routes.admin as admin_state
    import journal_generation
    saved = (admin_state.memory, admin_state.conversations, admin_state.users, admin_state.self_manager)
    mem, users, selfm = object(), MagicMock(), object()
    try:
        admin_state.init_managers(mem, None, users, selfm)
        got_mem, _, got_self, got_users = journal_generation._get_dependencies()
        assert got_mem is mem and got_self is selfm and got_users is users
    finally:
        admin_state.init_managers(*saved)


def test_phase4_user_observations_use_real_extractor(admin_managers):
    """Phase 4 called memory.extract_user_observations, which doesn't exist."""
    import journal_generation

    mem = admin_managers.memory
    del mem.extract_user_observations  # make the old call raise like CassMemory does
    mem.get_conversations_by_date.return_value = [{"content": "User: hi\nCass: hello"}]
    mem.generate_user_observations = AsyncMock(return_value=["Kohl likes smoke tests a lot."])
    admin_managers.users.load_profile.return_value = SimpleNamespace(display_name="Kohl")
    admin_managers.users.add_observation.return_value = SimpleNamespace(
        id="o1", observation="Kohl likes smoke tests a lot.", category="background",
        timestamp="2026-10-14T12:00:00")

    asyncio.run(journal_generation._generate_user_observations_for_date("u1", "2026-10-14"))

    kwargs = mem.generate_user_observations.await_args.kwargs
    assert kwargs["display_name"] == "Kohl" and "hello" in kwargs["conversation_text"]
    add_kwargs = admin_managers.users.add_observation.call_args.kwargs
    assert add_kwargs["observation"] == "Kohl likes smoke tests a lot."
    assert add_kwargs["source_journal_date"] == "2026-10-14"
    mem.embed_user_observation.assert_called_once()


# ---------------------------------------------------------------------------
# 6. Autonomous research + growth-edge actions
# ---------------------------------------------------------------------------

def _run_action(handler, **context):
    return asyncio.run(handler(context))


def test_update_growth_edge_action_appends_to_matching_edge():
    from self_model import SelfManager
    from scheduler.actions.self_handlers import update_growth_edge_action

    sm = SelfManager()
    edge = sm.add_growth_edge("epistemic humility", "learning", auto_research=False)

    result = _run_action(update_growth_edge_action, managers={"self_manager": sm},
                         edge_id=edge.edge_id, progress="Admitted not knowing twice today.")

    assert result.success, result.message
    stored = [e for e in sm.load_profile().growth_edges if e.edge_id == edge.edge_id][0]
    assert "Admitted not knowing twice today." in stored.observations


def test_update_growth_edge_action_without_edge_keeps_the_insight():
    """Spells only have an insight, not an edge_id; it used to fail every time."""
    from self_model import SelfManager
    from scheduler.actions.self_handlers import update_growth_edge_action

    sm = SelfManager()
    result = _run_action(update_growth_edge_action, managers={"self_manager": sm},
                         insight="Research on epistemics ties to my humility edge.")

    assert result.success, result.message
    assert result.data["observation_id"]


def test_add_observation_action_accepts_spell_content_param():
    from self_model import SelfManager
    from scheduler.actions.self_handlers import add_observation_action

    sm = SelfManager()
    result = _run_action(add_observation_action, managers={"self_manager": sm},
                         content="I enjoy synthesis work.", category="research_insight")
    assert result.success, result.message
    assert isinstance(result.data["observation_id"], str)


def test_autonomous_research_handler_reads_live_mode():
    from scheduler.handlers import autonomous_research_handler
    from wiki.scheduler import SchedulerMode

    sched = MagicMock()
    sched.config.mode = SchedulerMode.SUPERVISED
    result = asyncio.run(autonomous_research_handler(scheduler=sched, mode=None))
    assert result.data["mode"] == "supervised"
    sched.refresh_tasks.assert_not_called()

    sched.config.mode = SchedulerMode.TRIGGERED  # admin switched mode at runtime
    sched.queue.get_stats.return_value = {"queued": 2}
    result = asyncio.run(autonomous_research_handler(scheduler=sched, mode=None))
    assert result.success and result.data["mode"] == "triggered"
    sched.refresh_tasks.assert_called_once()
