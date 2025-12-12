"""
Cass Vessel - Research Scheduler
Schedule-based research session execution with initiative requests and admin approval.
"""
import uuid
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ScheduleStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"  # Cass requested, awaiting admin
    APPROVED = "approved"                   # Admin approved, will run
    PAUSED = "paused"                       # Temporarily paused
    COMPLETED = "completed"                 # One-time schedule completed
    REJECTED = "rejected"                   # Admin rejected
    EXPIRED = "expired"                     # Past scheduled time, never ran


class ScheduleRecurrence(str, Enum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"


class SessionType(str, Enum):
    REFLECTION = "reflection"
    RESEARCH = "research"


@dataclass
class ScheduledSession:
    """A scheduled activity session request"""
    schedule_id: str
    created_at: str
    status: ScheduleStatus

    # Request details
    requested_by: str  # "cass" or admin username
    focus_description: str
    focus_item_id: Optional[str] = None  # Agenda item to focus on

    # Session type - determines which runner handles it
    session_type: SessionType = SessionType.REFLECTION

    # Scheduling
    recurrence: ScheduleRecurrence = ScheduleRecurrence.ONCE
    preferred_time: Optional[str] = None  # HH:MM format
    duration_minutes: int = 30
    mode: str = "explore"

    # Approval
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None

    # Execution tracking
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    last_session_id: Optional[str] = None

    # Notes
    notes: str = ""


class ResearchScheduler:
    """
    Manages scheduled research sessions.

    Flow:
    1. Cass requests session via propose_research_session tool
    2. Admin reviews and approves/rejects via API
    3. Scheduler checks for due sessions and triggers them
    4. Session runs through ResearchSessionManager
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir / "research" / "schedules"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Callback for triggering sessions (set by main app)
        self._session_trigger: Optional[Callable] = None

        # Load existing schedules
        self.schedules: Dict[str, ScheduledSession] = {}
        self._load_schedules()

    def _load_schedules(self):
        """Load all schedules from disk"""
        for schedule_file in self.data_dir.glob("*.json"):
            try:
                with open(schedule_file) as f:
                    data = json.load(f)
                data["status"] = ScheduleStatus(data["status"])
                data["recurrence"] = ScheduleRecurrence(data["recurrence"])
                # Handle session_type (default to reflection for backwards compatibility)
                if "session_type" in data:
                    data["session_type"] = SessionType(data["session_type"])
                else:
                    data["session_type"] = SessionType.REFLECTION
                schedule = ScheduledSession(**data)
                self.schedules[schedule.schedule_id] = schedule
            except Exception as e:
                logger.error(f"Error loading schedule {schedule_file}: {e}")

    def _save_schedule(self, schedule: ScheduledSession):
        """Save a schedule to disk"""
        path = self.data_dir / f"{schedule.schedule_id}.json"
        data = asdict(schedule)
        data["status"] = schedule.status.value
        data["recurrence"] = schedule.recurrence.value
        data["session_type"] = schedule.session_type.value
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self.schedules[schedule.schedule_id] = schedule

    def set_session_trigger(self, trigger: Callable):
        """Set the callback for triggering research sessions"""
        self._session_trigger = trigger

    # === Cass-facing API ===

    def request_session(
        self,
        focus_description: str,
        focus_item_id: Optional[str] = None,
        preferred_time: Optional[str] = None,
        duration_minutes: int = 30,
        recurrence: str = "once",
        mode: str = "explore",
        session_type: str = "reflection"
    ) -> Dict[str, Any]:
        """
        Cass requests a scheduled activity session.
        Creates a pending request for admin approval.

        Args:
            focus_description: What Cass wants to do (research topic or reflection theme)
            focus_item_id: Optional agenda item ID
            preferred_time: Preferred time in HH:MM format
            duration_minutes: Requested duration
            recurrence: "once", "daily", or "weekly"
            mode: "explore" or "deep"
            session_type: "reflection" or "research"

        Returns:
            The created schedule request
        """
        schedule_id = str(uuid.uuid4())[:8]
        now = datetime.now()

        # Calculate next_run based on preferred_time
        next_run = None
        if preferred_time:
            try:
                hour, minute = map(int, preferred_time.split(":"))
                next_run_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run_dt <= now:
                    next_run_dt += timedelta(days=1)
                next_run = next_run_dt.isoformat()
            except:
                pass

        schedule = ScheduledSession(
            schedule_id=schedule_id,
            created_at=now.isoformat(),
            status=ScheduleStatus.PENDING_APPROVAL,
            requested_by="cass",
            focus_description=focus_description,
            focus_item_id=focus_item_id,
            session_type=SessionType(session_type),
            preferred_time=preferred_time,
            duration_minutes=min(duration_minutes, 60),
            recurrence=ScheduleRecurrence(recurrence),
            mode=mode,
            next_run=next_run
        )

        self._save_schedule(schedule)

        return {
            "success": True,
            "schedule_id": schedule_id,
            "status": "pending_approval",
            "message": "Research session request submitted for approval",
            "schedule": self._schedule_to_dict(schedule)
        }

    def list_my_requests(self, include_completed: bool = False) -> List[Dict[str, Any]]:
        """List Cass's schedule requests"""
        results = []
        for schedule in self.schedules.values():
            if schedule.requested_by != "cass":
                continue
            if not include_completed and schedule.status in [
                ScheduleStatus.COMPLETED, ScheduleStatus.REJECTED, ScheduleStatus.EXPIRED
            ]:
                continue
            results.append(self._schedule_to_dict(schedule))

        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results

    def cancel_request(self, schedule_id: str) -> Dict[str, Any]:
        """Cass cancels a pending request"""
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            return {"success": False, "error": "Schedule not found"}

        if schedule.requested_by != "cass":
            return {"success": False, "error": "Can only cancel your own requests"}

        if schedule.status != ScheduleStatus.PENDING_APPROVAL:
            return {"success": False, "error": f"Cannot cancel schedule in {schedule.status.value} state"}

        schedule.status = ScheduleStatus.REJECTED
        schedule.rejection_reason = "Cancelled by requester"
        self._save_schedule(schedule)

        return {"success": True, "message": "Request cancelled"}

    # === Admin API ===

    def approve_schedule(
        self,
        schedule_id: str,
        approved_by: str,
        adjust_time: Optional[str] = None,
        adjust_duration: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Admin approves a schedule request"""
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            return {"success": False, "error": "Schedule not found"}

        if schedule.status != ScheduleStatus.PENDING_APPROVAL:
            return {"success": False, "error": f"Schedule is {schedule.status.value}, not pending"}

        schedule.status = ScheduleStatus.APPROVED
        schedule.approved_by = approved_by
        schedule.approved_at = datetime.now().isoformat()

        if adjust_time:
            schedule.preferred_time = adjust_time
            # Recalculate next_run
            try:
                hour, minute = map(int, adjust_time.split(":"))
                now = datetime.now()
                next_run_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run_dt <= now:
                    next_run_dt += timedelta(days=1)
                schedule.next_run = next_run_dt.isoformat()
            except:
                pass

        if adjust_duration:
            schedule.duration_minutes = min(adjust_duration, 60)

        if notes:
            schedule.notes = notes

        self._save_schedule(schedule)

        return {
            "success": True,
            "message": "Schedule approved",
            "schedule": self._schedule_to_dict(schedule)
        }

    def reject_schedule(
        self,
        schedule_id: str,
        rejected_by: str,
        reason: str
    ) -> Dict[str, Any]:
        """Admin rejects a schedule request"""
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            return {"success": False, "error": "Schedule not found"}

        if schedule.status != ScheduleStatus.PENDING_APPROVAL:
            return {"success": False, "error": f"Schedule is {schedule.status.value}, not pending"}

        schedule.status = ScheduleStatus.REJECTED
        schedule.rejection_reason = reason
        schedule.notes = f"Rejected by {rejected_by}: {reason}"
        self._save_schedule(schedule)

        return {"success": True, "message": "Schedule rejected"}

    def pause_schedule(self, schedule_id: str) -> Dict[str, Any]:
        """Pause an approved schedule"""
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            return {"success": False, "error": "Schedule not found"}

        if schedule.status != ScheduleStatus.APPROVED:
            return {"success": False, "error": f"Can only pause approved schedules"}

        schedule.status = ScheduleStatus.PAUSED
        self._save_schedule(schedule)

        return {"success": True, "message": "Schedule paused"}

    def resume_schedule(self, schedule_id: str) -> Dict[str, Any]:
        """Resume a paused schedule"""
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            return {"success": False, "error": "Schedule not found"}

        if schedule.status != ScheduleStatus.PAUSED:
            return {"success": False, "error": f"Schedule is not paused"}

        schedule.status = ScheduleStatus.APPROVED
        self._save_schedule(schedule)

        return {"success": True, "message": "Schedule resumed"}

    def delete_schedule(self, schedule_id: str) -> Dict[str, Any]:
        """Delete a schedule entirely"""
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            return {"success": False, "error": "Schedule not found"}

        # Remove from memory and disk
        del self.schedules[schedule_id]
        path = self.data_dir / f"{schedule_id}.json"
        if path.exists():
            path.unlink()

        return {"success": True, "message": "Schedule deleted"}

    def list_schedules(
        self,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List all schedules with optional filtering"""
        results = []
        for schedule in self.schedules.values():
            if status and schedule.status.value != status:
                continue
            results.append(self._schedule_to_dict(schedule))

        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results[:limit]

    def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific schedule"""
        schedule = self.schedules.get(schedule_id)
        return self._schedule_to_dict(schedule) if schedule else None

    def get_pending_count(self) -> int:
        """Get count of pending approval requests"""
        return sum(
            1 for s in self.schedules.values()
            if s.status == ScheduleStatus.PENDING_APPROVAL
        )

    # === Scheduler Execution ===

    def get_due_schedules(self) -> List[ScheduledSession]:
        """Get schedules that are due to run now"""
        now = datetime.now()
        due = []

        for schedule in self.schedules.values():
            if schedule.status != ScheduleStatus.APPROVED:
                continue

            if not schedule.next_run:
                continue

            next_run = datetime.fromisoformat(schedule.next_run)
            if next_run <= now:
                due.append(schedule)

        return due

    def mark_session_started(self, schedule_id: str, session_id: str):
        """Mark that a scheduled session has started"""
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            return

        schedule.last_run = datetime.now().isoformat()
        schedule.last_session_id = session_id
        schedule.run_count += 1

        # Calculate next run for recurring schedules
        if schedule.recurrence == ScheduleRecurrence.ONCE:
            schedule.status = ScheduleStatus.COMPLETED
            schedule.next_run = None
        else:
            # Calculate next occurrence
            now = datetime.now()
            if schedule.preferred_time:
                hour, minute = map(int, schedule.preferred_time.split(":"))
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            else:
                next_run = now

            if schedule.recurrence == ScheduleRecurrence.DAILY:
                next_run += timedelta(days=1)
            elif schedule.recurrence == ScheduleRecurrence.WEEKLY:
                next_run += timedelta(weeks=1)

            schedule.next_run = next_run.isoformat()

        self._save_schedule(schedule)

    async def check_and_trigger_due_sessions(self, runners: Optional[Dict[str, Any]] = None):
        """
        Check for due sessions and trigger them.

        Args:
            runners: Dict mapping session_type to runner instances.
                     Each runner must have an async start_session() method.
                     If not provided, falls back to legacy _session_trigger callback.
        """
        due_schedules = self.get_due_schedules()
        triggered = []

        for schedule in due_schedules:
            try:
                logger.info(f"Triggering scheduled {schedule.session_type.value} session: {schedule.schedule_id}")

                session_id = None

                # New dispatch pattern: use runners dict
                if runners:
                    runner = runners.get(schedule.session_type.value)
                    if runner:
                        session = await runner.start_session(
                            duration_minutes=schedule.duration_minutes,
                            focus=schedule.focus_description,
                            focus_item_id=schedule.focus_item_id,
                            mode=schedule.mode,
                            trigger="scheduled",
                        )
                        session_id = getattr(session, 'session_id', None)
                    else:
                        logger.warning(f"No runner for session type: {schedule.session_type.value}")
                        continue

                # Legacy fallback: use single callback
                elif self._session_trigger:
                    session_id = await self._session_trigger(
                        duration_minutes=schedule.duration_minutes,
                        mode=schedule.mode,
                        focus_item_id=schedule.focus_item_id,
                        focus_description=schedule.focus_description
                    )
                else:
                    logger.warning("No runners or session trigger configured")
                    return []

                if session_id:
                    self.mark_session_started(schedule.schedule_id, session_id)
                    triggered.append(schedule.schedule_id)

            except Exception as e:
                logger.error(f"Error triggering schedule {schedule.schedule_id}: {e}")

        return triggered

    def _schedule_to_dict(self, schedule: ScheduledSession) -> Dict[str, Any]:
        """Convert schedule to dict for API responses"""
        d = asdict(schedule)
        d["status"] = schedule.status.value
        d["recurrence"] = schedule.recurrence.value
        d["session_type"] = schedule.session_type.value
        return d

    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics"""
        total = len(self.schedules)
        by_status = {}
        for schedule in self.schedules.values():
            status = schedule.status.value
            by_status[status] = by_status.get(status, 0) + 1

        total_runs = sum(s.run_count for s in self.schedules.values())

        return {
            "total_schedules": total,
            "by_status": by_status,
            "total_runs": total_runs,
            "pending_approval": by_status.get("pending_approval", 0),
            "active_schedules": by_status.get("approved", 0)
        }
