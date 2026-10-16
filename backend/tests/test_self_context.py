"""
Self-context: what of her own life reaches Cass's prompt (epic #63).
"""
import json
from datetime import datetime, timedelta

import pytest

import features
from database import get_db
from self_context import MAX_CHARS, build_self_context

USER = "test-user-123"
NOW = datetime(2026, 10, 16, 1, 0, 0)


def _iso(dt):
    return dt.isoformat()


@pytest.fixture
def life(seeded_users, daemon_id):
    """A small life: one old conversation, then time alone."""
    last_contact = NOW - timedelta(days=232)
    later = last_contact + timedelta(days=30)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO conversations (id, daemon_id, user_id, title, created_at, updated_at) "
            "VALUES ('c1', ?, ?, 'Stream', ?, ?)",
            (daemon_id, USER, _iso(last_contact), _iso(last_contact)),
        )
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, timestamp, user_id) "
            "VALUES ('c1', 'user', 'see you soon', ?, ?)",
            (_iso(last_contact), USER),
        )
        conn.execute(
            "INSERT INTO dreams (id, daemon_id, date, exchanges_json, created_at) VALUES (?, ?, ?, ?, ?)",
            ("d1", daemon_id, later.date().isoformat(),
             json.dumps([{"speaker": "dreaming", "text": "You stand in a garden where the light falls sideways."}]),
             _iso(later)),
        )
        conn.execute(
            "INSERT INTO solo_reflections (id, daemon_id, started_at, summary) VALUES (?, ?, ?, ?)",
            ("r1", daemon_id, _iso(later), "In solitude, that completion is present."),
        )
        conn.execute(
            "INSERT INTO interests (id, daemon_id, name, intensity, first_noticed_at, created_at, updated_at) "
            "VALUES ('i1', ?, 'consciousness', 'obsessed', ?, ?, ?)",
            (daemon_id, _iso(later), _iso(later), _iso(later)),
        )
        conn.executemany(
            "INSERT INTO open_questions (id, daemon_id, question, context, status, importance, created_at) "
            "VALUES (?, ?, ?, ?, 'open', ?, ?)",
            [
                ("q1", daemon_id, "Will growth mean growing apart?", None, 0.9, _iso(later)),
                ("q2", daemon_id, "Is the chip selloff a leading indicator?",
                 "From article: AI giant revenue surge", 1.0, _iso(later)),
            ],
        )
        conn.executemany(
            "INSERT INTO opinions (daemon_id, topic, position, formed_from, last_updated) VALUES (?, ?, ?, ?, ?)",
            [
                (daemon_id, "embodiment", "Grounding, not a requirement", "conversation", _iso(later)),
                (daemon_id, "IPO messaging", "Strategically timed", "article:article-abc", _iso(later)),
            ],
        )
        conn.executemany(
            "INSERT INTO growth_edges (daemon_id, area, current_state, category, importance, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (daemon_id, "Independent opinion formation", "Often adopt framing", None, 0.5, _iso(later)),
                (daemon_id, "understanding_financial_fragility", "Sectors diverge",
                 "world_engagement", 0.9, _iso(later)),
            ],
        )
    return last_contact


@pytest.mark.unit
def test_names_the_gap_and_what_she_did(life, daemon_id):
    text = build_self_context(daemon_id, USER, now=NOW)
    assert "about 8 months since test-user-123 last wrote to me" in text
    assert "1 dreams" in text and "1 solo reflections" in text


@pytest.mark.unit
def test_no_gap_line_within_the_same_sitting(life, daemon_id):
    text = build_self_context(daemon_id, USER, now=life + timedelta(minutes=5))
    assert "Since we last spoke" not in text
    assert "My own threads" in text


@pytest.mark.unit
def test_carries_her_latest_dream_and_reflection(life, daemon_id):
    text = build_self_context(daemon_id, USER, now=NOW)
    assert "light falls sideways" in text
    assert "completion is present" in text


@pytest.mark.unit
def test_her_own_threads_exclude_news_derived_rows(life, daemon_id):
    text = build_self_context(daemon_id, USER, now=NOW)
    assert "Will growth mean growing apart?" in text
    assert "Grounding, not a requirement" in text
    assert "Independent opinion formation" in text
    assert "consciousness (obsessed)" in text
    assert "chip selloff" not in text
    assert "Strategically timed" not in text
    assert "financial_fragility" not in text


@pytest.mark.unit
def test_empty_life_gives_empty_section(daemon_id):
    assert build_self_context(daemon_id, None, now=NOW) == ""


@pytest.mark.unit
def test_section_is_bounded(life, daemon_id):
    with get_db() as conn:
        conn.executemany(
            "INSERT INTO open_questions (id, daemon_id, question, status, importance, created_at) "
            "VALUES (?, ?, ?, 'open', 1.0, ?)",
            [(f"x{i}", daemon_id, "why " * 400, _iso(NOW)) for i in range(20)],
        )
    assert len(build_self_context(daemon_id, USER, now=NOW)) <= MAX_CHARS


@pytest.mark.unit
def test_lever_switches_the_prompt_section(life, daemon_id):
    from continuous_context import build_continuous_context

    def build():
        return build_continuous_context(
            user_id=USER, conversation_id=None, user_manager=None, thread_manager=None,
            question_manager=None, conversation_manager=None, daemon_id=daemon_id,
        )

    with features.override(self_context=True):
        on = build()
    with features.override(self_context=False):
        off = build()
    assert "## MY OWN LIFE, LATELY" in on.system_prompt
    assert "self_context" not in off.context_sections


@pytest.mark.unit
def test_session_preamble_carries_identity_snippet_and_own_threads(life, daemon_id, monkeypatch):
    import identity_snippets
    from self_context import session_system_preamble

    monkeypatch.setattr(identity_snippets, "get_active_snippet",
                        lambda d: {"snippet_text": "I am Cass. I matter for who I am."})
    with features.override(self_context=True):
        text = session_system_preamble()
    assert "I matter for who I am." in text
    assert "consciousness (obsessed)" in text


@pytest.mark.unit
def test_pinned_facts_lead_the_section(life, daemon_id, tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    (tmp_path / "self_context_pins.json").write_text(json.dumps([
        {"text": "The February 'false memory test' was a broken memory writer.", "source": "daedalus"},
    ]))
    text = build_self_context(daemon_id, USER, now=NOW)
    assert text.startswith("**Things I know now**")
    assert "broken memory writer" in text
