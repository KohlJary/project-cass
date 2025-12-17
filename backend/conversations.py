"""
Cass Vessel - Conversation Manager
Handles conversation history, switching, and persistence

Now uses SQLite database instead of JSON files.
"""
import json
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import uuid

from database import get_db, json_serialize, json_deserialize, get_daemon_id


@dataclass
class Message:
    """Single message in a conversation"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: str
    animations: Optional[List[Dict]] = None
    excluded: bool = False  # If True, excluded from summarization, context, and embeddings
    user_id: Optional[str] = None  # User ID for user messages (None for assistant)
    # Token usage metadata (for assistant messages)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    # Provider/model metadata (for assistant messages)
    provider: Optional[str] = None  # "anthropic", "openai", "local"
    model: Optional[str] = None  # e.g., "claude-sonnet-4-20250514", "gpt-4o"
    # Recognition-in-flow markers (for assistant messages)
    self_observations: Optional[List[Dict]] = None
    user_observations: Optional[List[Dict]] = None
    marks: Optional[List[Dict]] = None
    # Narration metrics (for assistant messages)
    narration_metrics: Optional[Dict] = None
    # Attachments (files/images)
    attachments: Optional[List[Dict]] = None  # [{id, filename, media_type, size, is_image, url}]
    # Database ID (internal, not part of original API)
    id: Optional[int] = None


@dataclass
class Conversation:
    """A conversation with metadata"""
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[Message]
    last_summary_timestamp: Optional[str] = None
    messages_since_last_summary: int = 0
    project_id: Optional[str] = None  # Optional project association
    working_summary: Optional[str] = None  # Token-optimized summary for prompt context
    user_id: Optional[str] = None  # Owner of this conversation

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [asdict(msg) for msg in self.messages],
            "last_summary_timestamp": self.last_summary_timestamp,
            "messages_since_last_summary": self.messages_since_last_summary,
            "project_id": self.project_id,
            "working_summary": self.working_summary,
            "user_id": self.user_id
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Conversation':
        """Create from dictionary"""
        messages = [Message(**msg) for msg in data.get("messages", [])]
        return cls(
            id=data["id"],
            title=data["title"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            messages=messages,
            last_summary_timestamp=data.get("last_summary_timestamp"),
            messages_since_last_summary=data.get("messages_since_last_summary", 0),
            project_id=data.get("project_id"),
            working_summary=data.get("working_summary"),
            user_id=data.get("user_id")
        )


class ConversationManager:
    """
    Manages multiple conversations with SQLite persistence.

    Conversations and messages are stored in the SQLite database.
    """

    def __init__(self, storage_dir: str = None):
        """
        Initialize the conversation manager.

        Args:
            storage_dir: Ignored - kept for API compatibility. Database path is in config.
        """
        self.daemon_id = get_daemon_id()

    def create_conversation(
        self,
        title: Optional[str] = None,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Conversation:
        """Create a new conversation"""
        conversation_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute("""
                INSERT INTO conversations (
                    id, daemon_id, user_id, project_id, title,
                    working_summary, last_summary_timestamp,
                    messages_since_last_summary, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                conversation_id,
                self.daemon_id,
                user_id,
                project_id,
                title or "New Conversation",
                None,  # working_summary
                None,  # last_summary_timestamp
                0,     # messages_since_last_summary
                now,
                now
            ))

        return Conversation(
            id=conversation_id,
            title=title or "New Conversation",
            created_at=now,
            updated_at=now,
            messages=[],
            project_id=project_id,
            user_id=user_id
        )

    def load_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Load a conversation by ID"""
        with get_db() as conn:
            # Load conversation metadata
            cursor = conn.execute("""
                SELECT id, title, created_at, updated_at, user_id, project_id,
                       working_summary, last_summary_timestamp, messages_since_last_summary
                FROM conversations WHERE id = ?
            """, (conversation_id,))
            row = cursor.fetchone()

            if not row:
                return None

            # Load messages
            cursor = conn.execute("""
                SELECT id, role, content, timestamp, excluded, user_id,
                       provider, model, input_tokens, output_tokens,
                       animations_json, self_observations_json,
                       user_observations_json, marks_json, narration_metrics_json
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
            """, (conversation_id,))

            messages = []
            for msg_row in cursor.fetchall():
                messages.append(Message(
                    id=msg_row['id'],
                    role=msg_row['role'],
                    content=msg_row['content'],
                    timestamp=msg_row['timestamp'],
                    excluded=bool(msg_row['excluded']),
                    user_id=msg_row['user_id'],
                    provider=msg_row['provider'],
                    model=msg_row['model'],
                    input_tokens=msg_row['input_tokens'],
                    output_tokens=msg_row['output_tokens'],
                    animations=json_deserialize(msg_row['animations_json']),
                    self_observations=json_deserialize(msg_row['self_observations_json']),
                    user_observations=json_deserialize(msg_row['user_observations_json']),
                    marks=json_deserialize(msg_row['marks_json']),
                    narration_metrics=json_deserialize(msg_row['narration_metrics_json'])
                ))

            return Conversation(
                id=row['id'],
                title=row['title'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                messages=messages,
                last_summary_timestamp=row['last_summary_timestamp'],
                messages_since_last_summary=row['messages_since_last_summary'] or 0,
                project_id=row['project_id'],
                working_summary=row['working_summary'],
                user_id=row['user_id']
            )

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        animations: Optional[List[Dict]] = None,
        user_id: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        self_observations: Optional[List[Dict]] = None,
        user_observations: Optional[List[Dict]] = None,
        marks: Optional[List[Dict]] = None,
        narration_metrics: Optional[Dict] = None
    ) -> bool:
        """Add a message to a conversation"""
        now = datetime.now().isoformat()

        with get_db() as conn:
            # Check conversation exists
            cursor = conn.execute(
                "SELECT id, title FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            conv_row = cursor.fetchone()
            if not conv_row:
                return False

            # Insert message
            conn.execute("""
                INSERT INTO messages (
                    conversation_id, role, content, timestamp, excluded, user_id,
                    provider, model, input_tokens, output_tokens,
                    animations_json, self_observations_json,
                    user_observations_json, marks_json, narration_metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                conversation_id,
                role,
                content,
                now,
                0,  # excluded
                user_id if role == "user" else None,
                provider if role == "assistant" else None,
                model if role == "assistant" else None,
                input_tokens if role == "assistant" else None,
                output_tokens if role == "assistant" else None,
                json_serialize(animations),
                json_serialize(self_observations) if role == "assistant" else None,
                json_serialize(user_observations) if role == "assistant" else None,
                json_serialize(marks) if role == "assistant" else None,
                json_serialize(narration_metrics) if role == "assistant" else None
            ))

            # Check if this is the first user message for auto-title
            new_title = None
            if role == "user":
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND role = 'user'",
                    (conversation_id,)
                )
                user_msg_count = cursor.fetchone()[0]
                if user_msg_count == 1:  # Just inserted the first user message
                    new_title = self._generate_title(content)

            # Update conversation metadata
            if new_title:
                conn.execute("""
                    UPDATE conversations
                    SET updated_at = ?, messages_since_last_summary = messages_since_last_summary + 1, title = ?
                    WHERE id = ?
                """, (now, new_title, conversation_id))
            else:
                conn.execute("""
                    UPDATE conversations
                    SET updated_at = ?, messages_since_last_summary = messages_since_last_summary + 1
                    WHERE id = ?
                """, (now, conversation_id))

        return True

    def _generate_title(self, first_message: str, max_length: int = 50) -> str:
        """Generate a title from the first message"""
        lines = first_message.strip().split('\n')
        title = lines[0]

        if len(title) > max_length:
            title = title[:max_length - 3] + "..."

        return title or "New Conversation"

    def list_conversations(
        self,
        limit: Optional[int] = None,
        user_id: Optional[str] = None
    ) -> List[Dict]:
        """
        List conversations with metadata.
        Returns most recently updated first.
        """
        with get_db() as conn:
            if user_id:
                # Include conversations for this user OR with no user_id (shared/legacy)
                cursor = conn.execute("""
                    SELECT c.id, c.title, c.created_at, c.updated_at, c.project_id, c.user_id,
                           COUNT(m.id) as message_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    WHERE c.daemon_id = ? AND (c.user_id = ? OR c.user_id IS NULL)
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT ?
                """, (self.daemon_id, user_id, limit or 1000))
            else:
                cursor = conn.execute("""
                    SELECT c.id, c.title, c.created_at, c.updated_at, c.project_id, c.user_id,
                           COUNT(m.id) as message_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    WHERE c.daemon_id = ?
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT ?
                """, (self.daemon_id, limit or 1000))

            return [
                {
                    "id": row['id'],
                    "title": row['title'],
                    "created_at": row['created_at'],
                    "updated_at": row['updated_at'],
                    "message_count": row['message_count'],
                    "project_id": row['project_id'],
                    "user_id": row['user_id']
                }
                for row in cursor.fetchall()
            ]

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation (messages cascade automatically)"""
        with get_db() as conn:
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return True

    def get_message_count(self, conversation_id: str) -> int:
        """Get number of messages in a conversation"""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (conversation_id,)
            )
            return cursor.fetchone()[0]

    def update_title(self, conversation_id: str, new_title: str) -> bool:
        """Update a conversation's title"""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            if not cursor.fetchone():
                return False

            conn.execute("""
                UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?
            """, (new_title, datetime.now().isoformat(), conversation_id))

        return True

    def assign_to_project(
        self,
        conversation_id: str,
        project_id: Optional[str]
    ) -> bool:
        """Assign a conversation to a project, or remove from project."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            if not cursor.fetchone():
                return False

            conn.execute("""
                UPDATE conversations SET project_id = ?, updated_at = ? WHERE id = ?
            """, (project_id, datetime.now().isoformat(), conversation_id))

        return True

    def assign_to_user(
        self,
        conversation_id: str,
        user_id: Optional[str]
    ) -> bool:
        """Assign a conversation to a user, or remove user assignment."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            if not cursor.fetchone():
                return False

            conn.execute("""
                UPDATE conversations SET user_id = ?, updated_at = ? WHERE id = ?
            """, (user_id, datetime.now().isoformat(), conversation_id))

        return True

    def list_by_project(
        self,
        project_id: Optional[str],
        limit: Optional[int] = None
    ) -> List[Dict]:
        """List conversations for a specific project (or unassigned)."""
        with get_db() as conn:
            if project_id is None:
                cursor = conn.execute("""
                    SELECT c.id, c.title, c.created_at, c.updated_at, c.project_id, c.user_id,
                           COUNT(m.id) as message_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    WHERE c.daemon_id = ? AND c.project_id IS NULL
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT ?
                """, (self.daemon_id, limit or 1000))
            else:
                cursor = conn.execute("""
                    SELECT c.id, c.title, c.created_at, c.updated_at, c.project_id, c.user_id,
                           COUNT(m.id) as message_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    WHERE c.daemon_id = ? AND c.project_id = ?
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT ?
                """, (self.daemon_id, project_id, limit or 1000))

            return [
                {
                    "id": row['id'],
                    "title": row['title'],
                    "created_at": row['created_at'],
                    "updated_at": row['updated_at'],
                    "message_count": row['message_count'],
                    "project_id": row['project_id'],
                    "user_id": row['user_id']
                }
                for row in cursor.fetchall()
            ]

    def search_conversations(self, query: str, limit: int = 10) -> List[Dict]:
        """Search conversations by title or message content."""
        results = []
        query_pattern = f"%{query}%"

        with get_db() as conn:
            # Search titles
            cursor = conn.execute("""
                SELECT c.id, c.title, c.created_at, c.updated_at, c.project_id, c.user_id,
                       COUNT(m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.daemon_id = ? AND c.title LIKE ?
                GROUP BY c.id
                ORDER BY c.updated_at DESC
            """, (self.daemon_id, query_pattern))

            for row in cursor.fetchall():
                results.append({
                    "id": row['id'],
                    "title": row['title'],
                    "created_at": row['created_at'],
                    "updated_at": row['updated_at'],
                    "message_count": row['message_count'],
                    "project_id": row['project_id'],
                    "user_id": row['user_id'],
                    "relevance": "title"
                })

            # Search message content (for conversations not already found)
            found_ids = {r['id'] for r in results}
            cursor = conn.execute("""
                SELECT DISTINCT c.id, c.title, c.created_at, c.updated_at, c.project_id, c.user_id
                FROM conversations c
                JOIN messages m ON m.conversation_id = c.id
                WHERE c.daemon_id = ? AND m.content LIKE ?
            """, (self.daemon_id, query_pattern))

            for row in cursor.fetchall():
                if row['id'] not in found_ids:
                    # Get message count
                    count_cursor = conn.execute(
                        "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                        (row['id'],)
                    )
                    results.append({
                        "id": row['id'],
                        "title": row['title'],
                        "created_at": row['created_at'],
                        "updated_at": row['updated_at'],
                        "message_count": count_cursor.fetchone()[0],
                        "project_id": row['project_id'],
                        "user_id": row['user_id'],
                        "relevance": "message"
                    })

        return results[:limit]

    def get_recent_messages(
        self,
        conversation_id: str,
        count: int = 10
    ) -> List[Dict]:
        """Get the most recent messages from a conversation (chronological order)."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT role, content, timestamp
                FROM messages
                WHERE conversation_id = ? AND excluded = 0
                ORDER BY timestamp DESC
                LIMIT ?
            """, (conversation_id, count))

            # Reverse to get chronological order
            messages = [
                {
                    "role": row['role'],
                    "content": row['content'],
                    "timestamp": row['timestamp']
                }
                for row in cursor.fetchall()
            ]
            messages.reverse()
            return messages

    def get_unsummarized_messages(
        self,
        conversation_id: str,
        max_messages: int = 30
    ) -> List[Dict]:
        """Get messages that need summarization."""
        with get_db() as conn:
            # Get last_summary_timestamp
            cursor = conn.execute(
                "SELECT last_summary_timestamp FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            row = cursor.fetchone()
            if not row:
                return []

            last_summary = row['last_summary_timestamp']

            if last_summary:
                cursor = conn.execute("""
                    SELECT role, content, timestamp, animations_json
                    FROM messages
                    WHERE conversation_id = ? AND timestamp > ? AND excluded = 0
                    ORDER BY timestamp ASC
                    LIMIT ?
                """, (conversation_id, last_summary, max_messages))
            else:
                cursor = conn.execute("""
                    SELECT role, content, timestamp, animations_json
                    FROM messages
                    WHERE conversation_id = ? AND excluded = 0
                    ORDER BY timestamp ASC
                    LIMIT ?
                """, (conversation_id, max_messages))

            return [
                {
                    "role": row['role'],
                    "content": row['content'],
                    "timestamp": row['timestamp'],
                    "animations": json_deserialize(row['animations_json'])
                }
                for row in cursor.fetchall()
            ]

    def mark_messages_summarized(
        self,
        conversation_id: str,
        last_message_timestamp: str,
        messages_summarized: int
    ) -> bool:
        """Mark messages as summarized."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT messages_since_last_summary FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False

            new_count = max(0, (row['messages_since_last_summary'] or 0) - messages_summarized)

            conn.execute("""
                UPDATE conversations
                SET last_summary_timestamp = ?, messages_since_last_summary = ?
                WHERE id = ?
            """, (last_message_timestamp, new_count, conversation_id))

        return True

    def needs_auto_summary(
        self,
        conversation_id: str,
        threshold: int
    ) -> bool:
        """Check if conversation needs automatic summarization."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT messages_since_last_summary FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False

            return (row['messages_since_last_summary'] or 0) >= threshold

    def update_working_summary(
        self,
        conversation_id: str,
        working_summary: str
    ) -> bool:
        """Update the working summary for a conversation."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            if not cursor.fetchone():
                return False

            conn.execute(
                "UPDATE conversations SET working_summary = ? WHERE id = ?",
                (working_summary, conversation_id)
            )

        return True

    def get_working_summary(self, conversation_id: str) -> Optional[str]:
        """Get the working summary for a conversation."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT working_summary FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            row = cursor.fetchone()
            return row['working_summary'] if row else None

    def get_idle_conversations_needing_summary(
        self,
        idle_minutes: int = 30,
        min_unsummarized: int = 5
    ) -> list:
        """
        Get conversations that have unsummarized messages and have been idle.

        Args:
            idle_minutes: Minutes since last message to consider "idle"
            min_unsummarized: Minimum unsummarized messages to warrant summarization

        Returns:
            List of conversation IDs needing summarization
        """
        from datetime import datetime, timedelta

        cutoff_time = (datetime.now() - timedelta(minutes=idle_minutes)).isoformat()

        with get_db() as conn:
            # Find conversations where:
            # 1. messages_since_last_summary >= min_unsummarized
            # 2. Most recent message is older than cutoff_time
            cursor = conn.execute("""
                SELECT c.id
                FROM conversations c
                WHERE c.messages_since_last_summary >= ?
                  AND (SELECT MAX(m.timestamp) FROM messages m WHERE m.conversation_id = c.id) < ?
            """, (min_unsummarized, cutoff_time))

            return [row['id'] for row in cursor.fetchall()]

    def exclude_message(
        self,
        conversation_id: str,
        message_timestamp: str,
        exclude: bool = True
    ) -> bool:
        """Mark a message as excluded (or un-exclude it)."""
        with get_db() as conn:
            cursor = conn.execute("""
                UPDATE messages SET excluded = ?
                WHERE conversation_id = ? AND timestamp = ?
            """, (1 if exclude else 0, conversation_id, message_timestamp))

            return cursor.rowcount > 0

    def get_message_by_timestamp(
        self,
        conversation_id: str,
        message_timestamp: str
    ) -> Optional[Message]:
        """Get a specific message by timestamp."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, role, content, timestamp, excluded, user_id,
                       provider, model, input_tokens, output_tokens,
                       animations_json, self_observations_json,
                       user_observations_json, marks_json, narration_metrics_json
                FROM messages
                WHERE conversation_id = ? AND timestamp = ?
            """, (conversation_id, message_timestamp))

            row = cursor.fetchone()
            if not row:
                return None

            return Message(
                id=row['id'],
                role=row['role'],
                content=row['content'],
                timestamp=row['timestamp'],
                excluded=bool(row['excluded']),
                user_id=row['user_id'],
                provider=row['provider'],
                model=row['model'],
                input_tokens=row['input_tokens'],
                output_tokens=row['output_tokens'],
                animations=json_deserialize(row['animations_json']),
                self_observations=json_deserialize(row['self_observations_json']),
                user_observations=json_deserialize(row['user_observations_json']),
                marks=json_deserialize(row['marks_json']),
                narration_metrics=json_deserialize(row['narration_metrics_json'])
            )


if __name__ == "__main__":
    # Test the conversation manager
    from database import init_database
    init_database()

    manager = ConversationManager()

    # Create conversation
    conv = manager.create_conversation()
    print(f"Created conversation: {conv.id}")

    # Add messages
    manager.add_message(conv.id, "user", "Hello Cass!")
    manager.add_message(conv.id, "assistant", "Hey! How are you?", [{"type": "gesture", "name": "wave"}])

    # List conversations
    conversations = manager.list_conversations()
    print(f"\nConversations: {len(conversations)}")
    for c in conversations:
        print(f"  - {c['title']} ({c['message_count']} messages)")

    # Load and display
    loaded = manager.load_conversation(conv.id)
    print(f"\nLoaded conversation: {loaded.title}")
    for msg in loaded.messages:
        print(f"  [{msg.role}]: {msg.content}")

    # Clean up test conversation
    manager.delete_conversation(conv.id)
    print("\nTest conversation deleted")
