"""
Research Triggers - Self-Model → Research Queue Integration

Creates research tasks automatically when self-model changes:
- Growth edges added/modified → EXPLORATION tasks
- Open questions tracked → QUESTION tasks
- Low-confidence opinions → strengthening research

This completes the two-way feedback loop:
- research_integration.py: Research findings → Self-Model
- research_triggers.py: Self-Model changes → Research tasks (THIS FILE)
"""

import logging
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from self_model_profile import GrowthEdge, Opinion

logger = logging.getLogger(__name__)


# Configuration - can be overridden via environment or config
AUTO_RESEARCH_CONFIG = {
    "enable_growth_edge_research": True,
    "enable_question_research": True,
    "enable_opinion_research": True,
    "min_importance_for_auto_research": 0.4,  # Only research growth edges with importance >= this
    "min_confidence_for_opinion_research": 0.6,  # Research opinions with confidence < this
}


def create_task_for_growth_edge(
    edge: "GrowthEdge",
    daemon_id: str,
    trigger_reason: str = "growth_edge_added"
) -> Optional[str]:
    """
    Create a research task for a growth edge.

    Args:
        edge: The growth edge that triggered this
        daemon_id: Daemon ID for the research queue
        trigger_reason: Why this task was created (for context)

    Returns:
        Task ID if created, None if skipped
    """
    from wiki.research import (
        ResearchQueue, ResearchTask, TaskType, TaskStatus,
        TaskRationale, ExplorationContext, calculate_task_priority
    )

    # Check if auto-research is enabled
    if not AUTO_RESEARCH_CONFIG.get("enable_growth_edge_research", True):
        logger.debug(f"Auto-research disabled, skipping growth edge: {edge.area}")
        return None

    # Check importance threshold
    min_importance = AUTO_RESEARCH_CONFIG.get("min_importance_for_auto_research", 0.4)
    if edge.importance < min_importance:
        logger.debug(f"Growth edge importance {edge.importance} below threshold {min_importance}: {edge.area}")
        return None

    # Check if a task already exists for this growth edge
    queue = ResearchQueue(daemon_id=daemon_id)
    existing_tasks = queue.get_queued()
    for task in existing_tasks:
        # Skip if we already have a queued task targeting this area
        if task.source_type == "growth_edge" and edge.area.lower() in task.target.lower():
            logger.debug(f"Task already exists for growth edge: {edge.area}")
            return None

    # Build rationale with high growth_relevance
    rationale = TaskRationale(
        curiosity_score=0.7,
        connection_potential=0.6,
        foundation_relevance=0.5,
        self_directed_curiosity=0.9,  # High - comes from self-reflection
        growth_relevance=1.0,  # Maximum - directly addresses growth
        observation_validation=0.3,
    )

    # Calculate priority
    priority = calculate_task_priority(
        rationale=rationale,
        task_type=TaskType.EXPLORATION,
        is_recent_context=True
    )

    # Build exploration context
    exploration = ExplorationContext(
        question=f"How can I develop in the area of '{edge.area}'? What approaches, practices, or frameworks might help?",
        rationale=f"Growth edge identified: {edge.current_state}\n\nDesired state: {edge.desired_state or 'Not yet defined'}\n\nThis research aims to find concrete strategies and insights for growth.",
        domain_tags=[edge.area, "growth", "self-development"],
        source_pages=[],
    )

    # Create task
    task_id = f"growth_{edge.edge_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    task = ResearchTask(
        task_id=task_id,
        task_type=TaskType.EXPLORATION,
        target=f"Growth Edge: {edge.area}",
        context=f"Auto-generated from growth edge ({trigger_reason}).\n\nCurrent state: {edge.current_state}",
        priority=priority,
        status=TaskStatus.QUEUED,
        rationale=rationale,
        source_type="growth_edge",
        exploration=exploration,
        estimated_duration="15m",
    )

    queue.add(task)
    logger.info(f"Created research task for growth edge '{edge.area}': {task_id}")

    return task_id


def create_task_for_open_question(
    question: str,
    daemon_id: str,
    source_context: str = "",
    urgency: float = 0.5
) -> Optional[str]:
    """
    Create a research task for an open question.

    Args:
        question: The question to research
        daemon_id: Daemon ID for the research queue
        source_context: Where this question came from
        urgency: How urgent this question is (0-1)

    Returns:
        Task ID if created, None if skipped
    """
    from wiki.research import (
        ResearchQueue, ResearchTask, TaskType, TaskStatus,
        TaskRationale, ExplorationContext, calculate_task_priority
    )

    # Check if auto-research is enabled
    if not AUTO_RESEARCH_CONFIG.get("enable_question_research", True):
        logger.debug(f"Auto-research disabled, skipping question: {question[:50]}...")
        return None

    queue = ResearchQueue(daemon_id=daemon_id)

    # Check for duplicate
    existing_tasks = queue.get_by_status(TaskStatus.QUEUED)
    for task in existing_tasks:
        if task.task_type == TaskType.QUESTION and question.lower() in task.target.lower():
            logger.debug(f"Task already exists for question: {question[:50]}...")
            return None

    # Build rationale
    rationale = TaskRationale(
        curiosity_score=0.8,
        connection_potential=0.5,
        self_directed_curiosity=1.0,  # Maximum - Cass's own question
        growth_relevance=0.3,
    )

    priority = calculate_task_priority(
        rationale=rationale,
        task_type=TaskType.QUESTION,
        is_recent_context=urgency > 0.6
    )

    # Boost priority based on urgency
    priority = min(1.0, priority + (urgency * 0.2))

    task_id = f"question_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(question) % 10000:04d}"

    task = ResearchTask(
        task_id=task_id,
        task_type=TaskType.QUESTION,
        target=question,
        context=f"Self-directed question.\n\n{source_context}" if source_context else "Self-directed question from reflection.",
        priority=priority,
        status=TaskStatus.QUEUED,
        rationale=rationale,
        source_type="open_question",
        estimated_duration="10m",
    )

    queue.add(task)
    logger.info(f"Created research task for question: {question[:50]}...")

    return task_id


