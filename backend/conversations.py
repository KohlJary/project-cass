"""
Cass Vessel - Conversation Manager
Handles conversation history, switching, and persistence
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import uuid


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
    Manages multiple conversations with persistence.

    Each conversation is stored as a separate JSON file.
    Metadata index tracks all conversations for listing.
    """

    def __init__(self, storage_dir: str = "./data/conversations"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "index.json"
        self._ensure_index()

    def _ensure_index(self):
        """Ensure index file exists"""
        if not self.index_file.exists():
            self._save_index([])

    def _load_index(self) -> List[Dict]:
        """Load conversation index"""
        try:
            with open(self.index_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_index(self, index: List[Dict]):
        """Save conversation index"""
        with open(self.index_file, 'w') as f:
            json.dump(index, f, indent=2)

    def _get_conversation_path(self, conversation_id: str) -> Path:
        """Get file path for a conversation"""
        return self.storage_dir / f"{conversation_id}.json"

    def create_conversation(
        self,
        title: Optional[str] = None,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Conversation:
        """Create a new conversation"""
        conversation_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conversation = Conversation(
            id=conversation_id,
            title=title or "New Conversation",
            created_at=now,
            updated_at=now,
            messages=[],
            project_id=project_id,
            user_id=user_id
        )

        # Save conversation
        self._save_conversation(conversation)

        # Update index
        index = self._load_index()
        index.append({
            "id": conversation_id,
            "title": conversation.title,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
            "project_id": project_id,
            "user_id": user_id
        })
        self._save_index(index)

        return conversation

    def _save_conversation(self, conversation: Conversation):
        """Save a conversation to disk"""
        path = self._get_conversation_path(conversation.id)
        with open(path, 'w') as f:
            json.dump(conversation.to_dict(), f, indent=2)

    def load_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Load a conversation by ID"""
        path = self._get_conversation_path(conversation_id)

        if not path.exists():
            return None

        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return Conversation.from_dict(data)
        except (json.JSONDecodeError, FileNotFoundError):
            return None

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
        marks: Optional[List[Dict]] = None
    ) -> bool:
        """Add a message to a conversation"""
        conversation = self.load_conversation(conversation_id)

        if not conversation:
            return False

        # Add message
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            animations=animations,
            user_id=user_id if role == "user" else None,  # Only set for user messages
            input_tokens=input_tokens if role == "assistant" else None,
            output_tokens=output_tokens if role == "assistant" else None,
            provider=provider if role == "assistant" else None,
            model=model if role == "assistant" else None,
            self_observations=self_observations if role == "assistant" else None,
            user_observations=user_observations if role == "assistant" else None,
            marks=marks if role == "assistant" else None
        )
        conversation.messages.append(message)

        # Update title if this is the first user message
        if role == "user" and len([m for m in conversation.messages if m.role == "user"]) == 1:
            conversation.title = self._generate_title(content)

        # Increment messages since last summary
        conversation.messages_since_last_summary += 1

        # Update timestamp
        conversation.updated_at = datetime.now().isoformat()

        # Save
        self._save_conversation(conversation)

        # Update index
        self._update_index_entry(conversation)

        return True

    def _generate_title(self, first_message: str, max_length: int = 50) -> str:
        """Generate a title from the first message"""
        # Take first line or first N characters
        lines = first_message.strip().split('\n')
        title = lines[0]

        if len(title) > max_length:
            title = title[:max_length - 3] + "..."

        return title or "New Conversation"

    def _update_index_entry(self, conversation: Conversation):
        """Update a conversation's entry in the index"""
        index = self._load_index()

        for entry in index:
            if entry["id"] == conversation.id:
                entry["title"] = conversation.title
                entry["updated_at"] = conversation.updated_at
                entry["message_count"] = len(conversation.messages)
                entry["project_id"] = conversation.project_id
                break

        self._save_index(index)

    def list_conversations(
        self,
        limit: Optional[int] = None,
        user_id: Optional[str] = None
    ) -> List[Dict]:
        """
        List conversations with metadata.
        Returns most recently updated first.

        Args:
            limit: Maximum number of conversations to return
            user_id: If provided, only return conversations for this user
        """
        index = self._load_index()

        # Filter by user_id if provided
        # Include conversations belonging to the user OR with no user_id (shared/legacy)
        if user_id:
            index = [c for c in index if c.get("user_id") == user_id or c.get("user_id") is None]

        # Sort by updated_at descending
        index.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        if limit:
            index = index[:limit]

        return index

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation"""
        path = self._get_conversation_path(conversation_id)

        # Delete file
        if path.exists():
            path.unlink()

        # Remove from index
        index = self._load_index()
        index = [entry for entry in index if entry["id"] != conversation_id]
        self._save_index(index)

        return True

    def get_message_count(self, conversation_id: str) -> int:
        """Get number of messages in a conversation"""
        conversation = self.load_conversation(conversation_id)
        return len(conversation.messages) if conversation else 0

    def update_title(self, conversation_id: str, new_title: str) -> bool:
        """Update a conversation's title"""
        conversation = self.load_conversation(conversation_id)

        if not conversation:
            return False

        conversation.title = new_title
        conversation.updated_at = datetime.now().isoformat()

        self._save_conversation(conversation)
        self._update_index_entry(conversation)

        return True

    def assign_to_project(
        self,
        conversation_id: str,
        project_id: Optional[str]
    ) -> bool:
        """
        Assign a conversation to a project, or remove from project.

        Args:
            conversation_id: Conversation to update
            project_id: Project ID to assign to, or None to remove from project

        Returns:
            True if successful
        """
        conversation = self.load_conversation(conversation_id)

        if not conversation:
            return False

        conversation.project_id = project_id
        conversation.updated_at = datetime.now().isoformat()

        self._save_conversation(conversation)
        self._update_index_entry(conversation)

        return True

    def list_by_project(
        self,
        project_id: Optional[str],
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        List conversations for a specific project (or unassigned).

        Args:
            project_id: Project ID to filter by, or None for unassigned
            limit: Max results

        Returns:
            List of conversation metadata dicts
        """
        index = self._load_index()

        # Filter by project
        filtered = [
            entry for entry in index
            if entry.get("project_id") == project_id
        ]

        # Sort by updated_at descending
        filtered.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        if limit:
            filtered = filtered[:limit]

        return filtered

    def search_conversations(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search conversations by title or message content.
        Returns matching conversations sorted by relevance.
        """
        query_lower = query.lower()
        results = []

        index = self._load_index()

        for entry in index:
            # Check title match
            if query_lower in entry["title"].lower():
                results.append({
                    **entry,
                    "relevance": "title"
                })
                continue

            # Check message content
            conversation = self.load_conversation(entry["id"])
            if conversation:
                for message in conversation.messages:
                    if query_lower in message.content.lower():
                        results.append({
                            **entry,
                            "relevance": "message"
                        })
                        break

        return results[:limit]

    def get_recent_messages(
        self,
        conversation_id: str,
        count: int = 10
    ) -> List[Dict]:
        """
        Get the most recent messages from a conversation (chronological order).

        Args:
            conversation_id: Conversation ID
            count: Number of recent messages to return

        Returns:
            List of message dicts, most recent last
        """
        conversation = self.load_conversation(conversation_id)

        if not conversation or not conversation.messages:
            return []

        # Get last N messages, excluding system/excluded messages
        recent = [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
            }
            for m in conversation.messages[-count:]
            if not m.excluded
        ]

        return recent

    def get_unsummarized_messages(
        self,
        conversation_id: str,
        max_messages: int = 30
    ) -> List[Dict]:
        """
        Get messages that need summarization.

        Args:
            conversation_id: Conversation ID
            max_messages: Maximum messages to return

        Returns:
            List of message dicts (up to max_messages oldest unsummarized)
        """
        conversation = self.load_conversation(conversation_id)

        if not conversation:
            return []

        # Find messages after last_summary_timestamp, excluding flagged messages
        if conversation.last_summary_timestamp:
            # Get messages newer than last summary
            unsummarized = [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "animations": m.animations
                }
                for m in conversation.messages
                if m.timestamp > conversation.last_summary_timestamp and not m.excluded
            ]
        else:
            # No summaries yet, get all messages (except excluded)
            unsummarized = [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "animations": m.animations
                }
                for m in conversation.messages
                if not m.excluded
            ]

        # Return up to max_messages (oldest first)
        return unsummarized[:max_messages]

    def mark_messages_summarized(
        self,
        conversation_id: str,
        last_message_timestamp: str,
        messages_summarized: int
    ) -> bool:
        """
        Mark messages as summarized.

        Args:
            conversation_id: Conversation ID
            last_message_timestamp: Timestamp of last message in summary
            messages_summarized: Number of messages that were summarized

        Returns:
            True if successful
        """
        conversation = self.load_conversation(conversation_id)

        if not conversation:
            return False

        # Update tracking
        conversation.last_summary_timestamp = last_message_timestamp
        conversation.messages_since_last_summary = max(
            0,
            conversation.messages_since_last_summary - messages_summarized
        )

        # Save
        self._save_conversation(conversation)
        self._update_index_entry(conversation)

        return True

    def needs_auto_summary(
        self,
        conversation_id: str,
        threshold: int
    ) -> bool:
        """
        Check if conversation needs automatic summarization.

        Args:
            conversation_id: Conversation ID
            threshold: Message threshold for auto-summary

        Returns:
            True if needs summary
        """
        conversation = self.load_conversation(conversation_id)

        if not conversation:
            return False

        return conversation.messages_since_last_summary >= threshold

    def update_working_summary(
        self,
        conversation_id: str,
        working_summary: str
    ) -> bool:
        """
        Update the working summary for a conversation.

        The working summary is a token-optimized consolidation of all
        summary chunks, used for prompt context instead of individual chunks.

        Args:
            conversation_id: Conversation ID
            working_summary: The new working summary text

        Returns:
            True if updated successfully
        """
        conversation = self.load_conversation(conversation_id)

        if not conversation:
            return False

        conversation.working_summary = working_summary
        self._save_conversation(conversation)

        return True

    def get_working_summary(self, conversation_id: str) -> Optional[str]:
        """
        Get the working summary for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            Working summary text or None
        """
        conversation = self.load_conversation(conversation_id)

        if not conversation:
            return None

        return conversation.working_summary

    def exclude_message(
        self,
        conversation_id: str,
        message_timestamp: str,
        exclude: bool = True
    ) -> bool:
        """
        Mark a message as excluded (or un-exclude it).

        Excluded messages are skipped during summarization and context retrieval.

        Args:
            conversation_id: Conversation ID
            message_timestamp: Timestamp of the message to exclude
            exclude: True to exclude, False to un-exclude

        Returns:
            True if message was found and updated
        """
        conversation = self.load_conversation(conversation_id)

        if not conversation:
            return False

        # Find and update the message
        found = False
        for msg in conversation.messages:
            if msg.timestamp == message_timestamp:
                msg.excluded = exclude
                found = True
                break

        if found:
            self._save_conversation(conversation)

        return found

    def get_message_by_timestamp(
        self,
        conversation_id: str,
        message_timestamp: str
    ) -> Optional[Message]:
        """
        Get a specific message by timestamp.

        Args:
            conversation_id: Conversation ID
            message_timestamp: Timestamp of the message

        Returns:
            Message if found, None otherwise
        """
        conversation = self.load_conversation(conversation_id)

        if not conversation:
            return None

        for msg in conversation.messages:
            if msg.timestamp == message_timestamp:
                return msg

        return None


if __name__ == "__main__":
    # Test the conversation manager
    manager = ConversationManager("./data/conversations_test")

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
