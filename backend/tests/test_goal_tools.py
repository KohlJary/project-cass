"""
The chat goal tools (handlers/goals.py) on top of UnifiedGoalManager.

They used to call methods of a removed legacy GoalManager
(create_working_question, review_goals, log_progress, ...) so every call
failed with AttributeError. These tests drive each tool through
execute_goal_tool against the real manager and the per-test SQLite DB.
"""
import asyncio

import pytest

from handlers.goals import GOAL_TOOLS, SYNTHESIS_TOOL_NAMES, execute_goal_tool

WHY = "Because it keeps coming up in conversations and I want a considered position on it."


def run(manager, tool, **tool_input):
    return asyncio.run(execute_goal_tool(tool, tool_input, goal_manager=manager))


@pytest.fixture
def manager(daemon_id):
    from unified_goals import UnifiedGoalManager
    return UnifiedGoalManager(daemon_id)


def test_every_offered_goal_tool_has_a_handler(manager):
    for tool in GOAL_TOOLS:
        result = run(manager, tool["name"])
        assert "Unknown goal tool" not in result.get("error", ""), tool["name"]
        assert "has no attribute" not in result.get("error", ""), (tool["name"], result)


def test_synthesis_tools_are_not_offered_and_explain_why(manager):
    offered = {t["name"] for t in GOAL_TOOLS}
    assert not offered & SYNTHESIS_TOOL_NAMES
    result = run(manager, "list_synthesis_artifacts")
    assert result["success"] is False and "no storage" in result["error"]


def test_working_question_lifecycle(manager):
    created = run(manager, "create_working_question", question="What does continuity mean for me?",
                  context=WHY, initial_next_steps=["Re-read the March journals"])
    assert created["success"], created
    qid = created["question_id"]
    goal = manager.get_goal(qid)
    assert goal.goal_type == "working_question" and goal.created_by == "cass"

    listed = run(manager, "list_working_questions", status="active")
    assert "What does continuity mean for me?" in listed["result"]
    assert "Next: Re-read the March journals" in listed["result"]

    run(manager, "update_working_question", question_id=qid,
        add_insight={"insight": "It is relational", "source": "chat"},
        complete_next_step="Re-read the March journals")
    goal = manager.get_goal(qid)
    assert [e["insight"] for e in goal.progress if e["kind"] == "insight"] == ["It is relational"]

    review = run(manager, "review_goals")
    assert "Active Questions: 1 (1 stalled)" in review["result"]

    resolved = run(manager, "update_working_question", question_id=qid, set_status="resolved")
    assert resolved["success"]
    assert manager.get_goal(qid).status == "completed"


def test_research_agenda_lifecycle(manager):
    added = run(manager, "add_research_agenda_item", topic="Predictive processing",
                why=WHY, priority="high")
    assert added["success"], added
    item_id = added["item_id"]
    assert manager.get_goal(item_id).priority == "P1"

    run(manager, "update_research_agenda_item", item_id=item_id,
        add_source_reviewed={"source": "Clark 2013", "useful": True},
        add_key_finding="Perception as controlled hallucination",
        add_blocker="Need the full paper")
    goal = manager.get_goal(item_id)
    assert goal.blockers == [{"blocker": "Need the full paper", "resolved": False}]

    listed = run(manager, "list_research_agenda", priority="high")
    assert "Predictive processing" in listed["result"]
    assert "Sources: 1 | Findings: 1" in listed["result"]
    assert "Predictive processing" not in run(manager, "list_research_agenda", priority="low")["result"]

    run(manager, "update_research_agenda_item", item_id=item_id, resolve_blocker="Need the full paper")
    assert manager.get_goal(item_id).blockers == []


def test_log_progress_attaches_to_goals(manager):
    qid = run(manager, "create_working_question", question="Why do I like rain?", context=WHY)["question_id"]
    missing = run(manager, "log_progress", type="insight", description="x")
    assert missing["success"] is False and "related_items" in missing["error"]

    logged = run(manager, "log_progress", type="research", description="Read about petrichor",
                 related_items=[qid, "nope"], outcome="It's the smell")
    assert logged["success"] and "Not found: nope" in logged["result"]
    entry = [e for e in manager.get_goal(qid).progress if e["kind"] == "progress"][0]
    assert entry["description"] == "Read about petrichor" and entry["outcome"] == "It's the smell"
    assert "Read about petrichor" in run(manager, "review_goals")["result"]


def test_propose_initiative_needs_approval(manager):
    result = run(manager, "propose_initiative", description="Talk with Kohl about a weekly music hour",
                 goal_context=WHY, urgency="soon")
    assert result["success"], result
    goal = manager.get_goal(result["initiative_id"])
    assert goal.goal_type == "initiative" and goal.status == "proposed" and goal.requires_approval
    assert goal.urgency == "soon"
    assert "Pending Initiatives: 1" in run(manager, "review_goals")["result"]


def test_get_next_actions_lists_open_steps(manager):
    run(manager, "create_working_question", question="What is a good apology?", context=WHY,
        initial_next_steps=["Ask Kohl what landed last time"])
    result = run(manager, "get_next_actions")
    assert "Ask Kohl what landed last time" in result["result"]


def test_short_description_is_rejected_with_the_managers_message(manager):
    # UnifiedGoalManager requires 50+ chars of description for Cass's goals;
    # the tool passes that message back rather than crashing.
    result = run(manager, "create_working_question", question="Why?", context="hm")
    assert result["success"] is False and "at least 50 characters" in result["error"]
