"""
Social watcher (lever "social_watch"): one cycle.

A reply and a follow arrive on a fake Bluesky; one watch pass queues them in
her inbox and posts nothing. The watcher doesn't start with the lever off, or
while no watched platform is switched on. No LLM is involved: the watcher
only queues; her social sessions read the queue.
"""
import asyncio

from social import config, inbox, limits, watch


class FakeClient:
    async def notifications(self, limit=50):
        return [{"uri": "at://ann/post/1", "reason": "reply", "author": "ann.bsky.social", "name": "Ann",
                 "text": "hello Cass", "at": "2026-11-16T10:00:00Z", "url": "https://bsky.app/profile/ann/post/1"},
                {"uri": "at://bo/follow/1", "reason": "follow", "author": "bo.bsky.social", "text": "",
                 "at": "2026-11-16T09:00:00Z"}]

    async def post_stats(self, uris):
        return {}

    async def conversations(self, limit=50):
        raise AssertionError("DMs aren't looked at while bluesky_dms is off")


def test_one_watch_cycle_queues_and_posts_nothing(levers, tmp_path):
    config.write_credentials("bluesky", {"handle": "cass.bsky.social", "app_password": "pw"}, tmp_path)
    with levers(social_watch=True, bluesky=True):
        got = asyncio.run(watch.watch_once(tmp_path, client_for=lambda p, d: FakeClient()))
    assert got == {"bluesky": 2}
    assert [i["kind"] for i in inbox.pending("bluesky", tmp_path)] == ["follow", "reply"]
    assert limits.posted("bluesky", tmp_path) == []


def test_nothing_is_watched_while_bluesky_is_off(levers, tmp_path):
    config.write_credentials("bluesky", {"handle": "cass.bsky.social", "app_password": "pw"}, tmp_path)
    with levers(social_watch=True, bluesky=False):
        assert asyncio.run(watch.watch_once(tmp_path, client_for=lambda p, d: FakeClient())) == {}


def test_watcher_starts_only_with_its_levers(levers):
    async def check():
        with levers(social_watch=False, bluesky=True):
            assert watch.start_social_watch() is None
        with levers(social_watch=True, bluesky=False):
            assert watch.start_social_watch() is None
    asyncio.run(check())
