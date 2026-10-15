"""
Scheduler time (card 04): Synkratos cron ran in UTC while day phases used
server-local time, and the phase queues lived only in memory, so a restart
lost queued work.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture
def cass_tz(monkeypatch):
    import config

    def set_tz(name):
        monkeypatch.setattr(config, "CASS_TIMEZONE", name)
    return set_tz


# ---------------------------------------------------------------------------
# One configurable timezone
# ---------------------------------------------------------------------------

def test_unset_keeps_old_clocks(cass_tz):
    """Default: cron in UTC, phases in naive server-local time (unchanged)."""
    from scheduler.core import CronParser
    from schedule_clock import phase_now

    cass_tz(None)
    start = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    nxt = CronParser.parse_next_run("5 0 * * *", start)
    assert nxt == datetime(2026, 3, 2, 0, 5, tzinfo=timezone.utc)
    assert phase_now().tzinfo is None


def test_cron_and_phases_share_cass_timezone(cass_tz):
    from scheduler.core import CronParser
    from scheduling.day_phase import DayPhase, DayPhaseTracker
    from schedule_clock import phase_now

    cass_tz("America/New_York")
    ny = ZoneInfo("America/New_York")

    # "5 0 * * *" means 00:05 New York time, not 00:05 UTC
    start = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    nxt = CronParser.parse_next_run("5 0 * * *", start)
    assert nxt.astimezone(ny).replace(tzinfo=None) == datetime(2026, 3, 2, 0, 5)
    assert nxt.astimezone(timezone.utc).hour == 5  # 00:05 EST == 05:05 UTC

    # Phases are measured on the same clock
    assert phase_now().tzinfo is not None
    assert phase_now().utcoffset() == datetime.now(ny).utcoffset()
    tracker = DayPhaseTracker()
    late_ny = datetime(2026, 3, 1, 23, 0, tzinfo=ny)
    assert tracker.get_phase_for_time(late_ny) == DayPhase.NIGHT


def test_scheduler_compares_aware_times(cass_tz):
    """next_run computed in a non-UTC zone still compares with the UTC loop clock."""
    from scheduler.core import CronParser

    cass_tz("Asia/Tokyo")
    nxt = CronParser.parse_next_run("0 9 * * *", datetime.now(timezone.utc))
    assert nxt.tzinfo is not None
    assert (nxt - datetime.now(timezone.utc)) <= timedelta(days=1)


# ---------------------------------------------------------------------------
# Phase queues survive a restart
# ---------------------------------------------------------------------------

def _unit(name):
    from scheduling.work_unit import WorkUnit
    return WorkUnit(id=f"wu-{name}", name=name, description=f"{name} work")


def test_phase_queue_survives_restart(tmp_path):
    from scheduling.day_phase import DayPhase
    from scheduling.phase_queue import PhaseQueueManager

    path = tmp_path / "phase_queues.json"
    before = PhaseQueueManager(persist_path=path)
    assert before.queue_for_phase(_unit("journal"), DayPhase.EVENING, priority=2)
    assert before.queue_for_phase(_unit("reflect"), DayPhase.EVENING, priority=1)
    assert before.queue_for_phase(_unit("tidy"), DayPhase.NIGHT)

    after = PhaseQueueManager(persist_path=path)  # "restart"

    assert [q["work_unit"]["name"] for q in after.get_queue(DayPhase.EVENING)] == ["reflect", "journal"]
    assert [q["work_unit"]["name"] for q in after.get_queue(DayPhase.NIGHT)] == ["tidy"]

    after.remove_from_queue(DayPhase.NIGHT, "wu-tidy")
    assert PhaseQueueManager(persist_path=path).get_queue(DayPhase.NIGHT) == []


def test_stale_queued_work_is_not_restored(tmp_path):
    import json
    from scheduling.day_phase import DayPhase
    from scheduling.phase_queue import PhaseQueueManager

    path = tmp_path / "phase_queues.json"
    manager = PhaseQueueManager(persist_path=path)
    manager.queue_for_phase(_unit("old"), DayPhase.MORNING)
    data = json.loads(path.read_text())
    data[0]["queued_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    path.write_text(json.dumps(data))

    assert PhaseQueueManager(persist_path=path).get_queue(DayPhase.MORNING) == []


def test_no_persist_path_stays_in_memory(tmp_path, monkeypatch):
    from scheduling.day_phase import DayPhase
    from scheduling.phase_queue import PhaseQueueManager

    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    manager = PhaseQueueManager()
    manager.queue_for_phase(_unit("x"), DayPhase.MORNING)
    assert list(workdir.iterdir()) == []
