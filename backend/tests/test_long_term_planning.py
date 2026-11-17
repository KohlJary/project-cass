"""Her long-term planning, and her plans opening her day plan (Kohl, 2026-11-16)."""
import asyncio
from datetime import datetime
from types import SimpleNamespace

import long_term_planning_turn as L

NOW = datetime(2026, 12, 1, 9, 0)
PLAN = {"plan": "tides-x1", "title": "Learn the tide tables", "goal": "read the sea",
        "phase": {"number": 1, "of": 2, "title": "Basics", "status": "draft"},
        "open": [{"kind": "research", "title": "Read about neap tides"}],
        "loose": [{"kind": "ask", "title": "Ask for a tide API"}]}


def test_her_plans_are_listed_with_where_each_stands():
    text = L.working_toward_text([PLAN], last_planned="2026-11-29T10:00:00", now=NOW)
    assert text.startswith("## WHAT I'M WORKING TOWARD")
    assert "**Learn the tide tables**: read the sea" in text and "Phase 1 of 2: Basics" in text
    assert "(research) Read about neap tides" in text and "(ask) Ask for a tide API" in text
    assert "days ago" not in text, "no nudge two days after the last one"


def test_a_week_without_one_is_named_and_left_to_her():
    assert "8 days ago" in L.working_toward_text([PLAN], last_planned="2026-11-23T10:00:00", now=NOW)
    text = L.working_toward_text([], last_planned=None, now=NOW)
    assert "haven't had a long-term planning session yet" in text and "long_term_planning" in text
    assert "don't have any plans of my own yet" in text
    assert L.working_toward_text([], last_planned=None, offered=False, now=NOW) == "", \
        "nothing to say when it isn't on her menu and she has no plans"


def test_long_plans_are_cut_with_a_count():
    many = dict(PLAN, open=[{"kind": "research", "title": f"t{i}"} for i in range(8)], loose=[])
    text = L.working_toward_text([many], last_planned="2026-11-30", now=NOW)
    assert "t4" in text and "t5" not in text and "and 3 more" in text


def test_unreadable_plans_are_said_not_hidden(monkeypatch):
    def boom():
        raise RuntimeError("babelr down")
    monkeypatch.setattr(L, "_her_plans", boom)
    assert "couldn't read my plans" in L.working_toward_text(last_planned="2026-11-30", now=NOW)


def test_day_plan_section_reads_the_menu(monkeypatch):
    monkeypatch.setattr(L, "_her_plans", lambda: [])
    menu = [SimpleNamespace(template_id="long_term_planning", last_done="2026-11-20T10:00:00")]
    assert "11 days ago" in L.day_plan_section(menu, now=NOW)
    assert L.day_plan_section([SimpleNamespace(template_id="painting", last_done=None)], now=NOW) == ""


def test_the_day_plan_opens_with_her_plans(monkeypatch):
    from scheduling import day_turn
    import agent_loop.session as S
    seen = {}

    async def turn(runner, **kw):
        seen.update(kw)
        return SimpleNamespace(status="completed")
    monkeypatch.setattr(S, "run_session_turn", turn)
    monkeypatch.setattr(L, "_her_plans", lambda: [PLAN])
    menu = [SimpleNamespace(template_id="long_term_planning", description="d", last_done=None,
                            estimated_duration_minutes=30, estimated_cost_usd=0.2)]
    asyncio.run(day_turn.plan_day_in_turn(object(), menu, [], 3.0, workspace=object()))
    assert seen["additions"].startswith("## WHAT I'M WORKING TOWARD")
    assert "## PLANNING MY DAY" in seen["additions"]

    def broken(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(L, "day_plan_section", broken)
    asyncio.run(day_turn.plan_day_in_turn(object(), menu, [], 3.0, workspace=object()))
    assert seen["additions"].startswith("## PLANNING MY DAY"), "a broken section never costs her the plan"


def test_wired_as_a_loop_session_with_her_plans_tool():
    from agent_loop.spec import ACTIVITY_PACKS, ACTIVITY_WORDS, ROUTER_PACKS, session_spec
    from handlers.tool_router import TOOL_REGISTRY
    from scheduling.templates import WORK_TEMPLATES
    from scheduler.actions import session_handlers
    assert "plans" in ACTIVITY_PACKS["long_term_planning"] and "plans" in ROUTER_PACKS
    assert "long_term_planning" in ACTIVITY_WORDS
    assert "babelr_plans" in session_spec("long_term_planning").tool_names()
    assert TOOL_REGISTRY["babelr_plans"] == "babelr"
    assert WORK_TEMPLATES["long_term_planning"].action_sequence == ["session.long_term_planning"]
    assert callable(session_handlers.long_term_planning_action)


def test_the_session_hands_her_plans_to_the_turn(monkeypatch):
    import agent_loop.session as S
    seen = {}

    async def turn(runner, **kw):
        seen.update(kw)
        return SimpleNamespace(status="completed")
    monkeypatch.setattr(S, "run_session_turn", turn)
    monkeypatch.setattr(L, "_her_plans", lambda: [PLAN])
    asyncio.run(L.run_long_term_planning_turn(object()))
    assert seen["session_type"] == "long_term_planning"
    assert "## LOOKING FURTHER AHEAD" in seen["additions"] and "Learn the tide tables" in seen["additions"]
    assert "WHAT I'M WORKING TOWARD" not in seen["additions"]
    assert "don't wait on anyone's yes" in seen["additions"]
