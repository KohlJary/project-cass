"""
Work Item Manager - Cass's Taskboard

Manages work items - units of work composed from atomic actions.
This is Cass's planning infrastructure, not user-facing features.

Storage: SQLite database (data/cass.db)
"""
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any

from database import get_db, json_serialize, json_deserialize
from work_planning.models import (
    WorkItem,
    WorkStatus,
    WorkPriority,
    ApprovalStatus,
)


class WorkItemManager:
    """
    Manages Cass's work items - her taskboard.

    Provides:
    - CRUD operations for work items
    - State transitions with validation
    - Query/filter operations
    - Approval workflow
    - Stats and summaries
    """

    DEFAULT_DAEMON_ID = None

    def __init__(self, daemon_id: str = None):
        """
        Initialize WorkItemManager.

        Args:
            daemon_id: UUID of the daemon. If None, uses default Cass daemon.
        """
        self._daemon_id = daemon_id
        if not self._daemon_id:
            self._load_default_daemon()

    def _load_default_daemon(self):
        """Load the default daemon ID from database"""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM daemons WHERE label = 'cass' LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                self._daemon_id = row['id']
            else:
                # Create default daemon if not exists
                self._daemon_id = str(uuid.uuid4())
                conn.execute("""
                    INSERT INTO daemons (id, label, name, created_at, kernel_version, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    self._daemon_id,
                    'cass',
                    'Cass',
                    datetime.now().isoformat(),
                    'temple-codex-1.0',
                    'active'
                ))

    @property
    def daemon_id(self) -> str:
        return self._daemon_id

    # =========================================================================
    # CRUD OPERATIONS
    # =========================================================================

    def create(
        self,
        title: str,
        action_sequence: List[str] = None,
        description: str = "",
        goal_id: Optional[str] = None,
        category: str = "general",
        priority: WorkPriority = WorkPriority.NORMAL,
        estimated_duration_minutes: int = 30,
        estimated_cost_usd: float = 0.0,
        deadline: Optional[datetime] = None,
        dependencies: List[str] = None,
        requires_approval: bool = False,
        created_by: str = "cass",
    ) -> WorkItem:
        """
        Create a new work item.

        Args:
            title: Short description of the work
            action_sequence: Ordered list of atomic action IDs
            description: Detailed description
            goal_id: Optional link to a goal
            category: Work category (reflection, research, growth, etc.)
            priority: Work priority level
            estimated_duration_minutes: Expected duration
            estimated_cost_usd: Expected cost
            deadline: Optional deadline
            dependencies: Other work_item IDs that must complete first
            requires_approval: Whether this work needs approval before execution
            created_by: Who created this (usually "cass" or "synkratos")

        Returns:
            Created WorkItem
        """
        work_id = str(uuid.uuid4())[:8]  # Short ID for readability
        now = datetime.now()

        work_item = WorkItem(
            id=work_id,
            title=title,
            description=description,
            action_sequence=action_sequence or [],
            goal_id=goal_id,
            category=category,
            priority=priority,
            estimated_duration_minutes=estimated_duration_minutes,
            estimated_cost_usd=estimated_cost_usd,
            deadline=deadline,
            dependencies=dependencies or [],
            requires_approval=requires_approval,
            approval_status=ApprovalStatus.PENDING if requires_approval else ApprovalStatus.NOT_REQUIRED,
            status=WorkStatus.PLANNED,
            created_at=now,
            created_by=created_by,
        )

        # Save to database
        with get_db() as conn:
            conn.execute("""
                INSERT INTO work_items (
                    id, daemon_id, title, description,
                    action_sequence_json, goal_id, category,
                    priority, estimated_duration_minutes, estimated_cost_usd,
                    deadline, dependencies_json,
                    requires_approval, approval_status,
                    status, created_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                work_item.id,
                self._daemon_id,
                work_item.title,
                work_item.description,
                json_serialize(work_item.action_sequence),
                work_item.goal_id,
                work_item.category,
                work_item.priority.value,
                work_item.estimated_duration_minutes,
                work_item.estimated_cost_usd,
                work_item.deadline.isoformat() if work_item.deadline else None,
                json_serialize(work_item.dependencies),
                1 if work_item.requires_approval else 0,
                work_item.approval_status.value,
                work_item.status.value,
                work_item.created_at.isoformat(),
                work_item.created_by,
            ))

        return work_item

    def get(self, work_item_id: str) -> Optional[WorkItem]:
        """Get a work item by ID."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM work_items
                WHERE id = ? AND daemon_id = ?
            """, (work_item_id, self._daemon_id))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_work_item(dict(row))

    def update(self, work_item_id: str, **updates) -> Optional[WorkItem]:
        """
        Update a work item's fields.

        Args:
            work_item_id: ID of the work item
            **updates: Fields to update

        Returns:
            Updated WorkItem or None if not found
        """
        work_item = self.get(work_item_id)
        if not work_item:
            return None

        # Build update query
        allowed_fields = {
            'title', 'description', 'action_sequence', 'goal_id', 'category',
            'priority', 'estimated_duration_minutes', 'estimated_cost_usd',
            'deadline', 'dependencies', 'result_summary'
        }

        set_clauses = []
        params = []

        for field, value in updates.items():
            if field not in allowed_fields:
                continue

            if field == 'action_sequence':
                set_clauses.append("action_sequence_json = ?")
                params.append(json_serialize(value))
            elif field == 'dependencies':
                set_clauses.append("dependencies_json = ?")
                params.append(json_serialize(value))
            elif field == 'priority':
                set_clauses.append("priority = ?")
                params.append(value.value if isinstance(value, WorkPriority) else value)
            elif field == 'deadline':
                set_clauses.append("deadline = ?")
                params.append(value.isoformat() if value else None)
            else:
                set_clauses.append(f"{field} = ?")
                params.append(value)

        if not set_clauses:
            return work_item

        params.extend([work_item_id, self._daemon_id])

        with get_db() as conn:
            conn.execute(f"""
                UPDATE work_items
                SET {', '.join(set_clauses)}
                WHERE id = ? AND daemon_id = ?
            """, params)

        return self.get(work_item_id)

    def delete(self, work_item_id: str) -> bool:
        """Delete a work item."""
        with get_db() as conn:
            cursor = conn.execute("""
                DELETE FROM work_items
                WHERE id = ? AND daemon_id = ?
            """, (work_item_id, self._daemon_id))
            return cursor.rowcount > 0

    # =========================================================================
    # QUERY OPERATIONS
    # =========================================================================

    def list_all(self, limit: int = 100) -> List[WorkItem]:
        """List all work items."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM work_items
                WHERE daemon_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (self._daemon_id, limit))
            return [self._row_to_work_item(dict(row)) for row in cursor.fetchall()]

    def list_by_status(self, status: WorkStatus) -> List[WorkItem]:
        """List work items with a specific status."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM work_items
                WHERE daemon_id = ? AND status = ?
                ORDER BY priority ASC, created_at ASC
            """, (self._daemon_id, status.value))
            return [self._row_to_work_item(dict(row)) for row in cursor.fetchall()]

    def list_by_goal(self, goal_id: str) -> List[WorkItem]:
        """List work items linked to a goal."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM work_items
                WHERE daemon_id = ? AND goal_id = ?
                ORDER BY priority ASC, created_at ASC
            """, (self._daemon_id, goal_id))
            return [self._row_to_work_item(dict(row)) for row in cursor.fetchall()]

    def list_by_category(self, category: str) -> List[WorkItem]:
        """List work items in a category."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM work_items
                WHERE daemon_id = ? AND category = ?
                ORDER BY priority ASC, created_at ASC
            """, (self._daemon_id, category))
            return [self._row_to_work_item(dict(row)) for row in cursor.fetchall()]

    def list_ready(self) -> List[WorkItem]:
        """
        List work items that are ready to execute.

        Ready means: status is READY, all dependencies completed,
        and (not requiring approval OR already approved).
        """
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM work_items
                WHERE daemon_id = ?
                AND status = ?
                AND (requires_approval = 0 OR approval_status = ?)
                ORDER BY priority ASC, created_at ASC
            """, (
                self._daemon_id,
                WorkStatus.READY.value,
                ApprovalStatus.APPROVED.value
            ))

            items = [self._row_to_work_item(dict(row)) for row in cursor.fetchall()]

            # Filter by dependencies
            return [item for item in items if self._dependencies_met(item)]

    def list_pending_approval(self) -> List[WorkItem]:
        """List work items waiting for approval."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM work_items
                WHERE daemon_id = ?
                AND requires_approval = 1
                AND approval_status = ?
                ORDER BY priority ASC, created_at ASC
            """, (self._daemon_id, ApprovalStatus.PENDING.value))
            return [self._row_to_work_item(dict(row)) for row in cursor.fetchall()]

    # =========================================================================
    # STATE TRANSITIONS
    # =========================================================================

    def mark_scheduled(self, work_item_id: str, slot_id: str) -> Optional[WorkItem]:
        """Mark a work item as scheduled with a slot."""
        return self._transition_status(
            work_item_id,
            WorkStatus.SCHEDULED,
            from_statuses=[WorkStatus.PLANNED]
        )

    def mark_ready(self, work_item_id: str) -> Optional[WorkItem]:
        """Mark a work item as ready for execution."""
        work_item = self.get(work_item_id)
        if not work_item:
            return None

        # Check approval if required
        if work_item.requires_approval and work_item.approval_status != ApprovalStatus.APPROVED:
            return None  # Can't mark ready without approval

        return self._transition_status(
            work_item_id,
            WorkStatus.READY,
            from_statuses=[WorkStatus.PLANNED, WorkStatus.SCHEDULED]
        )

    def mark_running(self, work_item_id: str) -> Optional[WorkItem]:
        """Mark a work item as currently running."""
        now = datetime.now()
        with get_db() as conn:
            conn.execute("""
                UPDATE work_items
                SET status = ?, started_at = ?
                WHERE id = ? AND daemon_id = ? AND status = ?
            """, (
                WorkStatus.RUNNING.value,
                now.isoformat(),
                work_item_id,
                self._daemon_id,
                WorkStatus.READY.value
            ))
        return self.get(work_item_id)

    def mark_completed(
        self,
        work_item_id: str,
        result_summary: str,
        actual_cost_usd: float = 0.0
    ) -> Optional[WorkItem]:
        """Mark a work item as completed."""
        now = datetime.now()
        with get_db() as conn:
            conn.execute("""
                UPDATE work_items
                SET status = ?, completed_at = ?, result_summary = ?, actual_cost_usd = ?
                WHERE id = ? AND daemon_id = ? AND status = ?
            """, (
                WorkStatus.COMPLETED.value,
                now.isoformat(),
                result_summary,
                actual_cost_usd,
                work_item_id,
                self._daemon_id,
                WorkStatus.RUNNING.value
            ))
        return self.get(work_item_id)

    def mark_failed(self, work_item_id: str, error_message: str) -> Optional[WorkItem]:
        """Mark a work item as failed."""
        now = datetime.now()
        with get_db() as conn:
            conn.execute("""
                UPDATE work_items
                SET status = ?, completed_at = ?, result_summary = ?
                WHERE id = ? AND daemon_id = ? AND status = ?
            """, (
                WorkStatus.FAILED.value,
                now.isoformat(),
                f"FAILED: {error_message}",
                work_item_id,
                self._daemon_id,
                WorkStatus.RUNNING.value
            ))
        return self.get(work_item_id)

    def mark_cancelled(self, work_item_id: str, reason: str = "") -> Optional[WorkItem]:
        """Mark a work item as cancelled."""
        work_item = self.get(work_item_id)
        if not work_item:
            return None

        # Can cancel from any non-terminal status
        if work_item.status in [WorkStatus.COMPLETED, WorkStatus.FAILED, WorkStatus.CANCELLED]:
            return None

        with get_db() as conn:
            conn.execute("""
                UPDATE work_items
                SET status = ?, result_summary = ?
                WHERE id = ? AND daemon_id = ?
            """, (
                WorkStatus.CANCELLED.value,
                f"CANCELLED: {reason}" if reason else "CANCELLED",
                work_item_id,
                self._daemon_id
            ))
        return self.get(work_item_id)

    # =========================================================================
    # APPROVAL WORKFLOW
    # =========================================================================

    def approve(self, work_item_id: str, approved_by: str) -> Optional[WorkItem]:
        """Approve a work item for execution."""
        now = datetime.now()
        with get_db() as conn:
            cursor = conn.execute("""
                UPDATE work_items
                SET approval_status = ?, approved_by = ?, approved_at = ?
                WHERE id = ? AND daemon_id = ?
                AND requires_approval = 1
                AND approval_status = ?
            """, (
                ApprovalStatus.APPROVED.value,
                approved_by,
                now.isoformat(),
                work_item_id,
                self._daemon_id,
                ApprovalStatus.PENDING.value
            ))
            if cursor.rowcount == 0:
                return None
        return self.get(work_item_id)

    def reject(self, work_item_id: str, reason: str) -> Optional[WorkItem]:
        """Reject a work item."""
        with get_db() as conn:
            cursor = conn.execute("""
                UPDATE work_items
                SET approval_status = ?, result_summary = ?
                WHERE id = ? AND daemon_id = ?
                AND requires_approval = 1
                AND approval_status = ?
            """, (
                ApprovalStatus.REJECTED.value,
                f"REJECTED: {reason}",
                work_item_id,
                self._daemon_id,
                ApprovalStatus.PENDING.value
            ))
            if cursor.rowcount == 0:
                return None
        return self.get(work_item_id)

    # =========================================================================
    # STATS
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get work item statistics."""
        with get_db() as conn:
            # Total count
            cursor = conn.execute("""
                SELECT COUNT(*) as total FROM work_items
                WHERE daemon_id = ?
            """, (self._daemon_id,))
            total = cursor.fetchone()['total']

            # By status
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count FROM work_items
                WHERE daemon_id = ?
                GROUP BY status
            """, (self._daemon_id,))
            by_status = {row['status']: row['count'] for row in cursor.fetchall()}

            # By category
            cursor = conn.execute("""
                SELECT category, COUNT(*) as count FROM work_items
                WHERE daemon_id = ?
                GROUP BY category
            """, (self._daemon_id,))
            by_category = {row['category']: row['count'] for row in cursor.fetchall()}

            # Pending approval count
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM work_items
                WHERE daemon_id = ?
                AND requires_approval = 1
                AND approval_status = ?
            """, (self._daemon_id, ApprovalStatus.PENDING.value))
            pending_approval = cursor.fetchone()['count']

            # Estimated total cost of pending work
            cursor = conn.execute("""
                SELECT COALESCE(SUM(estimated_cost_usd), 0) as cost FROM work_items
                WHERE daemon_id = ?
                AND status IN (?, ?, ?)
            """, (
                self._daemon_id,
                WorkStatus.PLANNED.value,
                WorkStatus.SCHEDULED.value,
                WorkStatus.READY.value
            ))
            estimated_pending_cost = cursor.fetchone()['cost']

            # Actual completed cost
            cursor = conn.execute("""
                SELECT COALESCE(SUM(actual_cost_usd), 0) as cost FROM work_items
                WHERE daemon_id = ?
                AND status = ?
            """, (self._daemon_id, WorkStatus.COMPLETED.value))
            actual_completed_cost = cursor.fetchone()['cost']

        return {
            "total": total,
            "by_status": by_status,
            "by_category": by_category,
            "pending_approval": pending_approval,
            "estimated_pending_cost_usd": estimated_pending_cost,
            "actual_completed_cost_usd": actual_completed_cost,
        }

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _row_to_work_item(self, row: Dict) -> WorkItem:
        """Convert a database row to a WorkItem."""
        return WorkItem(
            id=row['id'],
            title=row['title'],
            description=row.get('description', ''),
            action_sequence=json_deserialize(row.get('action_sequence_json')) or [],
            goal_id=row.get('goal_id'),
            category=row.get('category', 'general'),
            priority=WorkPriority(row.get('priority', 2)),
            estimated_duration_minutes=row.get('estimated_duration_minutes', 30),
            estimated_cost_usd=row.get('estimated_cost_usd', 0.0),
            deadline=datetime.fromisoformat(row['deadline']) if row.get('deadline') else None,
            dependencies=json_deserialize(row.get('dependencies_json')) or [],
            requires_approval=bool(row.get('requires_approval', 0)),
            approval_status=ApprovalStatus(row.get('approval_status', 'not_required')),
            approved_by=row.get('approved_by'),
            approved_at=datetime.fromisoformat(row['approved_at']) if row.get('approved_at') else None,
            status=WorkStatus(row.get('status', 'planned')),
            started_at=datetime.fromisoformat(row['started_at']) if row.get('started_at') else None,
            completed_at=datetime.fromisoformat(row['completed_at']) if row.get('completed_at') else None,
            actual_cost_usd=row.get('actual_cost_usd', 0.0),
            result_summary=row.get('result_summary'),
            created_at=datetime.fromisoformat(row['created_at']) if row.get('created_at') else datetime.now(),
            created_by=row.get('created_by', 'cass'),
        )

    def _transition_status(
        self,
        work_item_id: str,
        to_status: WorkStatus,
        from_statuses: List[WorkStatus]
    ) -> Optional[WorkItem]:
        """Generic status transition helper."""
        from_values = [s.value for s in from_statuses]
        placeholders = ','.join(['?' for _ in from_values])

        with get_db() as conn:
            cursor = conn.execute(f"""
                UPDATE work_items
                SET status = ?
                WHERE id = ? AND daemon_id = ? AND status IN ({placeholders})
            """, [to_status.value, work_item_id, self._daemon_id] + from_values)

            if cursor.rowcount == 0:
                return None

        return self.get(work_item_id)

    def _dependencies_met(self, work_item: WorkItem) -> bool:
        """Check if all dependencies are completed."""
        if not work_item.dependencies:
            return True

        with get_db() as conn:
            placeholders = ','.join(['?' for _ in work_item.dependencies])
            cursor = conn.execute(f"""
                SELECT COUNT(*) as count FROM work_items
                WHERE id IN ({placeholders})
                AND daemon_id = ?
                AND status != ?
            """, work_item.dependencies + [self._daemon_id, WorkStatus.COMPLETED.value])

            incomplete = cursor.fetchone()['count']
            return incomplete == 0
