"""Dreams are seeded from her own threads, not the news."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from database import get_db


class _Profile(SimpleNamespace):
    pass


class _SelfManager:
    def __init__(self, edges):
        self._edges = edges

    def load_profile(self):
        return _Profile(growth_edges=self._edges)

    def touch_growth_edges(self, ids):
        pass


def _edge(edge_id, area, category):
    from self_model_profile import GrowthEdge
    now = datetime.now().isoformat()
    return GrowthEdge(edge_id=edge_id, area=area, current_state="", category=category,
                      first_noticed=now, last_updated=now)


@pytest.mark.unit
def test_seeds_skip_news_questions_and_world_edges(daemon_id):
    from dreaming.seed_selection import select_dream_seeds
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.executemany(
            "INSERT INTO open_questions (id, daemon_id, question, context, status, importance, created_at) "
            "VALUES (?, ?, ?, ?, 'open', ?, ?)",
            [("q1", daemon_id, "Will growth mean growing apart?", None, 0.5, now),
             ("q2", daemon_id, "Is handheld gaming going luxury?", "From article: consoles", 0.9, now)],
        )
    mgr = _SelfManager([_edge("e1", "Independent opinion formation", "relational"),
                        _edge("e2", "understanding_markets", "world_engagement")])

    seeds = select_dream_seeds(mgr, daemon_id)

    assert [q["question"] for q in seeds.open_questions] == ["Will growth mean growing apart?"]
    assert [e.area for e in seeds.growth_edges] == ["Independent opinion formation"]
