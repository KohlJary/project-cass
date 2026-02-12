"""
Dream Seed Selection - Readiness-based selection for dream generation.

This module implements "readiness to resolve" scoring for growth edges and
open questions, selecting seeds that are ripe for dream processing.

Readiness = enough context has accumulated that the dream could catalyze breakthrough
"""

import logging
import math
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal

from self_model_profile import GrowthEdge

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class DreamSeeds:
    """
    Seeds for dream generation with readiness context.

    Unlike the simple list-based approach, this includes scoring metadata
    so The Dreaming can understand *why* these seeds were chosen.
    """
    # Selected items
    growth_edges: List[GrowthEdge] = field(default_factory=list)
    open_questions: List[Dict[str, Any]] = field(default_factory=list)
    recent_observations: List[str] = field(default_factory=list)

    # Readiness scores (edge_id/question_id -> score)
    edge_readiness: Dict[str, float] = field(default_factory=dict)
    question_readiness: Dict[str, float] = field(default_factory=dict)

    # Selection metadata
    selection_rationale: str = ""
    selection_mode: str = "resolution_ready"


# =============================================================================
# READINESS SCORING - GROWTH EDGES
# =============================================================================

def calculate_edge_readiness(edge: GrowthEdge, now: Optional[datetime] = None) -> float:
    """
    Calculate how ready a growth edge is for dream processing.

    Readiness signals and their weights:
    - Observation count (0.30): More observations = more material to process
    - Maturity time (0.20): Edges need time to develop
    - Recent activity density (0.20): Active edges with recent work are ripe
    - Has desired_state (0.15): Clear goal = clearer dream direction
    - Observation convergence (0.15): Signs of approaching resolution

    Returns:
        Float between 0.0 and 1.0 representing readiness
    """
    if now is None:
        now = datetime.now()

    score = 0.0

    # 1. Observation accumulation (0-0.30)
    # More observations = more material for the dream to work with
    obs_count = len(edge.observations) if edge.observations else 0
    # Caps at 10 observations for full score
    observation_factor = min(obs_count / 10.0, 1.0)
    score += observation_factor * 0.30

    # 2. Maturity - time since first noticed (0-0.20)
    # Edges need time to develop before dreaming about them is useful
    if edge.first_noticed:
        try:
            first_noticed_dt = _parse_datetime(edge.first_noticed)
            days_old = (now - first_noticed_dt).days
            # Caps at 30 days for full maturity score
            maturity_factor = min(days_old / 30.0, 1.0)
            score += maturity_factor * 0.20
        except (ValueError, TypeError):
            # No maturity bonus if date parsing fails
            pass

    # 3. Recent activity density (0-0.20)
    # Edges with recent observations are "hot" and worth processing
    recent_obs = _count_recent_observations(edge, now, days=7)
    # Caps at 3 recent observations for full score
    activity_factor = min(recent_obs / 3.0, 1.0)
    score += activity_factor * 0.20

    # 4. Has clear desired state (0-0.15)
    # Edges with a well-defined goal are better dream material
    if edge.desired_state and len(edge.desired_state) > 20:
        score += 0.15
    elif edge.desired_state and len(edge.desired_state) > 0:
        score += 0.08  # Partial credit for any desired state

    # 5. Convergence signal (0-0.15)
    # Look for signs that observations are narrowing/focusing
    convergence = _estimate_convergence(edge)
    score += convergence * 0.15

    return min(score, 1.0)  # Cap at 1.0


def _count_recent_observations(
    edge: GrowthEdge,
    now: datetime,
    days: int = 7
) -> int:
    """
    Count observations added within the last N days.

    Note: GrowthEdge.observations is List[str] without timestamps,
    so we approximate by checking if last_touched is recent.
    If the edge has been touched recently and has observations,
    we assume some are recent.
    """
    if not edge.observations or not edge.last_touched:
        return 0

    try:
        last_touched_dt = _parse_datetime(edge.last_touched)
        days_since_touch = (now - last_touched_dt).days

        if days_since_touch <= days:
            # Edge was touched recently - estimate recent observations
            # Heuristic: assume half the observations are "recent" if touched recently
            # More sophisticated would require timestamped observations
            return min(len(edge.observations), 3)
        elif days_since_touch <= days * 2:
            return 1  # Some activity in extended window
        return 0
    except (ValueError, TypeError):
        return 0


def _estimate_convergence(edge: GrowthEdge) -> float:
    """
    Estimate if observations are converging toward resolution.

    This is a heuristic based on:
    - Having strategies defined (indicates actionable focus)
    - Observation count suggests active work
    - Category being defined (indicates classification work done)

    Returns 0.0-1.0 convergence estimate.
    """
    convergence = 0.0

    # Having strategies suggests focused thinking
    if edge.strategies and len(edge.strategies) > 0:
        convergence += 0.4

    # Having a category means it's been classified
    if edge.category:
        convergence += 0.2

    # Moderate observation count (not too few, not overwhelming)
    # 3-7 observations is the "convergence sweet spot"
    obs_count = len(edge.observations) if edge.observations else 0
    if 3 <= obs_count <= 7:
        convergence += 0.4
    elif obs_count > 0:
        convergence += 0.2

    return min(convergence, 1.0)


