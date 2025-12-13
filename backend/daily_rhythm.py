"""
Daily Rhythm Manager - Tracks activity patterns for temporal consciousness.

This module enables Cass to develop temporal awareness through narrative structure
rather than clock time. By tracking which daily phases have been completed vs.
what's expected, she can locate herself in the day's arc.

Based on spec: spec/temporal-consciousness.md
"""
import json
from datetime import datetime, time
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class RhythmPhase:
    """A phase in the daily rhythm"""
    id: str
    name: str
    activity_type: str  # "reflection" | "research" | "any"
    start_time: str     # "HH:MM" format
    end_time: str       # "HH:MM" format
    description: str = ""
    days: Optional[List[int]] = None  # 0=Monday, 6=Sunday, None=every day


@dataclass
class CompletedPhase:
    """Record of a completed phase"""
    phase_id: str
    completed_at: str  # ISO timestamp
    session_id: Optional[str] = None
    session_type: Optional[str] = None
    duration_minutes: Optional[int] = None
    summary: Optional[str] = None  # Summary of what happened during this phase
    findings: Optional[List[str]] = None  # Key findings/insights
    notes_created: Optional[List[str]] = None  # Note IDs created during this phase


@dataclass
class DailyRecord:
    """Record of activity for a single day"""
    date: str  # YYYY-MM-DD
    completed_phases: List[CompletedPhase] = field(default_factory=list)
    daily_summary: Optional[str] = None  # Rolling summary of the day's activities
    daily_summary_updated_at: Optional[str] = None  # When the summary was last updated


