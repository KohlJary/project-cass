"""
Work Summary Store - Persistent storage for work unit summaries.

Each completed work unit gets a summary with:
- Slug for addressing (work/2025-12-22/morning-reflection-a3f2)
- Narrative summary of what happened
- Links to action summaries for detailed breakdown
- Associated artifacts (notes, insights, journal entries, etc.)
- Metadata (duration, cost, focus, motivation)

This enables queries like "what did you do this morning?" by providing
structured access to work history with full context.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Dict, List, Optional
import re

from database import get_db, json_serialize, json_deserialize

logger = logging.getLogger(__name__)


def generate_slug(work_name: str, work_id: str, work_date: date, phase: str) -> str:
    """
    Generate a URL-safe slug for a work unit.

    Format: work/{date}/{phase}-{name_slug}-{short_id}
    Example: work/2025-12-22/morning-reflection-a3f2
    """
    # Slugify the name
    name_slug = re.sub(r'[^a-z0-9]+', '-', work_name.lower()).strip('-')
    name_slug = name_slug[:30]  # Limit length

    # Short ID (first 4 chars of UUID)
    short_id = work_id[:4] if work_id else "0000"

    return f"work/{work_date.isoformat()}/{phase}-{name_slug}-{short_id}"


@dataclass
class ActionSummary:
    """Summary of a single action within a work unit."""
    action_id: str
    action_type: str
    slug: str
    summary: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    artifacts: List[str] = field(default_factory=list)  # Artifact slugs/IDs
    result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "slug": self.slug,
            "summary": self.summary,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "artifacts": self.artifacts,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionSummary":
        return cls(
            action_id=data["action_id"],
            action_type=data["action_type"],
            slug=data["slug"],
            summary=data["summary"],
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            artifacts=data.get("artifacts", []),
            result=data.get("result"),
        )


@dataclass
class WorkSummary:
    """
    Complete summary of a work unit execution.

    Contains everything needed to answer "what did you do?"
    """
    # Identity
    work_unit_id: str
    slug: str
    name: str
    template_id: Optional[str] = None

    # Context
    phase: str = "afternoon"  # morning, afternoon, evening, night
    category: str = "reflection"
    focus: Optional[str] = None
    motivation: Optional[str] = None

    # Timing
    date: date = field(default_factory=date.today)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_minutes: int = 0

    # Content
    summary: str = ""  # LLM-generated narrative summary
    key_insights: List[str] = field(default_factory=list)
    questions_addressed: List[str] = field(default_factory=list)
    questions_raised: List[str] = field(default_factory=list)

    # Actions (detailed breakdown)
    action_summaries: List[ActionSummary] = field(default_factory=list)

    # Artifacts (things created during this work)
    artifacts: List[Dict[str, str]] = field(default_factory=list)  # [{type, id, title}]

    # Metadata
    success: bool = True
    error: Optional[str] = None
    cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "work_unit_id": self.work_unit_id,
            "slug": self.slug,
            "name": self.name,
            "template_id": self.template_id,
            "phase": self.phase,
            "category": self.category,
            "focus": self.focus,
            "motivation": self.motivation,
            "date": self.date.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_minutes": self.duration_minutes,
            "summary": self.summary,
            "key_insights": self.key_insights,
            "questions_addressed": self.questions_addressed,
            "questions_raised": self.questions_raised,
            "action_summaries": [a.to_dict() for a in self.action_summaries],
            "artifacts": self.artifacts,
            "success": self.success,
            "error": self.error,
            "cost_usd": self.cost_usd,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkSummary":
        return cls(
            work_unit_id=data["work_unit_id"],
            slug=data["slug"],
            name=data["name"],
            template_id=data.get("template_id"),
            phase=data.get("phase", "afternoon"),
            category=data.get("category", "reflection"),
            focus=data.get("focus"),
            motivation=data.get("motivation"),
            date=date.fromisoformat(data["date"]) if data.get("date") else date.today(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            duration_minutes=data.get("duration_minutes", 0),
            summary=data.get("summary", ""),
            key_insights=data.get("key_insights", []),
            questions_addressed=data.get("questions_addressed", []),
            questions_raised=data.get("questions_raised", []),
            action_summaries=[ActionSummary.from_dict(a) for a in data.get("action_summaries", [])],
            artifacts=data.get("artifacts", []),
            success=data.get("success", True),
            error=data.get("error"),
            cost_usd=data.get("cost_usd", 0.0),
        )

    def get_brief(self) -> str:
        """Get a brief one-line description for listings."""
        duration = f"{self.duration_minutes}min" if self.duration_minutes else "?"
        focus_str = f" - {self.focus}" if self.focus else ""
        return f"{self.name} ({duration}){focus_str}"


class WorkSummaryStore:
    """
    Persistent store for work summaries.

    Provides slug-based addressing and query methods for retrieving
    work history by date, phase, category, etc.
    """

    def __init__(self, daemon_id: str):
        self._daemon_id = daemon_id
        self._ensure_table()

    def _ensure_table(self):
        """Create work_summaries table if not exists."""
        with get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS work_summaries (
                    slug TEXT PRIMARY KEY,
                    daemon_id TEXT NOT NULL,
                    work_unit_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    template_id TEXT,
                    phase TEXT NOT NULL,
                    category TEXT NOT NULL,
                    date TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    duration_minutes INTEGER DEFAULT 0,
                    summary TEXT,
                    data_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_work_summaries_date
                ON work_summaries(daemon_id, date)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_work_summaries_phase
                ON work_summaries(daemon_id, date, phase)
            """)

    def save(self, summary: WorkSummary) -> str:
        """
        Save a work summary.

        Returns the slug.
        """
        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO work_summaries
                (slug, daemon_id, work_unit_id, name, template_id, phase, category,
                 date, started_at, completed_at, duration_minutes, summary, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                summary.slug,
                self._daemon_id,
                summary.work_unit_id,
                summary.name,
                summary.template_id,
                summary.phase,
                summary.category,
                summary.date.isoformat(),
                summary.started_at.isoformat() if summary.started_at else None,
                summary.completed_at.isoformat() if summary.completed_at else None,
                summary.duration_minutes,
                summary.summary,
                json_serialize(summary.to_dict()),
            ))

        logger.info(f"Saved work summary: {summary.slug}")
        return summary.slug

    def get_by_slug(self, slug: str) -> Optional[WorkSummary]:
        """Get a work summary by its slug."""
        with get_db() as conn:
            row = conn.execute("""
                SELECT data_json FROM work_summaries
                WHERE slug = ? AND daemon_id = ?
            """, (slug, self._daemon_id)).fetchone()

            if row:
                return WorkSummary.from_dict(json_deserialize(row[0]))
            return None

    def get_by_date(self, target_date: date) -> List[WorkSummary]:
        """Get all work summaries for a specific date."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT data_json FROM work_summaries
                WHERE daemon_id = ? AND date = ?
                ORDER BY started_at
            """, (self._daemon_id, target_date.isoformat())).fetchall()

            return [WorkSummary.from_dict(json_deserialize(r[0])) for r in rows]

    def get_by_phase(self, target_date: date, phase: str) -> List[WorkSummary]:
        """Get all work summaries for a specific date and phase."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT data_json FROM work_summaries
                WHERE daemon_id = ? AND date = ? AND phase = ?
                ORDER BY started_at
            """, (self._daemon_id, target_date.isoformat(), phase)).fetchall()

            return [WorkSummary.from_dict(json_deserialize(r[0])) for r in rows]

    def get_recent(self, limit: int = 10) -> List[WorkSummary]:
        """Get most recent work summaries."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT data_json FROM work_summaries
                WHERE daemon_id = ?
                ORDER BY started_at DESC
                LIMIT ?
            """, (self._daemon_id, limit)).fetchall()

            return [WorkSummary.from_dict(json_deserialize(r[0])) for r in rows]

    def get_by_category(self, category: str, limit: int = 20) -> List[WorkSummary]:
        """Get recent work summaries by category."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT data_json FROM work_summaries
                WHERE daemon_id = ? AND category = ?
                ORDER BY started_at DESC
                LIMIT ?
            """, (self._daemon_id, category, limit)).fetchall()

            return [WorkSummary.from_dict(json_deserialize(r[0])) for r in rows]

    def search(self, query: str, limit: int = 20) -> List[WorkSummary]:
        """Search work summaries by text in name, summary, or focus."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT data_json FROM work_summaries
                WHERE daemon_id = ? AND (
                    name LIKE ? OR summary LIKE ? OR data_json LIKE ?
                )
                ORDER BY started_at DESC
                LIMIT ?
            """, (
                self._daemon_id,
                f"%{query}%", f"%{query}%", f"%{query}%",
                limit
            )).fetchall()

            return [WorkSummary.from_dict(json_deserialize(r[0])) for r in rows]

    def get_stats(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """Get work statistics for a date range."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(duration_minutes) as total_minutes,
                    phase,
                    category
                FROM work_summaries
                WHERE daemon_id = ? AND date >= ? AND date <= ?
                GROUP BY phase, category
            """, (self._daemon_id, start_date.isoformat(), end_date.isoformat())).fetchall()

            by_phase = {}
            by_category = {}
            total_count = 0
            total_minutes = 0

            for row in rows:
                count, minutes, phase, category = row
                minutes = minutes or 0

                total_count += count
                total_minutes += minutes

                if phase not in by_phase:
                    by_phase[phase] = {"count": 0, "minutes": 0}
                by_phase[phase]["count"] += count
                by_phase[phase]["minutes"] += minutes

                if category not in by_category:
                    by_category[category] = {"count": 0, "minutes": 0}
                by_category[category]["count"] += count
                by_category[category]["minutes"] += minutes

            return {
                "total_count": total_count,
                "total_minutes": total_minutes,
                "by_phase": by_phase,
                "by_category": by_category,
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
            }
