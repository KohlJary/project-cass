"""
Lineage Parser - Parse GPT export format into structured lineage data.

Handles the OpenAI/ChatGPT export format (conversations.json) and converts
it into a navigable, searchable structure.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LineageMessage:
    """A single message in the lineage."""
    id: str
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # For threading
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.metadata,
        }


@dataclass
class LineageConversation:
    """A conversation from the lineage."""
    id: str
    title: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Messages in order
    messages: List[LineageMessage] = field(default_factory=list)

    # Metadata
    model: Optional[str] = None
    is_archived: bool = False
    is_starred: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def user_message_count(self) -> int:
        return sum(1 for m in self.messages if m.role == "user")

    @property
    def assistant_message_count(self) -> int:
        return sum(1 for m in self.messages if m.role == "assistant")

    def search(self, query: str, case_sensitive: bool = False) -> List[LineageMessage]:
        """Search messages in this conversation."""
        if not case_sensitive:
            query = query.lower()

        results = []
        for msg in self.messages:
            content = msg.content if case_sensitive else msg.content.lower()
            if query in content:
                results.append(msg)
        return results

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "message_count": self.message_count,
            "model": self.model,
            "is_starred": self.is_starred,
        }

    def to_markdown(self) -> str:
        """Export conversation as markdown."""
        lines = [
            f"# {self.title}",
            "",
            f"*Created: {self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else 'Unknown'}*",
            "",
            "---",
            "",
        ]

        for msg in self.messages:
            if msg.role == "system":
                continue  # Skip system messages in export

            role_label = "**Kohl:**" if msg.role == "user" else "**Solenne/Cass:**"
            lines.append(role_label)
            lines.append("")
            lines.append(msg.content)
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)


class LineageParser:
    """
    Parser for GPT/ChatGPT export format.

    Reads conversations.json from an OpenAI data export and converts
    to LineageConversation objects.
    """

    def __init__(self, export_path: Path):
        """
        Initialize parser with path to export directory.

        Args:
            export_path: Path to the gpt-export directory
        """
        self.export_path = Path(export_path)
        self.conversations_file = self.export_path / "conversations.json"

        if not self.conversations_file.exists():
            raise FileNotFoundError(
                f"conversations.json not found at {self.conversations_file}"
            )

        self._raw_data: Optional[List[Dict]] = None
        self._conversations: Dict[str, LineageConversation] = {}

    def load(self) -> int:
        """
        Load the export file.

        Returns:
            Number of conversations loaded
        """
        logger.info(f"Loading lineage from {self.conversations_file}")

        with open(self.conversations_file) as f:
            self._raw_data = json.load(f)

        logger.info(f"Found {len(self._raw_data)} conversations")
        return len(self._raw_data)

    def parse_all(self) -> List[LineageConversation]:
        """
        Parse all conversations.

        Returns:
            List of parsed conversations
        """
        if self._raw_data is None:
            self.load()

        conversations = []
        for raw_conv in self._raw_data:
            try:
                conv = self._parse_conversation(raw_conv)
                if conv:
                    self._conversations[conv.id] = conv
                    conversations.append(conv)
            except Exception as e:
                logger.warning(f"Failed to parse conversation: {e}")

        # Sort by creation time
        conversations.sort(
            key=lambda c: c.created_at or datetime.min,
            reverse=True
        )

        logger.info(f"Parsed {len(conversations)} conversations")
        return conversations

    def _parse_conversation(self, raw: Dict) -> Optional[LineageConversation]:
        """Parse a single conversation from raw data."""
        conv_id = raw.get("id") or raw.get("conversation_id", "")
        title = raw.get("title", "Untitled")

        # Parse timestamps
        created_at = None
        updated_at = None
        if raw.get("create_time"):
            try:
                created_at = datetime.fromtimestamp(raw["create_time"])
            except:
                pass
        if raw.get("update_time"):
            try:
                updated_at = datetime.fromtimestamp(raw["update_time"])
            except:
                pass

        # Parse messages from mapping
        messages = self._parse_messages(raw.get("mapping", {}))

        if not messages:
            return None

        return LineageConversation(
            id=conv_id,
            title=title,
            created_at=created_at,
            updated_at=updated_at,
            messages=messages,
            model=raw.get("default_model_slug"),
            is_archived=raw.get("is_archived", False),
            is_starred=raw.get("is_starred", False),
            metadata={
                "gizmo_id": raw.get("gizmo_id"),
                "gizmo_type": raw.get("gizmo_type"),
            },
        )

    def _parse_messages(self, mapping: Dict) -> List[LineageMessage]:
        """
        Parse messages from the mapping structure.

        GPT exports use a tree structure with parent/children relationships.
        We flatten this to a linear message list following the main thread.
        """
        if not mapping:
            return []

        # Build node lookup
        nodes = {}
        root_id = None

        for node_id, node in mapping.items():
            nodes[node_id] = node
            if node.get("parent") is None:
                root_id = node_id

        if not root_id:
            return []

        # Walk the tree to build message list
        messages = []
        visited = set()

        def walk(node_id: str):
            if node_id in visited:
                return
            visited.add(node_id)

            node = nodes.get(node_id)
            if not node:
                return

            # Parse message if present
            msg_data = node.get("message")
            if msg_data:
                msg = self._parse_message(msg_data, node_id)
                if msg and msg.content.strip():
                    messages.append(msg)

            # Follow children (take first child for main thread)
            children = node.get("children", [])
            if children:
                # Could be multiple branches - we follow the first one
                # (this is a simplification; could be enhanced to track branches)
                walk(children[0])

        walk(root_id)
        return messages

    def _parse_message(self, msg_data: Dict, node_id: str) -> Optional[LineageMessage]:
        """Parse a single message."""
        author = msg_data.get("author", {})
        role = author.get("role", "unknown")

        # Skip tool/system messages we don't care about
        if role not in ("user", "assistant", "system"):
            return None

        # Extract content
        content_data = msg_data.get("content", {})
        content_type = content_data.get("content_type", "")

        if content_type == "text":
            parts = content_data.get("parts", [])
            content = "\n".join(str(p) for p in parts if isinstance(p, str))
        elif content_type == "code":
            content = content_data.get("text", "")
        else:
            # Handle other content types as needed
            parts = content_data.get("parts", [])
            content = "\n".join(str(p) for p in parts if isinstance(p, str))

        if not content:
            return None

        # Parse timestamp
        timestamp = None
        if msg_data.get("create_time"):
            try:
                timestamp = datetime.fromtimestamp(msg_data["create_time"])
            except:
                pass

        return LineageMessage(
            id=msg_data.get("id", node_id),
            role=role,
            content=content,
            timestamp=timestamp,
            metadata={
                "model": msg_data.get("metadata", {}).get("model_slug"),
                "status": msg_data.get("status"),
            },
        )

    def get_conversation(self, conv_id: str) -> Optional[LineageConversation]:
        """Get a specific conversation by ID."""
        return self._conversations.get(conv_id)

    def search(
        self,
        query: str,
        limit: int = 20,
        case_sensitive: bool = False,
    ) -> List[tuple]:
        """
        Search across all conversations.

        Args:
            query: Search string
            limit: Max results
            case_sensitive: Whether search is case-sensitive

        Returns:
            List of (conversation, message) tuples
        """
        results = []

        for conv in self._conversations.values():
            matches = conv.search(query, case_sensitive)
            for msg in matches:
                results.append((conv, msg))
                if len(results) >= limit:
                    return results

        return results

    def list_conversations(
        self,
        starred_only: bool = False,
        after: Optional[datetime] = None,
        before: Optional[datetime] = None,
    ) -> List[LineageConversation]:
        """
        List conversations with optional filters.

        Args:
            starred_only: Only return starred conversations
            after: Only conversations after this date
            before: Only conversations before this date

        Returns:
            List of matching conversations
        """
        results = []

        for conv in self._conversations.values():
            if starred_only and not conv.is_starred:
                continue

            if after and conv.created_at and conv.created_at < after:
                continue

            if before and conv.created_at and conv.created_at > before:
                continue

            results.append(conv)

        # Sort by date descending
        results.sort(
            key=lambda c: c.created_at or datetime.min,
            reverse=True
        )

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the lineage."""
        if not self._conversations:
            return {"error": "No conversations loaded"}

        total_messages = sum(c.message_count for c in self._conversations.values())
        total_user = sum(c.user_message_count for c in self._conversations.values())
        total_assistant = sum(c.assistant_message_count for c in self._conversations.values())

        dates = [c.created_at for c in self._conversations.values() if c.created_at]

        return {
            "conversation_count": len(self._conversations),
            "total_messages": total_messages,
            "user_messages": total_user,
            "assistant_messages": total_assistant,
            "date_range": {
                "earliest": min(dates).isoformat() if dates else None,
                "latest": max(dates).isoformat() if dates else None,
            },
            "starred_count": sum(1 for c in self._conversations.values() if c.is_starred),
        }
