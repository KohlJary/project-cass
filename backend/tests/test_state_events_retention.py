"""
state_events retention (card 02 "State bus": every write_delta/emit_event
inserted a row and nothing ever deleted one).
"""
from datetime import datetime, timedelta

import pytest


def _rows(daemon_id):
    from database import get_db
    with get_db() as conn:
        return [r[0] for r in conn.execute(
            "SELECT id FROM state_events WHERE daemon_id = ? ORDER BY created_at", (daemon_id,))]


def _insert(daemon_id, event_id, age_days):
    from database import get_db
    created = (datetime.now() - timedelta(days=age_days)).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO state_events (id, daemon_id, event_type, source, data_json, created_at) "
            "VALUES (?, ?, 'test', 'test', '{}', ?)", (event_id, daemon_id, created))


@pytest.fixture
def bus(daemon_id, monkeypatch):
    from state_bus import GlobalStateBus
    monkeypatch.setattr(GlobalStateBus, "_last_prune_monotonic", None)
    return GlobalStateBus(daemon_id)


def test_prune_keeps_recent_rows(bus, daemon_id):
    _insert(daemon_id, "old", age_days=120)
    _insert(daemon_id, "recent", age_days=5)

    assert bus.prune_state_events(retention_days=90) == 1
    assert _rows(daemon_id) == ["recent"]


def test_zero_retention_keeps_everything(bus, daemon_id):
    _insert(daemon_id, "ancient", age_days=10_000)
    assert bus.prune_state_events(retention_days=0) == 0
    assert _rows(daemon_id) == ["ancient"]


def test_writing_an_event_prunes_old_rows(bus, daemon_id, monkeypatch):
    import config
    monkeypatch.setattr(config, "STATE_EVENTS_RETENTION_DAYS", 30)
    _insert(daemon_id, "old", age_days=45)

    bus.emit_event("test.ping", {"x": 1})

    remaining = _rows(daemon_id)
    assert "old" not in remaining
    assert len(remaining) == 1  # the event just written


def test_prune_is_throttled(bus, daemon_id, monkeypatch):
    """Only the first write in an interval pays for the DELETE."""
    import config
    monkeypatch.setattr(config, "STATE_EVENTS_RETENTION_DAYS", 30)
    bus.emit_event("test.first", {})
    _insert(daemon_id, "old", age_days=45)

    bus.emit_event("test.second", {})

    assert "old" in _rows(daemon_id)
