"""
Schedule Manager - Cass's Calendar

Manages schedule slots - when Cass plans to do work.
This is Cass's scheduling infrastructure, not user-facing features.

Storage: SQLite database (data/cass.db)
"""
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from database import get_db, json_serialize, json_deserialize
from work_planning.models import (
    ScheduleSlot,
    SlotStatus,
    RecurrencePattern,
)


class ScheduleManager:
    """
    Manages Cass's schedule - her calendar.

    Provides:
    - CRUD operations for schedule slots
    - Time-based queries
    - Recurrence pattern handling
    - State transitions
    - Stats and summaries
    """

    DEFAULT_DAEMON_ID = None

    def __init__(self, daemon_id: str = None):
        """
        Initialize ScheduleManager.

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

    def create_slot(
        self,
        work_item_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        duration_minutes: int = 30,
        recurrence: Optional[RecurrencePattern] = None,
        priority: int = 2,
        budget_allocation_usd: float = 0.0,
        requires_idle: bool = False,
        notes: Optional[str] = None,
    ) -> ScheduleSlot:
        """
        Create a new schedule slot.

        Args:
            work_item_id: Optional link to a work item
            start_time: When the slot starts (None = flexible)
            end_time: When the slot ends (calculated from duration if None)
            duration_minutes: Duration of the slot
            recurrence: Optional recurrence pattern
            priority: Priority level (0-4, matches WorkPriority)
            budget_allocation_usd: Budget allocated for this slot
            requires_idle: Only run when no user activity
            notes: Additional notes

        Returns:
            Created ScheduleSlot
        """
        slot_id = str(uuid.uuid4())[:8]  # Short ID for readability
        now = datetime.now()

        # Calculate end_time if not provided
        if start_time and not end_time:
            end_time = start_time + timedelta(minutes=duration_minutes)

        slot = ScheduleSlot(
            id=slot_id,
            work_item_id=work_item_id,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes,
            recurrence=recurrence,
            priority=priority,
            budget_allocation_usd=budget_allocation_usd,
            requires_idle=requires_idle,
            status=SlotStatus.SCHEDULED,
            created_at=now,
            notes=notes,
        )

        # Save to database
        with get_db() as conn:
            conn.execute("""
                INSERT INTO schedule_slots (
                    id, daemon_id, work_item_id,
                    start_time, end_time, duration_minutes,
                    recurrence_type, recurrence_value, recurrence_end,
                    priority, budget_allocation_usd, requires_idle,
                    status, created_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                slot.id,
                self._daemon_id,
                slot.work_item_id,
                slot.start_time.isoformat() if slot.start_time else None,
                slot.end_time.isoformat() if slot.end_time else None,
                slot.duration_minutes,
                slot.recurrence.type if slot.recurrence else None,
                slot.recurrence.value if slot.recurrence else None,
                slot.recurrence.end_date.isoformat() if slot.recurrence and slot.recurrence.end_date else None,
                slot.priority,
                slot.budget_allocation_usd,
                1 if slot.requires_idle else 0,
                slot.status.value,
                slot.created_at.isoformat(),
                slot.notes,
            ))

        return slot

    def get_slot(self, slot_id: str) -> Optional[ScheduleSlot]:
        """Get a schedule slot by ID."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM schedule_slots
                WHERE id = ? AND daemon_id = ?
            """, (slot_id, self._daemon_id))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_slot(dict(row))

    def update_slot(self, slot_id: str, **updates) -> Optional[ScheduleSlot]:
        """
        Update a schedule slot's fields.

        Args:
            slot_id: ID of the slot
            **updates: Fields to update

        Returns:
            Updated ScheduleSlot or None if not found
        """
        slot = self.get_slot(slot_id)
        if not slot:
            return None

        # Build update query
        allowed_fields = {
            'work_item_id', 'start_time', 'end_time', 'duration_minutes',
            'priority', 'budget_allocation_usd', 'requires_idle', 'notes'
        }

        set_clauses = []
        params = []

        for field, value in updates.items():
            if field not in allowed_fields:
                continue

            if field in ('start_time', 'end_time'):
                set_clauses.append(f"{field} = ?")
                params.append(value.isoformat() if value else None)
            elif field == 'requires_idle':
                set_clauses.append("requires_idle = ?")
                params.append(1 if value else 0)
            else:
                set_clauses.append(f"{field} = ?")
                params.append(value)

        if not set_clauses:
            return slot

        params.extend([slot_id, self._daemon_id])

        with get_db() as conn:
            conn.execute(f"""
                UPDATE schedule_slots
                SET {', '.join(set_clauses)}
                WHERE id = ? AND daemon_id = ?
            """, params)

        return self.get_slot(slot_id)

    def delete_slot(self, slot_id: str) -> bool:
        """Delete a schedule slot."""
        with get_db() as conn:
            cursor = conn.execute("""
                DELETE FROM schedule_slots
                WHERE id = ? AND daemon_id = ?
            """, (slot_id, self._daemon_id))
            return cursor.rowcount > 0

    # =========================================================================
    # TIME-BASED QUERIES
    # =========================================================================

    def get_slots_for_range(
        self,
        start: datetime,
        end: datetime,
        include_flexible: bool = True
    ) -> List[ScheduleSlot]:
        """
        Get slots within a time range.

        Args:
            start: Start of range
            end: End of range
            include_flexible: Include slots with no start_time

        Returns:
            List of ScheduleSlot in the range
        """
        with get_db() as conn:
            if include_flexible:
                cursor = conn.execute("""
                    SELECT * FROM schedule_slots
                    WHERE daemon_id = ?
                    AND (
                        start_time IS NULL
                        OR (start_time >= ? AND start_time < ?)
                        OR (start_time < ? AND end_time > ?)
                    )
                    ORDER BY COALESCE(start_time, '9999-12-31') ASC, priority ASC
                """, (
                    self._daemon_id,
                    start.isoformat(),
                    end.isoformat(),
                    start.isoformat(),
                    start.isoformat()
                ))
            else:
                cursor = conn.execute("""
                    SELECT * FROM schedule_slots
                    WHERE daemon_id = ?
                    AND start_time IS NOT NULL
                    AND (
                        (start_time >= ? AND start_time < ?)
                        OR (start_time < ? AND end_time > ?)
                    )
                    ORDER BY start_time ASC, priority ASC
                """, (
                    self._daemon_id,
                    start.isoformat(),
                    end.isoformat(),
                    start.isoformat(),
                    start.isoformat()
                ))

            return [self._row_to_slot(dict(row)) for row in cursor.fetchall()]

    def get_upcoming_slots(self, hours: float = 24) -> List[ScheduleSlot]:
        """
        Get slots scheduled in the next N hours.

        Args:
            hours: Number of hours to look ahead

        Returns:
            List of upcoming ScheduleSlot
        """
        now = datetime.now()
        end = now + timedelta(hours=hours)

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM schedule_slots
                WHERE daemon_id = ?
                AND status = ?
                AND start_time IS NOT NULL
                AND start_time >= ?
                AND start_time < ?
                ORDER BY start_time ASC, priority ASC
            """, (
                self._daemon_id,
                SlotStatus.SCHEDULED.value,
                now.isoformat(),
                end.isoformat()
            ))

            return [self._row_to_slot(dict(row)) for row in cursor.fetchall()]

    def get_next_slot(self) -> Optional[ScheduleSlot]:
        """Get the next scheduled slot."""
        now = datetime.now()

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM schedule_slots
                WHERE daemon_id = ?
                AND status = ?
                AND start_time IS NOT NULL
                AND start_time >= ?
                ORDER BY start_time ASC
                LIMIT 1
            """, (
                self._daemon_id,
                SlotStatus.SCHEDULED.value,
                now.isoformat()
            ))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_slot(dict(row))

    def get_slots_due_now(self, window_minutes: int = 5) -> List[ScheduleSlot]:
        """
        Get slots that should be executing now.

        Args:
            window_minutes: Consider slots within this window as "now"

        Returns:
            List of ScheduleSlot that should be executing
        """
        now = datetime.now()
        window_end = now + timedelta(minutes=window_minutes)

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM schedule_slots
                WHERE daemon_id = ?
                AND status = ?
                AND start_time IS NOT NULL
                AND start_time <= ?
                AND start_time >= ?
                ORDER BY start_time ASC, priority ASC
            """, (
                self._daemon_id,
                SlotStatus.SCHEDULED.value,
                window_end.isoformat(),
                (now - timedelta(minutes=window_minutes)).isoformat()
            ))

            return [self._row_to_slot(dict(row)) for row in cursor.fetchall()]

    def get_slots_for_work_item(self, work_item_id: str) -> List[ScheduleSlot]:
        """Get all slots linked to a work item."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM schedule_slots
                WHERE daemon_id = ?
                AND work_item_id = ?
                ORDER BY start_time ASC
            """, (self._daemon_id, work_item_id))

            return [self._row_to_slot(dict(row)) for row in cursor.fetchall()]

    def get_flexible_slots(self) -> List[ScheduleSlot]:
        """Get slots with no fixed start time."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM schedule_slots
                WHERE daemon_id = ?
                AND status = ?
                AND start_time IS NULL
                ORDER BY priority ASC, created_at ASC
            """, (self._daemon_id, SlotStatus.SCHEDULED.value))

            return [self._row_to_slot(dict(row)) for row in cursor.fetchall()]

    def get_idle_slots(self) -> List[ScheduleSlot]:
        """Get slots that require idle time."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM schedule_slots
                WHERE daemon_id = ?
                AND status = ?
                AND requires_idle = 1
                ORDER BY priority ASC, created_at ASC
            """, (self._daemon_id, SlotStatus.SCHEDULED.value))

            return [self._row_to_slot(dict(row)) for row in cursor.fetchall()]

    # =========================================================================
    # STATE TRANSITIONS
    # =========================================================================

    def mark_executing(self, slot_id: str) -> Optional[ScheduleSlot]:
        """Mark a slot as currently executing."""
        now = datetime.now()
        with get_db() as conn:
            cursor = conn.execute("""
                UPDATE schedule_slots
                SET status = ?, executed_at = ?
                WHERE id = ? AND daemon_id = ? AND status = ?
            """, (
                SlotStatus.EXECUTING.value,
                now.isoformat(),
                slot_id,
                self._daemon_id,
                SlotStatus.SCHEDULED.value
            ))
            if cursor.rowcount == 0:
                return None
        return self.get_slot(slot_id)

    def mark_completed(self, slot_id: str) -> Optional[ScheduleSlot]:
        """Mark a slot as completed."""
        with get_db() as conn:
            cursor = conn.execute("""
                UPDATE schedule_slots
                SET status = ?
                WHERE id = ? AND daemon_id = ? AND status = ?
            """, (
                SlotStatus.COMPLETED.value,
                slot_id,
                self._daemon_id,
                SlotStatus.EXECUTING.value
            ))
            if cursor.rowcount == 0:
                return None
        return self.get_slot(slot_id)

    def mark_skipped(self, slot_id: str, reason: str = "") -> Optional[ScheduleSlot]:
        """Mark a slot as skipped."""
        with get_db() as conn:
            cursor = conn.execute("""
                UPDATE schedule_slots
                SET status = ?, notes = COALESCE(notes || ' | ', '') || ?
                WHERE id = ? AND daemon_id = ?
                AND status IN (?, ?)
            """, (
                SlotStatus.SKIPPED.value,
                f"SKIPPED: {reason}" if reason else "SKIPPED",
                slot_id,
                self._daemon_id,
                SlotStatus.SCHEDULED.value,
                SlotStatus.EXECUTING.value
            ))
            if cursor.rowcount == 0:
                return None
        return self.get_slot(slot_id)

    # =========================================================================
    # RECURRENCE
    # =========================================================================

    def expand_recurring_slots(
        self,
        until: datetime,
        from_date: Optional[datetime] = None
    ) -> List[ScheduleSlot]:
        """
        Expand recurring slot patterns into concrete slots.

        Args:
            until: Generate slots up to this datetime
            from_date: Start generating from this date (default: now)

        Returns:
            List of newly created ScheduleSlot instances
        """
        if from_date is None:
            from_date = datetime.now()

        # Get recurring patterns
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM schedule_slots
                WHERE daemon_id = ?
                AND recurrence_type IS NOT NULL
                AND (recurrence_end IS NULL OR recurrence_end > ?)
            """, (self._daemon_id, from_date.isoformat()))

            patterns = [self._row_to_slot(dict(row)) for row in cursor.fetchall()]

        created_slots = []

        for pattern in patterns:
            if not pattern.recurrence:
                continue

            # Generate instances based on recurrence type
            instances = self._generate_recurrence_instances(
                pattern, from_date, until
            )

            for instance_time in instances:
                # Check if slot already exists for this time
                if not self._slot_exists_at(pattern.work_item_id, instance_time):
                    new_slot = self.create_slot(
                        work_item_id=pattern.work_item_id,
                        start_time=instance_time,
                        duration_minutes=pattern.duration_minutes,
                        priority=pattern.priority,
                        budget_allocation_usd=pattern.budget_allocation_usd,
                        requires_idle=pattern.requires_idle,
                        notes=f"Generated from recurring pattern {pattern.id}",
                    )
                    created_slots.append(new_slot)

        return created_slots

    def _generate_recurrence_instances(
        self,
        pattern: ScheduleSlot,
        from_date: datetime,
        until: datetime
    ) -> List[datetime]:
        """Generate datetime instances for a recurring pattern."""
        if not pattern.recurrence:
            return []

        instances = []
        recurrence = pattern.recurrence

        if recurrence.type == "daily":
            # Value is time like "09:00"
            try:
                hour, minute = map(int, recurrence.value.split(":"))
            except (ValueError, AttributeError):
                return []

            current = from_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if current < from_date:
                current += timedelta(days=1)

            while current < until:
                if recurrence.end_date is None or current < recurrence.end_date:
                    instances.append(current)
                current += timedelta(days=1)

        elif recurrence.type == "weekly":
            # Value is comma-separated days like "Mon,Wed,Fri"
            day_map = {
                "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3,
                "Fri": 4, "Sat": 5, "Sun": 6
            }
            try:
                days = [day_map[d.strip()] for d in recurrence.value.split(",")]
            except (KeyError, AttributeError):
                return []

            # Use time from pattern's start_time or default to 09:00
            hour = pattern.start_time.hour if pattern.start_time else 9
            minute = pattern.start_time.minute if pattern.start_time else 0

            current = from_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

            while current < until:
                if current.weekday() in days:
                    if current >= from_date:
                        if recurrence.end_date is None or current < recurrence.end_date:
                            instances.append(current)
                current += timedelta(days=1)

        elif recurrence.type == "hourly":
            # Value is interval in hours, e.g., "4" for every 4 hours
            try:
                interval = int(recurrence.value)
            except (ValueError, TypeError):
                return []

            current = from_date.replace(minute=0, second=0, microsecond=0)
            if current < from_date:
                current += timedelta(hours=1)

            while current < until:
                if recurrence.end_date is None or current < recurrence.end_date:
                    instances.append(current)
                current += timedelta(hours=interval)

        # Note: "cron" type would require a cron parser library
        # Could add croniter support in the future

        return instances

    def _slot_exists_at(self, work_item_id: Optional[str], start_time: datetime) -> bool:
        """Check if a slot already exists at this time."""
        with get_db() as conn:
            if work_item_id:
                cursor = conn.execute("""
                    SELECT COUNT(*) as count FROM schedule_slots
                    WHERE daemon_id = ?
                    AND work_item_id = ?
                    AND start_time = ?
                """, (self._daemon_id, work_item_id, start_time.isoformat()))
            else:
                cursor = conn.execute("""
                    SELECT COUNT(*) as count FROM schedule_slots
                    WHERE daemon_id = ?
                    AND start_time = ?
                """, (self._daemon_id, start_time.isoformat()))

            return cursor.fetchone()['count'] > 0

    # =========================================================================
    # STATS
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get schedule statistics."""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        week_end = today_start + timedelta(days=7)

        with get_db() as conn:
            # Total slots
            cursor = conn.execute("""
                SELECT COUNT(*) as total FROM schedule_slots
                WHERE daemon_id = ?
            """, (self._daemon_id,))
            total = cursor.fetchone()['total']

            # By status
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count FROM schedule_slots
                WHERE daemon_id = ?
                GROUP BY status
            """, (self._daemon_id,))
            by_status = {row['status']: row['count'] for row in cursor.fetchall()}

            # Slots today
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM schedule_slots
                WHERE daemon_id = ?
                AND start_time >= ?
                AND start_time < ?
            """, (self._daemon_id, today_start.isoformat(), tomorrow_start.isoformat()))
            today_count = cursor.fetchone()['count']

            # Slots this week
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM schedule_slots
                WHERE daemon_id = ?
                AND start_time >= ?
                AND start_time < ?
            """, (self._daemon_id, today_start.isoformat(), week_end.isoformat()))
            week_count = cursor.fetchone()['count']

            # Total budget allocated (scheduled slots)
            cursor = conn.execute("""
                SELECT COALESCE(SUM(budget_allocation_usd), 0) as budget
                FROM schedule_slots
                WHERE daemon_id = ?
                AND status = ?
            """, (self._daemon_id, SlotStatus.SCHEDULED.value))
            budget_scheduled = cursor.fetchone()['budget']

            # Flexible slots count
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM schedule_slots
                WHERE daemon_id = ?
                AND status = ?
                AND start_time IS NULL
            """, (self._daemon_id, SlotStatus.SCHEDULED.value))
            flexible_count = cursor.fetchone()['count']

            # Idle slots count
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM schedule_slots
                WHERE daemon_id = ?
                AND status = ?
                AND requires_idle = 1
            """, (self._daemon_id, SlotStatus.SCHEDULED.value))
            idle_count = cursor.fetchone()['count']

        return {
            "total": total,
            "by_status": by_status,
            "today_count": today_count,
            "week_count": week_count,
            "budget_scheduled_usd": budget_scheduled,
            "flexible_slots": flexible_count,
            "idle_slots": idle_count,
        }

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _row_to_slot(self, row: Dict) -> ScheduleSlot:
        """Convert a database row to a ScheduleSlot."""
        # Reconstruct recurrence pattern if present
        recurrence = None
        if row.get('recurrence_type'):
            recurrence = RecurrencePattern(
                type=row['recurrence_type'],
                value=row.get('recurrence_value', ''),
                end_date=datetime.fromisoformat(row['recurrence_end']) if row.get('recurrence_end') else None,
            )

        return ScheduleSlot(
            id=row['id'],
            work_item_id=row.get('work_item_id'),
            start_time=datetime.fromisoformat(row['start_time']) if row.get('start_time') else None,
            end_time=datetime.fromisoformat(row['end_time']) if row.get('end_time') else None,
            duration_minutes=row.get('duration_minutes', 30),
            recurrence=recurrence,
            priority=row.get('priority', 2),
            budget_allocation_usd=row.get('budget_allocation_usd', 0.0),
            requires_idle=bool(row.get('requires_idle', 0)),
            status=SlotStatus(row.get('status', 'scheduled')),
            executed_at=datetime.fromisoformat(row['executed_at']) if row.get('executed_at') else None,
            created_at=datetime.fromisoformat(row['created_at']) if row.get('created_at') else datetime.now(),
            notes=row.get('notes'),
        )
