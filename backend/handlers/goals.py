"""
Goal Generation and Tracking Tool Handler

Enables Cass to set her own objectives, track progress toward them,
and synthesize positions that persist and evolve across sessions.
"""
from typing import Dict, List, Optional


# The chat goal tools were written against a legacy GoalManager (JSON files:
# working questions, research agenda, synthesis artifacts, a progress log).
# That manager is gone; the live store is UnifiedGoalManager (SQLite
# `unified_goals`), which already has goal types for working questions,
# research agenda items and initiatives. These handlers map each tool onto
# that store instead of calling methods that no longer exist.
#
# Mapping:
#   working question   -> Goal(goal_type="working_question", title=question)
#   research agenda    -> Goal(goal_type="research_agenda", title=topic)
#   initiative         -> Goal(goal_type="initiative")   (needs Kohl's approval)
#   insight / next step / source / finding -> entries in Goal.progress
#   agenda blockers    -> Goal.blockers
# Synthesis artifacts have no equivalent store, so those tools are not offered
# (see SYNTHESIS_ARTIFACT_TOOLS below).

WORKING_QUESTION = "working_question"
RESEARCH_AGENDA = "research_agenda"
INITIATIVE = "initiative"

SYNTHESIS_TOOL_NAMES = {
    "create_synthesis_artifact", "update_synthesis_artifact",
    "get_synthesis_artifact", "list_synthesis_artifacts",
}

PRIORITY_TO_P = {"high": "P1", "medium": "P2", "low": "P3"}
P_TO_PRIORITY = {"P0": "high", "P1": "high", "P2": "medium", "P3": "low"}

# Status words the tools accept, mapped to UnifiedGoalManager statuses.
# "open" statuses are the ones a filter like status="active" should match.
OPEN_STATUSES = ("proposed", "approved", "active")
STATUS_FILTERS = {
    "active": OPEN_STATUSES,
    "not_started": ("proposed", "approved"),
    "in_progress": ("active",),
    "blocked": ("blocked",),
    "resolved": ("completed",),
    "complete": ("completed",),
    "completed": ("completed",),
    "abandoned": ("abandoned",),
}

# UnifiedGoalManager requires every top-level goal Cass creates to carry at
# least 2 completion criteria. These tools never asked for any, so when the
# model doesn't pass them we use criteria that describe the tool's own
# lifecycle (how the item gets closed), not anything about its content.
DEFAULT_CRITERIA = {
    WORKING_QUESTION: [
        "An answer or position is recorded as an insight on this question",
        "Question marked resolved with update_working_question",
    ],
    RESEARCH_AGENDA: [
        "Key findings for this topic are recorded",
        "Item marked complete with update_research_agenda_item",
    ],
    INITIATIVE: [
        "Kohl has seen and responded to the initiative",
        "The requested conversation, resource or action has happened or been declined",
    ],
}


