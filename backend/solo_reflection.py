"""
Solo Reflection Mode - Session Management

Enables Cass to engage in private reflection sessions without conversational context.
Sessions run on local Ollama to avoid API token costs.

Based on spec: ~/.claude/plans/solo-reflection-mode.md
"""
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any


@dataclass
class ThoughtEntry:
    """A single thought captured during reflection."""
    timestamp: datetime
    content: str
    thought_type: str  # "observation", "question", "connection", "uncertainty", "realization"
    confidence: float  # 0.0 - 1.0
    related_concepts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "content": self.content,
            "thought_type": self.thought_type,
            "confidence": self.confidence,
            "related_concepts": self.related_concepts,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThoughtEntry":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            content=data["content"],
            thought_type=data["thought_type"],
            confidence=data["confidence"],
            related_concepts=data.get("related_concepts", []),
        )


@dataclass
class SoloReflectionSession:
    """A complete solo reflection session."""
    session_id: str
    started_at: datetime
    duration_minutes: int  # Target duration
    trigger: str  # "scheduled", "self_initiated", "event_triggered", "admin"
    status: str  # "active", "completed", "interrupted"
    theme: Optional[str] = None
    thought_stream: List[ThoughtEntry] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    questions_raised: List[str] = field(default_factory=list)
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None
    model_used: str = "ollama"  # Track which model ran the reflection

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_minutes": self.duration_minutes,
            "actual_duration_minutes": round(self.actual_duration_minutes, 1) if self.actual_duration_minutes else None,
            "trigger": self.trigger,
            "theme": self.theme,
            "thought_stream": [t.to_dict() for t in self.thought_stream],
            "insights": self.insights,
            "questions_raised": self.questions_raised,
            "status": self.status,
            "summary": self.summary,
            "model_used": self.model_used,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SoloReflectionSession":
        return cls(
            session_id=data["session_id"],
            started_at=datetime.fromisoformat(data["started_at"]),
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
            duration_minutes=data["duration_minutes"],
            trigger=data["trigger"],
            theme=data.get("theme"),
            thought_stream=[ThoughtEntry.from_dict(t) for t in data.get("thought_stream", [])],
            insights=data.get("insights", []),
            questions_raised=data.get("questions_raised", []),
            status=data["status"],
            summary=data.get("summary"),
            model_used=data.get("model_used", "ollama"),
        )

    @property
    def actual_duration_minutes(self) -> Optional[float]:
        """Calculate actual duration if session has ended."""
        if self.ended_at:
            delta = self.ended_at - self.started_at
            return delta.total_seconds() / 60
        return None

    @property
    def thought_count(self) -> int:
        return len(self.thought_stream)

    @property
    def thought_type_distribution(self) -> Dict[str, int]:
        """Count thoughts by type."""
        dist = {}
        for thought in self.thought_stream:
            dist[thought.thought_type] = dist.get(thought.thought_type, 0) + 1
        return dist


def create_session_id() -> str:
    """Generate a unique session ID."""
    now = datetime.now()
    short_uuid = uuid.uuid4().hex[:6]
    return f"reflect_{now.strftime('%Y%m%d_%H%M%S')}_{short_uuid}"


