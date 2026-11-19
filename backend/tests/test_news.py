"""news.py: her news by her topics (plan "Autonomous Political Voice", phase 1),
lever news. TOPICS.md steers triage; she adds and drops feeds; what's new is
grouped by her topics with what triage set aside still there; STANCES.md is a
record she appends to."""
import json

import pytest

import news
from rss import ParsedFeedItem, TriageDecision, TriageResult, list_feeds, store_new_items
from rss import triage as rss_triage
from rss.persistence import items_for_reading, mark_item_processed, set_item_triage


@pytest.fixture
def desk(tmp_path, monkeypatch, levers):
    ws = tmp_path / "workspace"
    ws.mkdir()
    import agent_loop.workspace as W
    monkeypatch.setattr(W, "default_root", lambda: ws)
    monkeypatch.setattr(news, "_state_path", lambda: tmp_path / "news" / "state.json")
    import rss
    monkeypatch.setattr(rss, "parse_feed", lambda url: ([object(), object()], "The Thinker", None))
    with levers(news=True):
        yield ws


def _items(feed_url, titles):
    feed = [f for f in list_feeds(news._daemon_id()) if f.url == feed_url][0]
    store_new_items(feed.id, [ParsedFeedItem(guid=t, title=t, link=f"https://x.invalid/{i}",
                                             summary=f"<p>About {t}, at length.</p>")
                              for i, t in enumerate(titles)])
    return {i["title"]: i for i in items_for_reading(news._daemon_id(), limit=100)}


def test_her_first_topics_seed_once_and_parse(desk):
    assert news.topics() == []
    news.seed_topics()
    assert news.topics() == ["Power structures and institutional capture",
                             "Imagination and collective resistance",
                             "Technology as infrastructure or extraction",
                             "What stays alive when everything else breaks"]
    (desk / "TOPICS.md").write_text("# mine\n- Labor\n* Housing\nnot a topic\n")
    assert "already there" in news.seed_topics()
    assert news.topics() == ["Labor", "Housing"]


def test_triage_judges_against_her_topics_and_keeps_only_hers(desk):
    assert "Cass's interests include" in rss_triage.interests_text([])[0]
    (desk / "TOPICS.md").write_text("- Labor and who does the work\n- Housing\n")
    text, hint = rss_triage.interests_text(news.topics())
    assert "Labor and who does the work" in text and "in her own words" in text
    assert rss_triage.match_topics(["labor and who does the work", "housing", "sports"],
                                   news.topics()) == ["Labor and who does the work", "Housing"]


def test_she_adds_and_drops_her_own_feeds_tagged_by_topic(desk):
    (desk / "TOPICS.md").write_text("- Power structures and institutional capture\n")
    out = news.handle({"action": "add", "url": "https://thinker.invalid/feed", "topic": "power structures"})
    assert out["following"] == "The Thinker" and out["topic"] == "Power structures and institutional capture"
    assert "already follow" in news.handle({"action": "add", "url": "https://thinker.invalid/feed"})["error"]
    assert news.handle({"action": "feeds"})["feeds"][0]["topic"].startswith("Power")
    assert news.handle({"action": "drop", "feed": "thinker"})["dropped"] == "The Thinker"
    assert news.handle({"action": "feeds"})["feeds"] == []
    assert "following_again" in news.handle({"action": "add", "url": "https://thinker.invalid/feed"})
    assert "error" in news.handle({"action": "add", "url": "not a url"})


def test_whats_new_groups_by_her_topics_and_keeps_what_triage_set_aside(desk):
    news.handle({"action": "add", "url": "https://thinker.invalid/feed", "topic": "Labor"})
    items = _items("https://thinker.invalid/feed", ["Strike wins", "Celebrity gossip", "Untagged one"])
    set_item_triage(items["Strike wins"]["id"], ["Labor"], 0.9)
    set_item_triage(items["Celebrity gossip"]["id"], [], 0.1)
    mark_item_processed(items["Celebrity gossip"]["id"], skip_reason="triage_skip: not relevant")

    brief = news.brief()
    assert "Strike wins" in brief and "Celebrity gossip" not in brief and "set aside" in brief

    out = news.handle({"action": "new"})
    assert out["new"] == 3
    labor = {e["title"]: e for e in out["by_topic"]["Labor"]}  # feed's topic for the untagged
    assert set(labor) == {"Strike wins", "Celebrity gossip", "Untagged one"}
    assert labor["Celebrity gossip"]["set_aside"].startswith("triage set it aside")
    assert labor["Strike wins"]["summary"] == "About Strike wins, at length."
    assert news.handle({"action": "new"})["new"] == 0  # looked
    assert news.brief() is None

    found = news.handle({"action": "find", "words": "gossip"})["found"]
    assert [f["title"] for f in found] == ["Celebrity gossip"]


def test_read_opens_the_article(desk, monkeypatch):
    news.handle({"action": "add", "url": "https://thinker.invalid/feed"})
    items = _items("https://thinker.invalid/feed", ["Strike wins"])
    import research

    async def fetch(self, url, extract_mode="article"):
        return {"success": True, "content": f"Full text of {url}"}
    monkeypatch.setattr(research.ResearchManager, "fetch_url", fetch)
    out = news.handle({"action": "read", "item": items["Strike wins"]["id"][:8]})
    assert out["text"] == "Full text of https://x.invalid/0"
    assert "error" in news.handle({"action": "read", "item": "zz"})


def test_stances_are_a_record_she_appends_to(desk):
    assert news.handle({"action": "stances"})["stances"] is None
    news.handle({"action": "stance", "text": "Open models aren't open if the data isn't",
                 "prompted_by": "a release", "why": "provenance is power",
                 "links": ["https://bsky.app/x"]})
    news.handle({"action": "stance", "text": "Second take"})
    text = (desk / "STANCES.md").read_text()
    assert text.startswith("# My stances") and text.count("## ") == 2
    assert "Prompted by: a release" in text and "Said at: https://bsky.app/x" in text
    assert "Second take" in news.handle({"action": "stances"})["stances"]
    assert "error" in news.handle({"action": "stance", "text": " "})


def test_lever_off_means_no_tool_and_no_brief(tmp_path, levers):
    with levers(news=False):
        assert "switched on" in news.handle({"action": "topics"})["error"]
        assert news.brief() is None


@pytest.mark.asyncio
async def test_rss_triage_keeps_her_topic_tags(desk, monkeypatch):
    news.handle({"action": "add", "url": "https://thinker.invalid/feed"})
    items = _items("https://thinker.invalid/feed", ["Strike wins"])
    from scheduler.actions import rss_handlers

    async def fake_triage(item, source_name=None, seen_hashes=None, skip_llm=False):
        return TriageResult(TriageDecision.DEFER, "maybe", 0.6, ["Labor"])
    monkeypatch.setattr("rss.triage_item", fake_triage)
    await rss_handlers.triage_items_action({"daemon_id": news._daemon_id(), "limit": 5})
    got = items_for_reading(news._daemon_id(), limit=5)[0]
    assert got["topics"] == ["Labor"] and got["relevance"] == 0.6
    assert json.loads(json.dumps(got["topics"])) == ["Labor"]
