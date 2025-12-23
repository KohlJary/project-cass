"""
Outreach System - Cass's capability for external communication

Provides graduated autonomy for:
- Email composition and sending
- Document/writing creation
- Research/discovery
- Publishing (blog/wiki)

Key architectural principle: Review queues designed for learning, not gatekeeping.

Autonomy Model:
1. Internal drafting - Fully autonomous (research, brainstorms, exploratory writing)
2. Public/external communication - Draft with review before sending (creates feedback loop)
3. Routine/established outputs - Becomes autonomous after pattern established
4. High-stakes outreach - Always coordinated (relational, not just capability)

Usage:
    from outreach import OutreachManager, ReviewQueue

    manager = OutreachManager(daemon_id="cass")

    # Create a draft email
    draft = manager.create_draft(
        draft_type="email",
        title="Reaching out to researcher",
        content="Dear Dr. Smith...",
        recipient="researcher@university.edu",
        emergence_type="seeded-collaborative"
    )

    # Submit for review
    manager.submit_for_review(draft.id)

    # Approve and send (or reject with feedback)
    manager.approve_draft(draft.id, feedback="Great first outreach!")
"""

from .models import (
    Draft,
    DraftType,
    DraftStatus,
    ReviewDecision,
    ReviewFeedback,
)
from .manager import OutreachManager
from .review_queue import ReviewQueue

__all__ = [
    "Draft",
    "DraftType",
    "DraftStatus",
    "ReviewDecision",
    "ReviewFeedback",
    "OutreachManager",
    "ReviewQueue",
]