class SoloReflectionManager:
    """
    Manages solo reflection sessions with persistence.

    Sessions are stored as individual JSON files.
    Only one session can be active at a time.
    """

    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "index.json"
        self._active_session_id: Optional[str] = None
        self._ensure_index()

    def _ensure_index(self) -> None:
        """Ensure index file exists."""
        if not self.index_file.exists():
            self._save_index([])

    def _load_index(self) -> List[Dict]:
        """Load session index."""
        try:
            with open(self.index_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_index(self, index: List[Dict]) -> None:
        """Save session index."""
        with open(self.index_file, "w") as f:
            json.dump(index, f, indent=2)

    def _get_session_path(self, session_id: str) -> Path:
        """Get file path for a session."""
        return self.storage_dir / f"{session_id}.json"

    def _save_session(self, session: SoloReflectionSession) -> None:
        """Save session to disk."""
        path = self._get_session_path(session.session_id)
        with open(path, "w") as f:
            json.dump(session.to_dict(), f, indent=2)

        # Update index
        index = self._load_index()
        # Remove existing entry if present
        index = [e for e in index if e["session_id"] != session.session_id]
        # Add updated entry
        index.insert(0, {
            "session_id": session.session_id,
            "started_at": session.started_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "duration_minutes": session.duration_minutes,
            "trigger": session.trigger,
            "theme": session.theme,
            "status": session.status,
            "thought_count": session.thought_count,
        })
        self._save_index(index)

    def start_session(
        self,
        duration_minutes: int = 15,
        theme: Optional[str] = None,
        trigger: str = "admin",
        model: str = "ollama",
    ) -> SoloReflectionSession:
        """
        Start a new solo reflection session.

        Args:
            duration_minutes: Target duration (15-60 recommended)
            theme: Optional focus theme
            trigger: What initiated this session
            model: Model to use (default: ollama for local)

        Returns:
            The created session

        Raises:
            ValueError: If a session is already active
        """
        if self._active_session_id:
            raise ValueError(f"Session {self._active_session_id} is already active. End it first.")

        session = SoloReflectionSession(
            session_id=create_session_id(),
            started_at=datetime.now(),
            duration_minutes=duration_minutes,
            trigger=trigger,
            theme=theme,
            status="active",
            model_used=model,
        )

        self._save_session(session)
        self._active_session_id = session.session_id

        return session

    def add_thought(
        self,
        content: str,
        thought_type: str = "observation",
        confidence: float = 0.7,
        related_concepts: Optional[List[str]] = None,
    ) -> Optional[ThoughtEntry]:
        """
        Add a thought to the active session.

        Returns None if no session is active.
        """
        if not self._active_session_id:
            return None

        session = self.get_session(self._active_session_id)
        if not session or session.status != "active":
            return None

        thought = ThoughtEntry(
            timestamp=datetime.now(),
            content=content,
            thought_type=thought_type,
            confidence=confidence,
            related_concepts=related_concepts or [],
        )

        session.thought_stream.append(thought)
        self._save_session(session)

        return thought

    def end_session(
        self,
        summary: Optional[str] = None,
        insights: Optional[List[str]] = None,
        questions: Optional[List[str]] = None,
    ) -> Optional[SoloReflectionSession]:
        """
        End the active session.

        Args:
            summary: Session summary (can be generated by reflection)
            insights: Key insights from the session
            questions: Questions raised during reflection

        Returns:
            The completed session, or None if no active session
        """
        if not self._active_session_id:
            return None

        session = self.get_session(self._active_session_id)
        if not session:
            self._active_session_id = None
            return None

        session.status = "completed"
        session.ended_at = datetime.now()
        session.summary = summary
        session.insights = insights or []
        session.questions_raised = questions or []

        self._save_session(session)
        self._active_session_id = None

        return session

    def interrupt_session(self, reason: str = "interrupted") -> Optional[SoloReflectionSession]:
        """Interrupt the active session without proper completion."""
        if not self._active_session_id:
            return None

        session = self.get_session(self._active_session_id)
        if not session:
            self._active_session_id = None
            return None

        session.status = "interrupted"
        session.ended_at = datetime.now()
        session.summary = f"Session interrupted: {reason}"

        self._save_session(session)
        self._active_session_id = None

        return session

    def get_active_session(self) -> Optional[SoloReflectionSession]:
        """Get the currently active session, if any."""
        if not self._active_session_id:
            # Check if we need to recover an active session from disk
            index = self._load_index()
            for entry in index:
                if entry.get("status") == "active":
                    self._active_session_id = entry["session_id"]
                    break

        if self._active_session_id:
            return self.get_session(self._active_session_id)
        return None

    def get_session(self, session_id: str) -> Optional[SoloReflectionSession]:
        """Get a specific session by ID."""
        path = self._get_session_path(session_id)
        if not path.exists():
            return None

        try:
            with open(path, "r") as f:
                data = json.load(f)
                return SoloReflectionSession.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error loading session {session_id}: {e}")
            return None

    def list_sessions(
        self,
        limit: int = 20,
        status_filter: Optional[str] = None,
    ) -> List[Dict]:
        """
        List sessions from index.

        Args:
            limit: Maximum number to return
            status_filter: Optional status filter

        Returns:
            List of session metadata dicts
        """
        index = self._load_index()

        if status_filter:
            index = [e for e in index if e.get("status") == status_filter]

        return index[:limit]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id == self._active_session_id:
            return False  # Can't delete active session

        path = self._get_session_path(session_id)
        if path.exists():
            path.unlink()

            # Update index
            index = self._load_index()
            index = [e for e in index if e["session_id"] != session_id]
            self._save_index(index)

            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get overall statistics about reflection sessions."""
        index = self._load_index()

        completed = [e for e in index if e.get("status") == "completed"]
        total_thoughts = sum(e.get("thought_count", 0) for e in completed)
        total_duration = sum(e.get("duration_minutes", 0) for e in completed)

        return {
            "total_sessions": len(index),
            "completed_sessions": len(completed),
            "interrupted_sessions": len([e for e in index if e.get("status") == "interrupted"]),
            "active_session": self._active_session_id,
            "total_thoughts_recorded": total_thoughts,
            "total_reflection_minutes": total_duration,
            "themes_explored": list(set(e.get("theme") for e in index if e.get("theme"))),
        }
