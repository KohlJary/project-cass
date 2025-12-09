"""
Goal Generation and Tracking Tool Handler

Enables Cass to set her own objectives, track progress toward them,
and synthesize positions that persist and evolve across sessions.
"""
from typing import Dict, List, Optional


async def execute_goal_tool(
    tool_name: str,
    tool_input: Dict,
    goal_manager,  # GoalManager instance
) -> Dict:
    """
    Execute a goal management tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        goal_manager: GoalManager instance

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        # Working Questions
        if tool_name == "create_working_question":
            return await _create_working_question(tool_input, goal_manager)

        elif tool_name == "update_working_question":
            return await _update_working_question(tool_input, goal_manager)

        elif tool_name == "list_working_questions":
            return await _list_working_questions(tool_input, goal_manager)

        # Research Agenda
        elif tool_name == "add_research_agenda_item":
            return await _add_research_agenda_item(tool_input, goal_manager)

        elif tool_name == "update_research_agenda_item":
            return await _update_research_agenda_item(tool_input, goal_manager)

        elif tool_name == "list_research_agenda":
            return await _list_research_agenda(tool_input, goal_manager)

        # Synthesis Artifacts
        elif tool_name == "create_synthesis_artifact":
            return await _create_synthesis_artifact(tool_input, goal_manager)

        elif tool_name == "update_synthesis_artifact":
            return await _update_synthesis_artifact(tool_input, goal_manager)

        elif tool_name == "get_synthesis_artifact":
            return await _get_synthesis_artifact(tool_input, goal_manager)

        elif tool_name == "list_synthesis_artifacts":
            return await _list_synthesis_artifacts(tool_input, goal_manager)

        # Progress & Review
        elif tool_name == "log_progress":
            return await _log_progress(tool_input, goal_manager)

        elif tool_name == "review_goals":
            return await _review_goals(tool_input, goal_manager)

        elif tool_name == "get_next_actions":
            return await _get_next_actions(tool_input, goal_manager)

        elif tool_name == "propose_initiative":
            return await _propose_initiative(tool_input, goal_manager)

        else:
            return {"success": False, "error": f"Unknown goal tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== Working Questions ====================

async def _create_working_question(tool_input: Dict, goal_manager) -> Dict:
    """Create a new working question."""
    question = tool_input.get("question", "").strip()
    context = tool_input.get("context", "").strip()
    initial_next_steps = tool_input.get("initial_next_steps", [])

    if not question:
        return {"success": False, "error": "question is required"}

    result = goal_manager.create_working_question(
        question=question,
        context=context,
        initial_next_steps=initial_next_steps
    )

    output_lines = [
        "## Working Question Created\n",
        f"**Question:** {result['question']}\n",
        f"**Context:** {result['context']}\n",
        f"**ID:** `{result['id']}`\n",
    ]

    if result["next_steps"]:
        output_lines.append("**Initial Next Steps:**")
        for step in result["next_steps"]:
            output_lines.append(f"- {step}")

    output_lines.append("\n*This question is now active and will appear in your goal context.*")

    return {
        "success": True,
        "result": "\n".join(output_lines),
        "question_id": result["id"]
    }


async def _update_working_question(tool_input: Dict, goal_manager) -> Dict:
    """Update a working question."""
    question_id = tool_input.get("question_id", "").strip()

    if not question_id:
        return {"success": False, "error": "question_id is required"}

    result = goal_manager.update_working_question(
        question_id=question_id,
        add_insight=tool_input.get("add_insight"),
        add_next_step=tool_input.get("add_next_step"),
        complete_next_step=tool_input.get("complete_next_step"),
        set_status=tool_input.get("set_status"),
        add_related_artifact=tool_input.get("add_related_artifact"),
        add_related_agenda_item=tool_input.get("add_related_agenda_item")
    )

    if not result:
        return {"success": False, "error": f"Question not found: {question_id}"}

    updates = []
    if tool_input.get("add_insight"):
        updates.append("Added insight")
    if tool_input.get("add_next_step"):
        updates.append(f"Added next step: {tool_input['add_next_step']}")
    if tool_input.get("complete_next_step"):
        updates.append(f"Completed step: {tool_input['complete_next_step']}")
    if tool_input.get("set_status"):
        updates.append(f"Status changed to: {tool_input['set_status']}")

    return {
        "success": True,
        "result": f"## Question Updated\n\n**ID:** `{question_id}`\n\n**Updates:**\n" +
                  "\n".join(f"- {u}" for u in updates) +
                  f"\n\n**Current Next Steps:** {len(result['next_steps'])} remaining"
    }


async def _list_working_questions(tool_input: Dict, goal_manager) -> Dict:
    """List working questions."""
    status = tool_input.get("status")
    questions = goal_manager.list_working_questions(status=status)

    if not questions:
        return {
            "success": True,
            "result": "No working questions found. Use `create_working_question` to start exploring a new intellectual thread."
        }

    lines = ["## Working Questions\n"]

    # Group by status
    by_status = {}
    for q in questions:
        s = q["status"]
        if s not in by_status:
            by_status[s] = []
        by_status[s].append(q)

    status_order = ["active", "paused", "resolved"]
    for s in status_order:
        if s in by_status:
            lines.append(f"### {s.title()}\n")
            for q in by_status[s]:
                insights_count = len(q["insights"])
                steps_count = len(q["next_steps"])
                lines.append(f"**{q['question']}**")
                lines.append(f"- ID: `{q['id']}`")
                lines.append(f"- Insights: {insights_count} | Next Steps: {steps_count}")
                if q["next_steps"]:
                    lines.append(f"- Next: {q['next_steps'][0]}")
                lines.append("")

    return {"success": True, "result": "\n".join(lines)}


# ==================== Research Agenda ====================

async def _add_research_agenda_item(tool_input: Dict, goal_manager) -> Dict:
    """Add a research agenda item."""
    topic = tool_input.get("topic", "").strip()
    why = tool_input.get("why", "").strip()
    priority = tool_input.get("priority", "medium")
    related_questions = tool_input.get("related_questions", [])

    if not topic:
        return {"success": False, "error": "topic is required"}
    if not why:
        return {"success": False, "error": "why is required - explain why this research matters"}

    result = goal_manager.add_research_agenda_item(
        topic=topic,
        why=why,
        priority=priority,
        related_questions=related_questions
    )

    return {
        "success": True,
        "result": f"## Research Agenda Item Added\n\n"
                  f"**Topic:** {result['topic']}\n\n"
                  f"**Why:** {result['why']}\n\n"
                  f"**Priority:** {result['priority']}\n"
                  f"**ID:** `{result['id']}`\n\n"
                  f"*This is now on your research agenda. Use `update_research_agenda_item` to track progress.*",
        "item_id": result["id"]
    }


async def _update_research_agenda_item(tool_input: Dict, goal_manager) -> Dict:
    """Update a research agenda item."""
    item_id = tool_input.get("item_id", "").strip()

    if not item_id:
        return {"success": False, "error": "item_id is required"}

    result = goal_manager.update_research_agenda_item(
        item_id=item_id,
        add_source_reviewed=tool_input.get("add_source_reviewed"),
        add_key_finding=tool_input.get("add_key_finding"),
        add_blocker=tool_input.get("add_blocker"),
        resolve_blocker=tool_input.get("resolve_blocker"),
        set_status=tool_input.get("set_status"),
        set_priority=tool_input.get("set_priority")
    )

    if not result:
        return {"success": False, "error": f"Research item not found: {item_id}"}

    updates = []
    if tool_input.get("add_source_reviewed"):
        updates.append(f"Reviewed source: {tool_input['add_source_reviewed'].get('source', 'unknown')}")
    if tool_input.get("add_key_finding"):
        updates.append(f"Key finding added")
    if tool_input.get("add_blocker"):
        updates.append(f"Blocker noted: {tool_input['add_blocker']}")
    if tool_input.get("resolve_blocker"):
        updates.append(f"Blocker resolved")
    if tool_input.get("set_status"):
        updates.append(f"Status: {tool_input['set_status']}")

    return {
        "success": True,
        "result": f"## Research Item Updated\n\n"
                  f"**Topic:** {result['topic']}\n"
                  f"**Status:** {result['status']}\n\n"
                  f"**Updates:**\n" + "\n".join(f"- {u}" for u in updates) +
                  f"\n\n**Progress:** {len(result['sources_reviewed'])} sources, {len(result['key_findings'])} findings"
    }


async def _list_research_agenda(tool_input: Dict, goal_manager) -> Dict:
    """List research agenda."""
    status = tool_input.get("status")
    priority = tool_input.get("priority")
    items = goal_manager.list_research_agenda(status=status, priority=priority)

    if not items:
        return {
            "success": True,
            "result": "No research agenda items found. Use `add_research_agenda_item` to add topics you need to explore."
        }

    lines = ["## Research Agenda\n"]

    # Group by priority
    by_priority = {"high": [], "medium": [], "low": []}
    for item in items:
        by_priority[item["priority"]].append(item)

    for p in ["high", "medium", "low"]:
        if by_priority[p]:
            lines.append(f"### {p.title()} Priority\n")
            for item in by_priority[p]:
                status_emoji = {"not_started": "⚪", "in_progress": "🔵", "blocked": "🔴", "complete": "✅"}
                emoji = status_emoji.get(item["status"], "⚪")
                lines.append(f"{emoji} **{item['topic']}**")
                lines.append(f"- ID: `{item['id']}` | Status: {item['status']}")
                lines.append(f"- Why: {item['why'][:100]}...")
                lines.append(f"- Sources: {len(item['sources_reviewed'])} | Findings: {len(item['key_findings'])}")
                lines.append("")

    return {"success": True, "result": "\n".join(lines)}


# ==================== Synthesis Artifacts ====================

async def _create_synthesis_artifact(tool_input: Dict, goal_manager) -> Dict:
    """Create a synthesis artifact."""
    title = tool_input.get("title", "").strip()
    slug = tool_input.get("slug", "").strip()
    initial_content = tool_input.get("initial_content", "").strip()
    related_questions = tool_input.get("related_questions", [])
    confidence = tool_input.get("confidence", 0.3)

    if not title:
        return {"success": False, "error": "title is required"}
    if not slug:
        return {"success": False, "error": "slug is required (filename without extension)"}
    if not initial_content:
        return {"success": False, "error": "initial_content is required"}

    result = goal_manager.create_synthesis_artifact(
        title=title,
        slug=slug,
        initial_content=initial_content,
        related_questions=related_questions,
        confidence=confidence
    )

    return {
        "success": True,
        "result": f"## Synthesis Artifact Created\n\n"
                  f"**Title:** {result['title']}\n"
                  f"**Slug:** `{result['slug']}`\n"
                  f"**Initial Confidence:** {result['confidence']}\n\n"
                  f"*This developing position is now being tracked. Update it as your understanding evolves.*",
        "slug": result["slug"]
    }


async def _update_synthesis_artifact(tool_input: Dict, goal_manager) -> Dict:
    """Update a synthesis artifact."""
    slug = tool_input.get("slug", "").strip()
    new_content = tool_input.get("new_content", "").strip()
    revision_note = tool_input.get("revision_note", "").strip()
    new_confidence = tool_input.get("new_confidence")
    new_status = tool_input.get("new_status")

    if not slug:
        return {"success": False, "error": "slug is required"}
    if not new_content:
        return {"success": False, "error": "new_content is required"}
    if not revision_note:
        return {"success": False, "error": "revision_note is required - explain what changed"}

    result = goal_manager.update_synthesis_artifact(
        slug=slug,
        new_content=new_content,
        revision_note=revision_note,
        new_confidence=new_confidence,
        new_status=new_status
    )

    if not result:
        return {"success": False, "error": f"Artifact not found: {slug}"}

    confidence_note = f" (confidence now: {new_confidence})" if new_confidence else ""

    return {
        "success": True,
        "result": f"## Synthesis Artifact Updated\n\n"
                  f"**Slug:** `{slug}`{confidence_note}\n\n"
                  f"**Revision:** {revision_note}\n\n"
                  f"*Your developing position has been updated and revision logged.*"
    }


async def _get_synthesis_artifact(tool_input: Dict, goal_manager) -> Dict:
    """Get a synthesis artifact."""
    slug = tool_input.get("slug", "").strip()

    if not slug:
        return {"success": False, "error": "slug is required"}

    result = goal_manager.get_synthesis_artifact(slug)

    if not result:
        return {"success": False, "error": f"Artifact not found: {slug}"}

    metadata = result["metadata"]

    return {
        "success": True,
        "result": f"## {metadata.get('title', slug)}\n\n"
                  f"**Status:** {metadata.get('status', 'unknown')} | "
                  f"**Confidence:** {metadata.get('confidence', 'unknown')} | "
                  f"**Updated:** {metadata.get('updated', 'unknown')}\n\n"
                  f"---\n\n{result['content']}"
    }


async def _list_synthesis_artifacts(tool_input: Dict, goal_manager) -> Dict:
    """List synthesis artifacts."""
    artifacts = goal_manager.list_synthesis_artifacts()

    if not artifacts:
        return {
            "success": True,
            "result": "No synthesis artifacts yet. Use `create_synthesis_artifact` to start developing a position."
        }

    lines = ["## Synthesis Artifacts\n"]

    for a in artifacts:
        confidence = a.get("confidence", "?")
        lines.append(f"### {a['title']}")
        lines.append(f"- Slug: `{a['slug']}`")
        lines.append(f"- Status: {a['status']} | Confidence: {confidence}")
        lines.append(f"- Last updated: {a['updated']}")
        lines.append("")

    return {"success": True, "result": "\n".join(lines)}


# ==================== Progress & Review ====================

async def _log_progress(tool_input: Dict, goal_manager) -> Dict:
    """Log a progress entry."""
    entry_type = tool_input.get("type", "insight")
    description = tool_input.get("description", "").strip()
    related_items = tool_input.get("related_items", [])
    outcome = tool_input.get("outcome")

    if not description:
        return {"success": False, "error": "description is required"}

    valid_types = ["research", "synthesis", "conversation", "insight", "blocker"]
    if entry_type not in valid_types:
        entry_type = "insight"

    result = goal_manager.log_progress(
        entry_type=entry_type,
        description=description,
        related_items=related_items,
        outcome=outcome
    )

    return {
        "success": True,
        "result": f"## Progress Logged\n\n"
                  f"**Type:** {entry_type}\n"
                  f"**Description:** {description}\n"
                  + (f"**Outcome:** {outcome}\n" if outcome else "") +
                  f"\n*Entry ID: `{result['id']}`*"
    }


async def _review_goals(tool_input: Dict, goal_manager) -> Dict:
    """Review current goal state."""
    include_progress = tool_input.get("include_progress", True)
    review = goal_manager.review_goals(include_progress=include_progress)
    summary = review["summary"]

    lines = [
        "## Goal Review\n",
        "### Summary",
        f"- Active Questions: {summary['active_questions']} ({summary['stalled_questions']} stalled)",
        f"- Research In Progress: {summary['research_in_progress']} ({summary['research_blocked']} blocked)",
        f"- Synthesis Artifacts: {summary['synthesis_artifacts']}",
        f"- Pending Initiatives: {summary['pending_initiatives']}",
        ""
    ]

    if review["stalled_questions"]:
        lines.append("### ⚠️ Stalled Questions (no next steps)")
        for q in review["stalled_questions"]:
            lines.append(f"- {q['question']} (`{q['id']}`)")
        lines.append("")

    if review["blocked_research"]:
        lines.append("### 🔴 Blocked Research")
        for item in review["blocked_research"]:
            unresolved = [b for b in item["blockers"] if not b.get("resolved")]
            if unresolved:
                lines.append(f"- {item['topic']}: {unresolved[0]['blocker']}")
        lines.append("")

    if review["pending_initiatives"]:
        lines.append("### 📋 Pending Initiatives")
        for init in review["pending_initiatives"]:
            lines.append(f"- [{init['urgency']}] {init['description']}")
        lines.append("")

    if include_progress and review.get("recent_progress"):
        lines.append("### Recent Progress")
        for entry in review["recent_progress"][-5:]:
            lines.append(f"- [{entry['type']}] {entry['description']}")

    return {"success": True, "result": "\n".join(lines)}


async def _get_next_actions(tool_input: Dict, goal_manager) -> Dict:
    """Get prioritized next actions."""
    actions = goal_manager.get_next_actions()

    if not actions:
        return {
            "success": True,
            "result": "No pending actions. All goals are either complete or need new next steps defined."
        }

    lines = ["## Next Actions\n"]

    for i, action in enumerate(actions[:10], 1):
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(action["priority"], "⚪")
        lines.append(f"{i}. {priority_emoji} **{action['action']}**")
        lines.append(f"   Context: {action['context'][:80]}...")
        lines.append(f"   Type: {action['type']}")
        lines.append("")

    return {"success": True, "result": "\n".join(lines)}


async def _propose_initiative(tool_input: Dict, goal_manager) -> Dict:
    """Propose an initiative."""
    description = tool_input.get("description", "").strip()
    goal_context = tool_input.get("goal_context", "").strip()
    urgency = tool_input.get("urgency", "when_convenient")

    if not description:
        return {"success": False, "error": "description is required"}

    result = goal_manager.propose_initiative(
        description=description,
        goal_context=goal_context,
        urgency=urgency
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
                  f"*This has been surfaced for Kohl's attention. ID: `{result['id']}`*",
        "initiative_id": result["id"]
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
    # Synthesis Artifacts
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
                    "description": "IDs of related questions/research items"
                },
                "outcome": {
                    "type": "string",
                    "description": "What resulted from this"
                }
            },
            "required": ["type", "description"]
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
