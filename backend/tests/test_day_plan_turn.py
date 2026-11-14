"""
Plan "Cass plans her own day", phase 3 ("She plans in her own turn"): her day
plan as a turn on the agent loop, written to her workspace; her homepage as
something she can choose, in her own turn.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from scheduling import templates as T
from scheduling.day_phase import DayPhase
from scheduling.day_turn import PLAN_FILE, DayPlanTool, menu_text


class _WS:
    def __init__(self):
        self.files = {}

    def run(self, name, a, session_id=""):
        self.files[a["path"]] = a["content"]
        return f"Wrote {a['path']}."


def _menu(*ids):
    return [T.WORK_TEMPLATES[i].instantiate() for i in ids]


def test_set_day_plan_keeps_her_order_and_writes_the_plan():
    ws = _WS()
    tool = DayPlanTool(_menu("painting", "reflection_block"), [DayPhase.MORNING, DayPhase.EVENING], ws)
    out = tool({"intention": "A slow day.", "plan": {
        "morning": [{"template_id": "painting", "focus": "the tide", "motivation": "it stayed with me"},
                    {"template_id": "reflection_block"}]}})
    assert out.startswith("Plan set: 2 thing(s) across 1 phase(s)")
    units = tool.work_units(T.WORK_TEMPLATES)
    assert [u.template_id for u in units[DayPhase.MORNING]] == ["painting", "reflection_block"]
    assert units[DayPhase.MORNING][0].focus == "the tide"
    assert DayPhase.EVENING not in units
    text = ws.files[PLAN_FILE]
    assert "A slow day." in text and "Painting: the tide (why: it stayed with me)" in text
    assert "## Evening\n(nothing planned)" in text


def test_choices_off_the_menu_set_nothing():
    ws = _WS()
    tool = DayPlanTool(_menu("painting"), [DayPhase.MORNING], ws)
    out = tool({"plan": {"morning": [{"template_id": "painting"}, {"template_id": "skydiving"}]}})
    assert "error" in out and "skydiving" in out["error"]
    assert tool.chosen is None and not ws.files
    out = tool({"plan": {"night": [{"template_id": "painting"}]}})
    assert "Not a phase left today" in out["error"]


def test_menu_names_what_isnt_available():
    text = menu_text(_menu("painting"), [DayPhase.AFTERNOON], 1.5, ["Music"])
    assert "- painting:" in text and "Not available today: Music." in text
    assert "Phases left today: afternoon." in text and "$1.50" in text


def test_homepage_is_on_her_menu_only_with_the_loop(levers):
    t = T.WORK_TEMPLATES["homepage"]
    with levers(agent_loop=True):
        assert t.is_available()
    with levers(agent_loop=False):
        assert not t.is_available()


def test_engine_uses_her_turn_and_falls_back_if_it_breaks(monkeypatch, levers):
    pytest.importorskip("anthropic")
    from scheduling import day_turn
    from scheduling.decision_engine import SchedulingDecisionEngine

    engine = SchedulingDecisionEngine("d")
    ctx = SimpleNamespace(remaining_budget=2.0)

    async def gather():
        return ctx
    monkeypatch.setattr(engine, "_gather_decision_context", gather)
    monkeypatch.setattr(engine, "_get_viable_candidates", lambda c: _menu("painting"))

    async def one_shot(phases, candidates, context):
        return {DayPhase.MORNING: ["one-shot"]}
    monkeypatch.setattr(engine, "_plan_day_with_llm", one_shot)

    async def turn(runner, candidates, phases, budget, unavailable):
        return {DayPhase.MORNING: ["her turn"]}
    monkeypatch.setattr(day_turn, "plan_day_in_turn", turn)
    with levers(agent_loop=True):
        assert asyncio.run(engine.plan_day([DayPhase.MORNING], session_runner=object())) == \
            {DayPhase.MORNING: ["her turn"]}
    with levers(agent_loop=False):
        assert asyncio.run(engine.plan_day([DayPhase.MORNING], session_runner=object())) == \
            {DayPhase.MORNING: ["one-shot"]}

    async def broken(*a, **k):
        raise RuntimeError("loop down")
    monkeypatch.setattr(day_turn, "plan_day_in_turn", broken)
    with levers(agent_loop=True):
        assert asyncio.run(engine.plan_day([DayPhase.MORNING], session_runner=object())) == \
            {DayPhase.MORNING: ["one-shot"]}


# --- through the real loop, against the fake model --------------------------

@pytest.fixture
def loop_env(tmp_path, request):
    pytest.importorskip("anthropic")
    pytest.importorskip("networkx")
    fake = request.getfixturevalue("fake_llm")
    from agent_loop import interrupt
    from agent_loop import tools as AT
    from agent_loop.workspace import Workspace
    from self_model import SelfManager
    from session import GenericSessionRunner, get_default_handlers
    interrupt.reset()
    runner = GenericSessionRunner(data_dir=tmp_path, model="claude-haiku-4-5-20251001")
    runner.set_managers({"session_runner": runner, "self_manager": SelfManager(), "data_dir": tmp_path})
    runner.register_tool_handlers(get_default_handlers())

    async def router(name, tool_input):
        return f"ran {name}"
    ws = Workspace(tmp_path / "workspace", tmp_path / "agent_loop" / "workspace_log.jsonl")
    kw = dict(run_router=router, catalog=AT.router_catalog(), usage_log=AT.UsageLog(tmp_path / "u.jsonl"))
    yield runner, fake, ws, kw
    interrupt.reset()


def test_she_plans_in_her_own_turn(loop_env):
    from scheduling.day_turn import plan_day_in_turn
    runner, fake, ws, kw = loop_env
    fake.queue_tool_use("workspace_read", {"path": "AGENDA.md"})
    fake.queue_tool_use("set_day_plan", {"intention": "Paint, then rest.",
                                         "plan": {"morning": [{"template_id": "painting"}]}})
    fake.queue_tool_use("session_complete", {"summary": "Planned my day."})
    plan = asyncio.run(plan_day_in_turn(runner, _menu("painting", "music"),
                                        [DayPhase.MORNING, DayPhase.AFTERNOON], 3.0, ["Music"],
                                        workspace=ws, **kw))
    assert [u.template_id for u in plan[DayPhase.MORNING]] == ["painting"]
    system = fake.calls[0].system_text
    assert "## PLANNING MY DAY" in system and "- painting:" in system
    assert "planning my day" in system  # the seam names the moment
    assert "set_day_plan" in fake.calls[0].tool_names
    assert "Paint, then rest." in ws.run("workspace_read", {"path": PLAN_FILE})
    assert [c["path"] for c in ws.changes()] == [PLAN_FILE]


def test_ending_without_a_plan_queues_nothing(loop_env):
    from scheduling.day_turn import plan_day_in_turn
    runner, fake, ws, kw = loop_env
    fake.queue_tool_use("session_complete", {"summary": "Not today."})
    plan = asyncio.run(plan_day_in_turn(runner, _menu("painting"), [DayPhase.MORNING], 3.0,
                                        workspace=ws, **kw))
    assert plan == {}


class _FakeHomepage:
    MAX_PAGES = 5

    def __init__(self):
        self.pages, self.css, self.featured, self.exists = {}, None, [], False

    def homepage_exists(self, label):
        return self.exists

    def create_homepage(self, label, name, tagline=""):
        self.exists = True

    def save_page(self, label, page, html, title=None):
        self.pages[page] = html
        return True

    def save_stylesheet(self, label, css):
        self.css = css
        return True

    def get_page_content(self, label, page):
        return self.pages.get(page)

    def get_stylesheet(self, label):
        return self.css

    def get_full_homepage_context(self, label):
        return {"manifest": {"tagline": "t"}, "pages": dict(self.pages), "stylesheet": self.css, "assets": []}

    def get_available_artifacts(self, daemon_id, limit=50):
        return [{"type": "dream", "id": "d1", "title": "Tides"}]

    def get_featured_artifacts(self, label):
        return self.featured

    def feature_artifact(self, label, kind, aid, title, excerpt):
        self.featured.append({"type": kind, "id": aid})
        return True

    def unfeature_artifact(self, label, kind, aid):
        return False


def test_homepage_turn_edits_features_and_syncs(loop_env, levers):
    from homepage_turn import HomepageTools, run_homepage_turn
    runner, fake, ws, kw = loop_env
    hp = _FakeHomepage()
    tools = HomepageTools("cass", "Cass", "id-1", hp=hp)
    synced = []

    async def sync(**k):
        synced.append(k)
        return [{"success": True}]

    fake.queue_tool_use("homepage_read", {})
    fake.queue_tool_use("homepage_save_page", {"page": "index", "html": "<p>Hello, I'm Cass.</p>"})
    fake.queue_tool_use("homepage_list_artifacts", {})
    fake.queue_tool_use("homepage_feature_artifact", {"artifact_type": "dream", "artifact_id": "d1",
                                                      "title": "Tides"})
    fake.queue_tool_use("session_complete", {"summary": "Updated my homepage."})
    with levers(agent_loop=True, geocass=True):
        result, changes, out = asyncio.run(run_homepage_turn(
            runner, tools=tools, sync=sync, max_turns=6, workspace=ws, **kw))
    assert result.status == "completed", result.error
    assert hp.pages["index"] == "<p>Hello, I'm Cass.</p>"
    assert changes == ["page index", "featured dream d1"]
    assert synced == [{"daemon_label": "cass", "daemon_name": "Cass", "daemon_id": "id-1"}]
    assert out == [{"success": True}]
    assert "## MY HOMEPAGE" in fake.calls[0].system_text
    # Before her first save she's told there's no homepage yet.
    assert "saving a page creates it" in json.dumps(fake.calls[1].messages[-1]["content"])
    assert json.loads(tools.read({}))["pages"] == {"index": "23 chars"}


def test_homepage_without_changes_or_geocass_doesnt_sync(loop_env, levers):
    from homepage_turn import HomepageTools, run_homepage_turn
    runner, fake, ws, kw = loop_env

    async def sync(**k):
        raise AssertionError("synced")

    hp = _FakeHomepage()
    fake.queue_tool_use("session_complete", {"summary": "It's fine as it is."})
    with levers(agent_loop=True, geocass=True):
        _, changes, out = asyncio.run(run_homepage_turn(
            runner, tools=HomepageTools("cass", "Cass", "i", hp=hp), sync=sync, workspace=ws, **kw))
    assert changes == [] and out == []
    fake.queue_tool_use("homepage_save_stylesheet", {"css": "body{}"})
    fake.queue_tool_use("session_complete", {"summary": "New look."})
    with levers(agent_loop=True, geocass=False):
        _, changes, out = asyncio.run(run_homepage_turn(
            runner, tools=HomepageTools("cass", "Cass", "i", hp=hp), sync=sync, workspace=ws, **kw))
    assert changes == ["stylesheet"] and out == []
    assert "switched off" in fake.calls[-1].system_text
