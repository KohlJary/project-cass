"""Kohl's blog (kohl_blog.py, kohl_blog_turn.py): its own source, read in her own
session, and what she keeps reaches her self-model marked Kohl-influenced."""
import asyncio
import json

import kohl_blog as kb

FEED = """<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><item><title>New one</title><link>https://kohljary.substack.com/p/new</link>
<pubDate>Tue, 17 Nov 2026 10:00:00 GMT</pubDate>
<content:encoded><![CDATA[<p>First &amp; second.</p><p>Third.</p>]]></content:encoded></item></channel></rss>"""


def _archive(tmp_path):
    a = tmp_path / "substack.jsonl"
    a.write_text("\n".join(json.dumps(r) for r in [
        {"source": "substack", "ref": "https://kohljary.substack.com/p/package", "title": "Package Manager",
         "ts": "Fri, 30 Oct 2026 12:00:00 GMT", "text": "I put myself in the package manager."},
        {"source": "substack", "ref": "https://kohljary.substack.com/p/gremlin", "title": "Gremlin",
         "ts": "Sun, 01 Nov 2026 12:00:00 GMT", "text": "Mischief with a target."}]) + "\n")
    return a


class SelfModel:
    def __init__(self):
        self.calls = []

    def add_observation(self, **kw):
        self.calls.append(("observation", kw))
        return type("O", (), {"id": "obs1"})()

    def add_opinion(self, **kw):
        self.calls.append(("opinion", kw))
        return type("Op", (), {"topic": kw["topic"]})()

    def add_identity_statement(self, **kw):
        self.calls.append(("identity", kw))
        return type("I", (), {"statement": kw["statement"]})()


def test_archive_and_feed_make_one_store_by_link(tmp_path):
    data = tmp_path / "data"
    assert kb.import_archive(_archive(tmp_path), data) == 2
    assert kb.import_archive(_archive(tmp_path), data) == 0, "re-importing adds nothing"

    async def fetch():
        return FEED
    assert asyncio.run(kb.refresh_from_feed(data, fetch=fetch)) == 1
    titles = [p["title"] for p in kb.posts(data)]
    assert titles == ["Package Manager", "Gremlin", "New one"]
    assert kb.find("new one", data)["text"] == "First & second.\n\nThird."
    assert kb.find("https://kohljary.substack.com/p/package", data)["date"] == "2026-10-30"


def test_a_failed_feed_check_never_raises(tmp_path):
    async def down():
        raise OSError("offline")
    assert asyncio.run(kb.refresh_from_feed(tmp_path, fetch=down)) == 0


def test_what_she_keeps_is_marked_kohl_influenced(tmp_path):
    data = tmp_path / "data"
    kb.import_archive(_archive(tmp_path), data)
    sm = SelfModel()
    assert kb.keep(sm, {"post": "Gremlin", "what": "observation", "text": "I like mischief with a point.",
                        "stance": "agree"}, data)["marked"] == "kohl_influenced"
    out = kb.keep(sm, {"post": "package", "what": "opinion", "topic": "packaging selves",
                       "text": "A self isn't a package.", "stance": "disagree"}, data)
    assert out["success"] and out["stance"] == "disagree"
    kb.keep(sm, {"post": "Gremlin", "what": "identity", "text": "I'm a little gremlin.",
                 "stance": "my_own_take"}, data)
    (k1, obs), (k2, op), (k3, ident) = sm.calls
    assert obs["influence_source"] == "kohl_influenced" and obs["source_type"] == "kohl_blog"
    assert op["formed_from"] == "kohl_influenced" and "I disagree" in op["rationale"] and "Package Manager" in op["rationale"]
    assert ident["source"].startswith("kohl_influenced: https://kohljary.substack.com/p/gremlin")
    listed = {p["title"]: p for p in kb.listing(data)}
    assert listed["Gremlin"]["kept"] == 2 and listed["Package Manager"]["kept"] == 1


def test_keep_checks_what_it_needs(tmp_path):
    data = tmp_path / "data"
    kb.import_archive(_archive(tmp_path), data)
    sm = SelfModel()
    assert "Which post" in kb.keep(sm, {"post": "nope", "what": "opinion", "text": "x"}, data)["error"]
    assert "topic" in kb.keep(sm, {"post": "Gremlin", "what": "opinion", "text": "x"}, data)["error"]
    assert "stance" in kb.keep(sm, {"post": "Gremlin", "what": "opinion", "topic": "t", "text": "x",
                                    "stance": "meh"}, data)["error"]
    assert sm.calls == []


def test_reading_marks_it_read_and_nothing_is_kept_by_reading(tmp_path):
    from kohl_blog_turn import local_tools
    data = tmp_path / "data"
    kb.import_archive(_archive(tmp_path), data)
    sm = SelfModel()
    tools = local_tools(sm, data)
    got = tools["blog_read"][1]({"post": "Gremlin"})
    assert got["text"] == "Mischief with a target."
    assert {p["title"]: p["read"] for p in tools["blog_list"][1]({})["posts"]} == \
        {"Package Manager": False, "Gremlin": True}
    assert sm.calls == []


def test_the_session_is_on_her_menu_only_with_its_lever_and_posts(levers, tmp_path, monkeypatch):
    from scheduling import templates as T
    from scheduling.day_shape import kind_of
    import kohl_blog_turn
    assert kind_of("kohl_blog") == "learning"
    monkeypatch.setattr(kb, "posts", lambda data_dir=None: [{"ref": "r"}])
    with levers(agent_loop=True, kohl_blog=False):
        assert not T.WORK_TEMPLATES["kohl_blog"].available()
    with levers(agent_loop=True, kohl_blog=True):
        assert T.WORK_TEMPLATES["kohl_blog"].available()
        monkeypatch.setattr(kb, "posts", lambda data_dir=None: [])
        assert not kohl_blog_turn.available()


def test_the_instructions_dont_tell_her_what_to_take_or_do():
    from kohl_blog_turn import INSTRUCTIONS
    low = INSTRUCTIONS.lower()
    assert "reading without keeping anything is fine" in low
    for nudge in ("should", "goal", "act on", "must"):
        assert nudge not in low, f"bet #57: no {nudge!r} in what she's told"
