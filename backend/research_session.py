"""
Cass Vessel - Research Session Management
Focused research execution mode with session state tracking.
"""
import uuid
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
from enum import Enum


class SessionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class SessionMode(str, Enum):
    EXPLORE = "explore"  # Broad exploration across agenda
    DEEP = "deep"        # Focused on one question/item


@dataclass
class ResearchSession:
    """A focused research session"""
    session_id: str
    started_at: str
    status: SessionStatus
    mode: SessionMode
    duration_limit_minutes: int

    # Focus
    focus_item_id: Optional[str] = None  # Agenda item ID
    focus_description: Optional[str] = None

    # Tracking
    ended_at: Optional[str] = None
    paused_at: Optional[str] = None
    pause_reason: Optional[str] = None

    # Activity counters
    searches_performed: int = 0
    urls_fetched: int = 0
    notes_created: List[str] = field(default_factory=list)
    progress_entries: List[str] = field(default_factory=list)

    # Summary
    summary: Optional[str] = None
    findings_summary: Optional[str] = None
    next_steps: Optional[str] = None

    # Conversation tracking
    conversation_id: Optional[str] = None
    message_count: int = 0

    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE

    def is_overtime(self) -> bool:
        if not self.is_active():
            return False
        started = datetime.fromisoformat(self.started_at)
        limit = timedelta(minutes=self.duration_limit_minutes)
        return datetime.now() - started > limit

    def elapsed_minutes(self) -> float:
        started = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.ended_at) if self.ended_at else datetime.now()
        return (end - started).total_seconds() / 60

    def remaining_minutes(self) -> float:
        return max(0, self.duration_limit_minutes - self.elapsed_minutes())


