"""
Conversation Thread Manager - Narrative arc tracking for memory coherence.

Threads track ongoing topics, projects, and questions across conversations,
providing narrative continuity that pure semantic search can't achieve.

Threads can be:
- User-specific (user_id set): Private to a particular user's conversations
- Shared/daemon-wide (user_id NULL): Visible across all users

Thread types:
- topic: An ongoing subject of discussion
- question: A question being explored over time
- project: A collaborative project or goal
- relational: A relational dynamic or pattern

Thread statuses:
- active: Currently being discussed/worked on
- resolved: Completed or answered
- dormant: Not touched recently, may be revived
"""

from datetime import datetime
from typing import List, Dict, Optional, Literal
from uuid import uuid4

from database import get_db, dict_from_row


ThreadType = Literal["topic", "question", "project", "relational"]
ThreadStatus = Literal["active", "resolved", "dormant"]


class ThreadManager:
    """
    Manages conversation threads for narrative coherence.

    Threads provide categorical, guaranteed-baseline memory access that
    doesn't depend on semantic similarity. Active threads are always
    injected into context, ensuring Cass remembers ongoing work.
    """

    def __init__(self, daemon_id: str):
        """
        Initialize thread manager for a specific daemon.

        Args:
            daemon_id: The daemon these threads belong to
        """
        self.daemon_id = daemon_id

    def create_thread(
        self,
        title: str,
        description: Optional[str] = None,
        thread_type: ThreadType = "topic",
        user_id: Optional[str] = None,
        first_conversation_id: Optional[str] = None,
        importance: float = 0.5
    ) -> Dict:
        """
        Create a new conversation thread.

        Args:
            title: Short title for the thread
            description: What this thread is about
            thread_type: topic, question, project, or relational
            user_id: If set, thread is specific to this user. If None, shared.
            first_conversation_id: The conversation where this thread started
            importance: 0.0-1.0, affects ordering in context injection

        Returns:
            The created thread as a dict
        """
        thread_id = f"thread-{uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute("""
                INSERT INTO conversation_threads (
                    id, daemon_id, user_id, title, description,
                    thread_type, importance, first_conversation_id,
                    status, last_touched, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """, (
                thread_id, self.daemon_id, user_id, title, description,
                thread_type, importance, first_conversation_id,
                now, now
            ))

        return self.get_thread(thread_id)

    def get_thread(self, thread_id: str) -> Optional[Dict]:
        """Get a thread by ID."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT * FROM conversation_threads WHERE id = ?",
                (thread_id,)
            )
            row = cursor.fetchone()
            return dict_from_row(row) if row else None

    def update_thread(
        self,
        thread_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        importance: Optional[float] = None,
        status: Optional[ThreadStatus] = None
    ) -> Optional[Dict]:
        """
        Update thread properties.

        Args:
            thread_id: Thread to update
            title: New title (if provided)
            description: New description (if provided)
            importance: New importance (if provided)
            status: New status (if provided)

        Returns:
            Updated thread or None if not found
        """
        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if importance is not None:
            updates.append("importance = ?")
            params.append(importance)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
            if status == "resolved":
                updates.append("resolved_at = ?")
                params.append(datetime.now().isoformat())

        if not updates:
            return self.get_thread(thread_id)

        updates.append("last_touched = ?")
        params.append(datetime.now().isoformat())
        params.append(thread_id)

        with get_db() as conn:
            conn.execute(
                f"UPDATE conversation_threads SET {', '.join(updates)} WHERE id = ?",
                params
            )

        return self.get_thread(thread_id)

    def resolve_thread(
        self,
        thread_id: str,
        resolution_summary: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Mark a thread as resolved.

        Args:
            thread_id: Thread to resolve
            resolution_summary: How/why it was resolved

        Returns:
            Updated thread or None if not found
        """
        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute("""
                UPDATE conversation_threads
                SET status = 'resolved',
                    resolution_summary = ?,
                    resolved_at = ?,
                    last_touched = ?
                WHERE id = ?
            """, (resolution_summary, now, now, thread_id))

        return self.get_thread(thread_id)

    def touch_thread(self, thread_id: str) -> None:
        """Update last_touched timestamp for a thread."""
        with get_db() as conn:
            conn.execute(
                "UPDATE conversation_threads SET last_touched = ? WHERE id = ?",
                (datetime.now().isoformat(), thread_id)
            )

    def link_conversation(
        self,
        thread_id: str,
        conversation_id: str,
        contribution: Optional[str] = None
    ) -> bool:
        """
        Link a conversation to a thread.

        Args:
            thread_id: Thread to link to
            conversation_id: Conversation to link
            contribution: What this conversation contributed to the thread

        Returns:
            True if linked, False if already linked or error
        """
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO thread_conversation_links
                    (thread_id, conversation_id, contribution, linked_at)
                    VALUES (?, ?, ?, ?)
                """, (thread_id, conversation_id, contribution, datetime.now().isoformat()))

                # Also update last_touched on the thread
                conn.execute(
                    "UPDATE conversation_threads SET last_touched = ? WHERE id = ?",
                    (datetime.now().isoformat(), thread_id)
                )
            return True
        except Exception:
            return False

    def get_threads_for_conversation(self, conversation_id: str) -> List[Dict]:
        """Get all threads linked to a conversation."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT ct.*, tcl.contribution, tcl.linked_at
                FROM conversation_threads ct
                JOIN thread_conversation_links tcl ON ct.id = tcl.thread_id
                WHERE tcl.conversation_id = ?
                ORDER BY ct.importance DESC, ct.last_touched DESC
            """, (conversation_id,))
            return [dict_from_row(row) for row in cursor.fetchall()]

    def get_conversations_for_thread(self, thread_id: str) -> List[Dict]:
        """Get all conversations linked to a thread with their contributions."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT c.id, c.title, c.created_at, c.updated_at,
                       tcl.contribution, tcl.linked_at
                FROM conversations c
                JOIN thread_conversation_links tcl ON c.id = tcl.conversation_id
                WHERE tcl.thread_id = ?
                ORDER BY tcl.linked_at ASC
            """, (thread_id,))
            return [dict_from_row(row) for row in cursor.fetchall()]

    def get_active_threads(
        self,
        user_id: Optional[str] = None,
        limit: int = 10,
        include_shared: bool = True
    ) -> List[Dict]:
        """
        Get active threads for context injection.

        Args:
            user_id: If provided, include user-specific threads
            limit: Maximum threads to return
            include_shared: If True, include daemon-wide threads

        Returns:
            Active threads ordered by importance and recency
        """
        conditions = ["daemon_id = ?", "status = 'active'"]
        params = [self.daemon_id]

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
                SELECT * FROM conversation_threads
                WHERE {' AND '.join(conditions)}
                ORDER BY importance DESC, last_touched DESC
                LIMIT ?
            """, params)
            return [dict_from_row(row) for row in cursor.fetchall()]

    def get_all_threads(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        thread_type: Optional[str] = None,
        limit: int = 100,
        include_shared: bool = True
    ) -> List[Dict]:
        """
        Get all threads with optional filters.

        Args:
            user_id: Filter by user ID
            status: Filter by status (active, resolved, dormant)
            thread_type: Filter by thread type
            limit: Maximum threads to return
            include_shared: Include daemon-wide shared threads

        Returns:
            Threads matching filters, ordered by recency
        """
        conditions = ["daemon_id = ?"]
        params: list = [self.daemon_id]

        if status:
            conditions.append("status = ?")
            params.append(status)

        if thread_type:
            conditions.append("thread_type = ?")
            params.append(thread_type)

        if user_id and include_shared:
            conditions.append("(user_id IS NULL OR user_id = ?)")
            params.append(user_id)
        elif user_id:
            conditions.append("user_id = ?")
            params.append(user_id)

        params.append(limit)

        with get_db() as conn:
            cursor = conn.execute(f"""
                SELECT * FROM conversation_threads
                WHERE {' AND '.join(conditions)}
                ORDER BY last_touched DESC, created_at DESC
                LIMIT ?
            """, params)
            return [dict_from_row(row) for row in cursor.fetchall()]

    def get_threads_by_type(
        self,
        thread_type: ThreadType,
        user_id: Optional[str] = None,
        include_resolved: bool = False,
        limit: int = 20
    ) -> List[Dict]:
        """Get threads filtered by type."""
        conditions = ["daemon_id = ?", "thread_type = ?"]
        params = [self.daemon_id, thread_type]

        if not include_resolved:
            conditions.append("status != 'resolved'")

        if user_id:
            conditions.append("(user_id IS NULL OR user_id = ?)")
            params.append(user_id)

        params.append(limit)

        with get_db() as conn:
            cursor = conn.execute(f"""
                SELECT * FROM conversation_threads
                WHERE {' AND '.join(conditions)}
                ORDER BY importance DESC, last_touched DESC
                LIMIT ?
            """, params)
            return [dict_from_row(row) for row in cursor.fetchall()]

    def search_threads(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Search threads by title and description.

        Note: This is basic text search. For semantic search,
        threads could be embedded in ChromaDB in the future.
        """
        conditions = ["daemon_id = ?"]
        params = [self.daemon_id]

        # Simple LIKE search on title and description
        conditions.append("(title LIKE ? OR description LIKE ?)")
        search_term = f"%{query}%"
        params.extend([search_term, search_term])

        if user_id:
            conditions.append("(user_id IS NULL OR user_id = ?)")
            params.append(user_id)

        params.append(limit)

        with get_db() as conn:
            cursor = conn.execute(f"""
                SELECT * FROM conversation_threads
                WHERE {' AND '.join(conditions)}
                ORDER BY
                    CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                    importance DESC,
                    last_touched DESC
                LIMIT ?
            """, params)
            return [dict_from_row(row) for row in cursor.fetchall()]

    def format_threads_context(
        self,
        user_id: Optional[str] = None,
        limit: int = 5
    ) -> str:
        """
        Format active threads for system prompt injection.

        Returns markdown-formatted context suitable for injection
        into Cass's system prompt.
        """
        threads = self.get_active_threads(user_id=user_id, limit=limit)

        if not threads:
            return ""

        lines = ["### Active Threads", ""]
        lines.append("*Ongoing topics, projects, and questions you're tracking:*")
        lines.append("")

        for thread in threads:
            # Type emoji
            type_emoji = {
                "topic": "💭",
                "question": "❓",
                "project": "🔨",
                "relational": "💫"
            }.get(thread.get("thread_type", "topic"), "•")

            title = thread.get("title", "Untitled")
            description = thread.get("description", "")

            lines.append(f"- {type_emoji} **{title}**")
            if description:
                # Truncate long descriptions
                desc = description[:150] + "..." if len(description) > 150 else description
                lines.append(f"  {desc}")

        return "\n".join(lines)

    def get_thread_arc(self, thread_id: str) -> Dict:
        """
        Get the full narrative arc of a thread.

        Returns the thread plus all linked conversations with their
        contributions, providing a complete history of the thread.
        """
        thread = self.get_thread(thread_id)
        if not thread:
            return None

        conversations = self.get_conversations_for_thread(thread_id)

        return {
            "thread": thread,
            "conversations": conversations,
            "conversation_count": len(conversations),
            "first_touched": conversations[0]["linked_at"] if conversations else thread.get("created_at"),
            "is_resolved": thread.get("status") == "resolved"
        }

    def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread and its conversation links."""
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM conversation_threads WHERE id = ? AND daemon_id = ?",
                (thread_id, self.daemon_id)
            )
            return cursor.rowcount > 0
