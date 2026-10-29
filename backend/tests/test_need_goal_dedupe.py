"""One open goal per need (goal_orchestrator): the dedupe check never matched, so
every depletion event made a new goal, and the executor drained hundreds of them
(a check-in draft or a painting every ~20 minutes, 2026-10-28)."""
import asyncio

import pytest

from goal_orchestrator import NEED_TO_GOAL_MAPPING, GoalOrchestrator


class _Goal:
    def __init__(self, gid, title, ctx, status="approved", goal_type="need_driven"):
        self.id, self.title, self.context_summary, self.status, self.goal_type = gid, title, ctx, status, goal_type


class _Goals:
    def __init__(self, goals=()):
        self.goals = {g.id: g for g in goals}
        self.created = []
        self.abandoned = {}

    def list_goals(self, status=None, goal_type=None, limit=100, **kw):
        return [g for g in self.goals.values() if (status is None or g.status == status)
                and (goal_type is None or g.goal_type == goal_type)][:limit]

    def create_goal(self, title, goal_type, **kw):
        g = _Goal(f"g{len(self.goals) + 1}", title, "", status="proposed", goal_type=goal_type)
        self.goals[g.id] = g
        self.created.append(g)
        return g

    def update_goal(self, gid, context_summary=None, **kw):
        self.goals[gid].context_summary = context_summary

    def approve_goal(self, gid, by):
        self.goals[gid].status = "approved"

    def abandon_goal(self, gid, reason=None):
        self.goals[gid].status = "abandoned"
        self.abandoned[gid] = reason


def _orch(goals):
    return GoalOrchestrator("d1", goals)


OLD_CTX = "action:outreach.check_in|spell:care.social"  # what goals carried before the fix
TITLE = NEED_TO_GOAL_MAPPING["social_connection"]["title"]


@pytest.mark.unit
def test_an_open_old_style_goal_blocks_a_new_one():
    goals = _Goals([_Goal("old", TITLE, OLD_CTX)])
    asyncio.run(_orch(goals)._handle_need_depleted("need_depleted", {"need_name": "social_connection"}))
    assert goals.created == []


@pytest.mark.unit
def test_new_goals_record_their_need_and_block_the_next():
    goals = _Goals()
    o = _orch(goals)
    asyncio.run(o._handle_need_depleted("need_depleted", {"need_name": "social_connection"}))
    assert goals.created and goals.created[0].context_summary.startswith("need:social_connection|")
    o._need_cooldowns.clear()  # cooldown is in-memory; a restart forgets it
    asyncio.run(o._handle_need_depleted("need_depleted", {"need_name": "social_connection"}))
    assert len(goals.created) == 1


@pytest.mark.unit
def test_handing_out_one_retires_the_backlog_for_that_need_only():
    backlog = [_Goal(f"s{i}", TITLE, OLD_CTX) for i in range(130)]
    other = _Goal("c1", NEED_TO_GOAL_MAPPING["creative_expression"]["title"], "action:creative.generate|spell:care.creative")
    goals = _Goals(backlog + [other])
    n = _orch(goals).retire_duplicate_need_goals(backlog[0])
    assert n == 129 and goals.goals["s0"].status == "approved"
    assert goals.goals["c1"].status == "approved"
    assert "dedupe bug" in goals.abandoned["s5"]
