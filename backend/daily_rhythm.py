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


@dataclass
class CompletedPhase:
    """Record of a completed phase"""
    phase_id: str
    completed_at: str  # ISO timestamp
    session_id: Optional[str] = None
    session_type: Optional[str] = None
    duration_minutes: Optional[int] = None


@dataclass
class DailyRecord:
    """Record of activity for a single day"""
    date: str  # YYYY-MM-DD
    completed_phases: List[CompletedPhase] = field(default_factory=list)


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
        path = self._get_today_record_path()
        today = datetime.now().strftime("%Y-%m-%d")

        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                completed = [CompletedPhase(**c) for c in data.get("completed_phases", [])]
                return DailyRecord(date=today, completed_phases=completed)
            except Exception as e:
                logger.error(f"Error loading daily record: {e}")

        return DailyRecord(date=today, completed_phases=[])

    def _save_today_record(self, record: DailyRecord):
        """Save today's activity record."""
        path = self._get_today_record_path()
        data = {
            "date": record.date,
            "completed_phases": [asdict(c) for c in record.completed_phases]
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

    # === Public API ===

    def get_phases(self) -> List[Dict[str, Any]]:
        """Get all configured rhythm phases."""
        return [asdict(p) for p in self.phases]

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
        Returns None if outside all defined phases.
        """
        now = datetime.now().time()

        for phase in self.phases:
            if self._time_in_range(now, phase.start_time, phase.end_time):
                return asdict(phase)

        return None

    def get_completed_today(self) -> List[Dict[str, Any]]:
        """Get list of phases completed today."""
        record = self._load_today_record()
        return [asdict(c) for c in record.completed_phases]

    def get_pending_phases(self) -> List[Dict[str, Any]]:
        """Get phases that haven't been completed yet today."""
        record = self._load_today_record()
        completed_ids = {c.phase_id for c in record.completed_phases}

        pending = []
        for phase in self.phases:
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

        # Check if already completed
        if any(c.phase_id == phase_id for c in record.completed_phases):
            return {"success": False, "error": f"Phase {phase_id} already completed today"}

        completed = CompletedPhase(
            phase_id=phase_id,
            completed_at=datetime.now().isoformat(),
            session_id=session_id,
            session_type=session_type,
            duration_minutes=duration_minutes,
        )

        record.completed_phases.append(completed)
        self._save_today_record(record)

        return {"success": True, "completed": asdict(completed)}

    def get_temporal_context(self) -> str:
        """
        Generate a temporal context string for LLM injection.

        This is the key method for temporal consciousness - it produces
        a narrative description of where Cass is in the day based on
        completed vs. pending activities.
        """
        record = self._load_today_record()
        completed_ids = {c.phase_id: c for c in record.completed_phases}

        now = datetime.now()
        current_time = now.time()
        lines = []

        for phase in self.phases:
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

    def get_rhythm_status(self) -> Dict[str, Any]:
        """
        Get complete rhythm status for Cass.
        Returns structured data about the day's rhythm.
        """
        record = self._load_today_record()
        completed_ids = {c.phase_id: c for c in record.completed_phases}
        now = datetime.now()
        current_time = now.time()

        phases_status = []
        for phase in self.phases:
            status = "pending"
            completed_at = None

            if phase.id in completed_ids:
                status = "completed"
                completed_at = completed_ids[phase.id].completed_at
            elif current_time > self._parse_time(phase.end_time):
                status = "missed"

            phases_status.append({
                "id": phase.id,
                "name": phase.name,
                "activity_type": phase.activity_type,
                "window": f"{phase.start_time}-{phase.end_time}",
                "status": status,
                "completed_at": completed_at,
            })

        current = self.get_current_phase()

        return {
            "date": record.date,
            "current_time": now.strftime("%H:%M"),
            "current_phase": current["name"] if current else None,
            "phases": phases_status,
            "completed_count": len(record.completed_phases),
            "total_phases": len(self.phases),
            "temporal_context": self.get_temporal_context(),
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
