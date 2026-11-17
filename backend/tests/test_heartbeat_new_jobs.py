"""
What moved onto Heartbeat after the #62 cutover was built (2026-11-17): the
social watcher, and a nightly prune so the run log keeps 90 days.
"""
from datetime import datetime, timedelta

import pytest

from heartbeat import Heartbeat, RunLog, wiring


@pytest.fixture
def clean_wiring():
    wiring.reset()
    yield wiring
    wiring.reset()


def _levers(monkeypatch, **on):
    import features
    real = features.is_enabled
    monkeypatch.setattr(features, "is_enabled", lambda name: on.get(name, real(name)))


@pytest.mark.unit
def test_social_watch_is_a_job_once_bluesky_is_on(monkeypatch):
    _levers(monkeypatch, bluesky=True)
    jobs = wiring.job_work({})
    assert "social_watch" in jobs
    assert jobs["social_watch"].lever == "social_watch"
    assert "social_watch" in wiring.HEARTBEAT_JOBS


@pytest.mark.unit
def test_no_social_watch_job_without_a_platform(monkeypatch):
    _levers(monkeypatch, bluesky=False)
    assert "social_watch" not in wiring.job_work({})


@pytest.mark.unit
def test_old_watcher_stands_down_when_heartbeat_has_it(monkeypatch, clean_wiring):
    _levers(monkeypatch, bluesky=True, social_watch=True)
    from social import watch
    hb = Heartbeat()
    hb.register(wiring.job_work({})["social_watch"])
    wiring._heartbeat = hb
    monkeypatch.setattr(watch, "_task", None)
    assert watch.start_social_watch() is None
    assert watch._task is None


@pytest.mark.unit
def test_runlog_prune_keeps_recent_and_running_rows():
    log = RunLog()
    now = datetime(2026, 11, 17, 3, 30)
    old = now - timedelta(days=120)
    keep = log.start("recent", "every", None, now - timedelta(days=5))
    log.finish(keep, "ok", now - timedelta(days=5), 1.0)
    gone = log.start("old", "every", None, old)
    log.finish(gone, "ok", old, 1.0)
    stuck = log.start("stuck", "every", None, old)
    assert log.prune(now=now) == 1
    names = {r["work_name"] for r in log.recent(limit=500)}
    assert {"recent", "stuck"} <= names and "old" not in names
    assert stuck


@pytest.mark.unit
def test_runlog_prune_is_a_nightly_job():
    jobs = wiring.job_work({})
    assert "runlog_prune" in jobs and "runlog_prune" in wiring.HEARTBEAT_JOBS
