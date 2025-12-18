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
    focus_edges: List[Dict[str, str]] = field(default_factory=list)  # Selected growth edges for this session

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
            "focus_edges": self.focus_edges,
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
            focus_edges=data.get("focus_edges", []),
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

    Sessions are stored in SQLite database.
    Only one session can be active at a time.
    """

    def __init__(self, daemon_id: str = None):
        self._daemon_id = daemon_id
        if not self._daemon_id:
            self._load_default_daemon()
        self._active_session_id: Optional[str] = None
        self._load_active_session()

    def _load_default_daemon(self):
        """Load default daemon ID from database"""
        from database import get_db
        with get_db() as conn:
            cursor = conn.execute("SELECT id FROM daemons LIMIT 1")
            row = cursor.fetchone()
            if row:
                self._daemon_id = row[0]

    def _load_active_session(self):
        """Load any active session from database"""
        from database import get_db
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id FROM solo_reflections
                WHERE daemon_id = ? AND status = 'active'
                ORDER BY started_at DESC LIMIT 1
            """, (self._daemon_id,))
            row = cursor.fetchone()
            if row:
                self._active_session_id = row[0]

    def _save_session(self, session: SoloReflectionSession) -> None:
        """Save session to database."""
        from database import get_db, json_serialize
        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO solo_reflections (
                    id, daemon_id, started_at, ended_at, duration_minutes,
                    trigger, theme, status, thought_stream_json, insights_json,
                    questions_raised_json, summary, model_used, focus_edges_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.session_id,
                self._daemon_id,
                session.started_at.isoformat(),
                session.ended_at.isoformat() if session.ended_at else None,
                session.duration_minutes,
                session.trigger,
                session.theme,
                session.status,
                json_serialize([t.to_dict() for t in session.thought_stream]),
                json_serialize(session.insights),
                json_serialize(session.questions_raised),
                session.summary,
                session.model_used,
                json_serialize(session.focus_edges)
            ))
            conn.commit()

    def start_session(
        self,
        duration_minutes: int = 15,
        theme: Optional[str] = None,
        trigger: str = "admin",
        model: str = "ollama",
        focus_edges: Optional[List[Dict[str, str]]] = None,
    ) -> SoloReflectionSession:
        """
        Start a new solo reflection session.

        Args:
            duration_minutes: Target duration (15-60 recommended)
            theme: Optional focus theme
            trigger: What initiated this session
            model: Model to use (default: ollama for local)
            focus_edges: Pre-selected growth edges for this session

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
            focus_edges=focus_edges or [],
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
            self._load_active_session()

        if self._active_session_id:
            return self.get_session(self._active_session_id)
        return None

    def get_session(self, session_id: str) -> Optional[SoloReflectionSession]:
        """Get a specific session by ID."""
        from database import get_db, json_deserialize
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, started_at, ended_at, duration_minutes, trigger, theme,
                       status, thought_stream_json, insights_json, questions_raised_json,
                       summary, model_used, focus_edges_json
                FROM solo_reflections
                WHERE daemon_id = ? AND id = ?
            """, (self._daemon_id, session_id))
            row = cursor.fetchone()
            if not row:
                return None

            thought_stream = []
            raw_thoughts = json_deserialize(row[7]) or []
            for t in raw_thoughts:
                thought_stream.append(ThoughtEntry.from_dict(t))

            return SoloReflectionSession(
                session_id=row[0],
                started_at=datetime.fromisoformat(row[1]),
                ended_at=datetime.fromisoformat(row[2]) if row[2] else None,
                duration_minutes=row[3],
                trigger=row[4],
                theme=row[5],
                status=row[6],
                thought_stream=thought_stream,
                insights=json_deserialize(row[8]) or [],
                questions_raised=json_deserialize(row[9]) or [],
                summary=row[10],
                model_used=row[11] or "ollama",
                focus_edges=json_deserialize(row[12]) or []
            )

    def list_sessions(
        self,
        limit: int = 20,
        status_filter: Optional[str] = None,
    ) -> List[Dict]:
        """
        List sessions from database.

        Args:
            limit: Maximum number to return
            status_filter: Optional status filter

        Returns:
            List of session metadata dicts
        """
        from database import get_db, json_deserialize
        with get_db() as conn:
            if status_filter:
                cursor = conn.execute("""
                    SELECT id, started_at, ended_at, duration_minutes, trigger, theme,
                           status, thought_stream_json
                    FROM solo_reflections
                    WHERE daemon_id = ? AND status = ?
                    ORDER BY started_at DESC LIMIT ?
                """, (self._daemon_id, status_filter, limit))
            else:
                cursor = conn.execute("""
                    SELECT id, started_at, ended_at, duration_minutes, trigger, theme,
                           status, thought_stream_json
                    FROM solo_reflections
                    WHERE daemon_id = ?
                    ORDER BY started_at DESC LIMIT ?
                """, (self._daemon_id, limit))

            sessions = []
            for row in cursor.fetchall():
                thoughts = json_deserialize(row[7]) or []
                sessions.append({
                    "session_id": row[0],
                    "started_at": row[1],
                    "ended_at": row[2],
                    "duration_minutes": row[3],
                    "trigger": row[4],
                    "theme": row[5],
                    "status": row[6],
                    "thought_count": len(thoughts)
                })
            return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id == self._active_session_id:
            return False  # Can't delete active session

        from database import get_db
        with get_db() as conn:
            cursor = conn.execute("""
                DELETE FROM solo_reflections
                WHERE daemon_id = ? AND id = ?
            """, (self._daemon_id, session_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_stats(self) -> Dict[str, Any]:
        """Get overall statistics about reflection sessions."""
        from database import get_db, json_deserialize
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT status, duration_minutes, theme, thought_stream_json
                FROM solo_reflections
                WHERE daemon_id = ?
            """, (self._daemon_id,))

            total = 0
            completed = 0
            interrupted = 0
            total_thoughts = 0
            total_duration = 0
            themes = set()

            for row in cursor.fetchall():
                total += 1
                status = row[0]
                if status == "completed":
                    completed += 1
                    total_duration += row[1] or 0
                    thoughts = json_deserialize(row[3]) or []
                    total_thoughts += len(thoughts)
                elif status == "interrupted":
                    interrupted += 1
                if row[2]:
                    themes.add(row[2])

            return {
                "total_sessions": total,
                "completed_sessions": completed,
                "interrupted_sessions": interrupted,
                "active_session": self._active_session_id,
                "total_thoughts_recorded": total_thoughts,
                "total_reflection_minutes": total_duration,
                "themes_explored": list(themes),
            }
