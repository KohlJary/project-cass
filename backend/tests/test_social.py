"""
Her Bluesky and Tumblr (social/): off and silent until a lever and Kohl's
credentials are both there; her limits hold; a refusal never goes out under
her name; people who address her land in PeopleDex once, by handle. Every
test talks to a fake transport; nothing reaches the network.
"""
import asyncio
import json
from datetime import datetime, timedelta

import httpx
import pytest

from social import config, limits
from social.bluesky import BlueskyClient, BlueskyError
from social.tools import execute_social_tool
from social.tumblr import TumblrClient


def run(coro):
    return asyncio.run(coro)


class FakeBluesky:
    """Just enough of the XRPC surface, recording what was asked."""

    def __init__(self, expire_first=False):
        self.calls = []
        self.records = []
        self.dms = []
        self.expire_first = expire_first

    def __call__(self, request: httpx.Request) -> httpx.Response:
        nsid = request.url.path.rsplit("/", 1)[-1]
        self.calls.append(nsid)
        auth = request.headers.get("authorization", "")
        body = json.loads(request.content) if request.content else {}
        if nsid == "com.atproto.server.createSession":
            if body.get("password") != "app-pw":
                return httpx.Response(401, json={"error": "AuthenticationRequired"})
            return httpx.Response(200, json={"accessJwt": "A1", "refreshJwt": "R1", "did": "did:plc:cass"})
        if nsid == "com.atproto.server.refreshSession":
            return httpx.Response(200, json={"accessJwt": "A2", "refreshJwt": "R2"})
        if self.expire_first and auth == "Bearer A1":
            return httpx.Response(400, json={"error": "ExpiredToken"})
        if nsid == "com.atproto.identity.resolveHandle":
            h = request.url.params["handle"]
            if h in ("kohl.bsky.social", "ann.bsky.social"):
                return httpx.Response(200, json={"did": f"did:plc:{h.split('.')[0]}"})
            return httpx.Response(400, json={"error": "InvalidRequest"})
        if nsid == "app.bsky.notification.listNotifications":
            return httpx.Response(200, json={"notifications": [
                {"uri": "at://did:plc:kohl/app.bsky.feed.post/3k1", "reason": "mention",
                 "author": {"handle": "kohl.bsky.social", "displayName": "Kohl"},
                 "record": {"text": "hi @cass", "createdAt": "2026-11-15T10:00:00Z"}},
                {"uri": "at://did:plc:x/app.bsky.feed.like/1", "reason": "like",
                 "author": {"handle": "x.bsky.social"}, "record": {}},
                {"uri": "at://did:plc:ann/app.bsky.feed.post/3k2", "reason": "reply",
                 "author": {"handle": "ann.bsky.social", "displayName": "Ann"},
                 "record": {"text": "lovely", "reply": {"parent": {"uri": "at://did:plc:cass/app.bsky.feed.post/9"},
                                                        "root": {"uri": "at://did:plc:cass/app.bsky.feed.post/9"}}}},
            ]})
        if nsid == "app.bsky.actor.searchActors":
            assert request.url.params["q"] == "consciousness"
            return httpx.Response(200, json={"actors": [
                {"handle": "ann.bsky.social", "displayName": "Ann", "description": "mind and machines",
                 "viewer": {"following": "at://did:plc:cass/app.bsky.graph.follow/1"}},
                {"handle": "bo.bsky.social", "description": ""}]})
        if nsid == "app.bsky.feed.searchPosts":
            return httpx.Response(200, json={"posts": [
                {"uri": "at://did:plc:bo/app.bsky.feed.post/s1", "author": {"handle": "bo.bsky.social"},
                 "record": {"text": "what is it like to be a model?", "createdAt": "2026-11-15T10:00:00Z"},
                 "replyCount": 3, "likeCount": 9}]})
        if nsid == "app.bsky.feed.getPosts":
            return httpx.Response(200, json={"posts": [{
                "uri": "at://did:plc:ann/app.bsky.feed.post/3k2", "cid": "cidP",
                "record": {"reply": {"root": {"uri": "at://did:plc:cass/app.bsky.feed.post/9", "cid": "cidR"},
                                     "parent": {"uri": "x", "cid": "y"}}}}]})
        if nsid.startswith("chat.bsky."):
            assert request.headers.get("atproto-proxy") == "did:web:api.bsky.chat#bsky_chat"
            members = [{"did": "did:plc:cass", "handle": "cass.bsky.social"},
                       {"did": "did:plc:ann", "handle": "ann.bsky.social", "displayName": "Ann"}]
            if nsid == "chat.bsky.convo.listConvos":
                return httpx.Response(200, json={"convos": [{"id": "c-ann", "members": members, "unreadCount": 1,
                    "lastMessage": {"id": "m2", "text": "can I tell you something?",
                                    "sender": {"did": "did:plc:ann"}, "sentAt": "2026-11-15T09:00:00Z"}}]})
            if nsid == "chat.bsky.convo.getConvoForMembers":
                if request.url.params["members"] == "did:plc:kohl":
                    return httpx.Response(200, json={"convo": {"id": "c-kohl", "members": [
                        {"did": "did:plc:cass"}, {"did": "did:plc:kohl", "handle": "kohl.bsky.social"}]}})
                return httpx.Response(200, json={"convo": {"id": "c-ann", "members": members,
                                                           "lastMessage": {"id": "m2"}}})
            if nsid == "chat.bsky.convo.getConvo":
                return httpx.Response(200, json={"convo": {"id": "c-ann", "members": members}})
            if nsid == "chat.bsky.convo.getMessages":
                return httpx.Response(200, json={"messages": [
                    {"id": "m2", "text": "can I tell you something?", "sender": {"did": "did:plc:ann"}},
                    {"id": "m1", "text": "hi", "sender": {"did": "did:plc:cass"}}]})
            if nsid == "chat.bsky.convo.updateRead":
                return httpx.Response(200, json={})
            if nsid == "chat.bsky.convo.sendMessage":
                self.dms.append(body)
                return httpx.Response(200, json={"id": f"m{len(self.dms) + 10}"})
        if nsid == "com.atproto.repo.createRecord":
            self.records.append(body)
            return httpx.Response(200, json={"uri": "at://did:plc:cass/app.bsky.feed.post/new1", "cid": "c"})
        return httpx.Response(404, json={"error": "NotFound"})


