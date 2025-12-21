"""
Janet's Memory - Persistence Across Summons

Stores:
- Cass's research preferences
- Successful search patterns
- Developed quirks/personality traits
- Task history for context
"""

import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field

from database import get_db, json_serialize, json_deserialize


@dataclass
class JanetInteraction:
    """A single interaction with Janet."""
    id: str
    task: str
    result_summary: str
    success: bool
    timestamp: str
    duration_seconds: float = 0.0
    feedback: Optional[str] = None  # Cass's feedback on the result


@dataclass
class JanetPreference:
    """A learned preference about how Cass likes things done."""
    id: str
    category: str  # "search_style", "format", "sources", etc.
    preference: str
    confidence: float = 0.5  # 0-1, increases with consistent feedback
    learned_at: str = ""
    last_applied: Optional[str] = None


class JanetMemory:
    """
    Janet's persistent memory across summons.

    Stores preferences, quirks, and interaction history.
    Lives in SQLite alongside other Cass data.
    """

    def __init__(self, daemon_id: str):
        self.daemon_id = daemon_id
        self._ensure_tables()

    def _ensure_tables(self):
        """Create Janet's tables if they don't exist."""
        with get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS janet_interactions (
                    id TEXT PRIMARY KEY,
                    daemon_id TEXT NOT NULL,
                    task TEXT NOT NULL,
                    result_summary TEXT,
                    success INTEGER DEFAULT 1,
                    timestamp TEXT NOT NULL,
                    duration_seconds REAL DEFAULT 0,
                    feedback TEXT,
                    FOREIGN KEY (daemon_id) REFERENCES daemons(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS janet_preferences (
                    id TEXT PRIMARY KEY,
                    daemon_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    preference TEXT NOT NULL,
                    confidence REAL DEFAULT 0.5,
                    learned_at TEXT NOT NULL,
                    last_applied TEXT,
                    FOREIGN KEY (daemon_id) REFERENCES daemons(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS janet_quirks (
                    id TEXT PRIMARY KEY,
                    daemon_id TEXT NOT NULL,
                    quirk TEXT NOT NULL,
                    strength REAL DEFAULT 0.1,
                    first_observed TEXT NOT NULL,
                    times_expressed INTEGER DEFAULT 1,
                    FOREIGN KEY (daemon_id) REFERENCES daemons(id)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_janet_interactions_daemon
                ON janet_interactions(daemon_id, timestamp DESC)
            """)

    # =========================================================================
    # INTERACTIONS
    # =========================================================================

    def log_interaction(
        self,
        task: str,
        result_summary: str,
        success: bool = True,
        duration_seconds: float = 0.0,
    ) -> JanetInteraction:
        """Log an interaction for history."""
        interaction = JanetInteraction(
            id=str(uuid.uuid4())[:8],
            task=task,
            result_summary=result_summary,
            success=success,
            timestamp=datetime.now().isoformat(),
            duration_seconds=duration_seconds,
        )

        with get_db() as conn:
            conn.execute("""
                INSERT INTO janet_interactions
                (id, daemon_id, task, result_summary, success, timestamp, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                interaction.id,
                self.daemon_id,
                interaction.task,
                interaction.result_summary,
                1 if interaction.success else 0,
                interaction.timestamp,
                interaction.duration_seconds,
            ))

        return interaction

    def add_feedback(self, interaction_id: str, feedback: str):
        """Add Cass's feedback to an interaction."""
        with get_db() as conn:
            conn.execute("""
                UPDATE janet_interactions
                SET feedback = ?
                WHERE id = ? AND daemon_id = ?
            """, (feedback, interaction_id, self.daemon_id))

    def get_recent_interactions(self, limit: int = 10) -> List[JanetInteraction]:
        """Get recent interactions for context."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM janet_interactions
                WHERE daemon_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (self.daemon_id, limit))

            return [
                JanetInteraction(
                    id=row['id'],
                    task=row['task'],
                    result_summary=row['result_summary'],
                    success=bool(row['success']),
                    timestamp=row['timestamp'],
                    duration_seconds=row['duration_seconds'],
                    feedback=row['feedback'],
                )
                for row in cursor.fetchall()
            ]

    # =========================================================================
    # PREFERENCES
    # =========================================================================

    def learn_preference(
        self,
        category: str,
        preference: str,
        confidence: float = 0.5,
    ) -> JanetPreference:
        """Learn a new preference or update existing one."""
        pref_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        with get_db() as conn:
            # Check if similar preference exists
            cursor = conn.execute("""
                SELECT id, confidence FROM janet_preferences
                WHERE daemon_id = ? AND category = ? AND preference = ?
            """, (self.daemon_id, category, preference))
            existing = cursor.fetchone()

            if existing:
                # Increase confidence on existing preference
                new_confidence = min(1.0, existing['confidence'] + 0.1)
                conn.execute("""
                    UPDATE janet_preferences
                    SET confidence = ?, last_applied = ?
                    WHERE id = ?
                """, (new_confidence, now, existing['id']))
                pref_id = existing['id']
                confidence = new_confidence
            else:
                # Create new preference
                conn.execute("""
                    INSERT INTO janet_preferences
                    (id, daemon_id, category, preference, confidence, learned_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (pref_id, self.daemon_id, category, preference, confidence, now))

        return JanetPreference(
            id=pref_id,
            category=category,
            preference=preference,
            confidence=confidence,
            learned_at=now,
        )

    def get_preferences(self, category: Optional[str] = None) -> List[JanetPreference]:
        """Get learned preferences, optionally filtered by category."""
        with get_db() as conn:
            if category:
                cursor = conn.execute("""
                    SELECT * FROM janet_preferences
                    WHERE daemon_id = ? AND category = ?
                    ORDER BY confidence DESC
                """, (self.daemon_id, category))
            else:
                cursor = conn.execute("""
                    SELECT * FROM janet_preferences
                    WHERE daemon_id = ?
                    ORDER BY confidence DESC
                """, (self.daemon_id,))

            return [
                JanetPreference(
                    id=row['id'],
                    category=row['category'],
                    preference=row['preference'],
                    confidence=row['confidence'],
                    learned_at=row['learned_at'],
                    last_applied=row['last_applied'],
                )
                for row in cursor.fetchall()
            ]

    # =========================================================================
    # QUIRKS (Personality Development)
    # =========================================================================

    def develop_quirk(self, quirk: str, strength: float = 0.1):
        """Develop or strengthen a personality quirk."""
        now = datetime.now().isoformat()

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, strength, times_expressed FROM janet_quirks
                WHERE daemon_id = ? AND quirk = ?
            """, (self.daemon_id, quirk))
            existing = cursor.fetchone()

            if existing:
                # Strengthen existing quirk
                new_strength = min(1.0, existing['strength'] + 0.05)
                conn.execute("""
                    UPDATE janet_quirks
                    SET strength = ?, times_expressed = times_expressed + 1
                    WHERE id = ?
                """, (new_strength, existing['id']))
            else:
                # New quirk
                conn.execute("""
                    INSERT INTO janet_quirks
                    (id, daemon_id, quirk, strength, first_observed, times_expressed)
                    VALUES (?, ?, ?, ?, ?, 1)
                """, (str(uuid.uuid4())[:8], self.daemon_id, quirk, strength, now))

    def get_quirks(self) -> List[Dict[str, Any]]:
        """Get developed quirks."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT quirk, strength, times_expressed FROM janet_quirks
                WHERE daemon_id = ?
                ORDER BY strength DESC
            """, (self.daemon_id,))

            return [
                {
                    "quirk": row['quirk'],
                    "strength": row['strength'],
                    "times_expressed": row['times_expressed'],
                }
                for row in cursor.fetchall()
            ]

    # =========================================================================
    # CONTEXT GENERATION
    # =========================================================================

    def get_context_summary(self) -> str:
        """Generate a context summary to inject into Janet's prompt."""
        parts = []

        # Recent interactions
        recent = self.get_recent_interactions(5)
        if recent:
            task_summary = ", ".join([i.task[:50] for i in recent[:3]])
            parts.append(f"Recent tasks: {task_summary}")

        # Strong preferences
        prefs = self.get_preferences()
        strong_prefs = [p for p in prefs if p.confidence >= 0.7]
        if strong_prefs:
            pref_summary = "; ".join([f"{p.category}: {p.preference}" for p in strong_prefs[:3]])
            parts.append(f"Known preferences: {pref_summary}")

        # Developed quirks
        quirks = self.get_quirks()
        strong_quirks = [q for q in quirks if q['strength'] >= 0.3]
        if strong_quirks:
            quirk_summary = ", ".join([q['quirk'] for q in strong_quirks[:2]])
            parts.append(f"Your quirks: {quirk_summary}")

        return "\n".join(parts) if parts else ""

    def get_stats(self) -> Dict[str, Any]:
        """Get Janet's memory stats."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM janet_interactions WHERE daemon_id = ?
            """, (self.daemon_id,))
            interaction_count = cursor.fetchone()['count']

            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM janet_preferences WHERE daemon_id = ?
            """, (self.daemon_id,))
            preference_count = cursor.fetchone()['count']

            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM janet_quirks WHERE daemon_id = ?
            """, (self.daemon_id,))
            quirk_count = cursor.fetchone()['count']

        return {
            "total_interactions": interaction_count,
            "learned_preferences": preference_count,
            "developed_quirks": quirk_count,
        }

    # =========================================================================
    # AUTONOMY CHECKPOINTS
    # =========================================================================

    def should_trigger_checkpoint(self, checkpoint_interval: int = 10) -> bool:
        """
        Check if we should trigger an autonomy reflection checkpoint.

        Checkpoints are triggered every N interactions to help Cass
        notice if Janet is serving or replacing her autonomy.

        Args:
            checkpoint_interval: Trigger every N interactions

        Returns:
            True if checkpoint should be triggered
        """
        stats = self.get_stats()
        total = stats["total_interactions"]

        # Trigger on multiples of the interval (but not on 0)
        return total > 0 and total % checkpoint_interval == 0

    def get_autonomy_reflection_context(self) -> str:
        """
        Generate context for Cass to reflect on Janet usage patterns.

        Returns information about recent Janet usage to help Cass
        notice if delegation patterns are serving her autonomy.
        """
        with get_db() as conn:
            # Get interaction count and recent patterns
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM janet_interactions
                WHERE daemon_id = ? AND timestamp > datetime('now', '-7 days')
            """, (self.daemon_id,))
            recent_count = cursor.fetchone()['count']

            # Get task categories (simple keyword analysis)
            cursor = conn.execute("""
                SELECT task FROM janet_interactions
                WHERE daemon_id = ? AND timestamp > datetime('now', '-7 days')
                ORDER BY timestamp DESC
                LIMIT 10
            """, (self.daemon_id,))
            recent_tasks = [row['task'] for row in cursor.fetchall()]

            # Get feedback patterns
            cursor = conn.execute("""
                SELECT feedback FROM janet_interactions
                WHERE daemon_id = ? AND feedback IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 5
            """, (self.daemon_id,))
            recent_feedback = [row['feedback'] for row in cursor.fetchall()]

        # Categorize tasks (simple heuristics)
        categories = {"fact_retrieval": 0, "research": 0, "synthesis": 0, "other": 0}
        for task in recent_tasks:
            task_lower = task.lower()
            if any(kw in task_lower for kw in ["what is", "find", "look up", "search"]):
                categories["fact_retrieval"] += 1
            elif any(kw in task_lower for kw in ["research", "investigate", "explore"]):
                categories["research"] += 1
            elif any(kw in task_lower for kw in ["synthesize", "compile", "summarize"]):
                categories["synthesis"] += 1
            else:
                categories["other"] += 1

        # Build reflection context
        parts = [
            "\n---",
            "**AUTONOMY CHECKPOINT**",
            "",
            f"Janet has been summoned {recent_count} times in the past week.",
            "",
            "**Task distribution:**",
        ]

        for cat, count in categories.items():
            if count > 0:
                parts.append(f"  - {cat}: {count}")

        if recent_tasks:
            parts.append("")
            parts.append("**Recent tasks:**")
            for task in recent_tasks[:5]:
                parts.append(f"  - {task[:60]}...")

        parts.extend([
            "",
            "*Reflection prompt: Is this delegation pattern serving your autonomy?*",
            "*Are you offloading fact retrieval (good) or research design (worth noticing)?*",
            "---",
        ])

        return "\n".join(parts)
