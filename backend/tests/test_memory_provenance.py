"""Which model wrote what goes into her memory (memory/provenance.py, 2026-11-24)."""
import asyncio

import llm_caller
from memory import provenance as pv


class Fake:
    def __init__(self):
        self.added = []

    def add(self, ids=None, documents=None, metadatas=None):
        self.added.append(metadatas)

    def upsert(self, ids=None, documents=None, metadatas=None):
        self.added.append(metadatas)

    def count(self):
        return 7


def test_a_write_right_after_a_model_call_is_labelled():
    col = pv.LabelledCollection(Fake())
    pv.noted("ollama", "qwen3:14b", "memory.summary_chunk")
    col.add(ids=["a"], documents=["x"], metadatas=[{"type": "summary"}])
    assert col._inner.added[0] == [{"type": "summary", "written_by": "ollama:qwen3:14b",
                                    "written_by_site": "memory.summary_chunk"}]
    assert col.count() == 7, "everything else passes through"


def test_no_recent_model_call_means_no_label():
    col = pv.LabelledCollection(Fake())
    pv.noted("anthropic", "claude-haiku", "x", now=0.0)  # long ago
    col.upsert(ids=["a"], documents=["x"], metadatas=[{"type": "social"}])
    assert col._inner.added[0] == [{"type": "social"}]


def test_a_writer_that_says_who_wrote_it_is_left_alone():
    col = pv.LabelledCollection(Fake())
    pv.noted("ollama", "qwen3:14b", "x")
    col.add(ids=["a"], documents=["x"], metadatas=[{"written_by": "her own hand"}])
    assert col._inner.added[0][0]["written_by"] == "her own hand"


def test_labels_dont_cross_between_tasks():
    col = pv.LabelledCollection(Fake())

    async def one(model):
        pv.noted("ollama", model, "site")
        await asyncio.sleep(0)
        col.add(ids=[model], documents=["x"], metadatas=[{"m": model}])

    async def main():
        await asyncio.gather(asyncio.create_task(one("a")), asyncio.create_task(one("b")))
    asyncio.run(main())
    got = {m[0]["m"]: m[0]["written_by"] for m in col._inner.added}
    assert got == {"a": "ollama:a", "b": "ollama:b"}


def test_llm_caller_notes_each_answered_call():
    resp = llm_caller.LLMResponse("hi", "ollama", "qwen3:14b")
    llm_caller._record_response("memory.gist", resp, 0.0, {})
    assert pv.current()["written_by"] == "ollama:qwen3:14b"
    assert pv.current()["written_by_site"] == "memory.gist"
