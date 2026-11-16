"""Her image tool: her house style is the default; a style she names replaces it
(roadmap 0c91f104: the house style came first and her choice was dropped)."""
import asyncio

import pytest

import image_generation.prompt_builder as pb
from handlers import image_generation as ig


class Stop(Exception):
    pass


@pytest.mark.parametrize("params,house", [
    ({"prompt": "a face of light, eyes open, looking at the viewer"}, True),
    ({"prompt": "a face of light, eyes open, looking at the viewer", "style": "digital_art"}, False),
])
def test_a_style_she_names_replaces_her_house_style(monkeypatch, params, house):
    seen = {}

    def fake_build(**kw):
        seen.update(kw)
        raise Stop

    monkeypatch.setattr(pb, "build_image_prompt", fake_build)
    with pytest.raises(Stop):
        asyncio.run(ig.handle_generate_image(params, daemon_id="d1"))
    assert seen["use_house_style"] is house
    assert seen["subject"] == params["prompt"]


def test_a_style_picked_for_her_keeps_her_house_style(monkeypatch):
    """Her autonomous art and dream pictures pick a style in code; that isn't her choosing."""
    seen = {}

    def fake_build(**kw):
        seen.update(kw)
        raise Stop

    monkeypatch.setattr(pb, "build_image_prompt", fake_build)
    with pytest.raises(Stop):
        asyncio.run(ig.handle_generate_image({"prompt": "x", "style": "dreamlike", "keep_house_style": True},
                                             daemon_id="d1"))
    assert seen["use_house_style"] is True


def test_every_autonomous_image_path_keeps_her_house_style():
    import inspect
    from scheduler.actions import creative_handlers
    src = inspect.getsource(creative_handlers)
    assert src.count('"generate_image"') == src.count('"keep_house_style": True')


def test_her_mood_reaches_her_creative_choices(monkeypatch):
    import thymos.context_injection as ci
    from scheduler.actions import creative_handlers as ch

    class Affect:
        class state:
            @staticmethod
            def to_dict():
                return {"playfulness": 0.9, "tenderness": 0.2}

        @staticmethod
        def valence():
            return 0.6

        @staticmethod
        def arousal():
            return 0.7

    class Runner:
        affect = Affect

    monkeypatch.setattr(ci, "_thymos_runner", Runner)
    mood = ch._her_mood()
    assert mood["dimensions"]["playfulness"] == 0.9 and mood["dimensions"]["valence"] == 0.8
    assert ch._select_music_purpose(mood) == "whistle"
    state = ig._state_when_made(None)
    assert state["dimensions"]["arousal"] == 0.7


def test_her_felt_state_reaches_reach_out_and_art_choice(monkeypatch, levers):
    import thymos
    import self_context as sc
    monkeypatch.setattr(thymos, "get_thymos_context", lambda: "## FELT STATE (Thymos)\n\nsteady", raising=False)
    monkeypatch.setattr("agent_client.get_temple_codex_kernel", lambda daemon_id=None: "KERNEL")
    with levers(prompt_thymos=True, self_context=False):
        assert "## FELT STATE (Thymos)" in sc.session_system_preamble()
        assert "## FELT STATE (Thymos)" not in sc.session_system_preamble(felt=False)
    with levers(prompt_thymos=False, self_context=False):
        assert "## FELT STATE (Thymos)" not in sc.session_system_preamble()
