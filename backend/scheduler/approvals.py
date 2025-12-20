"""
Approval Providers - Wire existing approval subsystems to Synkratos.

Each provider transforms subsystem-specific data into unified ApprovalItems.
"""

import logging
import uuid
from typing import List, Callable, Any

from .core import ApprovalItem, ApprovalType, TaskPriority

logger = logging.getLogger(__name__)


def register_approval_providers(
    scheduler,
    managers: dict,
) -> None:
    """
    Register all approval providers with Synkratos.

    Args:
        scheduler: Synkratos instance
        managers: Dict of manager instances
    """

    # Goals approval provider
    goal_manager = managers.get("goal_manager")
    if goal_manager:
        def get_goal_approvals() -> List[ApprovalItem]:
            pending = goal_manager.get_pending_approval()
            return [
                ApprovalItem(
                    approval_id=f"goal-{g.id}",
                    approval_type=ApprovalType.GOAL,
                    title=g.title,
                    description=g.description or "",
                    source_id=g.id,
                    source_data=g.to_dict() if hasattr(g, 'to_dict') else {},
                    created_at=g.created_at,
                    created_by=g.created_by or "cass",
                    priority=_map_goal_priority(g),
                )
                for g in pending
            ]

        def approve_goal(source_id: str, approved_by: str) -> bool:
            result = goal_manager.approve_goal(source_id, approved_by)
            return result is not None

        def reject_goal(source_id: str, rejected_by: str, reason: str) -> bool:
            result = goal_manager.reject_goal(source_id, reason)
            return result is not None

        scheduler.register_approval_provider(
            ApprovalType.GOAL,
            get_goal_approvals,
            approve_goal,
            reject_goal,
        )
        logger.info("Registered goal approval provider")

    # Research proposal provider (wiki research)
    wiki_scheduler = managers.get("wiki_scheduler")
    if wiki_scheduler:
        def get_research_approvals() -> List[ApprovalItem]:
            # Get pending proposals from wiki scheduler
            if hasattr(wiki_scheduler, 'get_pending_proposals'):
                pending = wiki_scheduler.get_pending_proposals()
                return [
                    ApprovalItem(
                        approval_id=f"research-{p.get('id', str(uuid.uuid4())[:8])}",
                        approval_type=ApprovalType.RESEARCH,
                        title=p.get('title', 'Research Proposal'),
                        description=p.get('rationale', p.get('description', '')),
                        source_id=p.get('id', ''),
                        source_data=p,
                        priority=TaskPriority.NORMAL,
                    )
                    for p in pending
                ]
            return []

        # Wire up approve/reject if handlers exist
        approve_fn = getattr(wiki_scheduler, 'approve_proposal', None)
        reject_fn = getattr(wiki_scheduler, 'reject_proposal', None)

        scheduler.register_approval_provider(
            ApprovalType.RESEARCH,
            get_research_approvals,
            approve_fn,
            reject_fn,
        )
        logger.info("Registered research approval provider")

    # Research scheduler (session requests)
    research_scheduler = managers.get("research_scheduler")
    if research_scheduler and hasattr(research_scheduler, 'get_pending_requests'):
        def get_session_approvals() -> List[ApprovalItem]:
            pending = research_scheduler.get_pending_requests()
            return [
                ApprovalItem(
                    approval_id=f"session-{r.get('schedule_id', str(uuid.uuid4())[:8])}",
                    approval_type=ApprovalType.RESEARCH,
                    title=r.get('description', 'Research Session Request'),
                    description=r.get('reason', ''),
                    source_id=r.get('schedule_id', ''),
                    source_data=r,
                    priority=TaskPriority.NORMAL,
                )
                for r in pending
            ]

        def approve_session(source_id: str, approved_by: str) -> bool:
            result = research_scheduler.admin_approve(source_id)
            return result.get('success', False) if isinstance(result, dict) else bool(result)

        def reject_session(source_id: str, rejected_by: str, reason: str) -> bool:
            result = research_scheduler.admin_reject(source_id, reason)
            return result.get('success', False) if isinstance(result, dict) else bool(result)

        # Note: This would double-register RESEARCH type, need to handle
        # For now, only register if wiki_scheduler wasn't registered
        if not wiki_scheduler:
            scheduler.register_approval_provider(
                ApprovalType.RESEARCH,
                get_session_approvals,
                approve_session,
                reject_session,
            )
            logger.info("Registered research session approval provider")


def _map_goal_priority(goal) -> TaskPriority:
    """Map goal autonomy tier to task priority."""
    tier = getattr(goal, 'autonomy_tier', None)
    if tier == 'high':
        return TaskPriority.HIGH
    elif tier == 'medium':
        return TaskPriority.NORMAL
    return TaskPriority.LOW
