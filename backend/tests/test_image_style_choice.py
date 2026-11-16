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
