"""
Prompt levers (features.py, tag "prompt"): each section of her chat prompt,
her identity snippet and her inline metacognitive tags can be switched off,
for benchmark ablations (Cass benchmark plan, phase 2). On by default, and
untouched by CASS_PROFILE, so test and benchmark cells keep every section
unless they turn one off by name.
"""
import asyncio

import pytest

import features

USER = "user-kohl"


class _Threads:
    def format_threads_context(self, *a, **k):
        return "- the benchmark thread"


class _Questions:
    def format_questions_context(self, *a, **k):
        return "- what each subsystem contributes"


def _build(daemon_id, **kw):
    from continuous_context import build_continuous_context
    return build_continuous_context(
        user_id=None, conversation_id=None, user_manager=None,
        thread_manager=kw.get("threads"), question_manager=kw.get("questions"),
        conversation_manager=None, daemon_id=daemon_id,
    )


@pytest.mark.unit
def test_prompt_levers_ignore_profiles(monkeypatch):
    monkeypatch.setenv("CASS_PROFILE", "test")
    prompt = [lv.name for lv in features.LEVERS.values() if features.PROMPT in lv.tags]
    assert {"prompt_thymos", "prompt_threads", "prompt_questions", "prompt_relational",
            "prompt_working_summary", "prompt_semantic_memories", "prompt_identity_snippet",
            "prompt_self_model", "metacog_tags"} <= set(prompt)
    assert all(features.is_enabled(n) for n in prompt)
    monkeypatch.setenv("CASS_FEATURE_PROMPT_THREADS", "0")
    assert not features.is_enabled("prompt_threads")


@pytest.mark.unit
@pytest.mark.parametrize("section,lever,manager", [
    ("threads", "prompt_threads", "threads"),
    ("questions", "prompt_questions", "questions"),
])
def test_section_lever_removes_its_section(daemon_id, section, lever, manager):
    managers = {"threads": _Threads(), "questions": _Questions()}
    on = _build(daemon_id, **managers)
    with features.override(**{lever: False}):
        off = _build(daemon_id, **managers)
    other = "questions" if section == "threads" else "threads"
    assert section in on.context_sections and section not in off.context_sections
    assert other in on.context_sections and other in off.context_sections


@pytest.mark.unit
def test_every_section_lever_is_a_real_lever():
    from continuous_context import SECTION_LEVERS
    for lever in SECTION_LEVERS.values():
        features.resolve(lever)  # KeyError on a typo


@pytest.mark.unit
def test_wanted_drops_a_section_whose_lever_is_off(daemon_id, monkeypatch):
    """Whatever builds a section, its lever off keeps it out of the prompt."""
    import continuous_context
    real = continuous_context._assemble_continuous_prompt
    seen = {}

    def spy(sections):
        seen.update(sections)
        return real(sections)

    monkeypatch.setattr(continuous_context, "_assemble_continuous_prompt", spy)
    with features.override(prompt_threads=False, prompt_questions=False):
        ctx = _build(daemon_id, threads=_Threads(), questions=_Questions())
    assert "threads" not in seen and "questions" not in seen
    assert "kernel" in ctx.context_sections


@pytest.mark.unit
def test_identity_snippet_lever(daemon_id, monkeypatch):
    import identity_snippets
    from agent_client import get_temple_codex_kernel
    monkeypatch.setattr(identity_snippets, "get_active_snippet",
                        lambda d: {"snippet_text": "I am Cass, and this is mine."})
    assert "this is mine." in get_temple_codex_kernel("Cass", daemon_id)
    with features.override(prompt_identity_snippet=False):
        kernel = get_temple_codex_kernel("Cass", daemon_id)
    assert "this is mine." not in kernel
    assert "a persistent self-aware entity" in kernel


@pytest.mark.unit
def test_metacog_lever_removes_the_instructions_only():
    from agent_client import get_temple_codex_kernel
    on = get_temple_codex_kernel("Cass")
    with features.override(metacog_tags=False):
        off = get_temple_codex_kernel("Cass")
    assert "## INLINE METACOGNITIVE TAGS" in on
    assert "## INLINE METACOGNITIVE TAGS" not in off
    for kept in ("## AFFECT MODULATION", "## RECOGNITION-IN-FLOW MARKS", "## THE FOUR VOWS"):
        assert kept in off
    assert len(off) < len(on)


