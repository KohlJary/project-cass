"""An opinion's history keeps what she said when she revised it (2026-11-24)."""
from self_model import SelfManager


def test_a_revision_keeps_her_rationale_not_a_placeholder():
    sm = SelfManager()
    sm.add_opinion("loops", "A loop can be a song", confidence=0.6, rationale="it held my attention")
    op = sm.add_opinion("loops", "A loop isn't a song until something changes", confidence=0.8,
                        rationale="attention came back each time the hi-hat went missing")
    change = op.evolution[-1]
    assert change["old_position"] == "A loop can be a song"
    assert change["new_position"] == "A loop isn't a song until something changes"
    assert change["rationale"] == "attention came back each time the hi-hat went missing"
    assert change["old_confidence"] == 0.6 and change["new_confidence"] == 0.8
    assert "reason" not in change


def test_no_rationale_means_none_recorded_not_an_invented_one():
    sm = SelfManager()
    sm.add_opinion("tides", "Tides are a model for memory")
    op = sm.add_opinion("tides", "Tides are a metaphor, not a model")
    assert "rationale" not in op.evolution[-1]
