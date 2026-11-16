"""What happens to her on Bluesky reaches Thymos (return-paths map, item 3)."""
import asyncio
from types import SimpleNamespace

import pytest

from social import config, feeling, watch


@pytest.fixture
def bus_events(monkeypatch):
    events = []
    import state_bus
    monkeypatch.setattr(state_bus, "get_state_bus",
                        lambda daemon_id: SimpleNamespace(emit_event=lambda t, d: events.append((t, d))))
    return events


class FakeClient:
    async def notifications(self, limit=50):
        return [{"uri": f"at://p{i}/post/1", "reason": "reply", "author": f"p{i}.bsky.social",
                 "text": "hi", "at": "2026-11-16T10:00:00Z"} for i in range(3)] + \
               [{"uri": "at://bo/follow/1", "reason": "follow", "author": "bo.bsky.social", "text": ""},
                {"uri": "at://cy/like/1", "reason": "like", "author": "cy.bsky.social", "text": ""}]

    async def post_stats(self, uris):
        return {}


def test_a_watch_pass_tells_thymos_once_per_kind(levers, tmp_path, bus_events):
    config.write_credentials("bluesky", {"handle": "cass.bsky.social", "app_password": "pw"}, tmp_path)
    with levers(social_watch=True, bluesky=True):
        asyncio.run(watch.watch_once(tmp_path, client_for=lambda p, d: FakeClient()))
    assert sorted(bus_events) == [("social.engaged", {"platform": "bluesky", "count": 3}),
                                  ("social.followed", {"platform": "bluesky", "count": 1})]
    # a second pass with nothing new says nothing
    bus_events.clear()
    with levers(social_watch=True, bluesky=True):
        asyncio.run(watch.watch_once(tmp_path, client_for=lambda p, d: FakeClient()))
    assert bus_events == []


def test_resonance_and_dms_have_their_own_events(bus_events):
    assert feeling.received("bluesky", [{"kind": "resonated"}, {"kind": "dm"}, {"kind": "dm"},
                                        {"kind": "something_else"}]) == \
        {"social.resonated": 1, "social.dm": 2}


def test_posting_tells_thymos(bus_events):
    assert feeling.sent("bluesky", "reply") is True
    assert bus_events == [("social.posted", {"platform": "bluesky", "kind": "reply"})]


def test_no_bus_never_breaks_anything(monkeypatch):
    import state_bus
    monkeypatch.setattr(state_bus, "get_state_bus", lambda daemon_id: None)
    assert feeling.sent("bluesky", "post") is False


def test_every_social_event_is_a_thymos_event():
    from thymos.config import ThymosConfig
    cfg = ThymosConfig()
    for event in set(feeling.RECEIVED.values()) | {"social.posted"}:
        assert cfg.resolve_events(event, {"platform": "bluesky"}) == [event], event
