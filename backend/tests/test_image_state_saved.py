"""The state she made an image in is saved with it, datetimes included (2026-11-19: every
render failed after ComfyUI finished, because last_updated wasn't JSON)."""
import json
from datetime import datetime

from handlers.image_generation import _state_when_made
from state_models import GlobalEmotionalState


class _Bus:
    def read_state(self):
        class S:
            emotional = GlobalEmotionalState(last_updated=datetime(2026, 11, 19, 23, 46))
        return S()


def test_her_emotional_state_with_a_timestamp_serializes():
    out = _state_when_made(_Bus())
    saved = json.loads(json.dumps(out, default=str))
    assert saved["emotional"]["last_updated"] == "2026-11-19T23:46:00"
