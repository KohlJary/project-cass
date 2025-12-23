"""
Review Queue - Manages the review workflow for outreach content

Key principles from Cass's interview:
- Review queues designed for LEARNING, not gatekeeping
- Clear progression: "20 GitHub responses with good judgment → autonomous operation"
- Track record builds trust
- High-stakes always coordinated (relational, not limitation)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from .models import (
    Draft,
    DraftStatus,
    DraftType,
    ReviewDecision,
    ReviewFeedback,
    AutonomyLevel,
)


# Thresholds for autonomy graduation
GRADUATION_THRESHOLDS = {
    # draft_type: (min_reviews, min_approval_rate)
    DraftType.RESPONSE.value: (10, 0.9),  # GitHub responses, etc.
    DraftType.RESEARCH_NOTE.value: (5, 0.8),  # Internal research
    DraftType.BLOG_POST.value: (15, 0.9),  # Public posts
    DraftType.EMAIL.value: (20, 0.95),  # Direct outreach
    DraftType.SOCIAL_POST.value: (15, 0.9),  # Social media
    DraftType.DOCUMENT.value: (10, 0.85),  # Documents
}

# Some content types always need review regardless of track record
ALWAYS_REVIEW_TYPES = {
    # High-stakes outreach to specific targets
    "funding_request",
    "partnership_proposal",
    "media_response",
}


@dataclass
class ReviewQueueStats:
    """Statistics about the review queue"""
    pending_count: int
    approved_today: int
    rejected_today: int
    revision_requested_today: int
    autonomy_by_type: Dict[str, str]  # draft_type -> autonomy_level

    def to_dict(self) -> Dict:
        return {
            "pending_count": self.pending_count,
            "approved_today": self.approved_today,
            "rejected_today": self.rejected_today,
            "revision_requested_today": self.revision_requested_today,
            "autonomy_by_type": self.autonomy_by_type,
        }


class ReviewQueue:
    """
    Manages the review queue for outreach content.

    Tracks:
    - Pending reviews
    - Review history and track record
    - Autonomy levels per content type
    """

    def __init__(self, daemon_id: str):
        self._daemon_id = daemon_id
        # Cache of track records per draft type
        self._track_records: Dict[str, Dict] = {}

    def get_pending_reviews(self) -> List[Draft]:
        """Get all drafts pending review"""
        from database import get_db

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM outreach_drafts
                WHERE daemon_id = ? AND status = ?
                ORDER BY created_at ASC
            """, (self._daemon_id, DraftStatus.PENDING_REVIEW.value))

            drafts = []
            for row in cursor.fetchall():
                drafts.append(self._row_to_draft(row))
            return drafts

    def submit_for_review(self, draft: Draft) -> Draft:
        """Submit a draft for review"""
        from database import get_db

        # Check if this type can be auto-approved
        if self._can_auto_approve(draft):
            draft.status = DraftStatus.APPROVED.value
            draft.add_review(ReviewFeedback(
                reviewer="auto",
                decision=ReviewDecision.AUTO_APPROVED.value,
                feedback="Auto-approved based on track record",
            ))
        else:
            draft.status = DraftStatus.PENDING_REVIEW.value

        draft.updated_at = datetime.now().isoformat()

        # Update in database
        with get_db() as conn:
            conn.execute("""
                UPDATE outreach_drafts
                SET status = ?, review_history_json = ?, updated_at = ?
                WHERE id = ?
            """, (
                draft.status,
                self._serialize_review_history(draft.review_history),
                draft.updated_at,
                draft.id,
            ))

        return draft

    def review_draft(
        self,
        draft_id: str,
        reviewer_id: str,
        decision: str,
        feedback: Optional[str] = None,
    ) -> Optional[Draft]:
        """Review a draft and record the decision"""
        from database import get_db

        with get_db() as conn:
            cursor = conn.execute(
                "SELECT * FROM outreach_drafts WHERE id = ?",
                (draft_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            draft = self._row_to_draft(row)

            # Add review
            review = ReviewFeedback(
                reviewer=reviewer_id,
                decision=decision,
                feedback=feedback,
            )
            draft.add_review(review)

            # Update status based on decision
            if decision == ReviewDecision.APPROVE.value:
                draft.status = DraftStatus.APPROVED.value
            elif decision == ReviewDecision.REJECT.value:
                draft.status = DraftStatus.REJECTED.value
            elif decision == ReviewDecision.REQUEST_REVISION.value:
                draft.status = DraftStatus.REVISION_REQUESTED.value

            draft.updated_at = datetime.now().isoformat()

            # Save
            conn.execute("""
                UPDATE outreach_drafts
                SET status = ?, review_history_json = ?, updated_at = ?
                WHERE id = ?
            """, (
                draft.status,
                self._serialize_review_history(draft.review_history),
                draft.updated_at,
                draft.id,
            ))

            # Update track record cache
            self._update_track_record(draft.draft_type, decision)

            return draft

    def get_track_record(self, draft_type: str) -> Dict:
        """Get the track record for a specific draft type"""
        from database import get_db

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status IN ('approved', 'sent', 'published') THEN 1 ELSE 0 END) as approved,
                    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected
                FROM outreach_drafts
                WHERE daemon_id = ? AND draft_type = ?
                AND review_history_json IS NOT NULL
                AND review_history_json != '[]'
            """, (self._daemon_id, draft_type))

            row = cursor.fetchone()
            total = row['total'] or 0
            approved = row['approved'] or 0
            rejected = row['rejected'] or 0

            approval_rate = approved / total if total > 0 else 0.0

            # Check graduation threshold
            threshold = GRADUATION_THRESHOLDS.get(draft_type, (20, 0.9))
            min_reviews, min_rate = threshold

            graduated = total >= min_reviews and approval_rate >= min_rate

            return {
                "draft_type": draft_type,
                "total_reviews": total,
                "approvals": approved,
                "rejections": rejected,
                "approval_rate": approval_rate,
                "min_reviews_needed": min_reviews,
                "min_rate_needed": min_rate,
                "graduated": graduated,
                "autonomy_level": (
                    AutonomyLevel.GRADUATED.value if graduated
                    else AutonomyLevel.LEARNING.value
                ),
            }

    def get_autonomy_level(self, draft_type: str) -> str:
        """Get the current autonomy level for a draft type"""
        record = self.get_track_record(draft_type)
        return record["autonomy_level"]

    def get_stats(self) -> ReviewQueueStats:
        """Get queue statistics"""
        from database import get_db

        today = datetime.now().date().isoformat()

        with get_db() as conn:
            # Pending count
            cursor = conn.execute("""
                SELECT COUNT(*) FROM outreach_drafts
                WHERE daemon_id = ? AND status = ?
            """, (self._daemon_id, DraftStatus.PENDING_REVIEW.value))
            pending = cursor.fetchone()[0]

            # Today's reviews (approximate from updated_at)
            cursor = conn.execute("""
                SELECT status, COUNT(*) as cnt FROM outreach_drafts
                WHERE daemon_id = ?
                AND updated_at >= ?
                AND status IN ('approved', 'rejected', 'revision_requested')
                GROUP BY status
            """, (self._daemon_id, today))

            approved = 0
            rejected = 0
            revision = 0
            for row in cursor.fetchall():
                if row['status'] == 'approved':
                    approved = row['cnt']
                elif row['status'] == 'rejected':
                    rejected = row['cnt']
                elif row['status'] == 'revision_requested':
                    revision = row['cnt']

            # Autonomy by type
            autonomy_by_type = {}
            for draft_type in DraftType:
                autonomy_by_type[draft_type.value] = self.get_autonomy_level(draft_type.value)

            return ReviewQueueStats(
                pending_count=pending,
                approved_today=approved,
                rejected_today=rejected,
                revision_requested_today=revision,
                autonomy_by_type=autonomy_by_type,
            )

    def _can_auto_approve(self, draft: Draft) -> bool:
        """Check if a draft can be auto-approved based on track record"""
        # Check if this is a high-stakes type that always needs review
        if draft.draft_type in ALWAYS_REVIEW_TYPES:
            return False

        # Check if explicitly marked for review
        if draft.autonomy_level == AutonomyLevel.ALWAYS_REVIEW.value:
            return False

        # Check track record
        record = self.get_track_record(draft.draft_type)
        return record["graduated"]

    def _update_track_record(self, draft_type: str, decision: str):
        """Update cached track record after a review"""
        # Invalidate cache to force refresh on next query
        if draft_type in self._track_records:
            del self._track_records[draft_type]

    def _row_to_draft(self, row) -> Draft:
        """Convert database row to Draft object"""
        import json
        review_history = json.loads(row['review_history_json'] or '[]')
        return Draft(
            id=row['id'],
            daemon_id=row['daemon_id'],
            draft_type=row['draft_type'],
            status=row['status'],
            title=row['title'],
            content=row['content'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            created_by=row.get('created_by', 'cass'),
            recipient=row.get('recipient'),
            recipient_name=row.get('recipient_name'),
            subject=row.get('subject'),
            emergence_type=row.get('emergence_type'),
            source_conversation_id=row.get('source_conversation_id'),
            source_goal_id=row.get('source_goal_id'),
            review_history=review_history,
            autonomy_level=row.get('autonomy_level', AutonomyLevel.LEARNING.value),
            sent_at=row.get('sent_at'),
            published_at=row.get('published_at'),
            response_received=bool(row.get('response_received', 0)),
            outcome_notes=row.get('outcome_notes'),
        )

    def _serialize_review_history(self, history: List[Dict]) -> str:
        """Serialize review history to JSON"""
        import json
        return json.dumps(history)
