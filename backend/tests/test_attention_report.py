"""scripts/attention_report.py: the before/after numbers for her attention."""
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import attention_report  # noqa: E402


@pytest.fixture
def seeded_dir(test_db, daemon_id, tmp_path):
    """A DATA_DIR whose cass.db is a copy of the test schema with a few rows."""
    from database import get_db

    now = datetime.now().isoformat()
    old = (datetime.now() - timedelta(days=90)).isoformat()
    with get_db() as conn:
        # opinions: two from articles (one old), one of her own
        for i, (formed_from, when) in enumerate([("article:a1", now), ("article:a2", old), ("conversation", now)]):
            conn.execute(
                "INSERT INTO opinions (daemon_id, topic, position, confidence, formed_from, date_formed, last_updated) "
                "VALUES (?, ?, 'pos', 0.8, ?, ?, ?)", (daemon_id, f"topic-{i}", formed_from, when, when))
        # growth edges: one from an article, one of her own
        conn.execute(
            "INSERT INTO growth_edges (daemon_id, edge_id, area, current_state, desired_state, importance, "
            "first_noticed, last_updated, observations_json, category) VALUES (?, 'e1', 'a', '', '', 0.7, ?, ?, "
            "'[\"Sparked by article a1\"]', 'world_engagement')", (daemon_id, now, now))
        conn.execute(
            "INSERT INTO growth_edges (daemon_id, edge_id, area, current_state, desired_state, importance, "
            "first_noticed, last_updated, observations_json, category) VALUES (?, 'e2', 'b', '', '', 0.7, ?, ?, "
            "'[]', 'identity')", (daemon_id, now, now))
        # open questions: one from an article, one of hers
        conn.execute(
            "INSERT INTO open_questions (id, daemon_id, question, context, status, created_at) "
            "VALUES ('q1', ?, 'q', 'From article: X\n\nctx', 'open', ?)", (daemon_id, now))
        conn.execute(
            "INSERT INTO open_questions (id, daemon_id, question, context, status, created_at) "
            "VALUES ('q2', ?, 'q', 'own wondering', 'open', ?)", (daemon_id, now))
        # reflections: two mismatched, one fine
        for i, text in enumerate([
            "This session didn't yield much value: the articles were about product launches rather than what I had hoped to explore.",
            "This session was irrelevant to my current questions.",
            "A genuinely useful session; I learned something about tides.",
        ]):
            conn.execute(
                "INSERT INTO self_observations (id, daemon_id, category, observation, created_at) "
                "VALUES (?, ?, ?, ?, ?)", (f"r{i}", daemon_id, attention_report.REFLECTION_CATEGORY, text, now))
        # articles
        conn.execute(
            "INSERT INTO consumed_articles (id, daemon_id, url, headline, category, consumed_at, processing_status) "
            "VALUES ('a1', ?, 'https://x/1', 'h', 'technology', ?, 'completed')", (daemon_id, now))
        conn.execute(
            "INSERT INTO consumed_articles (id, daemon_id, url, headline, category, consumed_at, processing_status) "
            "VALUES ('a2', ?, 'https://x/2', 'h', 'research_focus', ?, 'completed')", (daemon_id, now))
        conn.execute(
            "INSERT INTO research_focus (id, daemon_id, topic, source, status, times_used, created_at) "
            "VALUES ('f1', ?, 'tidal locking', 'chat', 'active', 2, ?)", (daemon_id, now))
        conn.commit()

    data_dir = tmp_path / "data_dir"
    data_dir.mkdir()
    src = sqlite3.connect(test_db)
    dst = sqlite3.connect(data_dir / "cass.db")
    src.backup(dst)
    src.close()
    dst.close()
    return data_dir


def test_report_counts(seeded_dir, capsys):
    assert attention_report.main([str(seeded_dir), "--days", "30"]) == 0
    out = capsys.readouterr().out
    assert "opinions" in out and "2/3 (67%)" in out and "1/2 (50%)" in out   # overall / last 30 days
    assert "growth edges" in out
    assert "open questions" in out
    assert "from a low-value session (rated < 5/10)" in out and "1/3 (33%)" in out
    assert "saying the material was not what she wanted" in out and "2/3 (67%)" in out
    assert "'rather than'" in out and "'irrelevant'" in out
    assert "2 (1 found via research focus)" in out
    assert "'tidal locking' set" in out and "used 2 time(s); 1 in history" in out


def test_report_is_read_only(seeded_dir):
    db = seeded_dir / "cass.db"
    before = db.read_bytes()
    attention_report.main([str(seeded_dir)])
    assert db.read_bytes() == before


def test_missing_db_exits_cleanly(tmp_path):
    # tmp_path itself holds the autouse test db; point at an empty subdir
    with pytest.raises(SystemExit):
        attention_report.main([str(tmp_path / "nowhere")])


def test_predates_focus_table(seeded_dir, capsys):
    conn = sqlite3.connect(seeded_dir / "cass.db")
    conn.execute("DROP TABLE research_focus")
    conn.commit()
    conn.close()
    attention_report.main([str(seeded_dir)])
    assert "predates it" in capsys.readouterr().out
