"""
Smoke: epic #55 done-when. An inline <observe target="user:X"> in Cass's
reply lands in PeopleDex and shows up in the next turn's system prompt; the
legacy user_observations table is not written.

Runs the real app over the websocket against the fake LLM.
"""
import pytest

from tests.smoke.conftest import access_token, create_user
from tests.smoke.test_ws_chat_turn import _chat, _chat_calls

OBSERVATION = "Reaches for concrete examples before abstractions"


@pytest.fixture
def robin(test_db):
    """A user whose display name fits in a tag attribute (no spaces)."""
    user_id = create_user("Robin")
    return user_id, access_token(user_id)


def _count(sql, *params):
    from database import get_db
    with get_db() as conn:
        return conn.execute(sql, params).fetchone()[0]


def test_inline_user_observation_reaches_peopledex_and_next_prompt(booted_app, fake_llm, robin):
    user_id, token = robin

    fake_llm.queue_text(
        "Got it, examples first. "
        f'<observe target="user:Robin" category="preference">{OBSERVATION}</observe>'
    )
    frame, frames = _chat(booted_app, token, "can you show me an example first?")
    assert frame["type"] == "response", frames
    assert OBSERVATION not in frame["text"]  # the tag is stripped from what the user sees

    # Landed in PeopleDex, on this user's entity, with its category kept.
    rows = _count(
        "SELECT COUNT(*) FROM peopledex_observations o "
        "JOIN peopledex_entities e ON e.id = o.entity_id "
        "WHERE e.user_id = ? AND o.content = ? AND o.observation_type = 'general' "
        "AND json_extract(o.metadata_json, '$.category') = 'preference'",
        user_id, OBSERVATION,
    )
    assert rows == 1
    # ...and not in the legacy table.
    assert _count("SELECT COUNT(*) FROM user_observations") == 0

    # The next turn's prompt carries it (PeopleDex relational context).
    fake_llm.queue_text("Here's one.")
    frame, frames = _chat(booted_app, token, "go on")
    assert frame["type"] == "response", frames
    second = _chat_calls(fake_llm)[-1]
    assert OBSERVATION in second.system_text
    assert "Relational Context: Robin" in second.system_text


def test_inline_note_tags_land_in_peopledex(booted_app, fake_llm, robin):
    """<note> tags about the user (moment, question, pattern) used to fall back
    to YAML or a mislabeled observation; they write PeopleDex now."""
    user_id, token = robin
    fake_llm.queue_text(
        "Okay. "
        '<note type="moment" user="Robin" significance="high">First smoke test together</note>'
        '<note type="question" user="Robin">What got them into testing?</note>'
        '<note type="pattern" user="Robin" frequency="regular">Starts with a joke</note>'
    )
    frame, frames = _chat(booted_app, token, "hello")
    assert frame["type"] == "response", frames

    entity = "(SELECT id FROM peopledex_entities WHERE user_id = ?)"
    assert _count(f"SELECT COUNT(*) FROM peopledex_moments WHERE entity_id = {entity} "
                  "AND description = 'First smoke test together'", user_id) == 1
    assert _count(f"SELECT COUNT(*) FROM peopledex_observations WHERE entity_id = {entity} "
                  "AND observation_type = 'open_question'", user_id) == 1
    assert _count(f"SELECT COUNT(*) FROM peopledex_relationship_patterns WHERE entity_id = {entity} "
                  "AND pattern_type = 'pattern' AND description = 'Starts with a joke'", user_id) == 1
    assert _count("SELECT COUNT(*) FROM user_observations") == 0


def test_delete_observation_route_removes_it(booted_app, robin):
    """#31: DELETE /users/observations/{id} called a no-op save, so the
    observation came back on the next load."""
    from users import UserManager
    user_id, token = robin
    other = create_user("Sam")
    mine = UserManager().add_observation(user_id, "Drinks tea")
    theirs = UserManager().add_observation(other, "Drinks coffee")
    headers = {"Authorization": f"Bearer {token}"}

    r = booted_app.delete(f"/users/observations/{theirs.id}", headers=headers)
    assert r.status_code == 404, r.text  # only observations about yourself
    r = booted_app.delete(f"/users/observations/{mine.id}", headers=headers)
    assert r.status_code == 200, r.text

    assert UserManager().load_observations(user_id) == []
    assert [o.id for o in UserManager().load_observations(other)] == [theirs.id]