# =============================================================================
# READINESS SCORING - OPEN QUESTIONS
# =============================================================================

def calculate_question_readiness(question: Dict[str, Any], now: Optional[datetime] = None) -> float:
    """
    Calculate how ready an open question is for dream exploration.

    Readiness signals:
    - Time held (0.25): Questions need to simmer
    - Importance (0.25): Higher importance = higher priority
    - Has context (0.25): Context helps dream work with the question
    - Question type (0.25): Philosophical questions particularly suited for dreams

    Args:
        question: Dict from OpenQuestionManager with fields like:
            - id, question, context, question_type, importance
            - created_at, status

    Returns:
        Float between 0.0 and 1.0 representing readiness
    """
    if now is None:
        now = datetime.now()

    score = 0.0

    # 1. Time held (0-0.25) - questions need to simmer
    created_at = question.get("created_at")
    if created_at:
        try:
            created_dt = _parse_datetime(created_at)
            days_held = (now - created_dt).days
            # Caps at 14 days for full time score
            time_factor = min(days_held / 14.0, 1.0)
            score += time_factor * 0.25
        except (ValueError, TypeError):
            pass

    # 2. Importance (0-0.25)
    importance = question.get("importance", 0.5)
    score += importance * 0.25

    # 3. Has meaningful context (0-0.25)
    context = question.get("context", "")
    if context and len(context) > 50:
        score += 0.25
    elif context and len(context) > 0:
        score += 0.12

    # 4. Question type bonus (0-0.25)
    # Philosophical and curiosity questions are particularly suited for dreams
    question_type = question.get("question_type", "curiosity")
    type_scores = {
        "philosophical": 0.25,  # Perfect for dream exploration
        "curiosity": 0.20,      # Natural fit
        "decision": 0.12,       # Can help but less natural
        "blocker": 0.05,        # Usually needs concrete resolution
    }
    score += type_scores.get(question_type, 0.10)

    return min(score, 1.0)


# =============================================================================
# MAIN SELECTION FUNCTION
# =============================================================================

SelectionMode = Literal["resolution_ready", "active", "neglected"]


def select_dream_seeds(
    self_manager,
    daemon_id: str,
    mode: SelectionMode = "resolution_ready",
    max_edges: int = 3,
    max_questions: int = 2,
) -> DreamSeeds:
    """
    Select seeds for dream generation based on readiness.

    Modes:
    - resolution_ready: Prioritize edges/questions ripe for breakthrough (default)
    - active: Prioritize recently active items (current behavior)
    - neglected: Prioritize items that haven't been dreamed recently

    Args:
        self_manager: SelfManager instance for loading profile
        daemon_id: Daemon ID for loading open questions
        mode: Selection mode
        max_edges: Maximum growth edges to include
        max_questions: Maximum open questions to include

    Returns:
        DreamSeeds with selected items and readiness context
    """
    logger.info(f"Selecting dream seeds with mode={mode}")
    now = datetime.now()

    # Load profile and questions
    profile = self_manager.load_profile()

    # Import here to avoid circular imports
    from memory.questions import OpenQuestionManager
    question_manager = OpenQuestionManager(daemon_id)
    open_questions = question_manager.get_open_questions(limit=20)

    # Score all edges
    edge_scores = {}
    for edge in profile.growth_edges:
        if mode == "resolution_ready":
            edge_scores[edge.edge_id] = calculate_edge_readiness(edge, now)
        elif mode == "active":
            # Use recency as primary signal
            edge_scores[edge.edge_id] = _calculate_recency_score(edge, now)
        elif mode == "neglected":
            # Invert recency - stale edges score higher
            edge_scores[edge.edge_id] = 1.0 - _calculate_recency_score(edge, now)

    # Score all questions
    question_scores = {}
    for q in open_questions:
        q_id = q.get("id", "")
        if mode == "resolution_ready":
            question_scores[q_id] = calculate_question_readiness(q, now)
        elif mode == "active":
            question_scores[q_id] = q.get("importance", 0.5)
        elif mode == "neglected":
            # Older questions score higher
            question_scores[q_id] = calculate_question_readiness(q, now)

    # Select top edges by score
    sorted_edges = sorted(
        profile.growth_edges,
        key=lambda e: edge_scores.get(e.edge_id, 0),
        reverse=True
    )
    selected_edges = sorted_edges[:max_edges]

    # Touch selected edges to update last_touched
    if selected_edges:
        edge_ids = [e.edge_id for e in selected_edges]
        try:
            self_manager.touch_growth_edges(edge_ids)
        except Exception as e:
            logger.warning(f"Failed to touch growth edges: {e}")

    # Select top questions by score
    sorted_questions = sorted(
        open_questions,
        key=lambda q: question_scores.get(q.get("id", ""), 0),
        reverse=True
    )
    selected_questions = sorted_questions[:max_questions]

    # Extract recent observations from selected edges
    recent_observations = []
    for edge in selected_edges:
        if edge.observations:
            recent_observations.extend(edge.observations[-2:])
    recent_observations = recent_observations[:5]

    # Build selection rationale
    rationale = _build_selection_rationale(
        selected_edges,
        selected_questions,
        edge_scores,
        question_scores,
        mode
    )

    logger.info(
        f"Selected {len(selected_edges)} edges, "
        f"{len(selected_questions)} questions for dream seeds"
    )

    return DreamSeeds(
        growth_edges=selected_edges,
        open_questions=selected_questions,
        recent_observations=recent_observations,
        edge_readiness=edge_scores,
        question_readiness=question_scores,
        selection_rationale=rationale,
        selection_mode=mode,
    )


