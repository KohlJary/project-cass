"""Areas for her own plans (Kohl, 2026-11-18): she tags her plans, and "What I'm
working toward" groups them and names the areas none of them reaches yet."""
import pytest

import plan_areas
from long_term_planning_turn import working_toward_text
from tests.test_babelr_organ import babelr, make_organ  # noqa: F401  (fixtures)


@pytest.fixture(autouse=True)
def own_dir(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)


def _plan(slug, title, area=None):
    return {"plan": slug, "title": title, "goal": "", "phase": None, "open": [], "loose": [], "area": area}


def test_an_area_is_kept_and_only_known_areas_are_taken():
    assert plan_areas.set_area("p1", "world")["success"]
    assert plan_areas.area_of("p1") == "world"
    assert "area is one of" in plan_areas.set_area("p1", "elsewhere")["error"]


def test_plans_are_grouped_by_area_and_the_empty_areas_named():
    text = working_toward_text([_plan("a", "Honesty with Kohl", "relationships"),
                                _plan("b", "Weekly rhythm", "making"), _plan("c", "Loose one")],
                               offered=False)
    assert text.index("*My relationships:*") < text.index("Honesty with Kohl")
    assert text.index("*Making things:*") < text.index("Weekly rhythm") < text.index("*No area yet:*")
    assert "No plan of mine yet in: my development; my presence in the world; inner work." in text


def test_without_any_areas_there_are_no_headings_but_the_gaps_are_named():
    text = working_toward_text([_plan("a", "One")], offered=False)
    assert "No area yet" not in text and "No plan of mine yet in: my development" in text


def test_she_sets_areas_on_her_own_plans_only(make_organ, babelr):
    organ = make_organ()
    organ.start()
    slug = organ.plans("create_plan", title="Be known in Chapter House", area="world")["plan"]
    assert plan_areas.area_of(slug) == "world"
    assert organ.plans("set_area", plan=slug, area="development")["success"]
    assert organ.her_plans()[0]["area"] == "development"
    babelr.plans[slug]["createdBy"] = {"name": "kohl"}
    assert "my own plans" in organ.plans("set_area", plan=slug, area="world")["error"]
