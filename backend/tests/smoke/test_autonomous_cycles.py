"""
Smoke (f): each Synkratos system job and each Grimoire timer spell runs one
cycle against the fake LLM, with its levers on.

The app is booted once for the module with the relevant levers on (so the
real startup wiring builds the scheduler, the action registry and Grimoire),
then each job/spell is run once by hand, which is what its timer would do.
Nothing runs on its own: the scheduler loop and Thymos tick stay off.

Known-broken cycles from the audit are xfail(strict=True). These tests check
that a cycle did its work, not just that it didn't crash, because most of the
breakage here is swallowed and reported as success.
"""
import json
import uuid
from datetime import datetime, timedelta

import pytest

from tests.fakes.llm import ScriptedResponse
from tests.smoke.conftest import module_app

LEVERS_ON = dict(
    # Synkratos jobs (registered at boot; the scheduler loop itself stays off)
    job_github_metrics=True, job_idle_summarization=True, job_daily_journal=True,
    job_goal_refinement=True, job_autonomous_research=True,
    # Action registry + the autonomous action domains the spells call
    autonomous_scheduling=True, rss=True, research=True, art_study=True,
    outreach=True, wonderland_actions=True,
)


@pytest.fixture(scope="module")
def app(template_db, tmp_path_factory):
    with module_app(template_db, tmp_path_factory, **LEVERS_ON) as booted:
        yield booted


@pytest.fixture
def test_db(app):
    # Share the module app's database with the test thread (overrides the
    # autouse per-test DB from tests/conftest.py).
    return app.db_path


def _structured_answers(source, kwargs):
    """Answer Grimoire's JSON-shaped prompts (RATE/ASK/CHOOSE) sensibly."""
    system = kwargs.get("system") or ""
    if not isinstance(system, str):
        return None
    if '"rating"' in system:
        return ScriptedResponse(text=json.dumps({"rating": 0.9, "reasoning": "smoke"}))
    if '"answer"' in system:
        return ScriptedResponse(text=json.dumps({"answer": True, "reasoning": "smoke"}))
    if '"should_summarize"' in str(kwargs.get("messages")):
        return ScriptedResponse(text=json.dumps(
            {"should_summarize": True, "reason": "smoke", "confidence": 0.9}))
    return None


@pytest.fixture(autouse=True)
def _answer_structured_prompts(fake_llm):
    fake_llm.responder = _structured_answers
    return fake_llm


def _run(app, coro_fn):
    """Run an async callable on the app's event loop (where its objects live)."""
    return app.portal.call(coro_fn)


# ---------------------------------------------------------------------------
# Synkratos system jobs
# ---------------------------------------------------------------------------

def _system_task(name):
    from routes.admin.scheduler import get_scheduler
    synkratos = get_scheduler()
    tasks = {t.name: t for t in synkratos.system_tasks.values()}
    assert name in tasks, f"{name} not registered (registered: {sorted(tasks)})"
    return tasks[name]


def _run_job(app, name):
    task = _system_task(name)
    return _run(app, lambda: task.handler(**task.context))


def test_scheduler_loop_not_started(app):
    from routes.admin.scheduler import get_scheduler
    assert get_scheduler()._running is False


def test_job_github_metrics(app):
    import github_metrics
    from database import get_db

    async def fake_fetch(self, repo, token=None):
        return github_metrics.RepoMetrics(repo=repo, stars=7)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(github_metrics.GitHubMetricsManager, "fetch_repo_metrics", fake_fetch)
        result = _run_job(app, "github_metrics")

    assert result.success, result.message
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM github_metrics").fetchone()[0] >= 1


def _seed_idle_conversation(user_turns=3):
    """A conversation whose last message is 2h old, with enough unsummarized turns."""
    from database import get_db, get_daemon_id

    conversation_id = str(uuid.uuid4())
    old = datetime.now() - timedelta(hours=2)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO conversations (id, daemon_id, title, created_at, updated_at, "
            "messages_since_last_summary) VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, get_daemon_id(), "idle smoke", old.isoformat(), old.isoformat(),
             user_turns * 2),
        )
        for i in range(user_turns * 2):
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, timestamp, excluded) "
                "VALUES (?, ?, ?, ?, 0)",
                (conversation_id, "user" if i % 2 == 0 else "assistant", f"message {i}",
                 (old + timedelta(seconds=i)).isoformat()),
            )
    return conversation_id


def test_job_idle_summarization(app, fake_llm):
    import main_sdk

    conversation_id = _seed_idle_conversation()
    fake_llm.queue_text("Kohl and Cass talked about smoke tests.")  # the summary itself

    result = _run_job(app, "idle_summarization")

    assert result.success, result.message
    assert result.data["summarized_count"] == 1
    summaries = main_sdk.memory.get_summaries_for_conversation(conversation_id)
    assert summaries, "no summary was stored for the idle conversation"


def test_job_daily_journal_writes_dream(app):
    from database import get_db

    result = _run_job(app, "daily_journal")

    assert result.success, result.message
    assert result.data["dream_generated"] is True
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM dreams").fetchone()[0] >= 1


