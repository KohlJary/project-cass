"""Bluesky people and DMs (Kohl and Cass, 2026-11-16).

- Someone she talks with gets a real PeopleDex entry: the exchange as a moment.
- After someone says yes, a DM conversation is kept, both sides, owned by them
  so it never comes up in a chat with anyone else.
- Someone who writes to her first is told apart, so she knows to ask.
- A follow can carry a note; a find is kept in her words.
"""
import asyncio
import json

import pytest

from social import config, dms, limits, people
from social.tools import execute_social_tool


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def placed(tmp_path, monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    config.write_credentials("bluesky", {"handle": "cass.bsky.social", "app_password": "pw"}, tmp_path)
    return tmp_path


class Memory:
    class _Col:
        def __init__(self):
            self.rows = {}

        def upsert(self, ids, documents, metadatas):
            for i, d, m in zip(ids, documents, metadatas):
                self.rows[i] = (d, m)

        def add(self, documents, metadatas, ids):
            self.upsert(ids, documents, metadatas)

    def __init__(self):
        self.collection = self._Col()


class DMClient:
    """Ann writes first ('ann_first'), or Cass did."""

    def __init__(self, ann_first=True):
        first = {"id": "m1", "from": "ann.bsky.social", "text": "hello, I liked your tide post",
                 "at": "2026-11-16T01:00:00Z"}
        reply = {"id": "m2", "from": "me", "text": "thank you", "at": "2026-11-16T01:05:00Z"}
        self.messages = [first, reply] if ann_first else [dict(reply, id="m0"), dict(first, id="m1")]
        self.sent = []

    async def conversation_with(self, handle):
        return {"id": "c-ann", "with": "ann.bsky.social", "new": False}

    async def read_conversation(self, convo_id, limit=30):
        return {"id": convo_id, "with": "ann.bsky.social", "messages": [dict(m) for m in self.messages]}

    async def send_dm(self, convo_id, text):
        self.sent.append(text)
        return {"id": f"s{len(self.sent)}", "convo": convo_id}


def test_a_reply_leaves_a_moment_with_that_person(placed, levers, daemon_id):
    from peopledex import PeopleDexManager

    class Client:
        async def post(self, text, reply_to=None):
            return {"uri": "at://cass/post/9", "url": "https://bsky.app/x",
                    "answering": {"uri": reply_to, "author": "ann.bsky.social", "text": "what do you paint?"}}
    with levers(bluesky=True):
        out = run(execute_social_tool("social_reply", {"platform": "bluesky", "to": "at://ann/post/1",
                                                       "text": "Mostly tides."},
                                      client=Client(), memory=Memory(), daemon_id=daemon_id))
    assert out["success"]
    dex = PeopleDexManager(daemon_id=daemon_id)
    entity = people.find("bluesky", "ann.bsky.social", dex)
    assert entity
    moments = [m.description for m in dex.get_moments(entity)]
    assert moments == ['On Bluesky, @ann.bsky.social wrote: "what do you paint?"\nI replied: "Mostly tides."']


def test_first_contact_is_told_apart_and_nothing_is_kept(placed, levers, daemon_id):
    memory = Memory()
    with levers(bluesky=True, bluesky_dms=True):
        read = run(execute_social_tool("social_dm_read", {"platform": "bluesky", "with": "ann.bsky.social"},
                                       client=DMClient(ann_first=True), memory=memory, daemon_id=daemon_id))
    assert read["unkept"] and "wrote to me first" in read["result"]["note"]
    assert memory.collection.rows == {}
    with levers(bluesky=True, bluesky_dms=True):
        read = run(execute_social_tool("social_dm_read", {"platform": "bluesky", "with": "ann.bsky.social"},
                                       client=DMClient(ann_first=False), memory=memory, daemon_id=daemon_id))
    assert "wrote to me first" not in read["result"]["note"] and "hasn't said" in read["result"]["note"]


def test_after_a_yes_the_whole_conversation_is_kept_and_only_theirs(placed, levers, daemon_id):
    memory = Memory()
    client = DMClient(ann_first=True)
    with levers(bluesky=True, bluesky_dms=True):
        run(execute_social_tool("social_dm_remember", {"platform": "bluesky", "handle": "ann.bsky.social",
                                                       "remember": True}, daemon_id=daemon_id))
        read = run(execute_social_tool("social_dm_read", {"platform": "bluesky", "with": "ann.bsky.social"},
                                       client=client, memory=memory, daemon_id=daemon_id))
        assert read["result"]["kept_in_my_memory"] == 2
        run(execute_social_tool("social_dm_send", {"platform": "bluesky", "to": "ann.bsky.social",
                                                   "text": "come back any time"},
                                client=client, memory=memory, daemon_id=daemon_id))
    rows = memory.collection.rows
    docs = sorted(d for d, _ in rows.values())
    assert any("@ann.bsky.social wrote: hello, I liked your tide post" in d for d in docs), "their side"
    assert any("I wrote: thank you" in d for d in docs) and any("I wrote: come back any time" in d for d in docs)
    assert {m["user_id"] for _, m in rows.values()} == {"bluesky:ann.bsky.social"}
    from memory.scope import recallable_with
    meta = next(iter(rows.values()))[1]
    assert not recallable_with("kohl-user-id", meta, agents=[], owners=lambda c: None, episodic=False), \
        "never comes up in a chat with someone else"
    # reading again doesn't duplicate
    with levers(bluesky=True, bluesky_dms=True):
        run(execute_social_tool("social_dm_read", {"platform": "bluesky", "with": "ann.bsky.social"},
                                client=client, memory=memory, daemon_id=daemon_id))
    assert len(rows) == 3


def test_a_follow_can_say_why_and_a_find_is_kept_in_her_words(placed, levers):
    class Client:
        async def follow(self, handle):
            return {"followed": handle, "uri": "at://cass/follow/1"}
    with levers(bluesky=True):
        run(execute_social_tool("social_follow", {"platform": "bluesky", "handle": "@twinks.bsky.social",
                                                  "note": "their glitch art"}, client=Client()))
        out = run(execute_social_tool("social_find", {"platform": "bluesky", "post": "at://bo/post/3",
                                                      "author": "@bo.bsky.social",
                                                      "note": "a map of a coastline that isn't there"}))
        assert out["success"]
        bad = run(execute_social_tool("social_find", {"platform": "bluesky", "post": "at://bo/post/3"}))
        assert not bad["success"]
    follow, find = limits.posted("bluesky", placed)[-2:]
    assert follow["kind"] == "follow" and follow["with"] == "twinks.bsky.social" and follow["note"] == "their glitch art"
    assert find == {**find, "kind": "find", "text": "a map of a coastline that isn't there",
                    "with": "bo.bsky.social", "uri": "at://bo/post/3"}


def test_her_social_session_has_finds_and_dms():
    from agent_loop.spec import PACKS
    assert {"social_find", "social_dm_read", "social_dm_remember"} <= set(PACKS["social"].tools)


def test_a_refused_dm_listing_doesnt_lose_the_mentions(placed):
    from social import inbox

    class Client:
        async def notifications(self, limit=50):
            return [{"uri": "at://ann/post/1", "reason": "reply", "author": "ann.bsky.social", "text": "hi"}]

        async def post_stats(self, uris):
            return {}

        async def conversations(self, limit=50):
            raise RuntimeError("Bluesky said no to chat.bsky.convo.listConvos: Bad token method")
    added = run(inbox.poll("bluesky", Client(), placed, dms=True))
    assert [i["kind"] for i in added] == ["reply"]
    assert [i["kind"] for i in inbox.pending("bluesky", placed)] == ["reply"], "saved, not thrown away"
