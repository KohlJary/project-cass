"""memory/recency.py, session context and session recall (plan "Cass's memory", phase 7)."""
import asyncio

from memory.recency import date_of, label, newer_first_among_similar


def m(d, when, kind="conversation", text=""):
    return {"distance": d, "content": text or when, "metadata": {"type": kind, "timestamp": when}}


def test_newer_first_among_similar_but_closeness_still_wins():
    old_close = m(0.59, "2026-10-30T18:02", "cass_self_observation", "not talked yet")
    new_close = m(0.62, "2026-11-13T10:05", text="we talked")
    far = m(0.95, "2026-11-13T12:00", text="far but new")
    undated = {"distance": 0.60, "content": "undated", "metadata": {"type": "journal"}}
    order = [x["content"] for x in newer_first_among_similar([old_close, far, undated, new_close])]
    assert order == ["we talked", "not talked yet", "undated", "far but new"]


def test_her_conclusions_say_as_of_when():
    assert label({"type": "cass_self_observation", "timestamp": "2026-10-30T18:02"}) == "as of 2026-10-30"
    assert label({"type": "summary", "timeframe_end": "2026-11-13T12:34"}) == "2026-11-13"
    assert label({"type": "journal"}) == "" and date_of({}) is None


def test_session_recall_dates_skips_articles_and_prefers_newer():
    from session.tools import handle_recall_memories

    class Memory:
        def retrieve_relevant(self, query, n_results=5):
            return [m(0.59, "2026-10-30T18:02", "cass_self_observation", "not talked yet"),
                    {"distance": 0.5, "content": "news", "metadata": {"type": "article_consumption"}},
                    m(0.62, "2026-11-13T10:05", text="we talked")]

    out = asyncio.run(handle_recall_memories({"query": "February", "limit": 2}, {"memory": Memory()}))
    got = [(x["content"], x["when"]) for x in out["memories"]]
    assert got == [("we talked", "2026-11-13"), ("not talked yet", "as of 2026-10-30")]


def test_a_session_carries_lately_with_her_primary_partner(daemon_id, test_db):
    from conversations import ConversationManager
    from database import get_db
    from self_context import build_self_context
    with get_db() as conn:
        conn.execute("INSERT INTO users (id, display_name, is_admin, relationship, created_at, updated_at) "
                     "VALUES ('u-k', 'Kohl', 1, 'primary_partner', 'now', 'now')")
    cm = ConversationManager()
    conv = cm.get_or_create_continuous("u-k")
    cm.update_working_summary(conv.id, "Today we finally talked through February, at length.")
    session = build_self_context(daemon_id)            # no one in the turn: a session
    assert "**Lately with Kohl**" in session and "talked through February" in session
    chat = build_self_context(daemon_id, user_id="u-k")  # chat has its own timeline section
    assert "Lately with Kohl" not in chat