def test_job_daily_journal_writes_journal(app):
    import main_sdk

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    main_sdk.memory.collection.add(
        ids=[f"smoke-conv-{uuid.uuid4()}"],
        documents=["User: hi\nCass: hello, a smoke-test exchange"],
        metadatas=[{"type": "conversation", "timestamp": f"{yesterday}T12:00:00"}],
    )

    result = _run_job(app, "daily_journal")

    assert result.data["journal_generated"] is True, result.message


def test_job_goal_refinement(app):
    result = _run_job(app, "goal_refinement")
    assert result.success, result.message
    assert "goals_checked" in result.data


@pytest.mark.xfail(strict=True, reason=(
    "cards/04_autonomy.md 1d: autonomous_research is never registered - "
    "system_tasks.py reads research_scheduler.config.mode, which doesn't exist"))
def test_job_autonomous_research(app):
    result = _run_job(app, "autonomous_research")
    assert result.success, result.message


# ---------------------------------------------------------------------------
# Grimoire timer spells
# ---------------------------------------------------------------------------

def _timer_spells():
    import main_sdk
    grimoire = main_sdk._grimoire
    assert grimoire is not None
    return {spell.metadata.name: spell for spell, _ in grimoire.registry.get_timer_spells()}


def _cast(app, spell_name):
    """Run one timer spell cycle; return (spell result, [(action, ActionResult)])."""
    import main_sdk
    from scheduler.actions import get_action_registry

    spell = _timer_spells()[spell_name]
    registry = get_action_registry()
    actions = []
    real_execute = registry.execute

    async def recording_execute(action_id, **kwargs):
        result = await real_execute(action_id, **kwargs)
        actions.append((action_id, result))
        return result

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(registry, "execute", recording_execute)
        result = _run(app, lambda: main_sdk._grimoire._execute_spell(
            spell, {"trigger_type": "timer"}, "timer"))
    return result, actions


def _assert_cycle_did_work(result, actions):
    assert result.status == "success", f"{result.status}: {result.reason}"
    failed = [(a, r.message) for a, r in actions if not r.success]
    assert not failed, f"actions failed inside the spell: {failed}"


def test_timer_spells_loaded(app):
    assert set(_timer_spells()) >= {"rss_monitor", "research_synthesis", "art_study"}


def test_grimoire_attached_to_thymos_without_starting_it(app):
    import main_sdk
    assert main_sdk.thymos_runner._grimoire is main_sdk._grimoire
    assert main_sdk.thymos_runner.running is False


@pytest.mark.xfail(strict=True, reason=(
    "cards/05_research_creative.md (RSS feeds): rss.* actions read context['daemon_id'] "
    "but the spell passes none (it's only under managers), so every step fails"))
def test_timer_spell_rss_monitor(app):
    _assert_cycle_did_work(*_cast(app, "rss_monitor"))


@pytest.mark.xfail(strict=True, reason=(
    "cards/04_autonomy.md (action registry): research.run_batch gets "
    "research_scheduler.ResearchScheduler, which has no refresh_tasks/run_batch"))
def test_timer_spell_research_synthesis(app):
    _assert_cycle_did_work(*_cast(app, "research_synthesis"))


@pytest.mark.xfail(strict=True, reason=(
    "cards/05_research_creative.md (Art study): handlers pass a sync anthropic client "
    "to code that awaits it; also list_studies_for_artist() called without daemon_id"))
def test_timer_spell_art_study(app):
    _assert_cycle_did_work(*_cast(app, "art_study"))


@pytest.mark.xfail(strict=True, reason=(
    "CAPABILITIES.md: spells/goal_executor.spell fails to parse at line 49 "
    "(ACTION is reserved), so the goal executor never loads"))
def test_timer_spell_goal_executor(app):
    _assert_cycle_did_work(*_cast(app, "goal_executor"))


# ---------------------------------------------------------------------------
# Need-threshold spells that call autonomous actions (outreach, Wonderland)
# ---------------------------------------------------------------------------

def _need_spell(name):
    import main_sdk
    return main_sdk._grimoire.registry.spells[name]


def _cast_need_spell(app, name):
    import main_sdk
    from scheduler.actions import get_action_registry

    registry = get_action_registry()
    actions = []
    real_execute = registry.execute

    async def recording_execute(action_id, **kwargs):
        result = await real_execute(action_id, **kwargs)
        actions.append((action_id, result))
        return result

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(registry, "execute", recording_execute)
        result = _run(app, lambda: main_sdk._grimoire._execute_spell(
            _need_spell(name), {"trigger_type": "need"}, "need"))
    return result, actions


@pytest.mark.xfail(strict=True, reason=(
    "cards/05_research_creative.md (Outreach): social_care calls "
    "`TASK outreach.draft type=... tone=...` but the handler requires title and content"))
def test_need_spell_social_care_outreach(app):
    result, actions = _cast_need_spell(app, "social_care")
    assert any(a == "outreach.draft" for a, _ in actions), "outreach.draft not reached"
    _assert_cycle_did_work(result, actions)


def test_need_spell_novelty_care_wonderland(app):
    result, actions = _cast_need_spell(app, "novelty_care")
    assert any(a == "wonderland.explore" for a, _ in actions)
    _assert_cycle_did_work(result, actions)