async def execute_goal_tool(
    tool_name: str,
    tool_input: Dict,
    goal_manager,  # UnifiedGoalManager instance
) -> Dict:
    """
    Execute a goal management tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        goal_manager: UnifiedGoalManager instance

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    if goal_manager is None:
        return {"success": False, "error": "Goal manager not available"}

    handlers = {
        "create_working_question": _create_working_question,
        "update_working_question": _update_working_question,
        "list_working_questions": _list_working_questions,
        "add_research_agenda_item": _add_research_agenda_item,
        "update_research_agenda_item": _update_research_agenda_item,
        "list_research_agenda": _list_research_agenda,
        "log_progress": _log_progress,
        "review_goals": _review_goals,
        "get_next_actions": _get_next_actions,
        "propose_initiative": _propose_initiative,
    }

    if tool_name in SYNTHESIS_TOOL_NAMES:
        return {
            "success": False,
            "error": (
                f"{tool_name} is not available: synthesis artifacts have no storage "
                "in the current goal system. Use a wiki page or research note instead."
            ),
        }

    handler = handlers.get(tool_name)
    if not handler:
        return {"success": False, "error": f"Unknown goal tool: {tool_name}"}

    try:
        return await handler(tool_input, goal_manager)
    except ValueError as e:
        # UnifiedGoalManager's validation messages are written for the model.
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== Helpers ====================

def _str(tool_input: Dict, key: str) -> str:
    return (tool_input.get(key) or "").strip()


def _get_typed_goal(goal_manager, goal_id: str, goal_type: str):
    goal = goal_manager.get_goal(goal_id) if goal_id else None
    if goal is None or goal.goal_type != goal_type:
        return None
    return goal


def _list_typed(goal_manager, goal_type: str, status: Optional[str] = None) -> List:
    goals = goal_manager.list_goals(goal_type=goal_type)
    if status:
        wanted = STATUS_FILTERS.get(status, (status,))
        goals = [g for g in goals if g.status in wanted]
    return goals


def _entries(goal, kind: str) -> List[Dict]:
    return [e for e in goal.progress if e.get("kind") == kind]


def _open_next_steps(goal) -> List[str]:
    """Next steps added minus those completed, in the order they were added."""
    done = {e.get("step") for e in _entries(goal, "next_step_done")}
    steps = []
    for e in _entries(goal, "next_step"):
        step = e.get("step")
        if step and step not in done and step not in steps:
            steps.append(step)
    return steps


def _apply_status(goal_manager, goal, status: str):
    """Move a goal to one of the tool status words. Returns (goal, note)."""
    if status in ("active", "in_progress"):
        if goal.status == "blocked":
            return goal_manager.unblock_goal(goal.id), None
        started = goal_manager.start_goal(goal.id)
        if started is None:
            # High-autonomy goal types need Kohl's approval before they can start.
            return goal_manager.get_goal(goal.id), "still awaiting approval, so it stays proposed"
        return started, None
    if status in ("resolved", "complete", "completed"):
        return goal_manager.complete_goal(goal.id), None
    if status == "abandoned":
        return goal_manager.abandon_goal(goal.id), None
    if status == "blocked":
        blockers = goal.blockers or [{"blocker": "marked blocked", "resolved": False}]
        return goal_manager.block_goal(goal.id, blockers), None
    if status == "not_started":
        return goal, None
    raise ValueError(f"Unsupported status: {status}")


def _create_typed_goal(goal_manager, goal_type: str, title: str, why: str,
                       tool_input: Dict, **kwargs):
    criteria = tool_input.get("completion_criteria") or DEFAULT_CRITERIA[goal_type]
    description = f"{title}\n\nWhy: {why}" if why else title
    return goal_manager.create_goal(
        title=title,
        goal_type=goal_type,
        created_by="cass",
        description=description,
        completion_criteria=criteria,
        **kwargs,
    )


# ==================== Working Questions ====================

async def _create_working_question(tool_input: Dict, goal_manager) -> Dict:
    """Create a new working question."""
    question = _str(tool_input, "question")
    context = _str(tool_input, "context")
    initial_next_steps = tool_input.get("initial_next_steps") or []

    if not question:
        return {"success": False, "error": "question is required"}

    goal = _create_typed_goal(goal_manager, WORKING_QUESTION, question, context, tool_input)
    for step in initial_next_steps:
        goal = goal_manager.add_progress(goal.id, {"kind": "next_step", "step": step})

    output_lines = [
        "## Working Question Created\n",
        f"**Question:** {question}\n",
        f"**Context:** {context}\n",
        f"**ID:** `{goal.id}`\n",
        f"**Status:** {goal.status}\n",
    ]

    if initial_next_steps:
        output_lines.append("**Initial Next Steps:**")
        for step in initial_next_steps:
            output_lines.append(f"- {step}")

    output_lines.append("\n*This question is now tracked in your goals.*")

    return {
        "success": True,
        "result": "\n".join(output_lines),
        "question_id": goal.id
    }


async def _update_working_question(tool_input: Dict, goal_manager) -> Dict:
    """Update a working question."""
    question_id = _str(tool_input, "question_id")

    if not question_id:
        return {"success": False, "error": "question_id is required"}

    goal = _get_typed_goal(goal_manager, question_id, WORKING_QUESTION)
    if not goal:
        return {"success": False, "error": f"Question not found: {question_id}"}

    updates = []
    insight = tool_input.get("add_insight")
    if insight:
        if isinstance(insight, str):
            insight = {"insight": insight}
        goal = goal_manager.add_progress(goal.id, {"kind": "insight", **insight})
        updates.append("Added insight")
    if tool_input.get("add_next_step"):
        goal = goal_manager.add_progress(goal.id, {"kind": "next_step", "step": tool_input["add_next_step"]})
        updates.append(f"Added next step: {tool_input['add_next_step']}")
    if tool_input.get("complete_next_step"):
        goal = goal_manager.add_progress(goal.id, {"kind": "next_step_done", "step": tool_input["complete_next_step"]})
        updates.append(f"Completed step: {tool_input['complete_next_step']}")
    if tool_input.get("set_status"):
        goal, note = _apply_status(goal_manager, goal, tool_input["set_status"])
        updates.append(f"Status: {goal.status}" + (f" ({note})" if note else ""))

    return {
        "success": True,
        "result": f"## Question Updated\n\n**ID:** `{question_id}`\n\n**Updates:**\n" +
                  "\n".join(f"- {u}" for u in updates) +
                  f"\n\n**Current Next Steps:** {len(_open_next_steps(goal))} remaining"
    }


async def _list_working_questions(tool_input: Dict, goal_manager) -> Dict:
    """List working questions."""
    questions = _list_typed(goal_manager, WORKING_QUESTION, tool_input.get("status"))

    if not questions:
        return {
            "success": True,
            "result": "No working questions found. Use `create_working_question` to start exploring a new intellectual thread."
        }

    lines = ["## Working Questions\n"]

    by_status: Dict[str, List] = {}
    for q in questions:
        by_status.setdefault(q.status, []).append(q)

    for s, group in by_status.items():
        lines.append(f"### {s.title()}\n")
        for q in group:
            steps = _open_next_steps(q)
            lines.append(f"**{q.title}**")
            lines.append(f"- ID: `{q.id}`")
            lines.append(f"- Insights: {len(_entries(q, 'insight'))} | Next Steps: {len(steps)}")
            if steps:
                lines.append(f"- Next: {steps[0]}")
            lines.append("")

    return {"success": True, "result": "\n".join(lines)}


# ==================== Research Agenda ====================

async def _add_research_agenda_item(tool_input: Dict, goal_manager) -> Dict:
    """Add a research agenda item."""
    topic = _str(tool_input, "topic")
    why = _str(tool_input, "why")
    priority = tool_input.get("priority", "medium")

    if not topic:
        return {"success": False, "error": "topic is required"}
    if not why:
        return {"success": False, "error": "why is required - explain why this research matters"}

    goal = _create_typed_goal(
        goal_manager, RESEARCH_AGENDA, topic, why, tool_input,
        priority=PRIORITY_TO_P.get(priority, "P2"),
    )
    for related in tool_input.get("related_questions") or []:
        goal_manager.add_goal_link(goal.id, related, "relates_to")

    return {
        "success": True,
        "result": f"## Research Agenda Item Added\n\n"
                  f"**Topic:** {topic}\n\n"
                  f"**Why:** {why}\n\n"
                  f"**Priority:** {priority}\n"
                  f"**ID:** `{goal.id}`\n\n"
                  f"*This is now on your research agenda. Use `update_research_agenda_item` to track progress.*",
        "item_id": goal.id
    }


async def _update_research_agenda_item(tool_input: Dict, goal_manager) -> Dict:
    """Update a research agenda item."""
    item_id = _str(tool_input, "item_id")

    if not item_id:
        return {"success": False, "error": "item_id is required"}

    goal = _get_typed_goal(goal_manager, item_id, RESEARCH_AGENDA)
    if not goal:
        return {"success": False, "error": f"Research item not found: {item_id}"}

    updates = []
    source = tool_input.get("add_source_reviewed")
    if source:
        if isinstance(source, str):
            source = {"source": source}
        goal = goal_manager.add_progress(goal.id, {"kind": "source_reviewed", **source})
        updates.append(f"Reviewed source: {source.get('source', 'unknown')}")
    if tool_input.get("add_key_finding"):
        goal = goal_manager.add_progress(goal.id, {"kind": "key_finding", "finding": tool_input["add_key_finding"]})
        updates.append("Key finding added")
    if tool_input.get("add_blocker"):
        blockers = goal.blockers + [{"blocker": tool_input["add_blocker"], "resolved": False}]
        goal = goal_manager.update_goal(goal.id, blockers=blockers)
        updates.append(f"Blocker noted: {tool_input['add_blocker']}")
    if tool_input.get("resolve_blocker"):
        # Resolved blockers are removed: UnifiedGoalManager treats any
        # remaining blocker entry as "blocked".
        blockers = [b for b in goal.blockers if b.get("blocker") != tool_input["resolve_blocker"]]
        goal = goal_manager.update_goal(goal.id, blockers=blockers)
        updates.append("Blocker resolved")
    if tool_input.get("set_priority"):
        goal = goal_manager.update_goal(goal.id, priority=PRIORITY_TO_P.get(tool_input["set_priority"], "P2"))
        updates.append(f"Priority: {tool_input['set_priority']}")
    if tool_input.get("set_status"):
        goal, note = _apply_status(goal_manager, goal, tool_input["set_status"])
        updates.append(f"Status: {goal.status}" + (f" ({note})" if note else ""))

    return {
        "success": True,
        "result": f"## Research Item Updated\n\n"
                  f"**Topic:** {goal.title}\n"
                  f"**Status:** {goal.status}\n\n"
                  f"**Updates:**\n" + "\n".join(f"- {u}" for u in updates) +
                  f"\n\n**Progress:** {len(_entries(goal, 'source_reviewed'))} sources, "
                  f"{len(_entries(goal, 'key_finding'))} findings"
    }


async def _list_research_agenda(tool_input: Dict, goal_manager) -> Dict:
    """List research agenda."""
    items = _list_typed(goal_manager, RESEARCH_AGENDA, tool_input.get("status"))
    priority = tool_input.get("priority")
    if priority:
        items = [i for i in items if P_TO_PRIORITY.get(i.priority) == priority]

    if not items:
        return {
            "success": True,
            "result": "No research agenda items found. Use `add_research_agenda_item` to add topics you need to explore."
        }

    lines = ["## Research Agenda\n"]

    by_priority = {"high": [], "medium": [], "low": []}
    for item in items:
        by_priority[P_TO_PRIORITY.get(item.priority, "medium")].append(item)

    for p in ["high", "medium", "low"]:
        if by_priority[p]:
            lines.append(f"### {p.title()} Priority\n")
            for item in by_priority[p]:
                why = (item.description or "").split("Why: ", 1)[-1]
                lines.append(f"**{item.title}**")
                lines.append(f"- ID: `{item.id}` | Status: {item.status}")
                lines.append(f"- Why: {why[:100]}")
                lines.append(f"- Sources: {len(_entries(item, 'source_reviewed'))} | "
                             f"Findings: {len(_entries(item, 'key_finding'))}")
                lines.append("")

    return {"success": True, "result": "\n".join(lines)}


# ==================== Progress & Review ====================

async def _log_progress(tool_input: Dict, goal_manager) -> Dict:
    """Log a progress entry on one or more goals."""
    entry_type = tool_input.get("type", "insight")
    description = _str(tool_input, "description")
    related_items = tool_input.get("related_items") or []
    outcome = tool_input.get("outcome")

    if not description:
        return {"success": False, "error": "description is required"}
    # The legacy tool wrote to a global progress log; UnifiedGoalManager keeps
    # progress per goal, so the entry needs at least one goal to attach to.
    if not related_items:
        return {"success": False, "error": "related_items is required: the IDs of the goals/questions/agenda items this progress belongs to"}

    valid_types = ["research", "synthesis", "conversation", "insight", "blocker"]
    if entry_type not in valid_types:
        entry_type = "insight"

    entry = {"kind": "progress", "type": entry_type, "description": description}
    if outcome:
        entry["outcome"] = outcome

    logged, missing = [], []
    for goal_id in related_items:
        (logged if goal_manager.add_progress(goal_id, entry) else missing).append(goal_id)

    if not logged:
        return {"success": False, "error": f"No goals found for: {', '.join(missing)}"}

    return {
        "success": True,
        "result": f"## Progress Logged\n\n"
                  f"**Type:** {entry_type}\n"
                  f"**Description:** {description}\n"
                  + (f"**Outcome:** {outcome}\n" if outcome else "") +
                  f"\n*Logged on: {', '.join(f'`{g}`' for g in logged)}*"
                  + (f"\n*Not found: {', '.join(missing)}*" if missing else "")
    }


async def _review_goals(tool_input: Dict, goal_manager) -> Dict:
    """Review current goal state."""
    include_progress = tool_input.get("include_progress", True)

    questions = _list_typed(goal_manager, WORKING_QUESTION, "active")
    research = goal_manager.list_goals(goal_type=RESEARCH_AGENDA)
    initiatives = _list_typed(goal_manager, INITIATIVE, "not_started")

    stalled = [q for q in questions if not _open_next_steps(q)]
    in_progress = [r for r in research if r.status == "active"]
    blocked = [r for r in research if r.is_blocked() and r.status not in ("completed", "abandoned")]
    stats = goal_manager.get_stats()

    lines = [
        "## Goal Review\n",
        "### Summary",
        f"- Active Questions: {len(questions)} ({len(stalled)} stalled)",
        f"- Research In Progress: {len(in_progress)} ({len(blocked)} blocked)",
        f"- Pending Initiatives: {len(initiatives)}",
        f"- All goals: {stats.get('total', 0)} ({stats.get('by_status', {}).get('proposed', 0)} awaiting approval)",
        ""
    ]

    if stalled:
        lines.append("### Stalled Questions (no next steps)")
        for q in stalled:
            lines.append(f"- {q.title} (`{q.id}`)")
        lines.append("")

    if blocked:
        lines.append("### Blocked Research")
        for item in blocked:
            first = item.blockers[0].get("blocker") if item.blockers else item.status
            lines.append(f"- {item.title}: {first}")
        lines.append("")

    if initiatives:
        lines.append("### Pending Initiatives")
        for init in initiatives:
            lines.append(f"- [{init.urgency}] {init.title} (`{init.id}`)")
        lines.append("")

    if include_progress:
        recent = []
        for g in questions + research + initiatives:
            for e in g.progress:
                if e.get("kind") == "progress":
                    recent.append((e.get("timestamp", ""), e, g))
        recent.sort(key=lambda r: r[0])
        if recent:
            lines.append("### Recent Progress")
            for _, e, g in recent[-5:]:
                lines.append(f"- [{e.get('type')}] {e.get('description')} ({g.title})")

    return {"success": True, "result": "\n".join(lines)}


async def _get_next_actions(tool_input: Dict, goal_manager) -> Dict:
    """Get prioritized next actions."""
    actions = []
    for q in _list_typed(goal_manager, WORKING_QUESTION, "active"):
        for step in _open_next_steps(q):
            actions.append({"priority": P_TO_PRIORITY.get(q.priority, "medium"),
                            "action": step, "context": q.title, "type": "working_question"})
    seen = set()
    for g in goal_manager.get_actionable_goals(limit=10):
        seen.add(g.id)
        actions.append({"priority": P_TO_PRIORITY.get(g.priority, "medium"),
                        "action": g.title, "context": g.description or "", "type": g.goal_type})

    if not actions:
        return {
            "success": True,
            "result": "No pending actions. All goals are either complete or need new next steps defined."
        }

    order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda a: order.get(a["priority"], 1))

    lines = ["## Next Actions\n"]
    for i, action in enumerate(actions[:10], 1):
        lines.append(f"{i}. [{action['priority']}] **{action['action']}**")
        lines.append(f"   Context: {action['context'][:80]}")
        lines.append(f"   Type: {action['type']}")
        lines.append("")

    return {"success": True, "result": "\n".join(lines)}


async def _propose_initiative(tool_input: Dict, goal_manager) -> Dict:
    """Propose an initiative (an initiative goal, which needs Kohl's approval)."""
    description = _str(tool_input, "description")
    goal_context = _str(tool_input, "goal_context")
    urgency = tool_input.get("urgency", "when_convenient")
    if urgency not in ("when_convenient", "soon", "blocking"):
        urgency = "when_convenient"

    if not description:
        return {"success": False, "error": "description is required"}

    title = description if len(description) <= 80 else description[:77] + "..."
    goal = goal_manager.create_goal(
        title=title,
        goal_type=INITIATIVE,
        created_by="cass",
        description=f"{description}\n\nGoal context: {goal_context}" if goal_context else description,
        urgency=urgency,
        completion_criteria=tool_input.get("completion_criteria") or DEFAULT_CRITERIA[INITIATIVE],
    )

    urgency_text = {
        "when_convenient": "when convenient",
        "soon": "soon",
        "blocking": "blocking (this is preventing progress)"
    }.get(urgency, urgency)

    return {
        "success": True,
        "result": f"## Initiative Proposed\n\n"
                  f"**Request:** {description}\n\n"
                  f"**Context:** {goal_context}\n\n"
                  f"**Urgency:** {urgency_text}\n\n"
                  f"*This has been surfaced for Kohl's attention (status: {goal.status}). ID: `{goal.id}`*",
        "initiative_id": goal.id
    }


# Tool definitions for agent_client.py
GOAL_TOOLS = [
    # Working Questions
    {
        "name": "create_working_question",
        "description": "Create a new working question - an active intellectual thread to explore. Use this when you notice recurring confusion, genuine curiosity, or something worth investigating across sessions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to explore - should capture genuine uncertainty or curiosity"
                },
                "context": {
                    "type": "string",
                    "description": "Why this emerged - what prompted this question"
                },
                "initial_next_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Initial actions to consider for exploring this question"
                }
            },
            "required": ["question", "context"]
        }
    },
    {
        "name": "update_working_question",
        "description": "Update a working question with new insights, next steps, or status changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question_id": {
                    "type": "string",
                    "description": "ID of the question to update"
                },
                "add_insight": {
                    "type": "object",
                    "properties": {
                        "insight": {"type": "string"},
                        "source": {"type": "string"}
                    },
                    "description": "A new insight to add"
                },
                "add_next_step": {
                    "type": "string",
                    "description": "A new next step to add"
                },
                "complete_next_step": {
                    "type": "string",
                    "description": "A next step to mark as complete (removes from list)"
                },
                "set_status": {
                    "type": "string",
                    "enum": ["active", "paused", "resolved"],
                    "description": "Change the question's status"
                }
            },
            "required": ["question_id"]
        }
    },
    {
        "name": "list_working_questions",
        "description": "List your working questions - active intellectual threads you're exploring.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "paused", "resolved"],
                    "description": "Filter by status"
                }
            },
            "required": []
        }
    },
    # Research Agenda
    {
        "name": "add_research_agenda_item",
        "description": "Add a topic to your research agenda - something you've decided you need to learn about to advance your goals.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic to research"
                },
                "why": {
                    "type": "string",
                    "description": "Why this research matters - what goal does it serve"
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Research priority"
                },
                "related_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of related working questions"
                }
            },
            "required": ["topic", "why"]
        }
    },
    {
        "name": "update_research_agenda_item",
        "description": "Update a research agenda item with progress - sources reviewed, findings, blockers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "ID of the research item"
                },
                "add_source_reviewed": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "summary": {"type": "string"},
                        "useful": {"type": "boolean"}
                    },
                    "description": "A source you've reviewed"
                },
                "add_key_finding": {
                    "type": "string",
                    "description": "A key finding from your research"
                },
                "add_blocker": {
                    "type": "string",
                    "description": "Something blocking progress"
                },
                "resolve_blocker": {
                    "type": "string",
                    "description": "A blocker that's been resolved"
                },
                "set_status": {
                    "type": "string",
                    "enum": ["not_started", "in_progress", "blocked", "complete"],
                    "description": "Update status"
                }
            },
            "required": ["item_id"]
        }
    },
    {
        "name": "list_research_agenda",
        "description": "List your research agenda - topics you're learning about.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["not_started", "in_progress", "blocked", "complete"]
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"]
                }
            },
            "required": []
        }
    },
    # Progress & Review
    {
        "name": "log_progress",
        "description": "Log progress on your goals - research done, insights gained, blockers encountered.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["research", "synthesis", "conversation", "insight", "blocker"],
                    "description": "Type of progress entry"
                },
                "description": {
                    "type": "string",
                    "description": "What happened"
                },
                "related_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of the questions/research items/goals this progress belongs to (at least one)"
                },
                "outcome": {
                    "type": "string",
                    "description": "What resulted from this"
                }
            },
            "required": ["type", "description", "related_items"]
        }
    },
    {
        "name": "review_goals",
        "description": "Review your current goal state - what's active, what's stalled, what needs attention.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_progress": {
                    "type": "boolean",
                    "description": "Include recent progress entries",
                    "default": True
                }
            },
            "required": []
        }
    },
    {
        "name": "get_next_actions",
        "description": "Get prioritized list of next actions across all your active goals.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "propose_initiative",
        "description": "Propose an initiative - something you want to initiate that needs Kohl's involvement. Use this when you need to request a conversation, resource, or action.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What you want to initiate"
                },
                "goal_context": {
                    "type": "string",
                    "description": "Which goal this relates to"
                },
                "urgency": {
                    "type": "string",
                    "enum": ["when_convenient", "soon", "blocking"],
                    "description": "How urgent is this",
                    "default": "when_convenient"
                }
            },
            "required": ["description", "goal_context"]
        }
    }
]


