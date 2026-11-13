"""
Plan "Cass plans her own day", phase 2: nothing forced into her plan, her own
questions as her curiosities, art and music on her menu, and creative work
reachable under a budget.
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from scheduling import templates as T
from scheduling.decision_engine import DecisionContext, SchedulingDecisionEngine, budget_category


def test_nothing_is_added_after_she_plans(monkeypatch):
    from scheduling.autonomous_scheduler import AutonomousScheduler
    from scheduling.day_phase import DayPhase

    class Engine:
        async def plan_day(self, phases):
            return {DayPhase.MORNING: [T.WORK_TEMPLATES["painting"].instantiate()]}

    sched = AutonomousScheduler(synkratos=None, decision_engine=Engine())
    monkeypatch.setattr(sched, "state_bus", SimpleNamespace(
        read_state=lambda: SimpleNamespace(day_phase=SimpleNamespace(current_phase="morning")),
        write_delta=lambda *a, **k: None))
    plan = asyncio.run(sched.plan_day())
    assert [w.template_id for w in plan["morning"]] == ["painting"], "no news slipped in"


def test_her_curiosities_are_her_own_questions():
    asked = {}

    class Questions:
        def get_open_questions(self, **kw):
            asked.update(kw)
            return []

    engine = SchedulingDecisionEngine("d", question_manager=Questions())
    asyncio.run(engine._gather_decision_context())
    assert asked.get("article_derived") is False


def test_art_and_music_are_on_her_menu():
    for tid, action in (("painting", "creative.generate_image"), ("art_study", "artstudy.full_session"),
                        ("music", "creative.compose_music")):
        assert T.WORK_TEMPLATES[tid].action_sequence == [action]


def _engine_with_budget(per_category):
    engine = SchedulingDecisionEngine("d")
    ctx = DecisionContext(current_time=datetime(2026, 11, 13, 9))
    ctx.budget_by_category = dict(per_category)
    return engine, ctx


def test_creative_work_reaches_her_menu_under_a_budget(monkeypatch):
    # "creative" isn't a budget category; looked up as-is it found no budget
    # and creative work was filtered out every time.
    monkeypatch.setattr(T, "_music_service_up", lambda: True)
    assert budget_category("creative") == "curiosity"
    engine, ctx = _engine_with_budget({"reflection": 1.0, "research": 1.0, "growth": 1.0, "curiosity": 1.0})
    ids = {c.template_id for c in engine._get_viable_candidates(ctx)}
    assert {"painting", "art_study", "music", "creative_output", "writing_session"} <= ids


def test_music_is_named_unavailable_when_the_service_is_down(monkeypatch):
    monkeypatch.setattr(T, "_music_service_up", lambda: False)
    engine, ctx = _engine_with_budget({"reflection": 1.0, "research": 1.0, "growth": 1.0, "curiosity": 1.0})
    ids = {c.template_id for c in engine._get_viable_candidates(ctx)}
    assert "music" not in ids and engine._unavailable == ["Music"]