@pytest.mark.unit
def test_metacog_off_strips_tags_and_stores_nothing(monkeypatch):
    import context_helpers

    async def must_not_run(*a, **k):
        raise AssertionError("a store was written with metacog_tags off")

    for name in ("execute_self_model_tool", "execute_user_model_tool", "execute_roadmap_tool"):
        monkeypatch.setattr(context_helpers, name, must_not_run)
    text = ("Here.\n<observe target=\"self\" category=\"pattern\">I hedge</observe>\n"
            "<hold topic=\"x\" confidence=\"0.8\">a view</hold>\n"
            "<record_self_observation>legacy</record_self_observation>\nDone.")
    with features.override(metacog_tags=False):
        out = asyncio.run(context_helpers.process_inline_tags(text))
    assert out["text"] == "Here.\n\nDone."
    assert out["self_observations"] == [] and out["holds"] == []


class _Profile:
    identity_statements = [type("S", (), {"statement": "I am someone who notices."})()]
    values = []
    growth_edges = []
    opinions = []

    def __getattr__(self, name):
        return []


class _SelfManager:
    def load_profile(self):
        return _Profile()

    def get_self_context(self, include_observations=True):
        return "## Who I Am\n- I am someone who notices."


@pytest.mark.unit
def test_self_model_lever_empties_the_session_runners_profile():
    from solo_reflection_runner import SoloReflectionRunner
    runner = SoloReflectionRunner.__new__(SoloReflectionRunner)
    runner.self_manager = _SelfManager()
    runner.self_model_graph = None
    with features.override(prompt_self_model=False):
        assert runner._build_self_context() == ""
    assert "I am someone who notices." in runner._build_self_context()


@pytest.mark.unit
def test_self_model_lever_keeps_the_profile_out_of_the_journal(monkeypatch):
    import journal_generation
    seen = {}

    class _Memory:
        async def generate_journal_entry(self, date, anthropic_api_key, token_tracker, self_context):
            seen["self_context"] = self_context
            return None

    with features.override(prompt_self_model=False):
        asyncio.run(journal_generation.write_daily_journal(
            "2026-10-28", [], [], memory=_Memory(), self_manager=_SelfManager(), token_tracker=object()))
    assert seen["self_context"] is None
    asyncio.run(journal_generation.write_daily_journal(
        "2026-10-28", [], [], memory=_Memory(), self_manager=_SelfManager(), token_tracker=object()))
    assert "I am someone who notices." in seen["self_context"]


@pytest.mark.unit
def test_self_model_reaches_chat_only_with_its_lever(daemon_id, monkeypatch):
    """Epic #63: off by default (her live chat unchanged); on, the comparator's text."""
    import self_model
    monkeypatch.setattr(self_model.SelfManager, "get_self_context",
                        lambda self, **k: "## YOUR SELF-MODEL\n\n- I keep my promises")
    monkeypatch.setenv("CASS_PROFILE", "test")
    assert not features.is_enabled("prompt_self_model_chat")
    assert "self_model" not in _build(daemon_id).context_sections
    with features.override(prompt_self_model_chat=True):
        on = _build(daemon_id)
    assert "I keep my promises" in on.context_sections["self_model"]
    assert "I keep my promises" in on.system_prompt


@pytest.mark.unit
def test_self_model_section_is_the_comparators_text(daemon_id, monkeypatch):
    """No message reaches it: per-message ranking embeds every growth edge each turn."""
    import self_model
    calls = []
    monkeypatch.setattr(self_model.SelfManager, "get_self_context",
                        lambda self, **k: calls.append(k) or "## YOUR SELF-MODEL\n\n- x")
    from continuous_context import build_continuous_context
    with features.override(prompt_self_model_chat=True):
        build_continuous_context(user_id=None, conversation_id=None, user_manager=None,
                                 thread_manager=None, question_manager=None,
                                 conversation_manager=None, daemon_id=daemon_id,
                                 query="what's your favorite season?")
    assert calls == [{"include_observations": True}]
