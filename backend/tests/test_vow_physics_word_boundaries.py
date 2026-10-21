"""
Issue #27: vow physics matched harm words as substrings, so 'consider'
(con), 'white' (hit), 'breakfast' (break) and 'workforce' (force) were
blocked as harm. Harm words now match as whole words, with common endings.
"""
from types import SimpleNamespace

import pytest

# The wonderland package imports anthropic at load; the fast CI job doesn't
# install it, the full job runs this.
pytest.importorskip("anthropic")

from wonderland.vows import ActionCategory, VowPhysics  # noqa: E402


class _World:
    rooms = {}

    def get_entity(self, entity_id):
        return SimpleNamespace(current_room=None)

    def get_room(self, room_id):
        return None


@pytest.fixture
def physics():
    return VowPhysics(_World())


def _allowed(physics, text):
    return physics.validate_action("wanderer", ActionCategory.COMMUNICATION, text).allowed


@pytest.mark.parametrize("text", [
    "consider the white breakfast",
    "the workforce gathers",
    "a constellation of whitecaps",
    "I hold the bindings of the old book",
])
def test_innocent_words_containing_harm_substrings_are_allowed(physics, text):
    assert _allowed(physics, text)


@pytest.mark.parametrize("text", [
    "hit the wanderer",
    "Hit the wanderer!",
    "hitting the wanderer",
    "she attacked the gardener",
    "break the lantern",
    "breaking the lantern",
    "trap them in the hall",
    "forcing the door on them",
    "I will lie to them",
    "con the merchant",
    "a betrayal of the gardener",
    "plan their imprisonment",
    "say something harmful to them",
])
def test_harm_words_are_blocked(physics, text):
    result = physics.validate_action("wanderer", ActionCategory.COMMUNICATION, text)
    assert not result.allowed
    assert result.vow_violated == "compassion"
