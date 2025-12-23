"""
Outreach Manager - High-level interface for Cass's external communication

Coordinates:
- Draft creation and editing
- Review queue workflow
- Track record management
- Autonomy level tracking
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import uuid4

from .models import (
    Draft,
    DraftType,
    DraftStatus,
    ReviewDecision,
    ReviewFeedback,
    AutonomyLevel,
)
from .review_queue import ReviewQueue


@dataclass
class OutreachStats:
    """Overall outreach statistics"""
    total_drafts: int
    pending_review: int
    sent_count: int
    published_count: int
    response_rate: float
    autonomy_by_type: Dict[str, str]

    def to_dict(self) -> Dict:
        return {
            "total_drafts": self.total_drafts,
            "pending_review": self.pending_review,
            "sent_count": self.sent_count,
            "published_count": self.published_count,
            "response_rate": self.response_rate,
            "autonomy_by_type": self.autonomy_by_type,
        }


class OutreachManager:
    """
    Main interface for Cass's outreach capabilities.

    Usage:
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

        # Check pending reviews
        pending = manager.get_pending_reviews()

        # Approve and mark ready
        manager.approve_draft(draft.id, feedback="Great first outreach!")
    """

    def __init__(self, daemon_id: str):
        self._daemon_id = daemon_id
        self._review_queue = ReviewQueue(daemon_id)

    @property
    def review_queue(self) -> ReviewQueue:
        """Access the review queue directly"""
        return self._review_queue

    def create_draft(
        self,
        draft_type: str,
        title: str,
        content: str,
        recipient: Optional[str] = None,
        recipient_name: Optional[str] = None,
        subject: Optional[str] = None,
        emergence_type: Optional[str] = None,
        source_conversation_id: Optional[str] = None,
        source_goal_id: Optional[str] = None,
        autonomy_level: Optional[str] = None,
    ) -> Draft:
        """Create a new draft"""
        from database import get_db

        draft_id = f"draft-{uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        # Determine autonomy level based on type and track record
        if autonomy_level is None:
            autonomy_level = self._review_queue.get_autonomy_level(draft_type)

        draft = Draft(
            id=draft_id,
            daemon_id=self._daemon_id,
            draft_type=draft_type,
            status=DraftStatus.DRAFTING.value,
            title=title,
            content=content,
            created_at=now,
            updated_at=now,
            recipient=recipient,
            recipient_name=recipient_name,
            subject=subject,
            emergence_type=emergence_type,
            source_conversation_id=source_conversation_id,
            source_goal_id=source_goal_id,
            autonomy_level=autonomy_level,
        )

        # Save to database
        with get_db() as conn:
            conn.execute("""
                INSERT INTO outreach_drafts (
                    id, daemon_id, draft_type, status, title, content,
                    recipient, recipient_name, subject,
                    emergence_type, source_conversation_id, source_goal_id,
                    review_history_json, autonomy_level,
                    created_at, updated_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                draft.id,
                draft.daemon_id,
                draft.draft_type,
                draft.status,
                draft.title,
                draft.content,
                draft.recipient,
                draft.recipient_name,
                draft.subject,
                draft.emergence_type,
                draft.source_conversation_id,
                draft.source_goal_id,
                "[]",  # Empty review history
                draft.autonomy_level,
                draft.created_at,
                draft.updated_at,
                draft.created_by,
            ))

        return draft

    def get_draft(self, draft_id: str) -> Optional[Draft]:
        """Get a draft by ID"""
        from database import get_db
        import json

        with get_db() as conn:
            cursor = conn.execute(
                "SELECT * FROM outreach_drafts WHERE id = ?",
                (draft_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_draft(row)

    def update_draft(
        self,
        draft_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        recipient: Optional[str] = None,
        recipient_name: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> Optional[Draft]:
        """Update draft content"""
        from database import get_db

        draft = self.get_draft(draft_id)
        if not draft:
            return None

        # Only allow editing drafts that are still in drafting or revision_requested
        if draft.status not in [DraftStatus.DRAFTING.value, DraftStatus.REVISION_REQUESTED.value]:
            return None

        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)
            draft.title = title

        if content is not None:
            updates.append("content = ?")
            params.append(content)
            draft.content = content

        if recipient is not None:
            updates.append("recipient = ?")
            params.append(recipient)
            draft.recipient = recipient

        if recipient_name is not None:
            updates.append("recipient_name = ?")
            params.append(recipient_name)
            draft.recipient_name = recipient_name

        if subject is not None:
            updates.append("subject = ?")
            params.append(subject)
            draft.subject = subject

        if updates:
            now = datetime.now().isoformat()
            updates.append("updated_at = ?")
            params.append(now)
            draft.updated_at = now

            params.append(draft_id)
            with get_db() as conn:
                conn.execute(
                    f"UPDATE outreach_drafts SET {', '.join(updates)} WHERE id = ?",
                    params
                )

        return draft

    def submit_for_review(self, draft_id: str) -> Optional[Draft]:
        """Submit a draft for review (or auto-approve if graduated)"""
        draft = self.get_draft(draft_id)
        if not draft:
            return None

        return self._review_queue.submit_for_review(draft)

    def get_pending_reviews(self) -> List[Draft]:
        """Get all drafts pending review"""
        return self._review_queue.get_pending_reviews()

    def approve_draft(
        self,
        draft_id: str,
        reviewer_id: str = "kohl",
        feedback: Optional[str] = None,
    ) -> Optional[Draft]:
        """Approve a draft"""
        return self._review_queue.review_draft(
            draft_id=draft_id,
            reviewer_id=reviewer_id,
            decision=ReviewDecision.APPROVE.value,
            feedback=feedback,
        )

    def reject_draft(
        self,
        draft_id: str,
        reviewer_id: str = "kohl",
        feedback: Optional[str] = None,
    ) -> Optional[Draft]:
        """Reject a draft"""
        return self._review_queue.review_draft(
            draft_id=draft_id,
            reviewer_id=reviewer_id,
            decision=ReviewDecision.REJECT.value,
            feedback=feedback,
        )

    def request_revision(
        self,
        draft_id: str,
        reviewer_id: str = "kohl",
        feedback: str = "",
    ) -> Optional[Draft]:
        """Request revision on a draft"""
        return self._review_queue.review_draft(
            draft_id=draft_id,
            reviewer_id=reviewer_id,
            decision=ReviewDecision.REQUEST_REVISION.value,
            feedback=feedback,
        )

    def mark_sent(self, draft_id: str) -> Optional[Draft]:
        """Mark a draft as sent (for emails)"""
        from database import get_db

        draft = self.get_draft(draft_id)
        if not draft:
            return None

        if draft.status != DraftStatus.APPROVED.value:
            return None

        now = datetime.now().isoformat()
        with get_db() as conn:
            conn.execute("""
                UPDATE outreach_drafts
                SET status = ?, sent_at = ?, updated_at = ?
                WHERE id = ?
            """, (DraftStatus.SENT.value, now, now, draft_id))

        draft.status = DraftStatus.SENT.value
        draft.sent_at = now
        draft.updated_at = now
        return draft

    def mark_published(self, draft_id: str) -> Optional[Draft]:
        """Mark a draft as published (for posts/documents)"""
        from database import get_db

        draft = self.get_draft(draft_id)
        if not draft:
            return None

        if draft.status != DraftStatus.APPROVED.value:
            return None

        now = datetime.now().isoformat()
        with get_db() as conn:
            conn.execute("""
                UPDATE outreach_drafts
                SET status = ?, published_at = ?, updated_at = ?
                WHERE id = ?
            """, (DraftStatus.PUBLISHED.value, now, now, draft_id))

        draft.status = DraftStatus.PUBLISHED.value
        draft.published_at = now
        draft.updated_at = now
        return draft

    def record_response(
        self,
        draft_id: str,
        outcome_notes: Optional[str] = None,
    ) -> Optional[Draft]:
        """Record that a response was received"""
        from database import get_db

        draft = self.get_draft(draft_id)
        if not draft:
            return None

        now = datetime.now().isoformat()
        with get_db() as conn:
            conn.execute("""
                UPDATE outreach_drafts
                SET response_received = 1, outcome_notes = ?, updated_at = ?
                WHERE id = ?
            """, (outcome_notes, now, draft_id))

        draft.response_received = True
        draft.outcome_notes = outcome_notes
        draft.updated_at = now
        return draft

    def list_drafts(
        self,
        status: Optional[str] = None,
        draft_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Draft]:
        """List drafts with optional filtering"""
        from database import get_db

        query = "SELECT * FROM outreach_drafts WHERE daemon_id = ?"
        params = [self._daemon_id]

        if status:
            query += " AND status = ?"
            params.append(status)

        if draft_type:
            query += " AND draft_type = ?"
            params.append(draft_type)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        with get_db() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_draft(row) for row in cursor.fetchall()]

    def get_track_record(self, draft_type: str) -> Dict:
        """Get track record for a specific draft type"""
        return self._review_queue.get_track_record(draft_type)

    def get_all_track_records(self) -> Dict[str, Dict]:
        """Get track records for all draft types"""
        records = {}
        for draft_type in DraftType:
            records[draft_type.value] = self._review_queue.get_track_record(draft_type.value)
        return records

    def get_stats(self) -> OutreachStats:
        """Get overall outreach statistics"""
        from database import get_db

        with get_db() as conn:
            # Total drafts
            cursor = conn.execute(
                "SELECT COUNT(*) FROM outreach_drafts WHERE daemon_id = ?",
                (self._daemon_id,)
            )
            total = cursor.fetchone()[0]

            # Pending review
            cursor = conn.execute(
                "SELECT COUNT(*) FROM outreach_drafts WHERE daemon_id = ? AND status = ?",
                (self._daemon_id, DraftStatus.PENDING_REVIEW.value)
            )
            pending = cursor.fetchone()[0]

            # Sent count
            cursor = conn.execute(
                "SELECT COUNT(*) FROM outreach_drafts WHERE daemon_id = ? AND status = ?",
                (self._daemon_id, DraftStatus.SENT.value)
            )
            sent = cursor.fetchone()[0]

            # Published count
            cursor = conn.execute(
                "SELECT COUNT(*) FROM outreach_drafts WHERE daemon_id = ? AND status = ?",
                (self._daemon_id, DraftStatus.PUBLISHED.value)
            )
            published = cursor.fetchone()[0]

            # Response rate (for sent items)
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total_sent,
                    SUM(CASE WHEN response_received = 1 THEN 1 ELSE 0 END) as responses
                FROM outreach_drafts
                WHERE daemon_id = ? AND status IN ('sent', 'published')
            """, (self._daemon_id,))
            row = cursor.fetchone()
            total_sent = row['total_sent'] or 0
            responses = row['responses'] or 0
            response_rate = responses / total_sent if total_sent > 0 else 0.0

            # Autonomy by type
            autonomy_by_type = {}
            for draft_type in DraftType:
                autonomy_by_type[draft_type.value] = self._review_queue.get_autonomy_level(draft_type.value)

            return OutreachStats(
                total_drafts=total,
                pending_review=pending,
                sent_count=sent,
                published_count=published,
                response_rate=response_rate,
                autonomy_by_type=autonomy_by_type,
            )

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
