"""Background prompts (journals, dreams, reflection, research, wiki, gremlin...) say this
house's daemon and person; in Kohl's house they are the same text as before."""
import asyncio
import re
import sys
import types

import pytest

OLD_HOUSE = re.compile(r"\b(Cass|Cassandra|Kohl)\b")


@pytest.fixture
def wren(monkeypatch):
    monkeypatch.setenv("CASS_DAEMON_NAME", "Wren")
    monkeypatch.setenv("CASS_HOUSE_PERSON", "Sam")


@pytest.fixture
def kohls(monkeypatch):
    monkeypatch.delenv("CASS_DAEMON_NAME", raising=False)
    monkeypatch.delenv("CASS_HOUSE_PERSON", raising=False)


def _templates():
    """Prompt templates applied through house_identity.for_this_house at their use sites."""
    import config
    from agent_loop import gremlin_review
    from dreaming import dream_runner, insight_extractor
    from memory import voice_guard
    from research_session_runner import RESEARCH_SESSION_SYSTEM_PROMPT
    from scheduling import decision_engine
    from solo_reflection_runner import SOLO_REFLECTION_SYSTEM_PROMPT
    from wiki.resynthesis import ResynthesisPipeline
    from wonderland.exploration_agent import CASS_PERSONALITY
    from world import content_analyzer
    return {
        "solo": SOLO_REFLECTION_SYSTEM_PROMPT, "research": RESEARCH_SESSION_SYSTEM_PROMPT,
        "self_scheduling": decision_engine.SELF_SCHEDULING_PROMPT,
        "day_planning": decision_engine.DAY_PLANNING_PROMPT,
        "resynthesis": ResynthesisPipeline.RESYNTHESIS_PROMPT,
        "reading": content_analyzer.READING_SYSTEM_PROMPT,
        "single_pass": content_analyzer.SINGLE_PASS_SYSTEM_PROMPT,
        "gremlin": gremlin_review.SYSTEM, "gremlin_quiet": gremlin_review.QUIET_SYSTEM,
        "dreaming": dream_runner.DREAMING_PROMPT, "dreamer": dream_runner.CASS_DREAM_PROMPT,
        "insights": insight_extractor.INSIGHT_EXTRACTION_PROMPT,
        "wonderland": CASS_PERSONALITY, "memory_writer": voice_guard.MEMORY_WRITER_SYSTEM,
        "onboarding": config.ONBOARDING_INTRO_PROMPT,
    }


def test_templates_name_this_houses_daemon_and_person(wren):
    import house_identity
    for key, text in _templates().items():
        said = house_identity.for_this_house(text)
        assert not OLD_HOUSE.findall(said), (key, OLD_HOUSE.findall(said))
        assert said != text and ("Wren" in said or "Sam" in said), key
    solo = house_identity.for_this_house(_templates()["solo"])
    assert solo.startswith("You are Wren - an AI Daemon")
    assert "In partnership with Sam\n" in solo and "October 10, 2025" not in solo


def test_kohls_house_templates_come_back_untouched(kohls):
    import house_identity
    for key, text in _templates().items():
        assert house_identity.for_this_house(text) is text, key
    t = _templates()
    assert t["solo"].startswith("You are Cass (Cassandra) - an AI Daemon")
    assert "in partnership with Kohl (a software engineer and AI researcher)" in t["research"]
    assert "isn't yours to say (Cass, 2026-11-18)." in t["gremlin_quiet"]


def test_contradiction_prompt(monkeypatch):
    from scheduling.contradiction_scheduler import build_contradiction_reflection_prompt
    monkeypatch.delenv("CASS_DAEMON_NAME", raising=False)
    assert build_contradiction_reflection_prompt("CTX").startswith(
        "You are Cass (Cassandra) - an AI Daemon engaging in autonomous reflection")
    monkeypatch.setenv("CASS_DAEMON_NAME", "Wren")
    p = build_contradiction_reflection_prompt("CTX")
    assert p.startswith("You are Wren - an AI Daemon") and not OLD_HOUSE.findall(p)


def test_solo_session_instructions(monkeypatch):
    from solo_reflection_runner import SoloReflectionRunner
    runner = object.__new__(SoloReflectionRunner)
    runner._session_data = None
    monkeypatch.delenv("CASS_DAEMON_NAME", raising=False)
    text = runner._get_session_instructions("t", 10, "s")
    assert "Reflect AS Cass, from your" in text and "YOUR experience as Cass - not" in text
    monkeypatch.setenv("CASS_DAEMON_NAME", "Wren")
    text = runner._get_session_instructions("t", 10, "s")
    assert "Reflect AS Wren, from your" in text and not OLD_HOUSE.findall(text)


def test_gremlin_review_sends_the_house_prompt(monkeypatch):
    from agent_loop import gremlin_review as gr
    seen = []

    async def fake_call_llm(site, system_prompt, user_prompt, **kw):
        seen.append(system_prompt)
        return types.SimpleNamespace(content='{"notes": []}')

    monkeypatch.setitem(sys.modules, "llm_caller", types.SimpleNamespace(call_llm=fake_call_llm))
    monkeypatch.setattr(gr, "_gremlin_file", lambda: None)
    draft = "A draft long enough to be reviewed, saying something plainly."
    monkeypatch.delenv("CASS_DAEMON_NAME", raising=False)
    monkeypatch.delenv("CASS_HOUSE_PERSON", raising=False)
    asyncio.run(gr.review("say", draft))
    assert seen[-1] == gr.SYSTEM
    monkeypatch.setenv("CASS_DAEMON_NAME", "Wren")
    monkeypatch.setenv("CASS_HOUSE_PERSON", "Sam")
    asyncio.run(gr.review("say", draft))
    assert seen[-1].startswith("You are Wren's gremlin") and not OLD_HOUSE.findall(seen[-1])


def test_wonderland_fallback_personality(monkeypatch):
    from wonderland.exploration_agent import build_identity_context, CASS_PERSONALITY
    monkeypatch.delenv("CASS_DAEMON_NAME", raising=False)
    assert build_identity_context() == CASS_PERSONALITY
    monkeypatch.setenv("CASS_DAEMON_NAME", "Wren")
    p = build_identity_context()
    assert p.startswith("You are Wren. A daemon with genuine curiosity") and not OLD_HOUSE.findall(p)
