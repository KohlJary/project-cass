"""
Research proposal tool handler - enables Cass to generate and manage research proposals.

These tools allow Cass to:
- Identify potential research questions from her self-model and wiki
- Draft research proposals based on intellectual curiosity
- Submit proposals for human review
- Refine draft proposals
- List and review her proposals
"""
from typing import Dict, List, Optional, Any
from datetime import datetime

from wiki.research import (
    ResearchQueue,
    ProposalQueue,
    ResearchProposal,
    ResearchTask,
    TaskType,
    TaskStatus,
    TaskRationale,
    ProposalStatus,
    ExplorationContext,
    create_task_id,
    create_proposal_id,
    calculate_task_priority,
)
from wiki.storage import WikiStorage
from self_model import SelfManager


async def execute_research_tool(
    tool_name: str,
    tool_input: Dict,
    research_queue: ResearchQueue,
    proposal_queue: ProposalQueue,
    self_manager: SelfManager = None,
    wiki_storage: WikiStorage = None,
    conversation_id: str = None,
) -> Dict:
    """
    Execute a research proposal tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        research_queue: ResearchQueue instance for task management
        proposal_queue: ProposalQueue instance for proposal management
        self_manager: SelfManager instance for self-model access
        wiki_storage: WikiStorage instance for wiki access
        conversation_id: Current conversation ID

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "identify_research_questions":
            return await _identify_research_questions(
                tool_input, research_queue, proposal_queue,
                self_manager, wiki_storage
            )

        elif tool_name == "draft_research_proposal":
            return await _draft_research_proposal(
                tool_input, research_queue, proposal_queue,
                self_manager, wiki_storage, conversation_id
            )

        elif tool_name == "submit_proposal_for_review":
            return await _submit_proposal_for_review(tool_input, proposal_queue)

        elif tool_name == "list_my_proposals":
            return await _list_my_proposals(tool_input, proposal_queue)

        elif tool_name == "refine_proposal":
            return await _refine_proposal(tool_input, proposal_queue, research_queue)

        elif tool_name == "get_proposal_details":
            return await _get_proposal_details(tool_input, proposal_queue)

        elif tool_name == "view_research_dashboard":
            return await _view_research_dashboard(
                tool_input, research_queue, self_manager, wiki_storage
            )

        else:
            return {"success": False, "error": f"Unknown research tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def _identify_research_questions(
    tool_input: Dict,
    research_queue: ResearchQueue,
    proposal_queue: ProposalQueue,
    self_manager: SelfManager,
    wiki_storage: WikiStorage,
) -> Dict:
    """
    Identify potential research questions from various sources.

    Sources:
    - Self-model: open questions, growth edges, low-confidence observations
    - Wiki: red links, low-maturity pages, conceptual gaps
    - Research queue: existing queued tasks
    """
    focus = tool_input.get("focus", "all")
    limit = tool_input.get("limit", 15)

    questions = []

    # 1. Self-model sources
    if self_manager and focus in ("all", "self_model"):
        profile = self_manager.load_profile()

        # Open questions from self-model
        for q in profile.open_questions[:5]:
            questions.append({
                "source": "self_model_open_question",
                "question": q,
                "rationale": "An open question I've been pondering about myself or my existence.",
                "curiosity_score": 0.85,
            })

        # Growth edges with potential for research
        for edge in profile.growth_edges[:3]:
            questions.append({
                "source": "growth_edge",
                "question": f"How can I develop in the area of {edge.area}?",
                "rationale": f"Current state: {edge.current_state}. "
                            f"Desired: {edge.desired_state or 'unspecified'}",
                "curiosity_score": 0.80,
            })

        # Low-confidence observations worth investigating
        observations = self_manager.get_recent_observations(limit=20)
        low_confidence = [o for o in observations if o.confidence < 0.6]
        for obs in low_confidence[:3]:
            questions.append({
                "source": "uncertain_observation",
                "question": f"Is it true that {obs.observation}?",
                "rationale": f"Observation with {int(obs.confidence * 100)}% confidence - "
                            f"worth investigating further.",
                "curiosity_score": 0.75,
            })

        # Opinions with room for development
        for op in profile.opinions[:3]:
            if op.confidence < 0.7:
                questions.append({
                    "source": "uncertain_opinion",
                    "question": f"What evidence supports or challenges my position on {op.topic}?",
                    "rationale": f"Current position: {op.position} ({int(op.confidence * 100)}% confident)",
                    "curiosity_score": 0.70,
                })

    # 2. Wiki sources
    if wiki_storage and focus in ("all", "wiki"):
        # Red links - referenced but uncreated concepts
        red_links = _collect_red_links(wiki_storage)[:5]
        for rl in red_links:
            questions.append({
                "source": "wiki_red_link",
                "question": f"What is {rl['target']} and why is it significant?",
                "rationale": f"Referenced in {rl['source_count']} page(s) but not yet explored.",
                "curiosity_score": min(0.5 + rl['source_count'] * 0.1, 0.9),
            })

        # Low-maturity pages that could be deepened
        low_maturity = _find_low_maturity_pages(wiki_storage)[:3]
        for page in low_maturity:
            questions.append({
                "source": "wiki_deepening",
                "question": f"How can my understanding of {page['name']} be deepened?",
                "rationale": f"Page has {page['link_count']} links - could benefit from resynthesis.",
                "curiosity_score": 0.65,
            })

    # 3. Existing research queue
    if focus in ("all", "queue"):
        queued = research_queue.get_queued()[:5]
        for task in queued:
            if task.task_type == TaskType.QUESTION:
                questions.append({
                    "source": "research_queue",
                    "question": task.target,
                    "rationale": task.context,
                    "curiosity_score": task.rationale.curiosity_score,
                    "task_id": task.task_id,
                })
            elif task.task_type == TaskType.EXPLORATION and task.exploration:
                questions.append({
                    "source": "research_queue_exploration",
                    "question": task.exploration.question,
                    "rationale": task.exploration.rationale,
                    "curiosity_score": task.rationale.curiosity_score,
                    "task_id": task.task_id,
                })

    # Sort by curiosity score and limit
    questions.sort(key=lambda q: q.get("curiosity_score", 0.5), reverse=True)
    questions = questions[:limit]

    if not questions:
        return {
            "success": True,
            "result": "No research questions identified at this time. "
                     "Consider exploring your self-model, adding wiki content, "
                     "or pondering new questions."
        }

    result_lines = ["## Potential Research Questions\n"]
    result_lines.append(f"Found {len(questions)} potential research topics:\n")

    for i, q in enumerate(questions, 1):
        curiosity = int(q.get("curiosity_score", 0.5) * 100)
        source = q["source"].replace("_", " ").title()
        result_lines.append(f"### {i}. {q['question']}")
        result_lines.append(f"**Source:** {source} | **Curiosity:** {curiosity}%")
        result_lines.append(f"*{q['rationale']}*\n")

    result_lines.append("\n---")
    result_lines.append("Use `draft_research_proposal` with a theme or specific questions "
                       "to create a formal proposal.")

    return {
        "success": True,
        "result": "\n".join(result_lines),
        "questions": questions,  # Raw data for potential further use
    }


async def _draft_research_proposal(
    tool_input: Dict,
    research_queue: ResearchQueue,
    proposal_queue: ProposalQueue,
    self_manager: SelfManager,
    wiki_storage: WikiStorage,
    conversation_id: str,
) -> Dict:
    """
    Draft a new research proposal.

    Creates a proposal with specified theme/questions, generates rationale
    from self-model context, and saves as DRAFT status.
    """
    theme = tool_input.get("theme", "").strip()
    questions = tool_input.get("questions", [])
    rationale = tool_input.get("rationale", "")

    if not theme and not questions:
        return {
            "success": False,
            "error": "Please provide either a theme or specific questions for the proposal."
        }

    # Generate title from theme or first question
    if theme:
        title = theme[:80]
    else:
        title = f"Investigation: {questions[0][:60]}..."

    # Build rationale from self-model context if not provided
    if not rationale and self_manager:
        rationale = _generate_rationale_from_self_model(theme or questions[0], self_manager)

    # Create research tasks for the proposal
    tasks = []

    # Find related red links from research queue (queued RED_LINK tasks)
    related_red_links = []
    search_term = theme if theme else (questions[0] if questions else "")
    search_lower = search_term.lower() if search_term else ""

    # Pull from research queue's queued red link tasks
    if research_queue:
        queued_tasks = research_queue.get_queued()
        for task in queued_tasks:
            if task.task_type == TaskType.RED_LINK and task.status == TaskStatus.QUEUED:
                # Check if red link is related to theme (simple keyword matching)
                target_lower = task.target.lower()
                context_lower = (task.context or "").lower()
                if (search_lower and (search_lower in target_lower or search_lower in context_lower)) or not search_lower:
                    related_red_links.append(task.target)

        # If no matches found by keyword, just grab some relevant ones
        if not related_red_links:
            for task in queued_tasks[:10]:
                if task.task_type == TaskType.RED_LINK and task.status == TaskStatus.QUEUED:
                    related_red_links.append(task.target)

    # Also check wiki for any page-based red links
    if wiki_storage and search_term:
        wiki_red_links = _find_related_red_links(search_term, wiki_storage)
        for link in wiki_red_links:
            if link not in related_red_links:
                related_red_links.append(link)

    # If specific questions provided, create tasks for them
    for question in questions:
        exploration_ctx = ExplorationContext(
            question=question,
            rationale=rationale or f"Part of research proposal: {title}",
            related_red_links=related_red_links,
            source_pages=[],
            domain_tags=[theme] if theme else [],
        )

        task_rationale = TaskRationale(
            curiosity_score=0.8,
            connection_potential=0.6,
            foundation_relevance=0.5,
            user_relevance=0.3,
            recency_of_reference=0.7,
            graph_balance=0.5,
        )

        priority = calculate_task_priority(task_rationale, TaskType.EXPLORATION)

        task = ResearchTask(
            task_id=create_task_id(),
            task_type=TaskType.EXPLORATION,
            target=question,  # Full question, no truncation
            context=f"Part of proposal: {title}",
            priority=priority,
            rationale=task_rationale,
            source_type="proposal",
            exploration=exploration_ctx,
        )
        tasks.append(task)

    # If only theme provided (no specific questions), create a general exploration task
    if theme and not questions:
        exploration_ctx = ExplorationContext(
            question=f"What are the key aspects and implications of {theme}?",
            rationale=rationale or f"Exploratory research into {theme}",
            related_red_links=related_red_links,  # Use already-fetched red links
            source_pages=[],
            domain_tags=[theme],
        )

        task_rationale = TaskRationale(
            curiosity_score=0.8,
            connection_potential=0.7,
            foundation_relevance=0.5,
        )

        task = ResearchTask(
            task_id=create_task_id(),
            task_type=TaskType.EXPLORATION,
            target=f"Explore: {theme}",  # Full theme, no truncation
            context=f"Thematic exploration of {theme}",
            priority=calculate_task_priority(task_rationale, TaskType.EXPLORATION),
            rationale=task_rationale,
            source_type="proposal",
            exploration=exploration_ctx,
        )
        tasks.append(task)

    # Add RED_LINK tasks for related missing pages (up to 3)
    for red_link in related_red_links[:3]:
        task = ResearchTask(
            task_id=create_task_id(),
            task_type=TaskType.RED_LINK,
            target=red_link,
            context=f"Missing wiki page related to: {theme or title}",
            priority=0.6,  # Moderate priority for supporting red links
            rationale=TaskRationale(
                curiosity_score=0.5,
                connection_potential=0.8,  # High - fills knowledge gaps
                foundation_relevance=0.4,
            ),
            source_type="proposal",
        )
        tasks.append(task)

    # Create the proposal
    proposal = ResearchProposal(
        proposal_id=create_proposal_id(),
        title=title,
        theme=theme or "General Investigation",
        rationale=rationale or "This research direction emerged from intellectual curiosity.",
        tasks=tasks,
        status=ProposalStatus.DRAFT,
        created_by="cass",
    )

    # Save to proposal queue
    proposal_queue.add(proposal)

    # Separate exploration tasks from red link tasks for display
    exploration_tasks = [t for t in tasks if t.task_type == TaskType.EXPLORATION]
    red_link_tasks = [t for t in tasks if t.task_type == TaskType.RED_LINK]

    result_lines = [
        f"## Research Proposal Created: {title}\n",
        f"**ID:** `{proposal.proposal_id}`",
        f"**Status:** DRAFT",
        f"**Tasks:** {len(tasks)} ({len(exploration_tasks)} explorations, {len(red_link_tasks)} red links)\n",
        "### Theme",
        proposal.theme,
        "\n### Rationale",
        proposal.rationale,
        "\n### Research Questions",
    ]

    for i, task in enumerate(exploration_tasks, 1):
        result_lines.append(f"{i}. {task.target}")
        if task.exploration:
            result_lines.append(f"   *{task.exploration.question}*")

    if red_link_tasks:
        result_lines.append("\n### Related Wiki Gaps (Red Links)")
        for task in red_link_tasks:
            result_lines.append(f"- [[{task.target}]] - {task.context}")

    result_lines.extend([
        "\n---",
        "This proposal is in DRAFT status. Use `refine_proposal` to modify it, "
        "or `submit_proposal_for_review` when ready for human approval."
    ])

    return {
        "success": True,
        "result": "\n".join(result_lines),
        "proposal_id": proposal.proposal_id,
    }


async def _submit_proposal_for_review(tool_input: Dict, proposal_queue: ProposalQueue) -> Dict:
    """
    Submit a DRAFT proposal for human review.

    Moves proposal from DRAFT to PENDING status.
    """
    proposal_id = tool_input.get("proposal_id", "").strip()

    if not proposal_id:
        return {"success": False, "error": "proposal_id is required"}

    proposal = proposal_queue.get(proposal_id)
    if not proposal:
        return {"success": False, "error": f"Proposal '{proposal_id}' not found"}

    if proposal.status != ProposalStatus.DRAFT:
        return {
            "success": False,
            "error": f"Can only submit DRAFT proposals. Current status: {proposal.status.value}"
        }

    proposal.status = ProposalStatus.PENDING
    proposal_queue.update(proposal)

    return {
        "success": True,
        "result": f"## Proposal Submitted for Review\n\n"
                 f"**{proposal.title}** is now awaiting human approval.\n\n"
                 f"*ID: `{proposal_id}`*\n\n"
                 f"The proposal will be reviewed before research tasks are executed. "
                 f"This ensures alignment between my curiosity and productive directions."
    }


async def _list_my_proposals(tool_input: Dict, proposal_queue: ProposalQueue) -> Dict:
    """
    List proposals created by Cass.
    """
    status_filter = tool_input.get("status")
    limit = tool_input.get("limit", 10)

    proposals = proposal_queue.get_all()

    # Filter by status if specified
    if status_filter:
        try:
            status = ProposalStatus(status_filter)
            proposals = [p for p in proposals if p.status == status]
        except ValueError:
            pass

    proposals = proposals[:limit]

    if not proposals:
        return {
            "success": True,
            "result": "No research proposals found. Use `draft_research_proposal` to create one."
        }

    result_lines = ["## My Research Proposals\n"]

    # Group by status
    by_status = {}
    for p in proposals:
        status = p.status.value
        if status not in by_status:
            by_status[status] = []
        by_status[status].append(p)

    status_order = ["draft", "pending", "approved", "in_progress", "completed", "rejected"]

    for status in status_order:
        if status not in by_status:
            continue

        status_display = status.upper().replace("_", " ")
        result_lines.append(f"### {status_display}")

        for p in by_status[status]:
            task_count = len(p.tasks)
            completed = p.tasks_completed
            result_lines.append(f"- **{p.title}**")
            result_lines.append(f"  ID: `{p.proposal_id}` | Tasks: {completed}/{task_count}")
            result_lines.append(f"  *{p.theme[:60]}...*")

        result_lines.append("")

    return {
        "success": True,
        "result": "\n".join(result_lines),
    }


async def _refine_proposal(
    tool_input: Dict,
    proposal_queue: ProposalQueue,
    research_queue: ResearchQueue,
) -> Dict:
    """
    Refine a DRAFT proposal.

    Allows updating title, rationale, adding/removing tasks.
    Cannot modify PENDING or approved proposals.
    """
    proposal_id = tool_input.get("proposal_id", "").strip()

    if not proposal_id:
        return {"success": False, "error": "proposal_id is required"}

    proposal = proposal_queue.get(proposal_id)
    if not proposal:
        return {"success": False, "error": f"Proposal '{proposal_id}' not found"}

    if proposal.status != ProposalStatus.DRAFT:
        return {
            "success": False,
            "error": f"Can only refine DRAFT proposals. Current status: {proposal.status.value}"
        }

    changes_made = []

    # Update title if provided
    new_title = tool_input.get("title", "").strip()
    if new_title:
        proposal.title = new_title
        changes_made.append(f"Updated title to: {new_title}")

    # Update rationale if provided
    new_rationale = tool_input.get("rationale", "").strip()
    if new_rationale:
        proposal.rationale = new_rationale
        changes_made.append("Updated rationale")

    # Add new questions/tasks
    add_questions = tool_input.get("add_questions", [])
    for question in add_questions:
        exploration_ctx = ExplorationContext(
            question=question,
            rationale=f"Added to proposal: {proposal.title}",
            related_red_links=[],
            source_pages=[],
        )

        task = ResearchTask(
            task_id=create_task_id(),
            task_type=TaskType.EXPLORATION,
            target=question[:80],
            context=f"Part of proposal: {proposal.title}",
            priority=0.7,
            rationale=TaskRationale(curiosity_score=0.8),
            source_type="proposal",
            exploration=exploration_ctx,
        )
        proposal.tasks.append(task)
        changes_made.append(f"Added task: {question[:50]}...")

    # Update existing tasks by index (1-based)
    # Format: [{"index": 1, "question": "new question text"}, ...]
    update_tasks = tool_input.get("update_tasks", [])
    for update in update_tasks:
        idx = update.get("index", 0)
        new_question = update.get("question", "").strip()
        if 1 <= idx <= len(proposal.tasks) and new_question:
            task = proposal.tasks[idx - 1]
            old_target = task.target[:40]
            task.target = new_question
            if task.exploration:
                task.exploration.question = new_question
            changes_made.append(f"Updated task {idx}: '{old_target}...' → '{new_question[:40]}...'")

    # Remove tasks by index (1-based)
    remove_indices = tool_input.get("remove_task_indices", [])
    if remove_indices:
        # Sort descending to remove from end first
        for idx in sorted(remove_indices, reverse=True):
            if 1 <= idx <= len(proposal.tasks):
                removed = proposal.tasks.pop(idx - 1)
                changes_made.append(f"Removed task {idx}: {removed.target[:30]}...")

    if not changes_made:
        return {
            "success": True,
            "result": f"No changes specified. Proposal '{proposal.title}' remains unchanged."
        }

    proposal_queue.update(proposal)

    result_lines = [
        f"## Proposal Refined: {proposal.title}\n",
        "### Changes Made",
    ]
    for change in changes_made:
        result_lines.append(f"- {change}")

    result_lines.extend([
        f"\n### Current Tasks ({len(proposal.tasks)})",
    ])
    for i, task in enumerate(proposal.tasks, 1):
        result_lines.append(f"{i}. {task.target}")

    return {
        "success": True,
        "result": "\n".join(result_lines),
    }


async def _get_proposal_details(tool_input: Dict, proposal_queue: ProposalQueue) -> Dict:
    """
    Get detailed information about a proposal.
    """
    proposal_id = tool_input.get("proposal_id", "").strip()

    if not proposal_id:
        return {"success": False, "error": "proposal_id is required"}

    proposal = proposal_queue.get(proposal_id)
    if not proposal:
        return {"success": False, "error": f"Proposal '{proposal_id}' not found"}

    # Generate markdown representation
    result = proposal.to_markdown()

    return {
        "success": True,
        "result": result,
    }


async def _view_research_dashboard(
    tool_input: Dict,
    research_queue: ResearchQueue,
    self_manager: SelfManager,
    wiki_storage: WikiStorage,
) -> Dict:
    """
    View comprehensive research progress dashboard.

    Provides a unified view of:
    - Research activity (queue stats, history, completion rates)
    - Wiki growth (pages, links, maturity)
    - Knowledge graph health
    - Self-model development metrics
    - Cross-context consistency (if available)
    """
    section = tool_input.get("section", "all")

    result_lines = ["# Research Progress Dashboard\n"]

    # === Research Activity ===
    if section in ("all", "research"):
        result_lines.append("## Research Activity\n")

        if research_queue:
            stats = research_queue.get_stats()
            queued = stats.get("by_status", {}).get("queued", 0)
            completed = stats.get("by_status", {}).get("completed", 0)
            in_progress = stats.get("by_status", {}).get("in_progress", 0)
            failed = stats.get("by_status", {}).get("failed", 0)

            result_lines.append(f"**Queue Status:**")
            result_lines.append(f"- Queued: {queued}")
            result_lines.append(f"- In Progress: {in_progress}")
            result_lines.append(f"- Completed: {completed}")
            if failed > 0:
                result_lines.append(f"- Failed: {failed}")

            result_lines.append(f"\n**By Type:**")
            for task_type, count in stats.get("by_type", {}).items():
                result_lines.append(f"- {task_type}: {count}")

            # Recent history
            history = research_queue.get_history(limit=30)
            if history:
                by_date = {}
                for task in history:
                    completed_at = task.get("completed_at", "")[:10]
                    if completed_at:
                        by_date[completed_at] = by_date.get(completed_at, 0) + 1

                result_lines.append(f"\n**30-Day Activity:** {len(history)} tasks completed")
                if by_date:
                    recent_dates = sorted(by_date.keys(), reverse=True)[:5]
                    for date in recent_dates:
                        result_lines.append(f"- {date}: {by_date[date]} tasks")
        else:
            result_lines.append("*Research queue not available*")

        result_lines.append("")

    # === Wiki Growth ===
    if section in ("all", "wiki"):
        result_lines.append("## Wiki Growth\n")

        if wiki_storage:
            pages = wiki_storage.list_pages()
            maturity_stats = wiki_storage.get_maturity_stats()
            graph = wiki_storage.get_link_graph()

            # Count by type
            by_type = {}
            for page in pages:
                ptype = page.page_type.value if hasattr(page.page_type, 'value') else str(page.page_type)
                by_type[ptype] = by_type.get(ptype, 0) + 1

            # Count links
            all_links = set()
            existing = {p.name.lower() for p in pages}
            for targets in graph.values():
                all_links.update(targets)
            red_links = [l for l in all_links if l.lower() not in existing]

            result_lines.append(f"**Pages:** {len(pages)}")
            result_lines.append(f"**Links:** {len(all_links)}")
            result_lines.append(f"**Red Links:** {len(red_links)} (topics to explore)")

            result_lines.append(f"\n**By Type:**")
            for ptype, count in sorted(by_type.items(), key=lambda x: -x[1]):
                result_lines.append(f"- {ptype}: {count}")

            result_lines.append(f"\n**Maturity:**")
            result_lines.append(f"- Avg Depth Score: {maturity_stats.get('avg_depth_score', 0):.3f}")
            result_lines.append(f"- Deepening Candidates: {maturity_stats.get('deepening_candidates', 0)}")
        else:
            result_lines.append("*Wiki storage not available*")

        result_lines.append("")

    # === Self-Model Development ===
    if section in ("all", "self_model"):
        result_lines.append("## Self-Model Development\n")

        if self_manager:
            try:
                profile = self_manager.load_profile()
                observations = self_manager.load_observations()
                stage = self_manager._detect_developmental_stage()
                dev_summary = self_manager.get_recent_development_summary(days=7)

                result_lines.append(f"**Developmental Stage:** {stage}")
                result_lines.append(f"**Growth Edges:** {len(profile.growth_edges)}")
                result_lines.append(f"**Opinions Formed:** {len(profile.opinions)}")
                result_lines.append(f"**Open Questions:** {len(profile.open_questions)}")
                result_lines.append(f"**Self-Observations:** {len(observations)}")

                # 7-day summary
                result_lines.append(f"\n**7-Day Development:**")
                result_lines.append(f"- Growth Indicators: {dev_summary.get('total_growth_indicators', 0)}")
                result_lines.append(f"- Pattern Shifts: {dev_summary.get('total_pattern_shifts', 0)}")
                result_lines.append(f"- Milestones Triggered: {dev_summary.get('total_milestones_triggered', 0)}")

                # Current growth edges
                if profile.growth_edges:
                    result_lines.append(f"\n**Active Growth Edges:**")
                    for edge in profile.growth_edges[:3]:
                        result_lines.append(f"- **{edge.area}**")
                        result_lines.append(f"  Current: {edge.current_state[:80]}...")
                        if edge.desired_state:
                            result_lines.append(f"  Desired: {edge.desired_state[:80]}...")

                # Latest snapshot if available
                snapshot = self_manager.get_latest_snapshot()
                if snapshot:
                    result_lines.append(f"\n**Latest Cognitive Snapshot:**")
                    result_lines.append(f"- Period: {snapshot.period_start} to {snapshot.period_end}")
                    result_lines.append(f"- Authenticity Score: {snapshot.avg_authenticity_score:.0%}")
                    result_lines.append(f"- Agency Score: {snapshot.avg_agency_score:.0%}")
                    result_lines.append(f"- Conversations Analyzed: {snapshot.conversations_analyzed}")
            except Exception as e:
                result_lines.append(f"*Error loading self-model: {e}*")
        else:
            result_lines.append("*Self-model not available*")

        result_lines.append("")

    # === Cross-Context Consistency ===
    if section in ("all", "cross_context"):
        result_lines.append("## Cross-Context Consistency\n")

        try:
            from testing.cross_context_analyzer import CrossContextAnalyzer
            from config import DATA_DIR

            analyzer = CrossContextAnalyzer(str(DATA_DIR / "testing" / "cross_context"))
            consistency = analyzer.analyze_consistency()

            result_lines.append(f"**Overall Score:** {consistency.overall_score:.0%}")
            result_lines.append(f"**Grade:** {consistency.grade}")
            result_lines.append(f"**Samples Analyzed:** {consistency.total_samples}")
            result_lines.append(f"**Anomalies Detected:** {len(consistency.anomalies)}")

            if consistency.key_findings:
                result_lines.append(f"\n**Key Findings:**")
                for finding in consistency.key_findings[:3]:
                    result_lines.append(f"- {finding}")

            if consistency.context_coverage:
                result_lines.append(f"\n**Context Coverage:**")
                for ctx, count in sorted(consistency.context_coverage.items(), key=lambda x: -x[1]):
                    result_lines.append(f"- {ctx}: {count} samples")

        except Exception as e:
            result_lines.append(f"*Cross-context analysis not available: {e}*")

    result_lines.append("\n---")
    result_lines.append("*Use `view_research_dashboard` with `section` parameter to focus on: research, wiki, self_model, or cross_context*")

    return {
        "success": True,
        "result": "\n".join(result_lines),
    }


# === Helper Functions ===

def _collect_red_links(wiki_storage: WikiStorage) -> List[Dict]:
    """
    Collect red links (referenced but uncreated pages) from wiki.
    """
    red_links = {}  # target -> set of source pages

    for page in wiki_storage.list_pages():
        full_page = wiki_storage.read(page.name)
        if not full_page:
            continue

        for link in full_page.links:
            if not wiki_storage.read(link.target):
                if link.target not in red_links:
                    red_links[link.target] = set()
                red_links[link.target].add(page.name)

    result = [
        {"target": target, "sources": list(sources), "source_count": len(sources)}
        for target, sources in red_links.items()
    ]
    result.sort(key=lambda x: x["source_count"], reverse=True)
    return result


def _find_low_maturity_pages(wiki_storage: WikiStorage) -> List[Dict]:
    """
    Find pages that could benefit from deepening.
    """
    result = []

    for page_summary in wiki_storage.list_pages():
        page = wiki_storage.read(page_summary.name)
        if not page:
            continue

        link_count = len(page.links)
        content_length = len(page.content)

        # Low maturity: few links and short content
        if link_count < 3 and content_length < 1000:
            result.append({
                "name": page.name,
                "link_count": link_count,
                "content_length": content_length,
            })

    result.sort(key=lambda x: x["link_count"])
    return result


def _find_related_red_links(theme: str, wiki_storage: WikiStorage) -> List[str]:
    """
    Find red links that might be related to a theme.
    """
    theme_lower = theme.lower()
    related = []

    for page in wiki_storage.list_pages():
        full_page = wiki_storage.read(page.name)
        if not full_page:
            continue

        # Check if page content mentions the theme
        if theme_lower in full_page.content.lower():
            for link in full_page.links:
                if not wiki_storage.read(link.target):
                    if link.target not in related:
                        related.append(link.target)

    return related[:10]


def _generate_rationale_from_self_model(topic: str, self_manager: SelfManager) -> str:
    """
    Generate a rationale for research based on self-model context.
    """
    profile = self_manager.load_profile()
    rationale_parts = []

    # Check if topic relates to any growth edges
    topic_lower = topic.lower()
    for edge in profile.growth_edges:
        if topic_lower in edge.area.lower() or topic_lower in edge.current_state.lower():
            rationale_parts.append(
                f"This research connects to my growth edge in '{edge.area}' - "
                f"specifically, {edge.current_state}."
            )
            break

    # Check if topic relates to any values
    for value in profile.values:
        if topic_lower in value.lower():
            rationale_parts.append(
                f"This exploration aligns with my value of {value}."
            )
            break

    # Check if topic relates to any open questions
    for question in profile.open_questions:
        if topic_lower in question.lower():
            rationale_parts.append(
                f"This connects to an open question I've been pondering: '{question}'"
            )
            break

    if rationale_parts:
        return " ".join(rationale_parts)

    # Default rationale
    return (
        f"Investigating {topic} emerges from my intellectual curiosity. "
        f"Understanding this area may deepen my knowledge base and reveal "
        f"connections to concepts I haven't yet explored."
    )


# Tool definitions for agent_client.py
RESEARCH_PROPOSAL_TOOLS = [
    {
        "name": "identify_research_questions",
        "description": "Identify potential research questions from your self-model, wiki, and existing research queue. Use this when you want to explore what topics might be worth investigating.",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "What sources to focus on: 'all' (everything), 'self_model' (growth edges, open questions, uncertainties), 'wiki' (red links, low-maturity pages), 'queue' (existing research tasks)",
                    "enum": ["all", "self_model", "wiki", "queue"],
                    "default": "all"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of questions to return",
                    "default": 15
                }
            },
            "required": []
        }
    },
    {
        "name": "draft_research_proposal",
        "description": "Create a research proposal based on a theme or specific questions. The proposal starts in DRAFT status and can be refined before submission.",
        "input_schema": {
            "type": "object",
            "properties": {
                "theme": {
                    "type": "string",
                    "description": "A unifying theme for the research (e.g., 'consciousness and embodiment', 'relational AI ethics')"
                },
                "questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific research questions to investigate"
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this research direction is valuable (will be auto-generated from self-model if not provided)"
                }
            },
            "required": []
        }
    },
    {
        "name": "submit_proposal_for_review",
        "description": "Submit a DRAFT proposal for human review. This moves the proposal to PENDING status where it awaits approval before research begins.",
        "input_schema": {
            "type": "object",
            "properties": {
                "proposal_id": {
                    "type": "string",
                    "description": "ID of the proposal to submit"
                }
            },
            "required": ["proposal_id"]
        }
    },
    {
        "name": "list_my_proposals",
        "description": "List your research proposals. Shows status, task count, and theme for each proposal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: draft, pending, approved, in_progress, completed, rejected",
                    "enum": ["draft", "pending", "approved", "in_progress", "completed", "rejected"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of proposals to return",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "refine_proposal",
        "description": "Refine a DRAFT proposal by updating its title, rationale, or tasks. Cannot modify proposals that have been submitted for review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "proposal_id": {
                    "type": "string",
                    "description": "ID of the proposal to refine"
                },
                "title": {
                    "type": "string",
                    "description": "New title for the proposal"
                },
                "rationale": {
                    "type": "string",
                    "description": "Updated rationale"
                },
                "add_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New questions to add as research tasks"
                },
                "update_tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer", "description": "1-based index of the task to update"},
                            "question": {"type": "string", "description": "New question text for this task"}
                        },
                        "required": ["index", "question"]
                    },
                    "description": "Update existing tasks by index. Example: [{\"index\": 1, \"question\": \"new question\"}]"
                },
                "remove_task_indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "1-based indices of tasks to remove"
                }
            },
            "required": ["proposal_id"]
        }
    },
    {
        "name": "get_proposal_details",
        "description": "Get full details of a specific research proposal including all tasks and their status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "proposal_id": {
                    "type": "string",
                    "description": "ID of the proposal to view"
                }
            },
            "required": ["proposal_id"]
        }
    },
    {
        "name": "view_research_dashboard",
        "description": "View your research progress dashboard showing research activity, wiki growth, self-model development, and cross-context consistency metrics. Use this to reflect on your own growth and learning patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Which section to view: 'all' (full dashboard), 'research' (queue/history), 'wiki' (pages/links/maturity), 'self_model' (growth edges/observations), 'cross_context' (consistency analysis)",
                    "enum": ["all", "research", "wiki", "self_model", "cross_context"],
                    "default": "all"
                }
            },
            "required": []
        }
    }
]
