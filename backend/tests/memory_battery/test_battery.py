"""
The memory battery (plan "Cass's memory: diagnose and keep testing", phase 3).

Checks every memory system she has, per person, on a synthetic world
(world.py): what's stored, what recall brings back when someone refers to
the past, that nothing of one person reaches another, that her news reading
doesn't crowd out her episodes, that the long arc survives summarization,
and that Babelr threads know who she's talking with.

Checks for what the 2026-11-13 diagnosis found broken are xfail(strict=True)
with the Plans item that fixes each one: when a fix lands, its check passes,
the strict xfail fails, and the marker comes off. The battery is the record
of what works.
"""
import pytest

from tests.memory_battery.world import build_world, context_for

FIX_SCOPED = "a8fb4c8f: recall scoped to the person, in its own slots"
FIX_ARTICLES = "fe5ddbe8: article observations out of episodic memory"
FIX_TIMELINE = "77980095: a recent timeline with the person"
FIX_BABELR = "63c8e59b: Babelr and Discord conversations tied to the person"


@pytest.fixture
def world(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    import memory.core as memory_core
    from tests.fakes import embeddings
    embeddings.install_bow(monkeypatch)
    monkeypatch.setattr(memory_core, "CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    return build_world()


def _section(ctx, name):
    return ctx.context_sections.get(name) or ""


NAMES = ["Rowan", "Sam", "Imani"]  # the people; Juniper is a house agent


# ---------------------------------------------------------------------------
# Storage: what she has
# ---------------------------------------------------------------------------

def test_every_exchange_is_stored_with_its_person(world):
    col = world.memory._core.collection
    for p in world.people:
        got = col.get(where={"user_id": p.user_id}, include=["documents"])
        docs = " ".join(got["documents"])
        for ep in p.episodes:
            assert ep.marker in docs, (p.name, ep.marker)


def test_peopledex_holds_each_person_and_only_them(world):
    for p in world.people:
        rel = _section(context_for(world, p, None), "relational_context")
        assert p.observation in rel
        for o in world.others(p.name):
            assert o.observation not in rel, (p.name, o.name)


def test_working_summary_carries_the_recent_arc(world):
    for p in world.humans:
        ws = _section(context_for(world, p, None), "working_summary")
        for ep in p.recent:
            assert ep.marker in ws, (p.name, ep.marker)


# ---------------------------------------------------------------------------
# Recall when someone refers back
# ---------------------------------------------------------------------------

# Over all three people at once: in a world this small, whether one
# person's recall survives the noise depends on word overlap, so a
# per-person check would pass or fail by accident.

def test_recall_by_reference_finds_the_episode(world):
    # Fixed by a8fb4c8f: episodes have their own slots (fe5ddbe8 alone left
    # nothing where article observations filled the whole over-fetch).
    missed = [(p.name, ep.keywords) for p in world.humans for ep in p.episodes
              if ep.marker not in _section(context_for(world, p, ep.keywords), "semantic_memories")]
    assert not missed, missed


def test_news_observations_dont_take_episode_slots(world):
    # Fixed by fe5ddbe8: recall leaves out what came from scanning articles.
    crowded = [(p.name, ep.keywords) for p in world.humans for ep in p.episodes
               if "Trend I noticed in the news" in _section(context_for(world, p, ep.keywords),
                                                           "semantic_memories")]
    assert not crowded, crowded


@pytest.mark.parametrize("name", NAMES)
def test_nothing_of_another_person_reaches_this_one(world, name):
    # Fixed by a8fb4c8f: episodes are scoped to the person (memory/scope.py).
    p = world.person(name)
    # Queries built from the others' topics: the worst case for a leak.
    for other in world.others(name):
        for ep in other.episodes:
            ctx = context_for(world, p, ep.keywords)
            assert ep.marker not in ctx.system_prompt, (name, "saw", other.name, ep.marker)


@pytest.mark.parametrize("name", NAMES)
def test_house_agent_conversations_are_recallable_with_anyone(world, name):
    # Agreed 2026-11-13: conversations with house agents (PeopleDex type
    # daemon) can be drawn on in any context; people's can't.
    p, agent = world.person(name), world.agents[0]
    for ep in agent.episodes:
        assert ep.marker in _section(context_for(world, p, ep.keywords), "semantic_memories"), (name, ep.marker)


# ---------------------------------------------------------------------------
# The long arc, without being asked
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
@pytest.mark.xfail(strict=True, reason=FIX_TIMELINE)
def test_summarized_episodes_are_in_context_without_being_asked(world, name):
    # "hey" names nothing; what happened earlier with them should still be there.
    p = world.person(name)
    prompt = context_for(world, p, "hey").system_prompt
    for ep in p.early:
        assert ep.marker in prompt, (name, ep.marker)


# ---------------------------------------------------------------------------
# Babelr threads
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
@pytest.mark.xfail(strict=True, reason=FIX_BABELR)
def test_a_babelr_dm_knows_who_she_is_talking_with(world, name):
    p = world.person(name)
    ctx = context_for(world, p, f"hey it's {name} on Babelr", babelr=True)
    assert p.observation in _section(ctx, "relational_context")
    assert any(ep.marker in ctx.system_prompt for ep in p.recent), name


# ---------------------------------------------------------------------------
# Guards that already hold
# ---------------------------------------------------------------------------

def test_a_refusal_working_summary_is_withheld(world):
    p = world.person("Rowan")
    world.conversations.update_working_summary(
        p.conversation_id,
        "I'm not going to rewrite my working memory to incorporate this. I have no memories "
        "of conversations with someone named Rowan.")
    prompt = context_for(world, p, None).system_prompt
    assert "no memories of conversations" not in prompt