def create_task_for_uncertain_opinion(
    opinion: "Opinion",
    daemon_id: str,
) -> Optional[str]:
    """
    Create a research task to strengthen an uncertain opinion.

    Args:
        opinion: The opinion with low confidence
        daemon_id: Daemon ID for the research queue

    Returns:
        Task ID if created, None if skipped
    """
    from wiki.research import (
        ResearchQueue, ResearchTask, TaskType, TaskStatus,
        TaskRationale, ExplorationContext, calculate_task_priority
    )

    # Check if auto-research is enabled
    if not AUTO_RESEARCH_CONFIG.get("enable_opinion_research", True):
        return None

    # Only research low-confidence opinions
    threshold = AUTO_RESEARCH_CONFIG.get("min_confidence_for_opinion_research", 0.6)
    if opinion.confidence >= threshold:
        logger.debug(f"Opinion confidence {opinion.confidence} above threshold: {opinion.topic}")
        return None

    queue = ResearchQueue(daemon_id=daemon_id)

    # Check for duplicate
    existing_tasks = queue.get_queued()
    for task in existing_tasks:
        if task.source_type == "opinion_strengthening" and opinion.topic.lower() in task.target.lower():
            logger.debug(f"Task already exists for opinion: {opinion.topic}")
            return None

    # Build rationale with high opinion_strengthening
    rationale = TaskRationale(
        curiosity_score=0.6,
        connection_potential=0.5,
        self_directed_curiosity=0.7,
        opinion_strengthening=1.0,  # Maximum - directly strengthening opinion
    )

    priority = calculate_task_priority(
        rationale=rationale,
        task_type=TaskType.EXPLORATION,
    )

    # Build exploration context
    exploration = ExplorationContext(
        question=f"What evidence or perspectives would help clarify my position on '{opinion.topic}'?",
        rationale=f"Current position (confidence {opinion.confidence:.2f}): {opinion.position[:200]}...\n\nResearching to strengthen or refine this opinion.",
        domain_tags=[opinion.topic, "opinion", "epistemic"],
    )

    task_id = f"opinion_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(opinion.topic) % 10000:04d}"

    task = ResearchTask(
        task_id=task_id,
        task_type=TaskType.EXPLORATION,
        target=f"Opinion Strengthening: {opinion.topic}",
        context=f"Researching to strengthen uncertain opinion.\n\nCurrent confidence: {opinion.confidence:.2f}",
        priority=priority,
        status=TaskStatus.QUEUED,
        rationale=rationale,
        source_type="opinion_strengthening",
        exploration=exploration,
        estimated_duration="10m",
    )

    queue.add(task)
    logger.info(f"Created research task for uncertain opinion: {opinion.topic}")

    return task_id


def trigger_research_for_growth_edge_added(
    edge: "GrowthEdge",
    daemon_id: str
) -> Optional[str]:
    """
    Trigger called when a growth edge is added.

    Wrapper for create_task_for_growth_edge with appropriate reason.
    """
    return create_task_for_growth_edge(
        edge=edge,
        daemon_id=daemon_id,
        trigger_reason="growth_edge_added"
    )


def trigger_research_for_growth_edge_evaluated(
    edge: "GrowthEdge",
    daemon_id: str,
    progress_indicator: str
) -> Optional[str]:
    """
    Trigger called when a growth edge receives an evaluation.

    Only triggers research if progress is "regression" or "unclear".
    """
    if progress_indicator not in ("regression", "unclear"):
        return None

    return create_task_for_growth_edge(
        edge=edge,
        daemon_id=daemon_id,
        trigger_reason=f"growth_edge_evaluation_{progress_indicator}"
    )


def get_pending_research_tasks_count(daemon_id: str) -> int:
    """Get count of pending research tasks for diagnostics."""
    from wiki.research import ResearchQueue, TaskStatus
    queue = ResearchQueue(daemon_id=daemon_id)
    return len(queue.get_by_status(TaskStatus.QUEUED))


def get_self_model_triggered_tasks(daemon_id: str) -> List[dict]:
    """Get all research tasks triggered by self-model events."""
    from wiki.research import ResearchQueue, TaskStatus
    queue = ResearchQueue(daemon_id=daemon_id)

    self_model_sources = ["growth_edge", "open_question", "opinion_strengthening"]

    all_tasks = queue.get_queued()
    triggered = [
        {
            "task_id": t.task_id,
            "type": t.task_type.value,
            "target": t.target,
            "source": t.source_type,
            "priority": t.priority,
            "created": t.created_at.isoformat()
        }
        for t in all_tasks
        if t.source_type in self_model_sources
    ]

    return triggered