class ResearchSessionManager:
    """
    Manages research sessions for Cass.
    Only one session can be active at a time.
    """

    # Rate limits for sessions
    MAX_SEARCHES_PER_SESSION = 50
    MAX_URLS_PER_SESSION = 30
    MIN_COOLDOWN_MINUTES = 5  # Between sessions

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir / "research" / "sessions"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.current_session: Optional[ResearchSession] = None
        self._load_current_session()

    def _load_current_session(self):
        """Load any active session from disk"""
        current_file = self.data_dir / "current.json"
        if current_file.exists():
            try:
                with open(current_file) as f:
                    data = json.load(f)
                # Convert enums
                data["status"] = SessionStatus(data["status"])
                data["mode"] = SessionMode(data["mode"])
                self.current_session = ResearchSession(**data)

                # Check if it should have timed out
                if self.current_session.is_active() and self.current_session.is_overtime():
                    self._auto_timeout_session()
            except Exception as e:
                print(f"Error loading current session: {e}")
                self.current_session = None

    def _save_current_session(self):
        """Save current session to disk"""
        current_file = self.data_dir / "current.json"
        if self.current_session:
            data = asdict(self.current_session)
            # Convert enums to strings
            data["status"] = self.current_session.status.value
            data["mode"] = self.current_session.mode.value
            with open(current_file, "w") as f:
                json.dump(data, f, indent=2)
        elif current_file.exists():
            current_file.unlink()

    def _archive_session(self, session: ResearchSession):
        """Archive a completed session"""
        archive_file = self.data_dir / f"{session.session_id}.json"
        data = asdict(session)
        data["status"] = session.status.value
        data["mode"] = session.mode.value
        with open(archive_file, "w") as f:
            json.dump(data, f, indent=2)

    def _auto_timeout_session(self):
        """Auto-terminate an overtime session"""
        if self.current_session and self.current_session.is_active():
            self.current_session.status = SessionStatus.TERMINATED
            self.current_session.ended_at = datetime.now().isoformat()
            self.current_session.summary = "[Session auto-terminated due to time limit]"
            self._archive_session(self.current_session)
            self._save_current_session()

    def _can_start_session(self) -> tuple[bool, str]:
        """Check if a new session can be started"""
        if self.current_session and self.current_session.is_active():
            return False, "A research session is already active"

        # Check cooldown
        if self.current_session and self.current_session.ended_at:
            ended = datetime.fromisoformat(self.current_session.ended_at)
            cooldown = timedelta(minutes=self.MIN_COOLDOWN_MINUTES)
            if datetime.now() - ended < cooldown:
                remaining = (cooldown - (datetime.now() - ended)).seconds // 60
                return False, f"Cooldown period: {remaining} minutes remaining"

        return True, ""

    # === Public API ===

    def start_session(
        self,
        duration_minutes: int = 30,
        mode: str = "explore",
        focus_item_id: Optional[str] = None,
        focus_description: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Start a new research session.

        Args:
            duration_minutes: Max session length
            mode: "explore" or "deep"
            focus_item_id: Specific agenda item to focus on
            focus_description: Human-readable description of focus
            conversation_id: Associated conversation

        Returns:
            Session info or error
        """
        can_start, reason = self._can_start_session()
        if not can_start:
            return {"success": False, "error": reason}

        session = ResearchSession(
            session_id=str(uuid.uuid4())[:8],
            started_at=datetime.now().isoformat(),
            status=SessionStatus.ACTIVE,
            mode=SessionMode(mode),
            duration_limit_minutes=duration_minutes,
            focus_item_id=focus_item_id,
            focus_description=focus_description,
            conversation_id=conversation_id
        )

        self.current_session = session
        self._save_current_session()

        return {
            "success": True,
            "session": asdict(session),
            "message": f"Research session started. You have {duration_minutes} minutes."
        }

    def get_current_session(self) -> Optional[Dict[str, Any]]:
        """Get the current session status"""
        if not self.current_session:
            return None

        # Check for timeout
        if self.current_session.is_active() and self.current_session.is_overtime():
            self._auto_timeout_session()

        data = asdict(self.current_session)
        data["status"] = self.current_session.status.value
        data["mode"] = self.current_session.mode.value
        data["elapsed_minutes"] = round(self.current_session.elapsed_minutes(), 1)
        data["remaining_minutes"] = round(self.current_session.remaining_minutes(), 1)
        data["is_overtime"] = self.current_session.is_overtime()
        return data

    def pause_session(self, reason: Optional[str] = None) -> Dict[str, Any]:
        """Pause the current session"""
        if not self.current_session or not self.current_session.is_active():
            return {"success": False, "error": "No active session to pause"}

        self.current_session.status = SessionStatus.PAUSED
        self.current_session.paused_at = datetime.now().isoformat()
        self.current_session.pause_reason = reason
        self._save_current_session()

        return {
            "success": True,
            "message": f"Session paused. Elapsed: {self.current_session.elapsed_minutes():.1f} minutes"
        }

    def resume_session(self) -> Dict[str, Any]:
        """Resume a paused session"""
        if not self.current_session:
            return {"success": False, "error": "No session to resume"}

        if self.current_session.status != SessionStatus.PAUSED:
            return {"success": False, "error": "Session is not paused"}

        # Extend duration by pause time
        if self.current_session.paused_at:
            paused = datetime.fromisoformat(self.current_session.paused_at)
            pause_duration = (datetime.now() - paused).total_seconds() / 60
            # Don't count pause time against duration
            # (Could add this as extension if desired)

        self.current_session.status = SessionStatus.ACTIVE
        self.current_session.paused_at = None
        self.current_session.pause_reason = None
        self._save_current_session()

        return {
            "success": True,
            "message": f"Session resumed. {self.current_session.remaining_minutes():.1f} minutes remaining"
        }

    def conclude_session(
        self,
        summary: str,
        findings_summary: Optional[str] = None,
        next_steps: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Conclude the current session with a summary.

        Args:
            summary: Cass's summary of what was accomplished
            findings_summary: Key findings from the session
            next_steps: What to explore next

        Returns:
            Final session info
        """
        if not self.current_session:
            return {"success": False, "error": "No active session"}

        if self.current_session.status not in [SessionStatus.ACTIVE, SessionStatus.PAUSED]:
            return {"success": False, "error": "Session already concluded"}

        self.current_session.status = SessionStatus.COMPLETED
        self.current_session.ended_at = datetime.now().isoformat()
        self.current_session.summary = summary
        self.current_session.findings_summary = findings_summary
        self.current_session.next_steps = next_steps

        self._archive_session(self.current_session)
        self._save_current_session()

        result = asdict(self.current_session)
        result["status"] = self.current_session.status.value
        result["mode"] = self.current_session.mode.value
        result["elapsed_minutes"] = round(self.current_session.elapsed_minutes(), 1)

        return {
            "success": True,
            "session": result,
            "message": f"Session completed. Duration: {self.current_session.elapsed_minutes():.1f} minutes"
        }

    def terminate_session(self, reason: str = "Manually terminated") -> Dict[str, Any]:
        """Force-terminate the current session (admin action)"""
        if not self.current_session:
            return {"success": False, "error": "No active session"}

        self.current_session.status = SessionStatus.TERMINATED
        self.current_session.ended_at = datetime.now().isoformat()
        self.current_session.summary = f"[Terminated: {reason}]"

        self._archive_session(self.current_session)
        self._save_current_session()

        return {
            "success": True,
            "message": f"Session terminated: {reason}"
        }

    def record_search(self) -> bool:
        """Record a search performed. Returns False if over limit."""
        if not self.current_session or not self.current_session.is_active():
            return True  # No session, don't block

        if self.current_session.searches_performed >= self.MAX_SEARCHES_PER_SESSION:
            return False

        self.current_session.searches_performed += 1
        self._save_current_session()
        return True

    def record_fetch(self) -> bool:
        """Record a URL fetch. Returns False if over limit."""
        if not self.current_session or not self.current_session.is_active():
            return True

        if self.current_session.urls_fetched >= self.MAX_URLS_PER_SESSION:
            return False

        self.current_session.urls_fetched += 1
        self._save_current_session()
        return True

    def record_note(self, note_id: str):
        """Record a note created during the session"""
        if self.current_session and self.current_session.is_active():
            self.current_session.notes_created.append(note_id)
            self._save_current_session()

    def record_progress(self, progress_id: str):
        """Record a progress entry from the session"""
        if self.current_session and self.current_session.is_active():
            self.current_session.progress_entries.append(progress_id)
            self._save_current_session()

    def increment_messages(self):
        """Track message count in session"""
        if self.current_session and self.current_session.is_active():
            self.current_session.message_count += 1
            self._save_current_session()

    def list_sessions(
        self,
        limit: int = 20,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List past research sessions"""
        sessions = []

        for session_file in self.data_dir.glob("*.json"):
            if session_file.name == "current.json":
                continue

            try:
                with open(session_file) as f:
                    data = json.load(f)

                if status and data.get("status") != status:
                    continue

                sessions.append(data)
            except Exception:
                continue

        # Sort by started_at descending
        sessions.sort(key=lambda x: x.get("started_at", ""), reverse=True)

        return sessions[:limit]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific session by ID"""
        # Check current
        if self.current_session and self.current_session.session_id == session_id:
            return self.get_current_session()

        # Check archive
        session_file = self.data_dir / f"{session_id}.json"
        if session_file.exists():
            with open(session_file) as f:
                return json.load(f)

        return None

    def get_session_stats(self) -> Dict[str, Any]:
        """Get aggregate stats about research sessions"""
        sessions = self.list_sessions(limit=100)

        if not sessions:
            return {
                "total_sessions": 0,
                "completed_sessions": 0,
                "total_research_minutes": 0,
                "total_searches": 0,
                "total_urls_fetched": 0,
                "total_notes_created": 0
            }

        completed = [s for s in sessions if s.get("status") == "completed"]

        total_minutes = sum(
            (datetime.fromisoformat(s["ended_at"]) - datetime.fromisoformat(s["started_at"])).total_seconds() / 60
            for s in sessions if s.get("ended_at")
        )

        return {
            "total_sessions": len(sessions),
            "completed_sessions": len(completed),
            "terminated_sessions": len([s for s in sessions if s.get("status") == "terminated"]),
            "total_research_minutes": round(total_minutes, 1),
            "total_searches": sum(s.get("searches_performed", 0) for s in sessions),
            "total_urls_fetched": sum(s.get("urls_fetched", 0) for s in sessions),
            "total_notes_created": sum(len(s.get("notes_created", [])) for s in sessions),
            "average_session_minutes": round(total_minutes / len(sessions), 1) if sessions else 0
        }