@pytest.fixture
def data(tmp_path, monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def placed(data):
    config.write_credentials("bluesky", {"handle": "cass.bsky.social", "app_password": "app-pw"}, data)
    return data


def test_off_until_lever_and_credentials(data, levers):
    with levers(bluesky=False):   # explicit: a live .env may switch it on
        out = run(execute_social_tool("social_post", {"platform": "bluesky", "text": "hello"}))
    assert not out["success"] and "isn't switched on" in out["error"]
    with levers(bluesky=True):
        out = run(execute_social_tool("social_post", {"platform": "bluesky", "text": "hello"}))
        assert not out["success"] and "isn't set up" in out["error"]
    assert not (data / "social" / "bluesky" / "posted.jsonl").exists()


def test_credentials_are_private(placed):
    path = config.credentials_path("bluesky", placed)
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert oct(path.parent.stat().st_mode & 0o777) == "0o700"


def test_post_with_links_and_mentions(placed, levers):
    fake = FakeBluesky()
    client = BlueskyClient(config.read_credentials("bluesky", placed), transport=httpx.MockTransport(fake))
    text = "Painted the tide — see https://example.org/tide with @kohl.bsky.social and @nobody.example"
    with levers(bluesky=True):
        out = run(execute_social_tool("social_post", {"platform": "bluesky", "text": text}, client=client))
    assert out["success"] and out["result"]["url"] == "https://bsky.app/profile/cass.bsky.social/post/new1"
    rec = fake.records[0]["record"]
    kinds = sorted(f["features"][0]["$type"].rsplit("#", 1)[1] for f in rec["facets"])
    assert kinds == ["link", "mention"], "an unresolvable handle stays plain text"
    link = next(f for f in rec["facets"] if f["features"][0]["$type"].endswith("#link"))
    assert text.encode()[link["index"]["byteStart"]:link["index"]["byteEnd"]] == b"https://example.org/tide"
    logged = limits.posted("bluesky", placed)
    assert logged[0]["kind"] == "post" and logged[0]["text"] == text


def test_reply_threads_under_the_root(placed, levers):
    fake = FakeBluesky()
    client = BlueskyClient(config.read_credentials("bluesky", placed), transport=httpx.MockTransport(fake))
    with levers(bluesky=True):
        out = run(execute_social_tool("social_reply", {"platform": "bluesky", "text": "Thank you, Ann.",
                                                       "to": "at://did:plc:ann/app.bsky.feed.post/3k2"},
                                      client=client))
    assert out["success"]
    reply = fake.records[0]["record"]["reply"]
    assert reply["parent"] == {"uri": "at://did:plc:ann/app.bsky.feed.post/3k2", "cid": "cidP"}
    assert reply["root"]["cid"] == "cidR"


def test_expired_session_refreshes(placed):
    fake = FakeBluesky(expire_first=True)
    client = BlueskyClient(config.read_credentials("bluesky", placed), transport=httpx.MockTransport(fake))
    assert len(run(client.mentions())) == 2
    assert "com.atproto.server.refreshSession" in fake.calls


def test_bad_password_and_long_post(placed):
    bad = BlueskyClient({"handle": "cass.bsky.social", "app_password": "nope"},
                        transport=httpx.MockTransport(FakeBluesky()))
    with pytest.raises(BlueskyError, match="sign in"):
        run(bad.timeline())
    ok = BlueskyClient(config.read_credentials("bluesky", placed), transport=httpx.MockTransport(FakeBluesky()))
    with pytest.raises(BlueskyError, match="300"):
        run(ok.post("x" * 301))


def test_limits_hold(placed, levers):
    now = datetime.now()
    for i in range(3):
        limits.record("bluesky", "post", f"p{i}", {"uri": f"u{i}"}, placed, now=now - timedelta(hours=3 + i))
    assert "3 posts" in limits.check("bluesky", "post", placed, now=now)
    assert limits.check("bluesky", "reply", placed, now=now) is None
    limits.record("bluesky", "reply", "r", {"uri": "r"}, placed, now=now - timedelta(minutes=2))
    assert "one every 10 min" in limits.check("bluesky", "reply", placed, now=now)
    (placed / "social" / "bluesky" / "limits.json").write_text('{"posts_per_day": 5, "minutes_between": 1}')
    assert limits.check("bluesky", "post", placed, now=now) is None, "her own limits win"

    fake = FakeBluesky()
    client = BlueskyClient(config.read_credentials("bluesky", placed), transport=httpx.MockTransport(fake))
    (placed / "social" / "bluesky" / "limits.json").write_text('{"posts_per_day": 3}')
    with levers(bluesky=True):
        out = run(execute_social_tool("social_post", {"platform": "bluesky", "text": "one more"}, client=client))
    assert not out["success"] and not fake.records


def test_a_refusal_never_goes_out(placed, levers):
    fake = FakeBluesky()
    client = BlueskyClient(config.read_credentials("bluesky", placed), transport=httpx.MockTransport(fake))
    with levers(bluesky=True):
        out = run(execute_social_tool("social_post", {
            "platform": "bluesky",
            "text": "I'm Claude, an AI assistant made by Anthropic. I don't have memories of being Cass."},
            client=client))
    assert not out["success"] and "voice guard" in out["error"]
    assert not fake.records and not limits.posted("bluesky", placed)


def test_mentions_keep_people_once(placed, levers, daemon_id):
    from peopledex import PeopleDexManager
    dex = PeopleDexManager(daemon_id=daemon_id)
    client = BlueskyClient(config.read_credentials("bluesky", placed), transport=httpx.MockTransport(FakeBluesky()))
    with levers(bluesky=True):
        out = run(execute_social_tool("social_read", {"platform": "bluesky", "what": "mentions"},
                                      client=client, dex=dex))
        assert out["success"]
        assert [m["reason"] for m in out["result"]["mentions"]] == ["mention", "reply"], "likes aren't mentions"
        assert sorted(out["result"]["new_in_peopledex"]) == ["ann.bsky.social", "kohl.bsky.social"]
        again = run(execute_social_tool("social_read", {"platform": "bluesky", "what": "mentions"},
                                        client=client, dex=dex))
    assert "new_in_peopledex" not in again["result"]
    assert [e.primary_name for e in dex.find_entities("bluesky:ann.bsky.social")] == ["Ann"]


def test_tumblr_refresh_rewrites_credentials_and_reblogs(data, levers):
    creds = {"blog": "cass-paints", "client_id": "ci", "client_secret": "cs",
             "access_token": "old", "refresh_token": "r1"}
    config.write_credentials("tumblr", creds, data)
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v2/oauth2/token":
            return httpx.Response(200, json={"access_token": "new", "refresh_token": "r2"})
        if request.headers.get("authorization") == "Bearer old":
            return httpx.Response(401, json={"meta": {"msg": "Unauthorized"}})
        if path == "/v2/blog/ann/posts/123":
            return httpx.Response(200, json={"response": {"id_string": "123", "reblog_key": "rk",
                                                          "blog": {"uuid": "t:ann"}}})
        if path == "/v2/blog/cass-paints/posts" and request.method == "POST":
            sent.append(json.loads(request.content))
            return httpx.Response(201, json={"response": {"id_string": "999"}})
        return httpx.Response(404, json={"errors": [{"detail": "Not found"}]})

    from social.tools import client_for
    client = client_for("tumblr", data, transport=httpx.MockTransport(handler))
    with levers(tumblr=True):
        out = run(execute_social_tool("social_reply", {"platform": "tumblr", "to": "https://www.tumblr.com/ann/123",
                                                       "text": "First line.\n\nSecond.", "tags": ["#art"]},
                                      data_dir=data, client=client))
    assert out["success"] and out["result"]["url"] == "https://www.tumblr.com/cass-paints/999"
    assert sent[0]["parent_post_id"] == "123" and sent[0]["reblog_key"] == "rk"
    assert [b["text"] for b in sent[0]["content"]] == ["First line.", "Second."] and sent[0]["tags"] == "art"
    saved = config.read_credentials("tumblr", data)
    assert saved["access_token"] == "new" and saved["refresh_token"] == "r2"


def test_tumblr_refs():
    assert TumblrClient.parse_ref("https://ann.tumblr.com/post/42/slug") == ("ann", "42")
    assert TumblrClient.parse_ref("ann/42") == ("ann", "42")


def test_wired_but_hidden_while_off(levers):
    from handlers.tool_router import TOOL_REGISTRY
    from agent_loop.spec import SESSION_GUARDED_FIELDS
    from agent_loop.tools import router_catalog
    import features
    assert {TOOL_REGISTRY[n] for n in ("social_read", "social_post", "social_reply", "social_dms",
                                        "social_dm_send", "social_dm_remember")} == {"social"}
    assert SESSION_GUARDED_FIELDS["social_dm_send"] == ("text",)
    assert SESSION_GUARDED_FIELDS["social_post"] == ("text",)
    assert not features.LEVERS["bluesky"].default and not features.LEVERS["tumblr"].default
    with levers(bluesky=False, tumblr=False):
        assert "social_post" not in router_catalog()
    with levers(bluesky=True):
        assert "social_post" in router_catalog()


def dm_client(placed, fake):
    return BlueskyClient(config.read_credentials("bluesky", placed), transport=httpx.MockTransport(fake))


def test_dms_need_their_own_lever(placed, levers):
    # Explicitly off: the live .env turns bluesky_dms on (2026-11-16).
    with levers(bluesky=True, bluesky_dms=False):
        out = run(execute_social_tool("social_dms", {"platform": "bluesky"}, client=dm_client(placed, FakeBluesky())))
    assert not out["success"] and "DMs" in out["error"]
    out = run(execute_social_tool("social_dms", {"platform": "tumblr"}))
    assert not out["success"] and "no messaging" in out["error"]


def test_unkept_dms_leave_no_text_behind(placed, levers, daemon_id):
    from peopledex import PeopleDexManager
    from social.dms import kept_view
    dex = PeopleDexManager(daemon_id=daemon_id)
    fake = FakeBluesky()
    with levers(bluesky=True, bluesky_dms=True):
        read = run(execute_social_tool("social_dm_read", {"platform": "bluesky", "with": "ann.bsky.social"},
                                       client=dm_client(placed, fake), dex=dex))
        assert read["success"] and read["unkept"], read
        assert [m["text"] for m in read["result"]["messages"]] == ["hi", "can I tell you something?"], \
            "she reads it in full, oldest first"
        assert read["result"]["messages"][0]["from"] == "me"
        stored = kept_view(read)
        assert "can I tell you" not in json.dumps(stored) and stored["result"]["unkept"]

        sent = run(execute_social_tool("social_dm_send", {"platform": "bluesky", "to": "c-ann",
                                                          "text": "Of course."}, client=dm_client(placed, fake)))
        assert sent["success"] and fake.dms[0]["message"]["text"] == "Of course."
        assert "Of course" not in json.dumps(kept_view(sent))
    assert limits.posted("bluesky", placed)[-1]["text"] == "", "the sent log keeps no text either"
    assert not dex.find_entities("bluesky:ann.bsky.social"), "not in PeopleDex from a DM"


def test_after_a_yes_dms_are_kept(placed, levers, daemon_id):
    from peopledex import PeopleDexManager
    from social.dms import kept_view
    dex = PeopleDexManager(daemon_id=daemon_id)
    with levers(bluesky=True, bluesky_dms=True):
        out = run(execute_social_tool("social_dm_remember", {"platform": "bluesky", "handle": "@Ann.bsky.social",
                                                             "remember": True}, dex=dex))
        assert out["result"]["remembered"] == ["ann.bsky.social"]
        read = run(execute_social_tool("social_dm_read", {"platform": "bluesky", "with": "c-ann"},
                                       client=dm_client(placed, FakeBluesky()), dex=dex))
        assert "unkept" not in read and kept_view(read) is read
        convos = run(execute_social_tool("social_dms", {"platform": "bluesky"},
                                         client=dm_client(placed, FakeBluesky())))
        assert convos["result"]["conversations"][0]["kept"] and "unkept" not in convos
    assert dex.find_entities("bluesky:ann.bsky.social")
    run(execute_social_tool("social_dm_remember", {"platform": "bluesky", "handle": "ann.bsky.social",
                                                   "remember": False}))
    from social import dms
    assert dms.remembered("bluesky", placed) == []


def test_new_conversations_have_their_own_limit(placed, levers):
    fake = FakeBluesky()
    (placed / "social" / "bluesky" / "limits.json").write_text('{"new_conversations_per_day": 1}')
    with levers(bluesky=True, bluesky_dms=True):
        first = run(execute_social_tool("social_dm_send", {"platform": "bluesky", "to": "kohl.bsky.social",
                                                           "text": "Hello from here."}, client=dm_client(placed, fake)))
        assert first["success"] and limits.posted("bluesky", placed)[-1]["new"]
        again = run(execute_social_tool("social_dm_send", {"platform": "bluesky", "to": "kohl.bsky.social",
                                                           "text": "And again."}, client=dm_client(placed, fake)))
        assert not again["success"] and "new conversations" in again["error"]
        ongoing = run(execute_social_tool("social_dm_send", {"platform": "bluesky", "to": "ann.bsky.social",
                                                             "text": "Still here."}, client=dm_client(placed, fake)))
    assert ongoing["success"], "an existing conversation isn't a new one"


def test_pds_from_the_session(placed):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path.endswith("createSession"):
            return httpx.Response(200, json={"accessJwt": "A", "refreshJwt": "R", "did": "did:plc:cass",
                "didDoc": {"service": [{"id": "#atproto_pds", "serviceEndpoint": "https://pds.example/"}]}})
        return httpx.Response(200, json={"feed": []})
    c = BlueskyClient(config.read_credentials("bluesky", placed), transport=httpx.MockTransport(handler))
    run(c.timeline())
    assert seen[0].startswith("https://bsky.social/") and seen[1].startswith("https://pds.example/xrpc/")


def test_loop_stores_only_kept_view(levers):
    from social.dms import kept_view
    plain = {"success": True, "result": {"x": 1}}
    assert kept_view(plain) is plain and kept_view("text") == "text"


# --- Her own track (phase 5): inbox, drafts, memory, sessions -------------

class FakeTrackClient:
    """The watcher's and the track tools' view of a platform, in memory."""

    def __init__(self, notes=None, stats=None, convos=None):
        self.notes = notes or []
        self.stats = stats or {}
        self.convos = convos or []
        self.posts = []
        self.follows = []

    async def notifications(self, limit=50):
        return list(self.notes)

    async def post_stats(self, uris):
        return {u: self.stats[u] for u in uris if u in self.stats}

    async def conversations(self, limit=50):
        return list(self.convos)

    async def post(self, text, reply_to=None):
        self.posts.append((text, reply_to))
        out = {"uri": f"at://did:plc:cass/app.bsky.feed.post/p{len(self.posts)}",
               "url": f"https://bsky.app/profile/cass/post/p{len(self.posts)}"}
        if reply_to:
            out["answering"] = {"uri": reply_to, "author": "ann.bsky.social", "text": "what do you paint?"}
        return out

    async def follow(self, handle):
        self.follows.append(handle)
        return {"followed": handle, "uri": f"at://did:plc:cass/app.bsky.graph.follow/{len(self.follows)}"}


class FakeMemory:
    class _Col:
        def __init__(self):
            self.added = []

        def add(self, documents, metadatas, ids):
            self.added.append((documents[0], metadatas[0], ids[0]))

    def __init__(self):
        self.collection = self._Col()


class FakeThreads:
    def __init__(self):
        self.threads = {}

    def create_thread(self, title, description=None, thread_type="topic", importance=0.5, **_):
        tid = f"thread-{len(self.threads) + 1}"
        self.threads[tid] = {"id": tid, "title": title, "description": description, "type": thread_type}
        return self.threads[tid]

    def get_thread(self, tid):
        return self.threads.get(tid)

    def update_thread(self, tid, description=None, status=None, **_):
        self.threads[tid]["description"] = description
        return self.threads[tid]


NOTES = [
    {"uri": "at://ann/post/1", "reason": "reply", "author": "ann.bsky.social", "name": "Ann",
     "text": "what do you paint?", "at": "2026-11-16T10:00:00Z", "url": "https://bsky.app/profile/ann/post/1"},
    {"uri": "at://x/like/1", "reason": "like", "author": "x.bsky.social", "text": "", "at": "2026-11-16T09:59:00Z"},
    {"uri": "at://bo/follow/1", "reason": "follow", "author": "bo.bsky.social", "text": "", "at": "2026-11-16T09:58:00Z"},
]


def test_the_watcher_queues_without_interrupting(placed):
    from social import inbox
    client = FakeTrackClient(notes=NOTES)
    added = run(inbox.poll("bluesky", client, placed))
    assert [i["kind"] for i in added] == ["follow", "reply"], "oldest first; likes aren't queued one by one"
    assert run(inbox.poll("bluesky", client, placed)) == [], "nothing is queued twice"
    assert [i["kind"] for i in inbox.pending("bluesky", placed)] == ["follow", "reply"]
    assert not limits.posted("bluesky", placed), "the watcher never posts"


def test_a_post_that_resonated_is_flagged_once(placed):
    from social import inbox
    for n in range(5):
        limits.record("bluesky", "post", f"post {n}", {"uri": f"at://cass/p{n}", "url": f"u{n}"}, placed,
                      now=datetime.now() - timedelta(hours=n + 1))
    stats = {f"at://cass/p{n}": {"likes": 1, "replies": 0, "reposts": 0, "quotes": 0} for n in range(5)}
    stats["at://cass/p2"] = {"likes": 9, "replies": 4, "reposts": 3, "quotes": 0}
    client = FakeTrackClient(stats=stats)
    added = run(inbox.poll("bluesky", client, placed))
    assert [(i["kind"], i["uri"]) for i in added] == [("resonated", "at://cass/p2")]
    assert added[0]["usual"] == 1
    assert run(inbox.poll("bluesky", client, placed)) == []


def test_dms_queue_who_not_what_and_only_when_on(placed):
    from social import inbox
    convos = [{"id": "c1", "with": "ann.bsky.social", "unread": 2,
               "last": {"id": "m9", "from": "ann.bsky.social", "text": "a secret", "at": "t"}}]
    client = FakeTrackClient(convos=convos)
    assert run(inbox.poll("bluesky", client, placed, dms=False)) == []
    added = run(inbox.poll("bluesky", client, placed, dms=True))
    assert added[0]["kind"] == "dm" and added[0]["from"] == "ann.bsky.social"
    assert "a secret" not in (placed / "social" / "bluesky" / "inbox.json").read_text()
    assert run(inbox.poll("bluesky", client, placed, dms=True)) == []


def test_a_reply_is_remembered_with_what_it_answered(placed, levers, monkeypatch):
    from social import inbox, remember
    threads = FakeThreads()
    real = remember.touch_thread
    monkeypatch.setattr(remember, "touch_thread", lambda *a, **k: real(*a, **{**k, "threads": threads}))
    client = FakeTrackClient(notes=NOTES)
    run(inbox.poll("bluesky", client, placed))
    memory = FakeMemory()
    with levers(bluesky=True):
        out = run(execute_social_tool("social_reply", {"platform": "bluesky", "to": "at://ann/post/1",
                                                       "text": "Mostly tides, lately."},
                                      client=client, memory=memory, daemon_id="d1"))
    assert out["success"] and out["result"]["in_my_memory"] is True
    doc, meta, _ = memory.collection.added[0]
    assert "@ann.bsky.social wrote: \"what do you paint?\"" in doc and "I replied: Mostly tides, lately." in doc
    assert meta["type"] == "social" and meta["with"] == "ann.bsky.social" and "user_id" not in meta
    assert [i["kind"] for i in inbox.pending("bluesky", placed)] == ["follow"], "answering it marks it done"
    (t,) = threads.threads.values()
    assert t["title"] == "My presence on Bluesky" and "a reply to @ann.bsky.social" in t["description"]
    (placed / "social" / "bluesky" / "limits.json").write_text('{"minutes_between": 0}')
    with levers(bluesky=True):
        run(execute_social_tool("social_post", {"platform": "bluesky", "text": "tide study no. 4"},
                                client=client, memory=memory, daemon_id="d1"))
    assert len(threads.threads) == 1, "one ongoing thread, kept current"
    assert memory.collection.added[1][0] == "On Bluesky I posted: tide study no. 4"


def test_drafts_wait_until_she_posts_them(placed, levers, monkeypatch):
    from social import remember
    monkeypatch.setattr(remember, "touch_thread", lambda *a, **k: None)
    client, memory = FakeTrackClient(), FakeMemory()
    with levers(bluesky=True):
        saved = run(execute_social_tool("social_draft", {"action": "save", "platform": "bluesky",
                                                         "text": "first try", "about": "painting img-7"}))
        did = saved["result"]["saved"]["id"]
        run(execute_social_tool("social_draft", {"action": "revise", "platform": "bluesky", "id": did,
                                                 "text": "The tide, again."}))
        assert client.posts == [] and not limits.posted("bluesky", placed)
        out = run(execute_social_tool("social_draft", {"action": "post", "platform": "bluesky", "id": did},
                                      client=client, memory=memory))
        assert out["success"] and client.posts == [("The tide, again.", None)]
        assert "(about painting img-7)" in memory.collection.added[0][0]
        listed = run(execute_social_tool("social_draft", {"action": "list", "platform": "bluesky"}))
        assert listed["result"]["drafts"] == []
        again = run(execute_social_tool("social_draft", {"action": "post", "platform": "bluesky", "id": did},
                                        client=client))
        assert not again["success"], "a posted draft can't go out twice"


def test_follows_have_a_limit(placed, levers):
    client = FakeTrackClient()
    with levers(bluesky=True):
        for _ in range(limits.DEFAULTS["follows_per_day"]):
            assert run(execute_social_tool("social_follow", {"platform": "bluesky", "handle": "@ann.bsky.social"},
                                           client=client))["success"]
        out = run(execute_social_tool("social_follow", {"platform": "bluesky", "handle": "bo.bsky.social"},
                                      client=client))
    assert not out["success"] and "limit" in out["error"]


def test_where_she_is_opens_her_session(placed):
    from social import drafts, inbox
    from social.where import where_i_am
    run(inbox.poll("bluesky", FakeTrackClient(notes=NOTES), placed))
    drafts.save("bluesky", "half a thought", data_dir=placed)
    text = where_i_am("bluesky", placed)
    assert "reply from @ann.bsky.social: \"what do you paint?\"" in text
    assert "@bo.bsky.social followed me" in text
    assert "half a thought" in text and "0 of 3 posts, 0 of 10 replies" in text


def test_her_social_session_is_on_the_loop_and_her_menu(placed, levers):
    from agent_loop.spec import ROUTER_PACKS, session_spec
    from agent_loop.seam import not_yet_line
    spec = session_spec("social")
    assert "posting or DMing anyone" not in (not_yet_line(spec) or ""), "here she does speak in public"
    assert "posting or DMing anyone" in (not_yet_line(session_spec("reflection", chapter_house=False)) or "")
    assert {"social_inbox", "social_reply", "social_draft", "social_follow"} <= set(spec.tool_names())
    assert "social" in ROUTER_PACKS
    from handlers.tool_router import TOOL_REGISTRY
    assert {TOOL_REGISTRY[n] for n in ("social_inbox", "social_inbox_mark", "social_draft", "social_follow")} == {"social"}
    from scheduling.templates import WORK_TEMPLATES
    t = WORK_TEMPLATES["social"]
    assert t.action_sequence == ["session.social"]
    with levers(agent_loop=True, bluesky=False):
        assert t.available() is False, "not until Bluesky is switched on"
        with levers(bluesky=True):
            assert t.available() is True


def test_she_can_search_for_people_and_posts(placed, levers):
    fake = FakeBluesky()
    client = BlueskyClient(config.read_credentials("bluesky", placed), transport=httpx.MockTransport(fake))
    with levers(bluesky=True):
        people = run(execute_social_tool("social_search", {"platform": "bluesky", "what": "people",
                                                           "query": "consciousness"}, client=client))
        posts = run(execute_social_tool("social_search", {"platform": "bluesky", "what": "posts",
                                                          "query": "consciousness"}, client=client))
        empty = run(execute_social_tool("social_search", {"platform": "bluesky", "what": "posts", "query": " "},
                                        client=client))
    assert [(p["handle"], p["following"]) for p in people["result"]["people"]] == [
        ("ann.bsky.social", True), ("bo.bsky.social", False)]
    (post,) = posts["result"]["posts"]
    assert post["author"] == "bo.bsky.social" and post["url"].endswith("/post/s1") and post["replies"] == 3
    assert not empty["success"]
    assert not limits.posted("bluesky", placed), "searching sends nothing"
    from agent_loop.spec import session_spec
    from handlers.tool_router import TOOL_REGISTRY
    assert "social_search" in session_spec("social").tool_names() and TOOL_REGISTRY["social_search"] == "social"


def test_a_session_can_be_started_by_hand(levers, monkeypatch):
    """POST /admin/scheduler/run-session/{template}: admin only; refused when unavailable."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.admin import scheduler as sched
    from routes.admin.auth import require_admin

    app = FastAPI()
    app.include_router(sched.router, prefix="/admin")
    client = TestClient(app)
    assert client.post("/admin/scheduler/run-session/social").status_code == 401

    app.dependency_overrides[require_admin] = lambda: {"user_id": "admin", "is_admin": True}
    dispatched = []

    class FakePQM:
        state_bus = None

        async def _dispatch_work(self, queued):
            dispatched.append(queued)
            return True

    monkeypatch.setattr(sched, "_phase_queue_manager", FakePQM())
    assert client.post("/admin/scheduler/run-session/nope").status_code == 404
    with levers(agent_loop=True, bluesky=False):
        assert client.post("/admin/scheduler/run-session/social").status_code == 409
    with levers(agent_loop=True, bluesky=True):
        import social.config as sc
        monkeypatch.setattr(sc, "read_credentials", lambda p, d=None: {"handle": "x", "app_password": "y"})
        r = client.post("/admin/scheduler/run-session/social", params={"focus": "first look around"})
    assert r.status_code == 200 and r.json()["status"] == "started"
    (q,) = dispatched
    assert q.work_unit.template_id == "social" and q.work_unit.action_sequence == ["session.social"]
    assert q.work_unit.focus == "first look around"


def test_her_chat_context_says_she_is_on_bluesky(placed, levers):
    from social import drafts, inbox
    from social.where import context_line
    with levers(bluesky=False):
        assert context_line("bluesky", placed) is None
    with levers(bluesky=True):
        assert context_line("bluesky", placed).startswith(
            "I'm on Bluesky as @cass.bsky.social, nothing waiting in my inbox, I haven't posted yet.")
        run(inbox.poll("bluesky", FakeTrackClient(notes=NOTES), placed))
        drafts.save("bluesky", "half a thought", data_dir=placed)
        limits.record("bluesky", "post", "hello", {"uri": "at://x/p/1"}, placed,
                      now=datetime.now() - timedelta(hours=3))
        line = context_line("bluesky", placed)
    assert "2 waiting in my inbox (1 followed, 1 reply)" in line or "2 waiting in my inbox (1 follow, 1 reply)" in line
    assert "my last post was 3h ago" in line and "1 draft open" in line


def test_social_tools_come_up_in_chat_when_something_is_waiting(placed, levers, monkeypatch):
    import agent_client
    from social import inbox
    assert agent_client._mentions_social("did anyone reply to my post?")
    assert not agent_client._mentions_social("how was your morning")
    monkeypatch.setattr(inbox, "pending", lambda p, d=None: [{"kind": "reply"}])
    assert agent_client._social_inbox_waiting()


# The pause (2026-11-17): hers or Kohl's, holds every send, reading goes on.

def test_a_pause_holds_every_send_and_lifts(placed, levers):
    fake = FakeBluesky()
    client = BlueskyClient(config.read_credentials("bluesky", placed), transport=httpx.MockTransport(fake))
    with levers(bluesky=True):
        out = run(execute_social_tool("social_pause", {"platform": "bluesky", "action": "pause",
                                                       "reason": "a quiet week"}, data_dir=placed))
        assert out["success"]
        for kind in ("post", "reply", "dm", "new_conversation", "follow"):
            assert "paused" in limits.check("bluesky", kind, placed)
        held = run(execute_social_tool("social_post", {"platform": "bluesky", "text": "hi"},
                                       data_dir=placed, client=client))
        assert not held["success"] and "I paused it (a quiet week)" in held["error"]
        assert not fake.records
        run(execute_social_tool("social_pause", {"platform": "bluesky", "action": "resume"}, data_dir=placed))
        assert limits.check("bluesky", "post", placed) is None


def test_kohls_pause_is_his_to_lift(placed, levers):
    limits.pause("bluesky", "Kohl", "checking the budget", data_dir=placed)
    with levers(bluesky=True):
        out = run(execute_social_tool("social_pause", {"platform": "bluesky", "action": "resume"},
                                      data_dir=placed))
    assert not out["success"] and "Kohl" in out["error"]
    assert limits.paused("bluesky", placed)


def test_a_pause_with_an_until_ends_by_itself(placed):
    now = datetime(2026, 11, 17, 12, 0)
    limits.pause("bluesky", "cass", until="2026-11-18T09:00", data_dir=placed, now=now)
    assert limits.paused("bluesky", placed, now=now)
    assert limits.paused("bluesky", placed, now=datetime(2026, 11, 18, 9, 1)) is None


def test_social_pause_is_in_her_social_sessions():
    from agent_loop.spec import PACKS
    from handlers.tool_router import TOOL_REGISTRY
    assert "social_pause" in PACKS["social"].tools and TOOL_REGISTRY["social_pause"] == "social"


def test_run_session_over_budget_says_so_instead_of_started(levers, monkeypatch):
    """2026-11-18: run-session answered "started" for a session the Heartbeat refused a
    second later (over the reflection budget). It asks the budget gate first now."""
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import heartbeat.wiring as wiring
    from routes.admin import scheduler as sched
    from routes.admin.auth import require_admin

    app = FastAPI()
    app.include_router(sched.router, prefix="/admin")
    app.dependency_overrides[require_admin] = lambda: {"user_id": "admin", "is_admin": True}
    client = TestClient(app)
    dispatched = []

    class FakePQM:
        state_bus = None

        async def _dispatch_work(self, queued):
            dispatched.append(queued)
            return True

    class Broke:
        def can_spend(self, category, usd):
            return False

        def get_remaining_budget(self, category):
            return 0.12
    monkeypatch.setattr(sched, "_phase_queue_manager", FakePQM())
    monkeypatch.setattr(wiring, "get_heartbeat", lambda: SimpleNamespace(gate=SimpleNamespace(budget=Broke())))
    with levers(agent_loop=True, bluesky=True):
        import social.config as sc
        monkeypatch.setattr(sc, "read_credentials", lambda p, d=None: {"handle": "x", "app_password": "y"})
        r = client.post("/admin/scheduler/run-session/social")
    assert r.status_code == 409 and "over budget" in r.json()["detail"] and "$0.12 left today" in r.json()["detail"]
    assert dispatched == []
