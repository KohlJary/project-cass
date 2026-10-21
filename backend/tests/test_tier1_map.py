"""
The Tier 1 map (tests/smoke/tier1_map.py) must classify every lever and every
smoke test, so docs/tier1-status.md can't silently miss a subsystem. This runs
in the fast suite: it reads source files only, no app import.
"""
from scripts.tier1_status import matches, smoke_test_units, validate_map


def test_every_lever_and_smoke_test_is_mapped():
    errors = validate_map()
    assert not errors, "\n".join(errors)


def test_node_id_matching():
    entry = "tests/smoke/test_x.py::test_y"
    assert matches("tests/smoke/test_x.py::test_y", entry)
    assert matches("tests/smoke/test_x.py::test_y[case]", entry)
    assert not matches("tests/smoke/test_x.py::test_y_other", entry)
    assert matches("tests/smoke/test_x.py::TestA::test_b", "tests/smoke/test_x.py")
    assert not matches("tests/smoke/test_xy.py::test_b", "tests/smoke/test_x.py")


def test_validation_catches_a_new_lever(monkeypatch):
    import features
    monkeypatch.setitem(features.LEVERS, "brand_new", features.Lever("brand_new", "x"))
    assert any("'brand_new' has no entry" in e for e in validate_map())


def test_validation_catches_a_new_test_in_a_lever_file():
    units = smoke_test_units()
    path = "tests/smoke/test_autonomous_cycles.py"
    units[path] = units[path] + ["test_brand_new_cycle"]
    errors = validate_map(units)
    assert any(f"{path}::test_brand_new_cycle is not in" in e for e in errors), errors


def test_spine_whole_file_entries_absorb_new_tests():
    """The documented loose spot: a test added to a whole-file SPINE entry counts as spine."""
    units = smoke_test_units()
    path = "tests/smoke/test_ws_chat_turn.py"
    units[path] = units[path] + ["test_brand_new_turn"]
    assert validate_map(units) == []


def test_validation_rejects_whole_file_lever_entries(monkeypatch):
    from tests.smoke import tier1_map
    entry = {"depth": "runs", "tests": ["tests/smoke/test_autonomous_cycles.py"], "note": ""}
    monkeypatch.setitem(tier1_map.LEVER_COVERAGE, "rss", entry)
    assert any("must name a single test" in e for e in validate_map())
