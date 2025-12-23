"""
Outreach Models - Data structures for outreach capabilities
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


class DraftType(str, Enum):
    """Types of outreach drafts"""
    EMAIL = "email"
    DOCUMENT = "document"
    BLOG_POST = "blog_post"
    SOCIAL_POST = "social_post"
    RESEARCH_NOTE = "research_note"
    RESPONSE = "response"  # Reply to external communication


class DraftStatus(str, Enum):
    """Lifecycle of a draft"""
    DRAFTING = "drafting"  # Still being worked on
    PENDING_REVIEW = "pending_review"  # Submitted for review
    APPROVED = "approved"  # Approved, ready to send/publish
    REJECTED = "rejected"  # Rejected with feedback
    REVISION_REQUESTED = "revision_requested"  # Needs changes
    SENT = "sent"  # Email sent
    PUBLISHED = "published"  # Document/post published
    ARCHIVED = "archived"  # No longer active


class ReviewDecision(str, Enum):
    """Possible review decisions"""
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REVISION = "request_revision"
    AUTO_APPROVED = "auto_approved"  # Passed autonomy threshold


class AutonomyLevel(str, Enum):
    """Autonomy levels for different content types"""
    ALWAYS_REVIEW = "always_review"  # High-stakes, always needs human review
    LEARNING = "learning"  # Building track record, review required
    GRADUATED = "graduated"  # Good track record, spot-checks only
    AUTONOMOUS = "autonomous"  # Full autonomy with periodic check-ins


@dataclass
class ReviewFeedback:
    """Feedback from a review"""
    reviewer: str  # Who reviewed (user_id or "auto")
    decision: str  # ReviewDecision value
    feedback: Optional[str] = None  # Comments/suggestions
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            "reviewer": self.reviewer,
            "decision": self.decision,
            "feedback": self.feedback,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ReviewFeedback":
        return cls(
            reviewer=data["reviewer"],
            decision=data["decision"],
            feedback=data.get("feedback"),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class Draft:
    """An outreach draft (email, document, post, etc.)"""
    id: str
    daemon_id: str
    draft_type: str  # DraftType value
    status: str  # DraftStatus value

    # Content
    title: str
    content: str  # Main body (markdown)

    # Metadata
    created_at: str
    updated_at: str
    created_by: str = "cass"  # Who created (usually cass)

    # Email-specific fields
    recipient: Optional[str] = None
    recipient_name: Optional[str] = None
    subject: Optional[str] = None

    # Context
    emergence_type: Optional[str] = None  # How this outreach emerged
    source_conversation_id: Optional[str] = None
    source_goal_id: Optional[str] = None  # Linked goal if any

    # Review tracking
    review_history: List[Dict] = field(default_factory=list)  # List of ReviewFeedback dicts
    autonomy_level: str = AutonomyLevel.LEARNING.value

    # Outcome tracking
    sent_at: Optional[str] = None
    published_at: Optional[str] = None
    response_received: bool = False
    outcome_notes: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "daemon_id": self.daemon_id,
            "draft_type": self.draft_type,
            "status": self.status,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "recipient": self.recipient,
            "recipient_name": self.recipient_name,
            "subject": self.subject,
            "emergence_type": self.emergence_type,
            "source_conversation_id": self.source_conversation_id,
            "source_goal_id": self.source_goal_id,
            "review_history": self.review_history,
            "autonomy_level": self.autonomy_level,
            "sent_at": self.sent_at,
            "published_at": self.published_at,
            "response_received": self.response_received,
            "outcome_notes": self.outcome_notes,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Draft":
        return cls(
            id=data["id"],
            daemon_id=data["daemon_id"],
            draft_type=data["draft_type"],
            status=data["status"],
            title=data["title"],
            content=data["content"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            created_by=data.get("created_by", "cass"),
            recipient=data.get("recipient"),
            recipient_name=data.get("recipient_name"),
            subject=data.get("subject"),
            emergence_type=data.get("emergence_type"),
            source_conversation_id=data.get("source_conversation_id"),
            source_goal_id=data.get("source_goal_id"),
            review_history=data.get("review_history", []),
            autonomy_level=data.get("autonomy_level", AutonomyLevel.LEARNING.value),
            sent_at=data.get("sent_at"),
            published_at=data.get("published_at"),
            response_received=data.get("response_received", False),
            outcome_notes=data.get("outcome_notes"),
        )

    def add_review(self, feedback: ReviewFeedback):
        """Add a review to history"""
        self.review_history.append(feedback.to_dict())

    def latest_review(self) -> Optional[ReviewFeedback]:
        """Get the most recent review"""
        if not self.review_history:
            return None
        return ReviewFeedback.from_dict(self.review_history[-1])

    def approval_rate(self) -> float:
        """Calculate approval rate from review history"""
        if not self.review_history:
            return 0.0
        approvals = sum(
            1 for r in self.review_history
            if r.get("decision") in [ReviewDecision.APPROVE.value, ReviewDecision.AUTO_APPROVED.value]
        )
        return approvals / len(self.review_history)
