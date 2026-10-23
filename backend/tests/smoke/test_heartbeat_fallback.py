"""
Smoke: the legacy-fallback guard with Heartbeat on.

When Synkratos init fails after Heartbeat has started, main_sdk falls back to
the old asyncio loops. A job Heartbeat owns must not get a second trigger path
there, and the ones it doesn't own still start. (Since the cutover, #62,
Heartbeat registers all four; this battery registers only two of them, so
both halves of the guard are exercised.)
"""
import pytest

from tests.smoke.conftest import module_app

LEVERS_ON = dict(heartbeat=True, job_github_metrics=True, legacy_background_loops=True)
OWNED = {"github_metrics", "daily_journal"}


@pytest.fixture(scope="module")
def app(template_db, tmp_path_factory):
    import main_sdk
    import routes.admin
    from heartbeat import wiring

    started = []

    def recorder(name):
        async def fake(*args, **kwargs):
            started.append(name)
        return fake

    def fail_late(*args, **kwargs):
        raise RuntimeError("smoke: Synkratos init fails after Heartbeat started")

    wiring.reset()
    try:
        with pytest.MonkeyPatch.context() as mp:
            for name in ("daily_journal_task", "autonomous_research_task",
                         "github_metrics_task", "idle_summarization_task"):
                mp.setattr(main_sdk, name, recorder(name))
            mp.setattr(routes.admin, "init_daily_activity_routes", fail_late)
            real_job_work = wiring.job_work
            mp.setattr(wiring, "job_work", lambda managers: {
                name: work for name, work in real_job_work(managers).items()
                if name in OWNED})
            with module_app(template_db, tmp_path_factory, **LEVERS_ON) as booted:
                booted.legacy_started = started
                yield booted
                hb = wiring.get_heartbeat()
                if hb is not None:
                    booted.portal.call(hb.stop)
    finally:
        wiring.reset()


@pytest.fixture
def test_db(app):
    return app.db_path


def test_fallback_skips_the_job_heartbeat_owns(app):
    from heartbeat import wiring

    assert wiring.runs_job("github_metrics") and wiring.runs_job("daily_journal")
    assert not wiring.runs_job("autonomous_research")
    started = set(app.legacy_started)
    assert not started & {"github_metrics_task", "daily_journal_task"}
    assert {"autonomous_research_task", "idle_summarization_task"} <= started
