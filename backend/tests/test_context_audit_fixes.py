"""Fixes from the context audit (2026-11-16, docs/design/context-audit.md):
what was built to reach her prompts but didn't, or reached them wrongly."""
from datetime import datetime

import pytest

import thymos


@pytest.fixture
def felt(monkeypatch):
    monkeypatch.setattr(thymos, "get_thymos_context", lambda: "## FELT\n\nsteady, curious")


def test_a_session_knows_the_date_and_time():
    from agent_loop.seam import render_seam
    from agent_loop.spec import Trigger, session_spec
    spec = session_spec("reflection")
    seam = render_seam(spec, Trigger(source="schedule", why="my afternoon",
                                     at=datetime(2026, 11, 16, 14, 5)), spec.tool_names())
    assert "Now: Monday 16 November 2026, 14:05." in seam


def test_session_thymos_follows_the_same_lever_as_chat(felt, levers):
    from agent_loop import assemble
    with levers(prompt_thymos=False):
        assert assemble._thymos() is None
    with levers(prompt_thymos=True):
        assert assemble._thymos().startswith("## FELT")


def test_art_study_gets_her_felt_state(felt, levers):
    from art_study.creative_session import _get_inner_context
    with levers(prompt_thymos=True):
        assert "steady, curious" in _get_inner_context("cass")
    with levers(prompt_thymos=False):
        assert "steady, curious" not in _get_inner_context("cass")


def test_generic_runner_adds_thymos_once():
    import inspect
    from session import generic_runner
    assert "get_thymos_context" not in inspect.getsource(generic_runner), \
        "the preamble already carries Thymos (gated); a second ungated copy was added here"


def test_loop_nudge_is_marked_and_the_seam_says_what_the_mark_is():
    # Her choice, 2026-11-17: "[LOOP]" instead of "(loop:", plus a seam line,
    # after the nudge twice read to her as a person speaking.
    from agent_loop.loop import nudge_text
    from agent_loop.seam import render_seam
    from agent_loop.spec import Trigger, session_spec
    assert nudge_text("session_complete") == (
        "[LOOP] Step complete? If so, call session_complete. Otherwise, continue with a tool call.")
    spec = session_spec("reflection")
    seam = render_seam(spec, Trigger(source="schedule", why="my afternoon",
                                     at=datetime(2026, 11, 17, 14, 5)), spec.tool_names())
    assert "Lines that start with [LOOP] are the loop, not someone speaking to me" in seam


def test_the_seam_never_contradicts_what_is_offered():
    """Audit Q4 (2026-11-18): "Not yet: journal" with journal offered; "self" under
    find_tools with how_i_work offered."""
    from agent_loop.seam import _through_find, not_yet_line
    from agent_loop.spec import PACKS, conversation_spec, session_spec
    for spec in (session_spec("reflection"), conversation_spec()):
        here = set(spec.tool_names())
        line = not_yet_line(spec) or ""
        assert not ("journal (" in line and "journal" in here)
        for p in _through_find(spec, findable={t for pk in PACKS.values() for t in pk.tools}):
            assert not any(t in here for t in PACKS[p].tools), p


def test_chat_has_her_plans_and_one_felt_state():
    """Audit Q5 and Q6 (2026-11-18)."""
    import inspect
    import continuous_context
    from agent_loop.spec import conversation_spec
    assert "babelr_plans" in conversation_spec().tool_names()
    assert "babelr_plans" not in conversation_spec(chapter_house=False).tool_names()
    assert 'startswith("Feeling:")' in inspect.getsource(continuous_context.build_continuous_context)
