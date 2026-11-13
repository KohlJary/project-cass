"""
Article observations out of her episodic recall (plan "Cass's memory",
item fe5ddbe8; Cass, 2026-11-13). What she noticed in an article stays with
the article and is found through search_articles; chat recall leaves out
everything that came from scanning articles.
"""
import json
from datetime import datetime

from continuous_context import _from_article_scanning, _retrieve_semantic_memories


def test_article_memories_are_recognized():
    assert _from_article_scanning({"type": "article_consumption"})
    assert _from_article_scanning({"type": "cass_self_observation", "category": "world_awareness:trend"})
    # What she records herself about the world in conversation stays.
    assert not _from_article_scanning({"type": "cass_self_observation", "category": "world_awareness"})
    assert not _from_article_scanning({"type": "conversation"})


class _Memory:
    def __init__(self, items):
        self.items = items
        self.asked = None

    def retrieve_relevant(self, query, n_results, filter_type=None):
        self.asked = n_results
        return self.items[:n_results]


def test_recall_skips_article_memories_and_keeps_five_of_hers():
    items = ([{"content": f"news {i}", "distance": 0.2,
               "metadata": {"type": "cass_self_observation", "category": "world_awareness:trend"}}
              for i in range(6)]
             + [{"content": f"talked with Rowan {i}", "distance": 0.4,
                 "metadata": {"type": "conversation", "user_id": "rowan"}}
                for i in range(7)])
    mem = _Memory(items)
    out = _retrieve_semantic_memories(mem, "Rowan", user_id="rowan", n_results=5)
    assert "news" not in out and out.count("talked with Rowan") == 5


def test_search_articles_finds_what_she_noticed(daemon_id):
    from database import get_db
    from world.memory_integration import search_consumed_articles
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO consumed_articles (id, daemon_id, url, headline, summary, category, consumed_at, "
            "processing_status, observations_json) VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?)",
            ("a1", daemon_id, "https://x/1", "Harbor news", "Boats.", "local", now,
             json.dumps([{"text": "Anemones recolonize faster than expected", "category": "trend"}])))
        conn.commit()
    found = search_consumed_articles(daemon_id, query="recolonize")
    assert [a["id"] for a in found] == ["a1"]