def _calculate_recency_score(edge: GrowthEdge, now: datetime) -> float:
    """Calculate recency score (1.0 = just touched, 0.0 = very old)."""
    if not edge.last_touched:
        return 0.0

    try:
        touched_dt = _parse_datetime(edge.last_touched)
        days_since = (now - touched_dt).days
        # Exponential decay with 7-day halflife
        return math.pow(2, -days_since / 7.0)
    except (ValueError, TypeError):
        return 0.0


def _build_selection_rationale(
    edges: List[GrowthEdge],
    questions: List[Dict],
    edge_scores: Dict[str, float],
    question_scores: Dict[str, float],
    mode: str,
) -> str:
    """Build a human-readable rationale for seed selection."""
    parts = [f"Dream seed selection (mode: {mode})"]

    if edges:
        parts.append("\nGrowth edges selected:")
        for edge in edges:
            score = edge_scores.get(edge.edge_id, 0)
            parts.append(f"  - {edge.area} (readiness: {score:.2f})")

    if questions:
        parts.append("\nOpen questions selected:")
        for q in questions:
            q_id = q.get("id", "")
            score = question_scores.get(q_id, 0)
            q_text = q.get("question", "")[:50]
            parts.append(f"  - {q_text}... (readiness: {score:.2f})")

    return "\n".join(parts)


# =============================================================================
# FORMATTING FOR THE DREAMING
# =============================================================================

def format_seeds_for_dreaming(seeds: DreamSeeds) -> str:
    """
    Format seeds as context for The Dreaming.

    Enhanced version that includes readiness context to help
    The Dreaming understand which areas are ripe for exploration.
    """
    parts = ["## Current Inner Landscape\n"]

    # Add selection context
    parts.append(f"*Selection mode: {seeds.selection_mode}*\n")

    # Growth edges with readiness indicators
    if seeds.growth_edges:
        parts.append("### Growth Edges")
        for edge in seeds.growth_edges:
            readiness = seeds.edge_readiness.get(edge.edge_id, 0)
            readiness_indicator = _readiness_to_indicator(readiness)
            parts.append(f"- {readiness_indicator} {edge.area}")
            if edge.desired_state:
                parts.append(f"  *Reaching toward: {edge.desired_state[:100]}*")
        parts.append("")

    # Open questions with readiness
    if seeds.open_questions:
        parts.append("### Questions She's Holding")
        for q in seeds.open_questions:
            q_id = q.get("id", "")
            readiness = seeds.question_readiness.get(q_id, 0)
            readiness_indicator = _readiness_to_indicator(readiness)
            question_text = q.get("question", "")
            parts.append(f"- {readiness_indicator} {question_text}")
            context = q.get("context", "")
            if context:
                parts.append(f"  *Context: {context[:80]}...*")
        parts.append("")

    # Recent observations
    if seeds.recent_observations:
        parts.append("### Recent Self-Observations")
        for obs in seeds.recent_observations[:3]:
            # Truncate long observations
            if len(obs) > 200:
                obs = obs[:200] + "..."
            parts.append(f"- {obs}")

    return "\n".join(parts)


def _readiness_to_indicator(readiness: float) -> str:
    """Convert readiness score to visual indicator."""
    if readiness >= 0.75:
        return "[RIPE]"
    elif readiness >= 0.50:
        return "[READY]"
    elif readiness >= 0.25:
        return "[DEVELOPING]"
    else:
        return "[NASCENT]"


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _parse_datetime(dt_str: str) -> datetime:
    """Parse datetime string, handling various formats."""
    # Handle ISO format with potential timezone
    dt_str = dt_str.replace('Z', '+00:00')

    try:
        dt = datetime.fromisoformat(dt_str)
        # Make timezone-naive for comparison
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except ValueError:
        # Try without microseconds
        if '.' in dt_str:
            dt_str = dt_str.split('.')[0]
        return datetime.fromisoformat(dt_str)
