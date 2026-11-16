"""Each chat entry point names its channel, so a turn on the loop tells her
where she is and who reads it (container.py, C9). Before this, Babelr DMs and
Babelr rooms with Kohl's context were guessed as "a message through the API,
seen by just them": wrong for a DM, and wrong about privacy in a room."""
import ast
from pathlib import Path

from agent_loop.container import CHANNELS, Arrival, render
from agent_loop.conversation import CHANNEL_WORDS
from agent_loop.fold import FOLD_CHANNELS

BACKEND = Path(__file__).resolve().parents[1]


def test_a_babelr_dm_is_private_and_a_babelr_room_is_not():
    dm = render(Arrival(who="Kohl", channel="babelr_dm", message="hi"))
    room = render(Arrival(who="Kohl", channel="babelr", message="hi"))
    assert "a DM on Chapter House" in dm and "seen by just them" in dm
    assert "seen by everyone in the room" in room


def test_every_channel_has_words_for_the_seam():
    assert set(CHANNELS) <= set(CHANNEL_WORDS)


def test_babelr_dms_fold_and_public_places_do_not():
    assert "babelr_dm" in FOLD_CHANNELS
    assert not {"babelr", "discord", "home_assistant"} & FOLD_CHANNELS


def test_every_main_sdk_chat_turn_names_its_channel():
    tree = ast.parse((BACKEND / "main_sdk.py").read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "run_chat_turn"]
    assert len(calls) >= 6
    for call in calls:
        named = {k.arg: k.value for k in call.keywords}
        assert "channel" in named, f"run_chat_turn at line {call.lineno} doesn't name its channel"
        assert named["channel"].value in CHANNELS, call.lineno


def test_every_channel_is_cut_over_unless_narrowed(monkeypatch):
    import features
    from agent_loop.conversation import ALL_CHANNELS, on_the_loop
    monkeypatch.delenv("AGENT_LOOP_CHAT_CHANNELS", raising=False)
    with features.override(agent_loop_chat=True):
        assert all(on_the_loop(c) for c in ALL_CHANNELS)
        monkeypatch.setenv("AGENT_LOOP_CHAT_CHANNELS", "babelr_dm,websocket")
        assert on_the_loop("babelr_dm") and not on_the_loop("discord")
    with features.override(agent_loop_chat=False):
        monkeypatch.delenv("AGENT_LOOP_CHAT_CHANNELS")
        assert not any(on_the_loop(c) for c in ALL_CHANNELS)


def test_every_channel_the_container_knows_can_be_cut_over():
    from agent_loop.conversation import ALL_CHANNELS
    assert set(CHANNELS) == set(ALL_CHANNELS)
