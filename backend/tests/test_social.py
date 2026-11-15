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
    assert "social_post" not in router_catalog()
    with levers(bluesky=True):
        assert "social_post" in router_catalog()


def dm_client(placed, fake):
    return BlueskyClient(config.read_credentials("bluesky", placed), transport=httpx.MockTransport(fake))


def test_dms_need_their_own_lever(placed, levers):
    with levers(bluesky=True):
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