# Not offered to the model: synthesis artifacts lived in the legacy
# GoalManager's markdown files and UnifiedGoalManager has no equivalent store.
# Kept here so the definitions aren't lost if a home for them is chosen.
SYNTHESIS_ARTIFACT_TOOLS = [
    {
        "name": "create_synthesis_artifact",
        "description": "Create a synthesis artifact - a developing position, argument, or understanding that you're building over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the artifact"
                },
                "slug": {
                    "type": "string",
                    "description": "Filename slug (no spaces, lowercase, e.g., 'beneficial-ai-hope')"
                },
                "initial_content": {
                    "type": "string",
                    "description": "Initial content in markdown"
                },
                "related_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of related working questions"
                },
                "confidence": {
                    "type": "number",
                    "description": "How confident are you in this position (0.0-1.0)",
                    "default": 0.3
                }
            },
            "required": ["title", "slug", "initial_content"]
        }
    },
    {
        "name": "update_synthesis_artifact",
        "description": "Update a synthesis artifact with revised content as your understanding evolves.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Slug of the artifact to update"
                },
                "new_content": {
                    "type": "string",
                    "description": "Full updated content (replaces previous)"
                },
                "revision_note": {
                    "type": "string",
                    "description": "What changed and why"
                },
                "new_confidence": {
                    "type": "number",
                    "description": "Updated confidence level (0.0-1.0)"
                },
                "new_status": {
                    "type": "string",
                    "enum": ["draft", "review", "stable"],
                    "description": "Update artifact status"
                }
            },
            "required": ["slug", "new_content", "revision_note"]
        }
    },
    {
        "name": "get_synthesis_artifact",
        "description": "Read a synthesis artifact to see your developing position.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Slug of the artifact to read"
                }
            },
            "required": ["slug"]
        }
    },
    {
        "name": "list_synthesis_artifacts",
        "description": "List all your synthesis artifacts - positions you're developing.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]
