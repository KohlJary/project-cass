"""
Smoke: Heartbeat (lever `heartbeat`) at boot.

Boots the app with Heartbeat and the Synkratos jobs on. Every Synkratos system
job must be registered on Heartbeat and not with Synkratos (one trigger path
per job, #62 cutover), and a run through Heartbeat must leave a run-log row.
"""
import pytest

from tests.smoke.conftest import module_app

LEVERS_ON = dict(
    heartbeat=True,
    job_github_metrics=True, job_idle_summarization=True, job_daily_journal=True,
    job_goal_refinement=True, job_autonomous_research=True,
)


@pytest.fixture(scope="module")
def app(template_db, tmp_path_factory):
    from heartbeat import wiring
    wiring.reset()
    try:
        with module_app(template_db, tmp_path_factory, **LEVERS_ON) as booted:
            yield booted
            hb = wiring.get_heartbeat()
            if hb is not None:
                booted.portal.call(hb.stop)
    finally:
        wiring.reset()


@pytest.fixture
def test_db(app):
    return app.db_path


def test_migrated_jobs_run_on_heartbeat_not_synkratos(app):
    from heartbeat import wiring
    from routes.admin.scheduler import get_scheduler

    hb = wiring.get_heartbeat()
    assert hb is not None, "heartbeat lever on, but Heartbeat did not start"
    on_heartbeat = {w.name for w in hb.registry.all()}
    on_synkratos = {t.name for t in get_scheduler().system_tasks.values()}

    system_jobs = {"github_metrics", "goal_refinement", "idle_summarization",
                   "daily_journal", "autonomous_research"}
    assert system_jobs <= on_heartbeat
    assert {"conversation_observation", "budget_sync"} <= on_heartbeat
    assert not on_heartbeat & on_synkratos
    assert on_synkratos == set()


def test_a_heartbeat_run_is_logged(app, levers):
    from heartbeat import RunLog, wiring

    hb = wiring.get_heartbeat()
    work = hb.registry.get("goal_refinement")
    work.next_run = hb.clock.now()

    async def run_due():
        await hb.tick()
        await hb.drain()

    with levers(scheduler=True, **LEVERS_ON):
        app.portal.call(run_due)
    rows = RunLog().recent(work_name="goal_refinement")
    assert rows and rows[0]["status"] == "ok", rows
