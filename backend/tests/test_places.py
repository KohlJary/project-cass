"""places.py and recall by place (spec/house-channel-memory.md, part 1).

Cass, 2026-11-24: "the boundary should be location-based, not filing-based.
House channels are recallable in house contexts."
"""
import pytest

import places
from memory.scope import recallable_with


def test_register_and_look_up_a_place():
    places.register("babelr", "channel:general", kind="channel", visibility="house",
                    conversation_id="conv-general", label="#general")
    row = places.by_conversation("conv-general")
    assert row["platform"] == "babelr" and row["visibility"] == "house" and row["label"] == "#general"
    assert places.house_conversation_ids() == {"conv-general"}


def test_registering_again_updates_and_keeps_what_it_had():
    places.register("babelr", "channel:general", kind="channel", visibility="house",
                    conversation_id="conv-general", label="#general")
    places.register("babelr", "channel:general", kind="channel", visibility="public",
                    conversation_id=None, label=None)
    row = places.by_conversation("conv-general")
    assert row["visibility"] == "public", "visibility follows the latest registration"
    assert row["label"] == "#general", "a missing label doesn't erase the old one"
    assert places.house_conversation_ids() == set()


def test_only_house_places_are_house_conversations():
    places.register("babelr", "dm:x", kind="dm", visibility="person", conversation_id="conv-dm")
    places.register("mastodon", "thread:1", kind="thread", visibility="public", conversation_id="conv-pub")
    places.register("babelr", "channel:g", kind="channel", visibility="house", conversation_id="conv-g")
    assert places.house_conversation_ids() == {"conv-g"}
    assert [p["platform"] for p in places.all_places(visibility="public")] == ["mastodon"]


def test_unknown_visibility_or_kind_is_refused():
    with pytest.raises(ValueError):
        places.register("babelr", "c", kind="channel", visibility="secret", conversation_id="x")
    with pytest.raises(ValueError):
        places.register("babelr", "c", kind="room", visibility="house", conversation_id="x")


# -- the scope rule ------------------------------------------------------------------

OWNERS = {"conv-general": None, "conv-kohl": "kohl"}.get
HOUSE = {"conv-general"}


def ok(with_user, meta, episodic=True):
    return recallable_with(with_user, meta, set(), OWNERS, episodic=episodic, house_places=HOUSE)


def test_a_house_place_comes_up_whoever_woke_her():
    # A guest woke her: the turn was saved with nobody as owner.
    assert ok("kohl", {"conversation_id": "conv-general"})
    # Kohl woke her: saved as with Kohl, still house context with anyone in the house.
    assert ok("robokohl", {"conversation_id": "conv-general", "user_id": "kohl"})
    # Her own sessions (nobody known).
    assert ok(None, {"conversation_id": "conv-general"})


def test_places_dont_loosen_anything_else():
    assert not ok("sam", {"conversation_id": "conv-kohl"}), "Kohl's thread is still only his"
    assert not ok("kohl", {"conversation_id": "conv-elsewhere"}), "an unregistered channel stays out"
    assert not ok("kohl", {})


# -- _scoped_recall: what comes up on its own each turn -----------------------------

class FakeMemory:
    def __init__(self, found):
        self.found = found

    def retrieve_where(self, query, n, where):
        return list(self.found)


def _mem(i, conv, type_="conversation", user_id=None):
    meta = {"type": type_, "conversation_id": conv, "timestamp": f"2026-11-24T00:0{i}:00"}
    if user_id:
        meta["user_id"] = user_id
    return {"id": f"m{i}", "content": f"memory {i}", "metadata": meta, "distance": 0.1 * i}


def _recall(found, user_id, house=False):
    import continuous_context as cc
    return {m["id"] for m in cc._scoped_recall(FakeMemory(found), "crazy day", user_id, 5, house=house)}


def test_with_kohl_she_recalls_the_house_channel_a_guest_woke_her_in():
    places.register("babelr", "channel:general", kind="channel", visibility="house",
                    conversation_id="conv-general", label="#general")
    found = [_mem(1, "conv-general"), _mem(2, "conv-unknown")]
    assert _recall(found, "kohl") == {"m1"}


def test_a_housemates_dm_gets_house_channels_but_no_other_conversation():
    places.register("babelr", "channel:general", kind="channel", visibility="house",
                    conversation_id="conv-general", label="#general")
    found = [_mem(1, "conv-general"), _mem(2, "conv-kohl", user_id="kohl"),
             _mem(3, None, type_="user_observation", user_id="kohl")]
    assert _recall(found, None, house=True) == {"m1"}


def test_without_places_nothing_changes():
    found = [_mem(1, "conv-general")]
    assert _recall(found, "kohl") == set()


# -- the Babelr organ registers its places --------------------------------------------

def _organ(is_public, conversations):
    from babelr_organ.organ import BabelrOrgan
    organ = BabelrOrgan.__new__(BabelrOrgan)

    class State:
        data = {"conversations": conversations}

    organ.state = State()
    organ._server = {"id": "s", "isPublic": is_public}
    organ._channels = {"g": {"id": "g", "name": "general"}}
    from collections import deque
    organ._buffers = {}
    organ._buffer = lambda place: deque()
    return organ


def test_organ_backfills_its_conversations_as_places():
    organ = _organ(False, {"channel:g": "conv-general", "dm:d": "conv-dm"})
    organ._register_places()
    assert places.by_conversation("conv-general")["visibility"] == "house"
    assert places.by_conversation("conv-general")["label"] == "#general"
    assert places.by_conversation("conv-dm")["visibility"] == "person"


def test_a_public_servers_channels_are_public():
    organ = _organ(True, {"channel:g": "conv-general"})
    organ._register_places()
    assert places.by_conversation("conv-general")["visibility"] == "public"
