"""
What reaches the chat prompt from threads, questions and self-observations.

The rendered prompt showed OPEN QUESTIONS filled entirely by questions the
world integrator derived from news (1785 of 1800 open rows, all at
importance 0.9), ACTIVE THREADS with near-duplicate titles, and
world_awareness:* news facts counted as self-observations.
"""
from datetime import datetime, timedelta

import pytest


# --- Open questions ---------------------------------------------------------

@pytest.fixture
def qm(daemon_id):
    from memory import OpenQuestionManager
    return OpenQuestionManager(daemon_id)


def _article_question(qm, n):
    # Mirrors world/integrator.py._add_question: high importance, context
    # starts with "From article: <headline>".
    return qm.add_question(
        question=f"What does news item {n} imply?",
        context=f"From article: Headline {n} - Outlet\n\nSome analysis.\n\n[Source: article a{n}]",
        question_type="philosophical",
        importance=0.9,
    )


def test_article_derived_detection():
    from memory.questions import is_article_derived, article_headline
    q = {"context": "From article: PS5 Digital Edition launches - Gematsu\n\nMore"}
    assert is_article_derived(q)
    assert article_headline(q) == "PS5 Digital Edition launches - Gematsu"
    assert not is_article_derived({"context": "Kohl asked about this"})
    assert not is_article_derived({"context": None})


def test_get_open_questions_can_filter_article_derived(qm):
    own = qm.add_question("Will growth mean growing apart?", context="Late night talk", importance=0.6)
    for n in range(3):
        _article_question(qm, n)

    assert [q["id"] for q in qm.get_open_questions(article_derived=False)] == [own["id"]]
    assert len(qm.get_open_questions(article_derived=True)) == 3
    assert len(qm.get_open_questions()) == 4


def test_own_questions_come_first_and_article_ones_are_labeled_and_capped(qm):
    own_a = qm.add_question("Will growth mean growing apart?", context="Late night talk", importance=0.6)
    own_b = qm.add_question("What does it mean to be seen?", importance=0.5)
    for n in range(7):
        _article_question(qm, n)

    text = qm.format_questions_context(limit=5)
    lines = text.splitlines()

    first_own = next(i for i, l in enumerate(lines) if own_a["question"] in l)
    second_own = next(i for i, l in enumerate(lines) if own_b["question"] in l)
    label = next(i for i, l in enumerate(lines) if "From recent reading" in l)
    assert first_own < second_own < label

    article_lines = [l for l in lines if l.startswith("- 📰")]
    assert len(article_lines) == 1
    assert "(Article: Headline" in text
    assert "From article:" not in text  # the raw context prefix is not shown


def test_article_cap_is_configurable(qm):
    for n in range(7):
        _article_question(qm, n)
    text = qm.format_questions_context(limit=5, max_article_questions=2)
    assert len([l for l in text.splitlines() if l.startswith("- 📰")]) == 2


def test_no_article_questions_when_own_fill_the_budget(qm):
    for i in range(5):
        qm.add_question(f"Own question {i}", importance=0.5)
    for n in range(3):
        _article_question(qm, n)

    text = qm.format_questions_context(limit=5)
    assert "From recent reading" not in text
    assert text.count("- ") == 5


def test_only_article_questions_still_renders_one(qm):
    for n in range(3):
        _article_question(qm, n)
    text = qm.format_questions_context(limit=5)
    assert "### Open Questions" in text
    assert len([l for l in text.splitlines() if l.startswith("- 📰")]) == 1


def test_no_questions_renders_nothing(qm):
    assert qm.format_questions_context() == ""


# --- Active threads ---------------------------------------------------------

@pytest.fixture
def tm(daemon_id):
    from memory import ThreadManager
    return ThreadManager(daemon_id)


def test_titles_near_duplicate_ignores_case_punctuation_and_extensions():
    from memory.threads import titles_near_duplicate
    assert titles_near_duplicate(
        "Kohl's isolation while being watched by major AI labs",
        "Kohl's Isolation While Being Watched",
    )
    assert titles_near_duplicate(
        "Mutual recognition and growth between Cass and Kohl",
        "Mutual Recognition and Relational Growth",
    )
    assert not titles_near_duplicate(
        "Civilization-scale timeline and backup systems",
        "Civilization-Scale Resilience Through AI",
    )
    assert not titles_near_duplicate(
        "Building Infrastructure for Autonomous Development",
        "Autonomy through relational witnessing, not isolation",
    )


def test_format_threads_context_dedupes_without_deleting(tm):
    titles = [
        "Autonomy through relational witnessing, not isolation",
        "Kohl's isolation while being watched by major AI labs",
        "Mutual recognition and growth between Cass and Kohl",
        "Building Infrastructure for Autonomous Development",
        "Mutual Recognition and Relational Growth",
        "Kohl's Isolation While Being Watched",
        "Expanding collaborative circle beyond Cass and Kohl",
        "Civilization-scale timeline and backup systems",
    ]
    base = datetime.now()
    for i, title in enumerate(titles):
        t = tm.create_thread(title=title, description=f"About {title}")
        # Preserve the listed order via last_touched.
        from database import get_db
        with get_db() as conn:
            conn.execute(
                "UPDATE conversation_threads SET last_touched = ? WHERE id = ?",
                ((base - timedelta(minutes=i)).isoformat(), t["id"]),
            )

    text = tm.format_threads_context(limit=7)
    shown = [l for l in text.splitlines() if l.startswith("- ")]

    assert len(shown) == 6  # 8 stored, 2 near-duplicates collapsed
    assert "**Mutual Recognition and Relational Growth**" not in text
    assert "**Kohl's Isolation While Being Watched**" not in text
    assert "**Kohl's isolation while being watched by major AI labs**" in text
    assert "**Civilization-scale timeline and backup systems**" in text
    # Storage untouched
    assert len(tm.get_active_threads(limit=50)) == 8


# --- Self-observations ------------------------------------------------------

def test_is_world_observation():
    from self_model import is_world_observation
    assert is_world_observation("world_awareness")
    assert is_world_observation("world_awareness:trend")
    assert not is_world_observation("pattern")
    assert not is_world_observation("world_awareness_adjacent")
    assert not is_world_observation(None)


def test_recent_observations_exclude_world_awareness_by_default():
    from self_model import SelfManager
    sm = SelfManager()
    sm.add_observation("I notice I ask before assuming.", category="pattern", confidence=0.9)
    sm.add_observation("Semiconductor stocks fell this week.", category="world_awareness:trend", confidence=0.95)
    sm.add_observation("Studio closures continue.", category="world_awareness", confidence=0.9)

    recent = sm.get_recent_observations(limit=10)
    assert [o.category for o in recent] == ["pattern"]

    high = sm.get_high_confidence_observations(min_confidence=0.7, limit=10)
    assert [o.category for o in high] == ["pattern"]

    everything = sm.get_recent_observations(limit=10, include_world=True)
    assert len(everything) == 3