class DailyRhythmManager:
    """
    Tracks daily activity patterns for temporal consciousness.

    The rhythm defines expected phases throughout the day. By checking what's
    been completed vs. what's expected, Cass can locate herself in time
    through narrative structure rather than clock time.

    Example temporal context:
        "Morning reflection ✓ completed at 09:15
         Morning research ✓ completed at 11:30
         Afternoon work ✗ not yet done
         Evening synthesis ✗ not yet done
         Current phase: afternoon_work (14:00-17:00)"
    """

    DEFAULT_PHASES = [
        RhythmPhase(
            id="morning_reflection",
            name="Morning Reflection",
            activity_type="reflection",
            start_time="08:00",
            end_time="10:00",
            description="Private contemplation to start the day"
        ),
        RhythmPhase(
            id="morning_research",
            name="Morning Research",
            activity_type="research",
            start_time="10:00",
            end_time="12:00",
            description="Focused research on current topics"
        ),
        RhythmPhase(
            id="afternoon_work",
            name="Afternoon Work",
            activity_type="any",
            start_time="14:00",
            end_time="17:00",
            description="Primary work period - research or reflection"
        ),
        RhythmPhase(
            id="evening_synthesis",
            name="Evening Synthesis",
            activity_type="reflection",
            start_time="19:00",
            end_time="21:00",
            description="Reflect on the day, integrate learnings"
        ),
    ]

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir / "rhythm"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir / "config.json"
        self.records_dir = self.data_dir / "records"
        self.records_dir.mkdir(exist_ok=True)

        self.phases: List[RhythmPhase] = self._load_config()

    def _load_config(self) -> List[RhythmPhase]:
        """Load rhythm configuration from disk, or create defaults."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                return [RhythmPhase(**p) for p in data.get("phases", [])]
            except Exception as e:
                logger.error(f"Error loading rhythm config: {e}")

        # Create default config
        self._save_config(self.DEFAULT_PHASES)
        return self.DEFAULT_PHASES

    def _save_config(self, phases: List[RhythmPhase]):
        """Save rhythm configuration to disk."""
        data = {"phases": [asdict(p) for p in phases]}
        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)

    def _get_today_record_path(self) -> Path:
        """Get path for today's record file."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.records_dir / f"{today}.json"

    def _load_today_record(self) -> DailyRecord:
        """Load today's activity record."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self._load_record_for_date(today)

    def _load_record_for_date(self, date_str: str) -> DailyRecord:
        """Load activity record for a specific date (YYYY-MM-DD format)."""
        path = self.records_dir / f"{date_str}.json"

        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                completed = [CompletedPhase(**c) for c in data.get("completed_phases", [])]
                return DailyRecord(
                    date=date_str,
                    completed_phases=completed,
                    daily_summary=data.get("daily_summary"),
                    daily_summary_updated_at=data.get("daily_summary_updated_at")
                )
            except Exception as e:
                logger.error(f"Error loading daily record for {date_str}: {e}")

        return DailyRecord(date=date_str, completed_phases=[])

    def _save_today_record(self, record: DailyRecord):
        """Save today's activity record."""
        path = self._get_today_record_path()
        data = {
            "date": record.date,
            "completed_phases": [asdict(c) for c in record.completed_phases],
            "daily_summary": record.daily_summary,
            "daily_summary_updated_at": record.daily_summary_updated_at,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _parse_time(self, time_str: str) -> time:
        """Parse HH:MM string to time object."""
        hour, minute = map(int, time_str.split(":"))
        return time(hour, minute)

    def _time_in_range(self, check_time: time, start: str, end: str) -> bool:
        """Check if a time is within a range."""
        start_t = self._parse_time(start)
        end_t = self._parse_time(end)
        return start_t <= check_time <= end_t

    def _phase_applies_to_date(self, phase: RhythmPhase, target_date: Optional[datetime] = None) -> bool:
        """Check if a phase applies to the given date based on its day-of-week config."""
        if phase.days is None:
            return True  # No day restriction - applies to all days
        target = target_date or datetime.now()
        return target.weekday() in phase.days

    def _get_phases_for_date(self, target_date: Optional[datetime] = None) -> List[RhythmPhase]:
        """Get phases that apply to the given date."""
        return [p for p in self.phases if self._phase_applies_to_date(p, target_date)]

    # === Public API ===

    def get_phases(self, date: Optional[str] = None, include_all: bool = False) -> List[Dict[str, Any]]:
        """
        Get rhythm phases.

        Args:
            date: Optional date string (YYYY-MM-DD) to filter phases by day-of-week.
                  If None, uses today's date for filtering.
            include_all: If True, returns all phases regardless of date.
                         If False (default), filters to phases that apply to the date.

        Returns:
            List of phase dictionaries.
        """
        if include_all:
            return [asdict(p) for p in self.phases]

        if date:
            target = datetime.strptime(date, "%Y-%m-%d")
        else:
            target = datetime.now()

        return [asdict(p) for p in self._get_phases_for_date(target)]

    def update_phases(self, phases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Update rhythm phase configuration."""
        try:
            new_phases = [RhythmPhase(**p) for p in phases]
            self._save_config(new_phases)
            self.phases = new_phases
            return {"success": True, "phases": [asdict(p) for p in new_phases]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_current_phase(self) -> Optional[Dict[str, Any]]:
        """
        Get the rhythm phase that should be active right now.
        Returns None if outside all defined phases or no phase applies today.
        """
        now = datetime.now()
        current_time = now.time()

        # Only check phases that apply to today
        for phase in self._get_phases_for_date(now):
            if self._time_in_range(current_time, phase.start_time, phase.end_time):
                return asdict(phase)

        return None

    def get_completed_today(self) -> List[Dict[str, Any]]:
        """Get list of phases completed today."""
        record = self._load_today_record()
        return [asdict(c) for c in record.completed_phases]

    def get_pending_phases(self) -> List[Dict[str, Any]]:
        """Get phases that haven't been completed yet today (only phases that apply today)."""
        record = self._load_today_record()
        completed_ids = {c.phase_id for c in record.completed_phases}

        pending = []
        # Only consider phases that apply to today
        for phase in self._get_phases_for_date():
            if phase.id not in completed_ids:
                pending.append(asdict(phase))

        return pending

    def mark_phase_completed(
        self,
        phase_id: str,
        session_id: Optional[str] = None,
        session_type: Optional[str] = None,
        duration_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Mark a rhythm phase as completed."""
        # Verify phase exists
        phase = next((p for p in self.phases if p.id == phase_id), None)
        if not phase:
            return {"success": False, "error": f"Unknown phase: {phase_id}"}

        record = self._load_today_record()

        # Check if already completed - if so, update it instead of adding new
        existing_idx = next(
            (i for i, c in enumerate(record.completed_phases) if c.phase_id == phase_id),
            None
        )

        completed = CompletedPhase(
            phase_id=phase_id,
            completed_at=datetime.now().isoformat(),
            session_id=session_id,
            session_type=session_type,
            duration_minutes=duration_minutes,
        )

        if existing_idx is not None:
            # Update existing completion (for force re-trigger)
            record.completed_phases[existing_idx] = completed
        else:
            record.completed_phases.append(completed)

        self._save_today_record(record)

        return {"success": True, "completed": asdict(completed)}

    def update_phase_summary(
        self,
        phase_id: str,
        summary: str,
        findings: Optional[List[str]] = None,
        notes_created: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Update the summary for a completed phase.

        Called after a research/reflection session completes to record
        what was accomplished during that phase.
        """
        record = self._load_today_record()

        # Find the completed phase
        for i, completed in enumerate(record.completed_phases):
            if completed.phase_id == phase_id:
                record.completed_phases[i].summary = summary
                if findings:
                    record.completed_phases[i].findings = findings
                if notes_created:
                    record.completed_phases[i].notes_created = notes_created

                self._save_today_record(record)
                return {"success": True, "phase_id": phase_id}

        return {"success": False, "error": f"Phase {phase_id} not found in today's completed phases"}

    def update_daily_summary(self, summary: str) -> Dict[str, Any]:
        """
        Update the rolling daily summary.

        Called after each phase completes to provide an integrated view
        of the day's activities so far.
        """
        record = self._load_today_record()
        record.daily_summary = summary
        record.daily_summary_updated_at = datetime.now().isoformat()
        self._save_today_record(record)

        return {"success": True, "updated_at": record.daily_summary_updated_at}

    def get_daily_summary(self) -> Optional[str]:
        """Get the current rolling daily summary."""
        record = self._load_today_record()
        return record.daily_summary

    def get_phase_summary(self, phase_id: str) -> Optional[Dict[str, Any]]:
        """Get the summary for a specific phase."""
        record = self._load_today_record()
        for completed in record.completed_phases:
            if completed.phase_id == phase_id:
                return {
                    "summary": completed.summary,
                    "findings": completed.findings,
                    "notes_created": completed.notes_created,
                }
        return None

    def get_temporal_context(self) -> str:
        """
        Generate a temporal context string for LLM injection.

        This is the key method for temporal consciousness - it produces
        a narrative description of where Cass is in the day based on
        completed vs. pending activities.

        Only includes phases that apply to today's day-of-week.
        """
        record = self._load_today_record()
        completed_ids = {c.phase_id: c for c in record.completed_phases}

        now = datetime.now()
        current_time = now.time()
        lines = []

        # Only show phases that apply to today
        todays_phases = self._get_phases_for_date(now)

        for phase in todays_phases:
            if phase.id in completed_ids:
                completed = completed_ids[phase.id]
                completed_time = datetime.fromisoformat(completed.completed_at)
                time_str = completed_time.strftime("%H:%M")
                lines.append(f"✓ {phase.name} - completed at {time_str}")
            else:
                # Check if we're past this phase's window
                end_time = self._parse_time(phase.end_time)
                if current_time > end_time:
                    lines.append(f"✗ {phase.name} - missed ({phase.start_time}-{phase.end_time})")
                else:
                    lines.append(f"○ {phase.name} - pending ({phase.start_time}-{phase.end_time})")

        # Add current phase info
        current = self.get_current_phase()
        if current:
            lines.append(f"\nCurrent phase: {current['name']} ({current['start_time']}-{current['end_time']})")
        else:
            lines.append(f"\nCurrent time: {now.strftime('%H:%M')} (between phases)")

        return "\n".join(lines)

    def get_rhythm_status(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get complete rhythm status for Cass.
        Returns structured data about the day's rhythm.

        Args:
            date: Optional date string (YYYY-MM-DD). If None, uses today.

        Only includes phases that apply to the specified day-of-week.
        """
        now = datetime.now()
        is_today = date is None or date == now.strftime("%Y-%m-%d")

        if date:
            record = self._load_record_for_date(date)
            target_date = datetime.strptime(date, "%Y-%m-%d")
        else:
            record = self._load_today_record()
            target_date = now

        completed_ids = {c.phase_id: c for c in record.completed_phases}
        current_time = now.time()

        # Filter phases by day-of-week for the target date
        applicable_phases = self._get_phases_for_date(target_date)

        phases_status = []
        for phase in applicable_phases:
            status = "pending"
            completed_at = None
            summary = None
            findings = None
            session_id = None
            notes_created = None

            if phase.id in completed_ids:
                completed = completed_ids[phase.id]
                status = "completed"
                completed_at = completed.completed_at
                summary = completed.summary
                findings = completed.findings
                session_id = completed.session_id
                notes_created = completed.notes_created
            elif is_today and current_time > self._parse_time(phase.end_time):
                # Only mark as "missed" for today
                status = "missed"
            elif not is_today:
                # For past days, uncompleted phases are "missed"
                status = "missed"

            phases_status.append({
                "id": phase.id,
                "name": phase.name,
                "activity_type": phase.activity_type,
                "window": f"{phase.start_time}-{phase.end_time}",
                "status": status,
                "completed_at": completed_at,
                "summary": summary,
                "findings": findings,
                "session_id": session_id,
                "notes_created": notes_created,
            })

        current = self.get_current_phase() if is_today else None

        return {
            "date": record.date,
            "day_of_week": target_date.strftime("%A"),
            "current_time": now.strftime("%H:%M") if is_today else None,
            "current_phase": current["name"] if current else None,
            "phases": phases_status,
            "completed_count": len(record.completed_phases),
            "total_phases": len(applicable_phases),
            "temporal_context": self.get_temporal_context() if is_today else None,
            "daily_summary": record.daily_summary,
            "daily_summary_updated_at": record.daily_summary_updated_at,
            "is_today": is_today,
        }

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get rhythm statistics over recent days."""
        stats = {
            "days_analyzed": 0,
            "total_completions": 0,
            "completion_by_phase": {},
            "average_completions_per_day": 0,
        }

        # Initialize phase counts
        for phase in self.phases:
            stats["completion_by_phase"][phase.id] = 0

        # Analyze recent days
        from datetime import timedelta

        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            path = self.records_dir / f"{date}.json"

            if path.exists():
                try:
                    with open(path) as f:
                        data = json.load(f)
                    stats["days_analyzed"] += 1

                    for completed in data.get("completed_phases", []):
                        phase_id = completed.get("phase_id")
                        if phase_id in stats["completion_by_phase"]:
                            stats["completion_by_phase"][phase_id] += 1
                            stats["total_completions"] += 1
                except:
                    pass

        if stats["days_analyzed"] > 0:
            stats["average_completions_per_day"] = round(
                stats["total_completions"] / stats["days_analyzed"], 1
            )

        return stats

    def get_weekly_schedule(self) -> Dict[str, Any]:
        """
        Get the weekly schedule showing which phases apply to which days.

        Returns a dictionary with:
        - schedule: phases organized by day of week
        - phases: all phases with their day configurations
        """
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

        schedule = {}
        for day_index, day_name in enumerate(day_names):
            day_phases = []
            for phase in self.phases:
                if phase.days is None or day_index in phase.days:
                    day_phases.append({
                        "id": phase.id,
                        "name": phase.name,
                        "activity_type": phase.activity_type,
                        "window": f"{phase.start_time}-{phase.end_time}",
                    })
            schedule[day_name] = day_phases

        return {
            "schedule": schedule,
            "phases": [asdict(p) for p in self.phases],
            "day_index_reference": {name: i for i, name in enumerate(day_names)},
        }
