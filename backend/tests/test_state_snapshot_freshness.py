"""
CURRENT STATE freshness: the state bus snapshot showed the boot-time date
("Today: Saturday, September 19" on October 16), a fallback city instead of
the resolved one, and a raw user id after "Present with:".
"""
from datetime import datetime, timedelta

import pytest


class FakeWorldSource:
    """Stands in for WorldStateSource: only the rollups the bus reads."""

    def __init__(self, rollups):
        self._rollups = rollups

    def get_precomputed_rollups(self):
        return dict(self._rollups)


def _stale_world(days_ago=27):
    from state_models import WorldStateData
    then = datetime.now() - timedelta(days=days_ago)
    return WorldStateData(
        server_location="Seattle, WA",
        current_date=then.strftime("%A, %B %d, %Y"),
        season="summer",
        time_of_day="afternoon",
        day_of_week=then.strftime("%A"),
        last_updated=then,
    )


def test_world_summary_date_is_computed_at_read_time():
    world = _stale_world()
    now = datetime(2026, 10, 16, 0, 52)

    summary = world.get_context_summary(now=now)

    assert "**Today:** Friday, October 16, 2026 (fall) - night" in summary.splitlines()[0]
    # Stored snapshot untouched; only the rendering is fresh.
    assert world.season == "summer"


def test_world_summary_defaults_to_now():
    world = _stale_world()
    today = datetime.now().strftime("%A, %B %d, %Y")
    assert today in world.get_context_summary()


def test_world_summary_keeps_location_and_weather_from_snapshot():
    world = _stale_world()
    world.current_weather = "Overcast, 53°F"
    assert "Seattle, WA - Overcast, 53°F" in world.get_context_summary()


@pytest.fixture
def bus(daemon_id):
    from state_bus import GlobalStateBus
    return GlobalStateBus(daemon_id)


def _hold_world(bus, world):
    state = bus.read_state()
    state.world = world
    bus._save_to_db(state)
    bus._state_cache = state
    bus._cache_time = datetime.now()


def test_snapshot_resyncs_world_when_source_rollups_are_newer(bus):
    _hold_world(bus, _stale_world())
    bus._queryable_sources["world_state"] = FakeWorldSource({
        "server_location": "Brockport, NY",
        "server_coords": [43.2, -77.9],
        "server_timezone": "America/New_York",
        "current_weather": "Overcast, 53°F",
        "last_updated": datetime.now().isoformat(),
    })

    snapshot = bus.get_context_snapshot()

    assert "Brockport, NY - Overcast, 53°F" in snapshot
    assert "Seattle" not in snapshot
    # Persisted, so the next read (and a restart) sees it too.
    bus._state_cache = None
    assert bus.read_state().world.server_location == "Brockport, NY"


def test_snapshot_keeps_held_world_when_source_is_older(bus):
    _hold_world(bus, _stale_world(days_ago=1))
    bus._queryable_sources["world_state"] = FakeWorldSource({
        "server_location": "Nowhere, XX",
        "last_updated": (datetime.now() - timedelta(days=3)).isoformat(),
    })

    assert "Seattle, WA" in bus.get_context_snapshot()


def test_snapshot_without_world_source_still_renders(bus):
    _hold_world(bus, _stale_world())
    snapshot = bus.get_context_snapshot()
    assert datetime.now().strftime("%B %d, %Y") in snapshot


def test_present_with_shows_display_name_not_uuid(bus, daemon_id):
    from database import get_db
    from state_models import StateDelta

    uid = "3ead7531-0000-0000-0000-000000000000"
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, display_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (uid, "Kohl", now, now),
        )
    bus.write_delta(StateDelta(source="test", activity_delta={"active_user_id": uid}))

    snapshot = bus.get_context_snapshot()

    assert "Present with: Kohl" in snapshot
    assert uid not in snapshot


def test_present_with_falls_back_to_id_for_unknown_user(bus):
    from state_models import StateDelta
    bus.write_delta(StateDelta(source="test", activity_delta={"active_user_id": "ghost-user"}))
    assert "Present with: ghost-user" in bus.get_context_snapshot()


# --- Location fallback in the world state source ---------------------------

@pytest.fixture
def world_source(daemon_id, tmp_path):
    from sources.world_state_source import WorldStateSource
    return WorldStateSource(daemon_id, str(tmp_path), home_location="")


def test_fallback_location_prefers_last_resolved(world_source):
    world_source._rollups["server_location"] = "Brockport, NY"
    world_source._home_location = "Seattle, WA"
    assert world_source._fallback_location() == "Brockport, NY"


def test_fallback_location_uses_configured_home_when_nothing_resolved(world_source):
    world_source._home_location = "Seattle, WA"
    assert world_source._fallback_location() == "Seattle, WA"


def test_fallback_location_is_unknown_when_unconfigured(world_source):
    assert world_source._fallback_location() is None


def test_default_home_location_is_not_a_guessed_city(daemon_id, tmp_path):
    from sources.world_state_source import WorldStateSource
    source = WorldStateSource(daemon_id, str(tmp_path))
    assert source._fallback_location() is None
