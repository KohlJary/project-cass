"""
Smoke: the Heartbeat cutover (#62) at boot, with Thymos, Grimoire, the day
phases and the phase queue on as well.

With the `heartbeat` lever on, the old loops of the work Heartbeat took over
must not also run: Thymos's own tick loop, the day-phase tracker's minute
loop, the Grimoire tick hook (spells become Heartbeat work), and the
Synkratos system jobs. Then one Thymos tick and one day-phase check run
through Heartbeat.
"""
import pytest

from tests.smoke.conftest import module_app

LEVERS_ON = dict(
    heartbeat=True, scheduler=True, thymos=True,
    grimoire_timer_spells=True, grimoire_need_spells=True,
    autonomous_scheduling=True, day_phases=True, goal_orchestrator=True,
    job_github_metrics=True, job_idle_summarization=True, job_daily_journal=True,
    job_goal_refinement=True, job_autonomous_research=True,
)


@pytest.fixture(scope="module")
def app(template_db, tmp_path_factory):
    import main_sdk
    from heartbeat import wiring

    wiring.reset()
    try:
        with module_app(template_db, tmp_path_factory, **LEVERS_ON) as booted:
            booted.thymos = main_sdk.thymos_runner
            yield booted
            hb = wiring.get_heartbeat()
            if hb is not None:
                booted.portal.call(hb.stop)
            booted.portal.call(main_sdk.thymos_runner.stop)
    finally:
        wiring.reset()


@pytest.fixture
def test_db(app):
    return app.db_path


def test_old_loops_stand_down_for_heartbeat(app):
    from heartbeat import wiring
    from routes.admin.scheduler import get_phase_queue_manager, get_scheduler

    hb = wiring.get_heartbeat()
    assert hb is not None, "heartbeat lever on, but Heartbeat did not start"
    names = hb.registry.names()

    # Thymos: Heartbeat ticks it; its own loop is off.
    assert wiring.owns("thymos_tick") and "thymos_tick" in names
    assert app.thymos.running and app.thymos._tick_task is None

    # Grimoire: spells are Heartbeat work; the tick hook no longer runs them.
    assert wiring.owns("grimoire_spells") and app.thymos.spells_on_heartbeat
    spells = {n for n in names if n.startswith("spell.")}
    assert {"spell.goal_executor", "spell.research_synthesis",
            "spell.cognitive_rest"} <= spells

    # Day phases: Heartbeat checks; the tracker has no loop of its own.
    assert wiring.owns("day_phase") and "day_phase" in names
    # Phase-queue items and GoalOrchestrator events submit Heartbeat work.
    assert get_phase_queue_manager() is not None
    for subsystem in ("phase_queue", "phase_email", "goal_orchestrator"):
        assert wiring.owns(subsystem), subsystem

    # Synkratos keeps none of the jobs.
    assert {t.name for t in get_scheduler().system_tasks.values()} == set()


def test_thymos_tick_and_day_phase_check_run_on_heartbeat(app, levers):
    from heartbeat import wiring

    hb = wiring.get_heartbeat()
    before = app.thymos.current_needs()
    for name in ("thymos_tick", "day_phase"):
        hb.registry.get(name).next_run = hb.clock.now()

    async def run_due():
        await hb.tick()
        await hb.drain()

    with levers(**LEVERS_ON):
        app.portal.call(run_due)
    assert hb.registry.get("thymos_tick").run_count >= 1
    assert hb.registry.get("day_phase").run_count >= 1
    # A tick applies need decay; at least one need moved.
    assert app.thymos.current_needs() != before
