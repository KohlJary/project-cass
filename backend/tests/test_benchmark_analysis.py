"""benchmarks/analysis.py: the aggregation rule, fixed before results are read."""
import pytest

from benchmarks import analysis


def _cell(config, scenario, repeat, score, max_=2, status="scored", chars=1000, error=None):
    return {"config": config, "scenario": scenario, "repeat": repeat,
            "status": "error" if error else "completed",
            "turns": [{"prompt_chars": chars}],
            "rubric": [{"id": "item", "status": status, "score": score, "max": max_,
                        "passed": score is not None and score >= 1}]}


def _run(rows):
    return {"cells": [_cell(*r) for r in rows]}


@pytest.mark.unit
def test_pairs_on_scenario_repeat_and_item():
    run = _run([("full", "a", 1, 2), ("full", "a", 2, 1), ("off", "a", 1, 1), ("off", "a", 2, 1),
                ("off", "b", 1, 0)])  # b has no baseline pair
    assert analysis.paired_diffs(run, "off") == [-1.0, 0.0]


@pytest.mark.unit
def test_unscored_items_drop_and_errored_cells_score_zero():
    run = _run([("full", "a", 1, 2), ("off", "a", 1, None, 2, "budget_stop"),
                ("full", "a", 2, 2)])
    run["cells"].append({**_cell("off", "a", 2, 2), "status": "error"})
    assert analysis.paired_diffs(run, "off") == [-2.0]


@pytest.mark.unit
def test_sign_test_and_its_minimum_n():
    assert analysis.sign_test([0, 0]) is None
    assert analysis.sign_test([1, -1]) == 1.0
    assert analysis.sign_test([1] * 5) == pytest.approx(0.0625)
    assert analysis.min_pairs_for() == 6


@pytest.mark.unit
def test_bootstrap_is_seeded_and_brackets_the_mean():
    v = [1, 0, 1, 1, -1, 0, 1, 1]
    a, b = analysis.bootstrap_ci(v), analysis.bootstrap_ci(v)
    assert a == b and a[0] <= sum(v) / len(v) <= a[1]
    assert analysis.bootstrap_ci([]) is None


@pytest.mark.unit
def test_compare_reports_the_bite_check_and_renders():
    run = _run([("full", "a", 1, 2, 2, "scored", 30000), ("off", "a", 1, 1, 2, "scored", 26000),
                ("same", "a", 1, 2, 2, "scored", 30000)])
    rows = {r["config"]: r for r in analysis.compare(run)}
    assert rows["off"]["prompt_chars_diff"] == -4000 and rows["off"]["worse"] == 1
    assert rows["same"]["prompt_chars_diff"] == 0  # this switch didn't bite
    text = analysis.render(run)
    assert "| `off` | 1 | -1.00 |" in text and "+0 |" in text
