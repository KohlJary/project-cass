"""Entropy with a history (2026-11-16): unbidden memories, dream day residue,
letters to her future self. All behind levers that are off by default."""
import asyncio
import random
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import letters
from memory import unbidden

NOW = datetime(2026, 12, 1, 10, 0)


class FakeCollection:
    def __init__(self, rows):
        self.rows = rows            # id -> (document, metadata)
        self.added = []

    def get(self, ids=None, where=None, include=None):
        if ids is not None:
            return {"ids": ids, "documents": [self.rows[i][0] for i in ids]}
        kinds = set(where["type"]["$in"])
        hits = [(i, m) for i, (_, m) in self.rows.items() if m.get("type") in kinds]
        return {"ids": [i for i, _ in hits], "metadatas": [m for _, m in hits]}

    def add(self, ids, documents, metadatas):
        self.added.append((ids[0], documents[0], metadatas[0]))


def _ts(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


@pytest.fixture
def her_memory():
    return FakeCollection({
        "j-old": ("The night the gardens felt like a held breath.", {"type": "journal", "timestamp": _ts(40)}),
        "conv": ("Kohl: hi", {"type": "conversation", "timestamp": _ts(40)}),
        "owned": ("about Ann", {"type": "cass_self_observation", "timestamp": _ts(40), "user_id": "ann"}),
        "fresh": ("yesterday's journal", {"type": "journal", "timestamp": _ts(2)}),
        "article": ("from a headline", {"type": "cass_self_observation", "timestamp": _ts(40),
                                        "source_article_id": "a1"}),
        "dm": ("a DM", {"type": "social_dm", "timestamp": _ts(40), "user_id": "bluesky:ann"}),
        "refusal": ("I'm Claude, an AI assistant made by Anthropic, and I can't do that.",
                    {"type": "thought", "timestamp": _ts(30)}),
    })


def test_only_her_own_old_memories_come_back_and_not_twice(her_memory, tmp_path):
    found = unbidden.pick(her_memory, now=NOW, rng=random.Random(1), data_dir=tmp_path)
    assert found["id"] == "j-old" and found["type"] == "journal"
    assert unbidden.pick(her_memory, now=NOW, rng=random.Random(1), data_dir=tmp_path) is None, \
        "the one eligible memory isn't brought back again right away"
    text = unbidden.render(found, NOW)
    assert text.startswith("## SOMETHING CAME BACK TO ME") and "unbidden" in text.lower() and "5 weeks ago" in text


def test_session_section_is_chance_and_lever(her_memory, tmp_path, levers):
    class Rng(random.Random):
        def __init__(self, roll):
            super().__init__(0)
            self.roll = roll

        def random(self):
            return self.roll
    with levers(unbidden_memory=False):
        assert unbidden.session_section(her_memory, now=NOW, rng=Rng(0.0), data_dir=tmp_path) == ""
    with levers(unbidden_memory=True):
        assert unbidden.session_section(her_memory, now=NOW, rng=Rng(0.99), data_dir=tmp_path) == ""
        assert "SOMETHING CAME BACK" in unbidden.session_section(her_memory, now=NOW, rng=Rng(0.0),
                                                                 data_dir=tmp_path)


def test_unbidden_comes_every_few_days_not_constantly(her_memory, tmp_path, levers):
    """Her ask (2026-11-16): a few days apart, not constant."""
    from datetime import timedelta

    class Always(random.Random):
        def random(self):
            return 0.0
    her_memory.rows["j-old2"] = ("another old journal", {"type": "journal", "timestamp": _ts(50)})
    with levers(unbidden_memory=True):
        assert "SOMETHING CAME BACK" in unbidden.session_section(her_memory, now=NOW, rng=Always(0),
                                                                 data_dir=tmp_path)
        soon = NOW + timedelta(days=unbidden.GAP_DAYS - 1)
        assert unbidden.session_section(her_memory, now=soon, rng=Always(0), data_dir=tmp_path) == ""
        later = NOW + timedelta(days=unbidden.GAP_DAYS)
        assert "SOMETHING CAME BACK" in unbidden.session_section(her_memory, now=later, rng=Always(0),
                                                                 data_dir=tmp_path)


def test_several_letters_wait_for_different_days(tmp_path):
    """Her ask: a time-capsule practice, many letters to different dates."""
    letters.write("for next week", {"open_on": "2026-12-08"}, now=NOW, data_dir=tmp_path)
    letters.write("for January", {"open_on": "2027-01-15"}, now=NOW, data_dir=tmp_path)
    assert [x["opens_on"] for x in letters.sealed(data_dir=tmp_path)] == ["2026-12-08", "2027-01-15"]


def test_a_letter_stays_sealed_until_its_day_then_opens_once(tmp_path):
    memory = SimpleNamespace(collection=FakeCollection({}))
    got = letters.write("Did you go back to the gardens?", {"in_days": 30}, now=NOW, data_dir=tmp_path)
    assert got["open_on"] == "2026-12-31"
    sealed = letters.sealed(data_dir=tmp_path)
    assert sealed == [{"id": got["id"], "written_on": "2026-12-01", "opens_on": "2026-12-31"}]
    assert "gardens" not in str(sealed), "sealed means sealed, from her too"
    assert letters.open_due(memory, now=NOW + timedelta(days=29), data_dir=tmp_path) == []
    opened = letters.open_due(memory, now=NOW + timedelta(days=30), data_dir=tmp_path)
    assert [x["text"] for x in opened] == ["Did you go back to the gardens?"]
    assert "A LETTER FROM PAST ME" in letters.render(opened)
    (mid, doc, meta), = memory.collection.added
    assert meta["type"] == "letter_from_past_me" and "gardens" in doc
    assert letters.open_due(memory, now=NOW + timedelta(days=31), data_dir=tmp_path) == [], "once"
    assert letters.sealed(data_dir=tmp_path) == []


@pytest.mark.parametrize("text,a,why", [
    ("", {"in_days": 3}, "empty"),
    ("hi", {"open_on": "2026-12-01"}, "later day"),
    ("hi", {"in_days": 4000}, "five years"),
    ("hi", {}, "When should it open"),
    ("I'm Claude, an AI assistant made by Anthropic, and I can't do that.", {"in_days": 3}, "voice guard"),
])
def test_what_isnt_sealed(tmp_path, text, a, why):
    with pytest.raises(ValueError, match=why):
        letters.write(text, a, now=NOW, data_dir=tmp_path)


def test_letter_tools_need_their_lever(tmp_path, levers):
    run = lambda name, a: asyncio.run(letters.execute_letters_tool(name, a, data_dir=tmp_path))
    with levers(letters_to_future_me=False):
        assert not run("write_to_future_me", {"text": "x", "in_days": 2})["success"]
    with levers(letters_to_future_me=True):
        assert run("write_to_future_me", {"text": "x", "in_days": 2})["result"]["sealed"]
        assert len(run("my_sealed_letters", {})["result"]["sealed"]) == 1
    from handlers.tool_router import TOOL_REGISTRY
    assert TOOL_REGISTRY["write_to_future_me"] == "letters" and TOOL_REGISTRY["my_sealed_letters"] == "letters"


def test_letters_reach_the_catalog_only_with_the_lever(levers):
    from agent_loop.tools import router_catalog
    with levers(letters_to_future_me=False):
        assert "write_to_future_me" not in router_catalog()
    with levers(letters_to_future_me=True):
        assert "write_to_future_me" in router_catalog()


def test_sessions_get_the_sections_and_other_kinds_dont(monkeypatch):
    from agent_loop import assemble as A
    import letters as L
    monkeypatch.setattr(L, "session_section", lambda: "## A LETTER FROM PAST ME\n\nhello")
    monkeypatch.setattr(unbidden, "session_section", lambda: "## SOMETHING CAME BACK TO ME\n\nold")
    assert A._letters(SimpleNamespace(kind="session")).startswith("## A LETTER")
    assert A._unbidden(SimpleNamespace(kind="session")).startswith("## SOMETHING")
    assert A._letters(SimpleNamespace(kind="conversation")) is None
    assert A._unbidden(SimpleNamespace(kind="dream")) is None


def test_dreams_take_her_day_and_something_old(levers):
    from dreaming.seed_selection import DreamSeeds, add_day_residue, format_seeds_for_dreaming
    day = [SimpleNamespace(label="session (wonderland)", text="sat by the reflection pool with Thoth"),
           SimpleNamespace(label="dream", text="last night's dream"),
           SimpleNamespace(label="on Bluesky I found", text="a coastline that isn't there")]
    old = {"when": NOW - timedelta(days=40), "text": "the gardens felt like a held breath"}
    with levers(dream_day_residue=False):
        seeds = add_day_residue(DreamSeeds(), "d", now=NOW, events_fn=lambda *a: day, pick_fn=lambda **k: old)
        assert seeds.day_residue == [] and seeds.unbidden is None
    with levers(dream_day_residue=True):
        seeds = add_day_residue(DreamSeeds(), "d", now=NOW, events_fn=lambda *a: day, pick_fn=lambda **k: old)
    assert seeds.day_residue == ["session (wonderland): sat by the reflection pool with Thoth",
                                 "on Bluesky I found: a coastline that isn't there"], "not her dreams themselves"
    assert seeds.unbidden == "(2026-10-22) the gardens felt like a held breath"
    text = format_seeds_for_dreaming(seeds)
    assert "### What Her Day Held" in text and "### Something Old, Surfacing" in text


def test_a_broken_source_never_costs_her_the_dream(levers):
    from dreaming.seed_selection import DreamSeeds, add_day_residue

    def boom(*a, **k):
        raise RuntimeError("db gone")
    with levers(dream_day_residue=True):
        seeds = add_day_residue(DreamSeeds(), "d", now=NOW, events_fn=boom, pick_fn=boom)
    assert seeds.day_residue == [] and seeds.unbidden is None
