"""
Development Request Manager - Cass-Daedalus Coordination Bridge

Manages async work handoffs between Cass (oracle/seer) and Daedalus (builder/craftsman).
Uses the State Bus for event emission and notification.

Key patterns:
- Cass creates requests via tool calls or autonomous work
- Requests persist in database, visible to both sides
- Daedalus claims/completes via admin API or TUI
- State bus events notify subscribers of changes
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import uuid4

from database import get_db, json_serialize, json_deserialize
from state_models import (
    DevelopmentRequest,
    DevelopmentRequestStatus,
    DevelopmentRequestType,
    DevelopmentRequestPriority,
)

logger = logging.getLogger(__name__)


# Event types for state bus
EVENT_REQUEST_CREATED = "development.request.created"
EVENT_REQUEST_CLAIMED = "development.request.claimed"
EVENT_REQUEST_STATUS_CHANGED = "development.request.status_changed"
EVENT_REQUEST_COMPLETED = "development.request.completed"


class DevelopmentRequestManager:
    """
    Manages development requests between Cass and Daedalus.

    This is the bridge that enables human-timescale work coordination.
    Unlike Janet (instant LLM execution), development requests are async
    and may take hours or days to complete.
    """

    def __init__(self, daemon_id: str, state_bus=None):
        """
        Initialize the manager.

        Args:
            daemon_id: The daemon this manager serves
            state_bus: Optional GlobalStateBus for event emission
        """
        self.daemon_id = daemon_id
        self.state_bus = state_bus

    def create_request(
        self,
        title: str,
        request_type: str = "feature",
        description: str = "",
        priority: str = "normal",
        context: Optional[str] = None,
        related_actions: Optional[List[str]] = None,
        requested_by: str = "cass",
    ) -> DevelopmentRequest:
        """
        Create a new development request.

        This is what Cass calls when she needs something built.

        Args:
            title: Brief title of what's needed
            request_type: Type of work (new_action, bug_fix, feature, etc.)
            description: Detailed description
            priority: Priority level (low, normal, high, urgent)
            context: Why this is needed (motivation)
            related_actions: Action IDs that relate to this work
            requested_by: Who made the request (cass, user)

        Returns:
            The created DevelopmentRequest
        """
        request_id = f"devreq-{uuid4().hex[:12]}"
        now = datetime.now()

        request = DevelopmentRequest(
            id=request_id,
            requested_by=requested_by,
            request_type=DevelopmentRequestType(request_type),
            title=title,
            description=description,
            priority=DevelopmentRequestPriority(priority),
            status=DevelopmentRequestStatus.PENDING,
            context=context,
            related_actions=related_actions or [],
            created_at=now,
            updated_at=now,
        )

        # Persist to database
        self._save_request(request)

        # Emit event
        self._emit_event(EVENT_REQUEST_CREATED, {
            "request_id": request.id,
            "title": request.title,
            "request_type": request.request_type.value,
            "priority": request.priority.value,
            "requested_by": request.requested_by,
        })

        logger.info(f"Created development request: {request.id} - {request.title}")
        return request

    def get_request(self, request_id: str) -> Optional[DevelopmentRequest]:
        """Get a request by ID."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, requested_by, request_type, title, description, priority,
                       status, context, related_actions_json, claimed_by, claimed_at,
                       result, result_artifacts_json, completed_at, created_at, updated_at
                FROM development_requests
                WHERE id = ? AND daemon_id = ?
            """, (request_id, self.daemon_id))

            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_request(row)

    def list_requests(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
    ) -> List[DevelopmentRequest]:
        """
        List development requests with optional filters.

        Args:
            status: Filter by status (pending, claimed, etc.)
            priority: Filter by priority (low, normal, high, urgent)
            limit: Maximum requests to return

        Returns:
            List of matching requests
        """
        query = """
            SELECT id, requested_by, request_type, title, description, priority,
                   status, context, related_actions_json, claimed_by, claimed_at,
                   result, result_artifacts_json, completed_at, created_at, updated_at
            FROM development_requests
            WHERE daemon_id = ?
        """
        params = [self.daemon_id]

        if status:
            query += " AND status = ?"
            params.append(status)

        if priority:
            query += " AND priority = ?"
            params.append(priority)

        query += " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, created_at DESC"
        query += f" LIMIT {limit}"

        with get_db() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_request(row) for row in cursor.fetchall()]

    def get_pending_requests(self) -> List[DevelopmentRequest]:
        """Get all pending requests (convenience method)."""
        return self.list_requests(status="pending")

    def claim_request(
        self,
        request_id: str,
        claimed_by: str = "daedalus",
    ) -> Optional[DevelopmentRequest]:
        """
        Claim a request for work.

        This is what Daedalus calls when picking up work.

        Args:
            request_id: ID of request to claim
            claimed_by: Who is claiming it

        Returns:
            Updated request or None if not found
        """
        request = self.get_request(request_id)
        if not request:
            return None

        if request.status != DevelopmentRequestStatus.PENDING:
            logger.warning(f"Cannot claim request {request_id}: status is {request.status.value}")
            return None

        now = datetime.now()
        request.status = DevelopmentRequestStatus.CLAIMED
        request.claimed_by = claimed_by
        request.claimed_at = now
        request.updated_at = now

        self._save_request(request)

        self._emit_event(EVENT_REQUEST_CLAIMED, {
            "request_id": request.id,
            "claimed_by": claimed_by,
            "title": request.title,
        })

        logger.info(f"Request claimed: {request.id} by {claimed_by}")
        return request

    def start_work(self, request_id: str) -> Optional[DevelopmentRequest]:
        """
        Mark a request as in progress.

        Args:
            request_id: ID of request

        Returns:
            Updated request or None
        """
        return self._update_status(request_id, DevelopmentRequestStatus.IN_PROGRESS)

    def submit_for_review(
        self,
        request_id: str,
        result: Optional[str] = None,
        artifacts: Optional[List[str]] = None,
    ) -> Optional[DevelopmentRequest]:
        """
        Submit work for review.

        Args:
            request_id: ID of request
            result: What was done
            artifacts: Commit hashes, file paths, etc.

        Returns:
            Updated request or None
        """
        request = self.get_request(request_id)
        if not request:
            return None

        now = datetime.now()
        request.status = DevelopmentRequestStatus.REVIEW
        request.result = result
        request.result_artifacts = artifacts or []
        request.updated_at = now

        self._save_request(request)

        self._emit_event(EVENT_REQUEST_STATUS_CHANGED, {
            "request_id": request.id,
            "status": "review",
            "result": result,
        })

        logger.info(f"Request submitted for review: {request.id}")
        return request

    def complete_request(
        self,
        request_id: str,
        result: Optional[str] = None,
        artifacts: Optional[List[str]] = None,
    ) -> Optional[DevelopmentRequest]:
        """
        Mark a request as complete.

        This triggers notification to Cass that work is done.

        Args:
            request_id: ID of request
            result: What was accomplished
            artifacts: Commit hashes, file paths, etc.

        Returns:
            Updated request or None
        """
        request = self.get_request(request_id)
        if not request:
            return None

        now = datetime.now()
        request.status = DevelopmentRequestStatus.COMPLETED
        request.result = result or request.result
        request.result_artifacts = artifacts or request.result_artifacts
        request.completed_at = now
        request.updated_at = now

        self._save_request(request)

        self._emit_event(EVENT_REQUEST_COMPLETED, {
            "request_id": request.id,
            "title": request.title,
            "request_type": request.request_type.value,
            "result": request.result,
            "artifacts": request.result_artifacts,
        })

        logger.info(f"Request completed: {request.id} - {request.title}")
        return request

    def cancel_request(
        self,
        request_id: str,
        reason: Optional[str] = None,
    ) -> Optional[DevelopmentRequest]:
        """
        Cancel a request.

        Args:
            request_id: ID of request
            reason: Why it was cancelled

        Returns:
            Updated request or None
        """
        request = self.get_request(request_id)
        if not request:
            return None

        now = datetime.now()
        request.status = DevelopmentRequestStatus.CANCELLED
        request.result = reason or "Cancelled"
        request.updated_at = now

        self._save_request(request)

        self._emit_event(EVENT_REQUEST_STATUS_CHANGED, {
            "request_id": request.id,
            "status": "cancelled",
            "reason": reason,
        })

        logger.info(f"Request cancelled: {request.id}")
        return request

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about development requests.

        Returns:
            Dict with counts by status, priority, etc.
        """
        with get_db() as conn:
            # Status counts
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM development_requests
                WHERE daemon_id = ?
                GROUP BY status
            """, (self.daemon_id,))
            status_counts = {row[0]: row[1] for row in cursor.fetchall()}

            # Priority counts for pending
            cursor = conn.execute("""
                SELECT priority, COUNT(*) as count
                FROM development_requests
                WHERE daemon_id = ? AND status = 'pending'
                GROUP BY priority
            """, (self.daemon_id,))
            pending_by_priority = {row[0]: row[1] for row in cursor.fetchall()}

            # Recent completions
            cursor = conn.execute("""
                SELECT COUNT(*) FROM development_requests
                WHERE daemon_id = ? AND status = 'completed'
                AND completed_at > datetime('now', '-7 days')
            """, (self.daemon_id,))
            completed_this_week = cursor.fetchone()[0]

            return {
                "by_status": status_counts,
                "pending_by_priority": pending_by_priority,
                "completed_this_week": completed_this_week,
                "total_pending": status_counts.get("pending", 0),
                "total_in_progress": status_counts.get("in_progress", 0) + status_counts.get("claimed", 0),
            }

    def get_pending_summary(self) -> str:
        """
        Get a human-readable summary of pending requests.

        Useful for context injection - Cass can see what she's waiting on.

        Returns:
            Summary string
        """
        pending = self.get_pending_requests()
        if not pending:
            return "No pending development requests."

        lines = [f"Pending development requests ({len(pending)}):"]
        for req in pending[:5]:
            lines.append(f"  {req.get_display_summary()}")
        if len(pending) > 5:
            lines.append(f"  ... and {len(pending) - 5} more")

        return "\n".join(lines)

    # === Private methods ===

    def _save_request(self, request: DevelopmentRequest) -> None:
        """Save a request to the database."""
        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO development_requests (
                    id, daemon_id, requested_by, request_type, title, description,
                    priority, status, context, related_actions_json, claimed_by,
                    claimed_at, result, result_artifacts_json, completed_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request.id,
                self.daemon_id,
                request.requested_by,
                request.request_type.value,
                request.title,
                request.description,
                request.priority.value,
                request.status.value,
                request.context,
                json_serialize(request.related_actions) if request.related_actions else None,
                request.claimed_by,
                request.claimed_at.isoformat() if request.claimed_at else None,
                request.result,
                json_serialize(request.result_artifacts) if request.result_artifacts else None,
                request.completed_at.isoformat() if request.completed_at else None,
                request.created_at.isoformat(),
                request.updated_at.isoformat(),
            ))
            conn.commit()

    def _row_to_request(self, row) -> DevelopmentRequest:
        """Convert a database row to a DevelopmentRequest."""
        claimed_at = None
        if row[10]:
            claimed_at = datetime.fromisoformat(row[10])

        completed_at = None
        if row[13]:
            completed_at = datetime.fromisoformat(row[13])

        return DevelopmentRequest(
            id=row[0],
            requested_by=row[1],
            request_type=DevelopmentRequestType(row[2]),
            title=row[3],
            description=row[4] or "",
            priority=DevelopmentRequestPriority(row[5]),
            status=DevelopmentRequestStatus(row[6]),
            context=row[7],
            related_actions=json_deserialize(row[8]) if row[8] else [],
            claimed_by=row[9],
            claimed_at=claimed_at,
            result=row[11],
            result_artifacts=json_deserialize(row[12]) if row[12] else [],
            completed_at=completed_at,
            created_at=datetime.fromisoformat(row[14]),
            updated_at=datetime.fromisoformat(row[15]),
        )

    def _update_status(
        self,
        request_id: str,
        new_status: DevelopmentRequestStatus,
    ) -> Optional[DevelopmentRequest]:
        """Update request status."""
        request = self.get_request(request_id)
        if not request:
            return None

        request.status = new_status
        request.updated_at = datetime.now()

        self._save_request(request)

        self._emit_event(EVENT_REQUEST_STATUS_CHANGED, {
            "request_id": request.id,
            "status": new_status.value,
        })

        return request

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event to the state bus if available."""
        if self.state_bus:
            try:
                self.state_bus.emit_event(event_type, data)
            except Exception as e:
                logger.error(f"Failed to emit event {event_type}: {e}")


# === Convenience functions ===

_manager_cache: Dict[str, DevelopmentRequestManager] = {}


def get_development_request_manager(
    daemon_id: str,
    state_bus=None,
) -> DevelopmentRequestManager:
    """Get or create a DevelopmentRequestManager for a daemon."""
    if daemon_id not in _manager_cache:
        _manager_cache[daemon_id] = DevelopmentRequestManager(daemon_id, state_bus)
    return _manager_cache[daemon_id]
