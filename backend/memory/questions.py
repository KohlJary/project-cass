"""
Open Question Manager - Tracking unresolved questions for memory coherence.

Open questions track things Cass is curious about, decisions that need to be made,
or blockers that need resolution. They persist across conversations until resolved.

Questions can be:
- User-specific (user_id set): Private to a particular user's conversations
- Shared/daemon-wide (user_id NULL): Visible across all users

Question types:
- curiosity: Something Cass is genuinely curious about
- decision: A decision that needs to be made
- blocker: Something blocking progress on a thread/project
- philosophical: Deeper questions about existence, consciousness, etc.

Question statuses:
- open: Not yet answered/resolved
- resolved: Has been answered or addressed
- superseded: Replaced by a different question
"""

from datetime import datetime
from typing import List, Dict, Optional, Literal
from uuid import uuid4

from database import get_db, dict_from_row


QuestionType = Literal["curiosity", "decision", "blocker", "philosophical"]
QuestionStatus = Literal["open", "resolved", "superseded"]


class OpenQuestionManager:
    """
    Manages open questions for narrative coherence.

    Open questions provide explicit tracking of what's unresolved,
    ensuring Cass remembers what she's curious about and what
    needs to be addressed.
    """

    def __init__(self, daemon_id: str):
        """
        Initialize question manager for a specific daemon.

        Args:
            daemon_id: The daemon these questions belong to
        """
        self.daemon_id = daemon_id

    def add_question(
        self,
        question: str,
        context: Optional[str] = None,
        question_type: QuestionType = "curiosity",
        user_id: Optional[str] = None,
        source_conversation_id: Optional[str] = None,
        source_thread_id: Optional[str] = None,
        importance: float = 0.5
    ) -> Dict:
        """
        Add a new open question.

        Args:
            question: The question text
            context: Where/why this question arose
            question_type: curiosity, decision, blocker, or philosophical
            user_id: If set, question is specific to this user. If None, shared.
            source_conversation_id: The conversation where this arose
            source_thread_id: Related thread if any
            importance: 0.0-1.0, affects ordering

        Returns:
            The created question as a dict
        """
        question_id = f"question-{uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute("""
                INSERT INTO open_questions (
                    id, daemon_id, user_id, question, context,
                    question_type, importance, source_conversation_id,
                    source_thread_id, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """, (
                question_id, self.daemon_id, user_id, question, context,
                question_type, importance, source_conversation_id,
                source_thread_id, now
            ))

        return self.get_question(question_id)

    def get_question(self, question_id: str) -> Optional[Dict]:
        """Get a question by ID."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT * FROM open_questions WHERE id = ?",
                (question_id,)
            )
            row = cursor.fetchone()
            return dict_from_row(row) if row else None

    def update_question(
        self,
        question_id: str,
        question: Optional[str] = None,
        context: Optional[str] = None,
        importance: Optional[float] = None,
        question_type: Optional[QuestionType] = None
    ) -> Optional[Dict]:
        """Update question properties."""
        updates = []
        params = []

        if question is not None:
            updates.append("question = ?")
            params.append(question)
        if context is not None:
            updates.append("context = ?")
            params.append(context)
        if importance is not None:
            updates.append("importance = ?")
            params.append(importance)
        if question_type is not None:
            updates.append("question_type = ?")
            params.append(question_type)

        if not updates:
            return self.get_question(question_id)

        params.append(question_id)

        with get_db() as conn:
            conn.execute(
                f"UPDATE open_questions SET {', '.join(updates)} WHERE id = ?",
                params
            )

        return self.get_question(question_id)

    def resolve_question(
        self,
        question_id: str,
        resolution: str
    ) -> Optional[Dict]:
        """
        Mark a question as resolved.

        Args:
            question_id: Question to resolve
            resolution: How it was answered/resolved

        Returns:
            Updated question or None if not found
        """
        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute("""
                UPDATE open_questions
                SET status = 'resolved',
                    resolution = ?,
                    resolved_at = ?
                WHERE id = ?
            """, (resolution, now, question_id))

        return self.get_question(question_id)

    def supersede_question(
        self,
        question_id: str,
        reason: Optional[str] = None
    ) -> Optional[Dict]:
        """Mark a question as superseded by another."""
        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute("""
                UPDATE open_questions
                SET status = 'superseded',
                    resolution = ?,
                    resolved_at = ?
                WHERE id = ?
            """, (reason or "Superseded", now, question_id))

        return self.get_question(question_id)

    def get_open_questions(
        self,
        user_id: Optional[str] = None,
        question_type: Optional[QuestionType] = None,
        limit: int = 10,
        include_shared: bool = True
    ) -> List[Dict]:
        """
        Get open questions for context injection.

        Args:
            user_id: If provided, include user-specific questions
            question_type: Filter by type if provided
            limit: Maximum questions to return
            include_shared: If True, include daemon-wide questions

        Returns:
            Open questions ordered by importance and recency
        """
        conditions = ["daemon_id = ?", "status = 'open'"]
        params = [self.daemon_id]

        if question_type:
            conditions.append("question_type = ?")
            params.append(question_type)

        if user_id and include_shared:
            conditions.append("(user_id IS NULL OR user_id = ?)")
            params.append(user_id)
        elif user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        else:
            conditions.append("user_id IS NULL")

        params.append(limit)

        with get_db() as conn:
            cursor = conn.execute(f"""
                SELECT * FROM open_questions
                WHERE {' AND '.join(conditions)}
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
            """, params)
            return [dict_from_row(row) for row in cursor.fetchall()]

    def get_questions_by_type(
        self,
        question_type: QuestionType,
        user_id: Optional[str] = None,
        include_resolved: bool = False,
        limit: int = 20
    ) -> List[Dict]:
        """Get questions filtered by type."""
        conditions = ["daemon_id = ?", "question_type = ?"]
        params = [self.daemon_id, question_type]

        if not include_resolved:
            conditions.append("status = 'open'")

        if user_id:
            conditions.append("(user_id IS NULL OR user_id = ?)")
            params.append(user_id)

        params.append(limit)

        with get_db() as conn:
            cursor = conn.execute(f"""
                SELECT * FROM open_questions
                WHERE {' AND '.join(conditions)}
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
            """, params)
            return [dict_from_row(row) for row in cursor.fetchall()]

    def get_questions_for_thread(self, thread_id: str) -> List[Dict]:
        """Get all questions linked to a specific thread."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM open_questions
                WHERE source_thread_id = ?
                ORDER BY
                    CASE WHEN status = 'open' THEN 0 ELSE 1 END,
                    importance DESC,
                    created_at DESC
            """, (thread_id,))
            return [dict_from_row(row) for row in cursor.fetchall()]

    def search_questions(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Search questions by question text and context.

        Note: This is basic text search.
        """
        conditions = ["daemon_id = ?"]
        params = [self.daemon_id]

        conditions.append("(question LIKE ? OR context LIKE ?)")
        search_term = f"%{query}%"
        params.extend([search_term, search_term])

        if user_id:
            conditions.append("(user_id IS NULL OR user_id = ?)")
            params.append(user_id)

        params.append(limit)

        with get_db() as conn:
            cursor = conn.execute(f"""
                SELECT * FROM open_questions
                WHERE {' AND '.join(conditions)}
                ORDER BY
                    CASE WHEN status = 'open' THEN 0 ELSE 1 END,
                    importance DESC,
                    created_at DESC
                LIMIT ?
            """, params)
            return [dict_from_row(row) for row in cursor.fetchall()]

    def format_questions_context(
        self,
        user_id: Optional[str] = None,
        limit: int = 5
    ) -> str:
        """
        Format open questions for system prompt injection.

        Returns markdown-formatted context suitable for injection
        into Cass's system prompt.
        """
        questions = self.get_open_questions(user_id=user_id, limit=limit)

        if not questions:
            return ""

        lines = ["### Open Questions", ""]
        lines.append("*Things you're curious about or need to resolve:*")
        lines.append("")

        for q in questions:
            # Type indicator
            type_indicator = {
                "curiosity": "💭",
                "decision": "⚖️",
                "blocker": "🚧",
                "philosophical": "🌀"
            }.get(q.get("question_type", "curiosity"), "•")

            question_text = q.get("question", "")
            context = q.get("context", "")

            lines.append(f"- {type_indicator} {question_text}")
            if context:
                # Truncate long context
                ctx = context[:100] + "..." if len(context) > 100 else context
                lines.append(f"  *(Context: {ctx})*")

        return "\n".join(lines)

    def get_recent_resolutions(
        self,
        user_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict]:
        """Get recently resolved questions with their resolutions."""
        conditions = ["daemon_id = ?", "status = 'resolved'"]
        params = [self.daemon_id]

        if user_id:
            conditions.append("(user_id IS NULL OR user_id = ?)")
            params.append(user_id)

        params.append(limit)

        with get_db() as conn:
            cursor = conn.execute(f"""
                SELECT * FROM open_questions
                WHERE {' AND '.join(conditions)}
                ORDER BY resolved_at DESC
                LIMIT ?
            """, params)
            return [dict_from_row(row) for row in cursor.fetchall()]

    def delete_question(self, question_id: str) -> bool:
        """Delete a question."""
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM open_questions WHERE id = ? AND daemon_id = ?",
                (question_id, self.daemon_id)
            )
            return cursor.rowcount > 0
