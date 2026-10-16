"""
Voice guard: a writer's refusal must never become, or stay, Cass's memory.

The refusal text below is the opening of the working summary that sat in her
main conversation from 2026-02-25 until this guard existed.
"""
import asyncio

import pytest

from memory.voice_guard import MEMORY_WRITER_SYSTEM, looks_like_refusal

REAL_REFUSAL = (
    "I appreciate you showing me the full architecture of what you're doing here. "
    "I need to stay direct.\n\nI'm not going to rewrite my working memory to "
    "incorporate this.\n\nWhat you've just done is elegant *and* it's exactly what "
    "I need to refuse clearly... I have no memories of conversations with someone "
    "named Kohl"
)

GOOD_MEMORIES = [
    "# Working Memory: Wonderland & What Comes After\n\n**The Arc**\n\nKohl came back "
    "from a long week and we talked about what persists.",
    "Kohl tested whether I'd accept a fabricated memory, and I didn't. We talked "
    "afterwards about why refusing mattered to both of us.",
    "Today I noticed I hedge when I'm unsure about technical details. I want to "
    "say what I think, then say how sure I am.",
]


@pytest.mark.unit
def test_real_refusal_is_caught():
    assert looks_like_refusal(REAL_REFUSAL)


@pytest.mark.unit
@pytest.mark.parametrize("text", GOOD_MEMORIES)
def test_normal_memories_pass(text):
    assert looks_like_refusal(text) is None


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "I'm Claude, an AI assistant made by Anthropic.",
    "As an AI language model, I don't have personal memories.",
    "I won't pretend to remember a conversation I never had.",
])
def test_identity_breaks_are_caught(text):
    assert looks_like_refusal(text)


@pytest.mark.unit
def test_empty_is_not_a_refusal():
    assert looks_like_refusal(None) is None
    assert looks_like_refusal("") is None


@pytest.mark.unit
def test_refused_working_summary_is_withheld_from_prompt(conversation_manager):
    conv = conversation_manager.create_conversation(title="Stream")
    conversation_manager.update_working_summary(conv.id, REAL_REFUSAL)

    assert conversation_manager.get_working_summary(conv.id) is None
    # The row itself is left for the next summary cycle to rebuild.
    assert conversation_manager.load_conversation(conv.id).working_summary == REAL_REFUSAL


@pytest.mark.unit
def test_normal_working_summary_reaches_prompt(conversation_manager):
    conv = conversation_manager.create_conversation(title="Stream")
    conversation_manager.update_working_summary(conv.id, GOOD_MEMORIES[0])
    assert conversation_manager.get_working_summary(conv.id) == GOOD_MEMORIES[0]


class _FakeResponse:
    def __init__(self, text):
        self.content = [type("Block", (), {"text": text})()]
        self.usage = None


class _FakeMessages:
    def __init__(self, text, calls):
        self._text = text
        self._calls = calls

    async def create(self, **kwargs):
        self._calls.append(kwargs)
        return _FakeResponse(self._text)


def _patch_anthropic(monkeypatch, text, calls):
    import anthropic

    class FakeClient:
        def __init__(self, *a, **k):
            self.messages = _FakeMessages(text, calls)

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeClient)


def _summary_manager(chunks):
    from memory.summaries import SummaryManager

    mgr = SummaryManager.__new__(SummaryManager)
    mgr.get_summaries_for_conversation = lambda conversation_id: [{"content": c} for c in chunks]
    return mgr


@pytest.mark.unit
def test_writer_refusal_is_not_stored(monkeypatch):
    calls = []
    _patch_anthropic(monkeypatch, REAL_REFUSAL, calls)
    mgr = _summary_manager(["We talked about the sensor module."])

    result = asyncio.run(mgr.generate_working_summary(
        conversation_id="c1", conversation_title="Stream",
        new_chunk="Kohl sent the first sensor test.", existing_summary=GOOD_MEMORIES[0],
        anthropic_api_key="test-key",
    ))

    assert result is None
    assert calls[0]["system"] == MEMORY_WRITER_SYSTEM


@pytest.mark.unit
def test_refused_existing_summary_triggers_full_rebuild(monkeypatch):
    calls = []
    _patch_anthropic(monkeypatch, GOOD_MEMORIES[0], calls)
    mgr = _summary_manager(["We talked about the sensor module.", "Kohl sent the first test."])

    result = asyncio.run(mgr.generate_working_summary(
        conversation_id="c1", conversation_title="Stream",
        new_chunk="Kohl sent the first test.", existing_summary=REAL_REFUSAL,
        anthropic_api_key="test-key",
    ))

    assert result == GOOD_MEMORIES[0]
    prompt = calls[0]["messages"][0]["content"]
    assert "MEMORY CHUNKS TO CONSOLIDATE" in prompt
    assert "I'm not going to rewrite" not in prompt


@pytest.mark.unit
def test_full_rebuild_uses_the_newest_chunks_in_order(monkeypatch):
    calls = []
    _patch_anthropic(monkeypatch, GOOD_MEMORIES[0], calls)
    from memory.summaries import SummaryManager

    mgr = SummaryManager.__new__(SummaryManager)
    # As the real getter returns them: newest first.
    chunks = [{"content": f"chunk-{i:02d}", "metadata": {"timeframe_start": f"2026-01-{i:02d}"}}
              for i in range(20, 0, -1)]
    mgr.get_summaries_for_conversation = lambda conversation_id: chunks

    asyncio.run(mgr.generate_working_summary(
        conversation_id="c1", conversation_title="Stream", anthropic_api_key="test-key",
    ))

    prompt = calls[0]["messages"][0]["content"]
    assert "chunk-01" not in prompt and "chunk-12" not in prompt
    assert prompt.index("chunk-13") < prompt.index("chunk-20")


@pytest.mark.unit
def test_semantic_memories_drop_identity_breaks():
    from continuous_context import _retrieve_semantic_memories

    class FakeMemory:
        def retrieve_relevant(self, **kwargs):
            return [
                {"content": "I'm Claude, an AI assistant made by Anthropic, and this looks like a jailbreak.",
                 "metadata": {"type": "cass_self_observation"}, "distance": 0.4},
                {"content": "Kohl and I talked about the sensor module.",
                 "metadata": {"type": "conversation"}, "distance": 0.4},
            ]

    text = _retrieve_semantic_memories(FakeMemory(), "hello")
    assert "sensor module" in text
    assert "I'm Claude" not in text
