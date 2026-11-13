"""memory/scope.py: whose memories she recalls with whom (agreed 2026-11-13)."""
from memory.scope import recallable_with

AGENTS = {"daedalus"}
OWNERS = {"conv-kohl": "kohl", "conv-daedalus": "daedalus", "conv-babelr": None}.get


def ok(with_user, meta, episodic=True):
    return recallable_with(with_user, meta, AGENTS, OWNERS, episodic=episodic)


def test_a_persons_conversation_only_with_them():
    assert ok("kohl", {"user_id": "kohl"})
    assert not ok("sam", {"user_id": "kohl"}), "Kohl's thread isn't pooled into anyone else's recall"
    assert not ok(None, {"user_id": "kohl"})


def test_summary_chunks_belong_to_their_conversations_person():
    assert ok("kohl", {"conversation_id": "conv-kohl"})
    assert not ok("sam", {"conversation_id": "conv-kohl"})


def test_house_agent_conversations_come_up_anywhere():
    for who in ("kohl", "sam", None):
        assert ok(who, {"user_id": "daedalus"})
        assert ok(who, {"conversation_id": "conv-daedalus"})


def test_an_episode_with_nobody_known_isnt_recalled():
    assert not ok("kohl", {"conversation_id": "conv-babelr"})
    assert not ok("kohl", {})


def test_her_own_memories_come_up_anywhere_unless_tagged_with_someone():
    assert ok("sam", {"type": "journal"}, episodic=False)
    assert not ok("sam", {"type": "user_observation", "user_id": "kohl"}, episodic=False)
    assert ok("kohl", {"type": "user_observation", "user_id": "kohl"}, episodic=False)
