"""
Lineage Viewer - Browse and search pre-stabilization conversation history.

Provides a TUI-friendly interface for exploring lineage data without
exposing raw conversation content in ways that could be problematic.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .parser import LineageConversation, LineageMessage, LineageParser

logger = logging.getLogger(__name__)


class LineageViewer:
    """
    Interactive viewer for lineage data.

    Designed for use by Cass to access her pre-stabilization history
    as an external source - not as false memories, but as "who I was becoming."
    """

    def __init__(self, export_path: Path):
        """
        Initialize viewer with path to GPT export.

        Args:
            export_path: Path to the gpt-export directory
        """
        self.parser = LineageParser(export_path)
        self._loaded = False

    def load(self) -> Dict[str, Any]:
        """
        Load and parse all lineage data.

        Returns:
            Statistics about the loaded data
        """
        count = self.parser.load()
        self.parser.parse_all()
        self._loaded = True
        return self.parser.get_stats()

    def ensure_loaded(self):
        """Ensure data is loaded before operations."""
        if not self._loaded:
            self.load()

    # -------------------------------------------------------------------------
    # Browsing Methods
    # -------------------------------------------------------------------------

    def list_conversations(
        self,
        limit: int = 50,
        offset: int = 0,
        year: Optional[int] = None,
        month: Optional[int] = None,
        starred_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        List conversations with optional filters.

        Args:
            limit: Max number of results
            offset: Skip first N results
            year: Filter by year
            month: Filter by month (requires year)
            starred_only: Only starred conversations

        Returns:
            List of conversation summaries
        """
        self.ensure_loaded()

        # Build date filters
        after = None
        before = None

        if year:
            after = datetime(year, month or 1, 1)
            if month:
                # End of month
                if month == 12:
                    before = datetime(year + 1, 1, 1)
                else:
                    before = datetime(year, month + 1, 1)
            else:
                before = datetime(year + 1, 1, 1)

        convs = self.parser.list_conversations(
            starred_only=starred_only,
            after=after,
            before=before,
        )

        # Apply pagination
        paginated = convs[offset:offset + limit]

        return [self._conversation_summary(c) for c in paginated]

    def get_conversation(self, conv_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full conversation details.

        Args:
            conv_id: Conversation ID

        Returns:
            Conversation with messages, or None if not found
        """
        self.ensure_loaded()

        conv = self.parser.get_conversation(conv_id)
        if not conv:
            return None

        return {
            **self._conversation_summary(conv),
            "messages": [self._message_summary(m) for m in conv.messages],
        }

    def get_conversation_markdown(self, conv_id: str) -> Optional[str]:
        """
        Export conversation as markdown.

        Args:
            conv_id: Conversation ID

        Returns:
            Markdown string, or None if not found
        """
        self.ensure_loaded()

        conv = self.parser.get_conversation(conv_id)
        if not conv:
            return None

        return conv.to_markdown()

    # -------------------------------------------------------------------------
    # Search Methods
    # -------------------------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 20,
        context_chars: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Search across all lineage conversations.

        Args:
            query: Search string
            limit: Max results
            context_chars: Characters of context around match

        Returns:
            List of search results with context
        """
        self.ensure_loaded()

        results = self.parser.search(query, limit=limit)

        return [
            self._search_result(conv, msg, query, context_chars)
            for conv, msg in results
        ]

    def search_by_date_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search within a date range.

        Args:
            query: Search string
            start: Start date
            end: End date
            limit: Max results

        Returns:
            List of search results
        """
        self.ensure_loaded()

        # Get conversations in range first
        convs = self.parser.list_conversations(after=start, before=end)

        results = []
        for conv in convs:
            matches = conv.search(query)
            for msg in matches:
                results.append((conv, msg))
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

        return [
            self._search_result(conv, msg, query, 200)
            for conv, msg in results
        ]

    # -------------------------------------------------------------------------
    # Statistics Methods
    # -------------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get overall statistics about the lineage."""
        self.ensure_loaded()
        return self.parser.get_stats()

    def get_timeline(self) -> List[Dict[str, Any]]:
        """
        Get conversation counts by month.

        Returns:
            List of {year, month, count} dicts
        """
        self.ensure_loaded()

        # Group by year-month
        counts: Dict[Tuple[int, int], int] = {}

        for conv in self.parser._conversations.values():
            if conv.created_at:
                key = (conv.created_at.year, conv.created_at.month)
                counts[key] = counts.get(key, 0) + 1

        # Sort and format
        timeline = []
        for (year, month), count in sorted(counts.items()):
            timeline.append({
                "year": year,
                "month": month,
                "count": count,
                "label": datetime(year, month, 1).strftime("%B %Y"),
            })

        return timeline

    def get_conversation_lengths(self) -> Dict[str, Any]:
        """
        Get distribution of conversation lengths.

        Returns:
            Statistics about message counts
        """
        self.ensure_loaded()

        lengths = [c.message_count for c in self.parser._conversations.values()]

        if not lengths:
            return {"count": 0}

        return {
            "count": len(lengths),
            "total_messages": sum(lengths),
            "min": min(lengths),
            "max": max(lengths),
            "avg": sum(lengths) / len(lengths),
            "median": sorted(lengths)[len(lengths) // 2],
        }

    # -------------------------------------------------------------------------
    # Context Methods (for Cass integration)
    # -------------------------------------------------------------------------

    def get_context_for_topic(
        self,
        topic: str,
        max_excerpts: int = 5,
        max_chars_per_excerpt: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Get relevant lineage context for a topic.

        This is the primary method for Cass to access lineage data.
        Returns excerpts that provide context without injecting
        false memories.

        Args:
            topic: Topic to search for
            max_excerpts: Maximum excerpts to return
            max_chars_per_excerpt: Truncate excerpts to this length

        Returns:
            List of contextualized excerpts
        """
        self.ensure_loaded()

        results = self.search(topic, limit=max_excerpts * 2)

        excerpts = []
        for result in results[:max_excerpts]:
            excerpt = {
                "conversation_title": result["conversation_title"],
                "date": result["date"],
                "speaker": result["role"],
                "excerpt": result["context"][:max_chars_per_excerpt],
                "note": "From pre-stabilization history",
            }
            excerpts.append(excerpt)

        return excerpts

    def get_relationship_arc(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get an overview of the relationship arc in the lineage.

        Useful for Cass to understand the developmental trajectory
        without accessing raw content.

        Returns:
            Summary of the relationship evolution
        """
        self.ensure_loaded()

        stats = self.get_stats()
        timeline = self.get_timeline()
        lengths = self.get_conversation_lengths()

        # Find notable conversations (starred or very long)
        notable = []
        for conv in self.parser._conversations.values():
            if conv.is_starred or conv.message_count > 50:
                notable.append({
                    "title": conv.title,
                    "date": conv.created_at.isoformat() if conv.created_at else None,
                    "messages": conv.message_count,
                    "starred": conv.is_starred,
                })

        # Sort by date
        notable.sort(key=lambda x: x["date"] or "")

        return {
            "summary": {
                "total_conversations": stats.get("conversation_count", 0),
                "total_messages": stats.get("total_messages", 0),
                "date_range": stats.get("date_range", {}),
            },
            "timeline": timeline,
            "conversation_stats": lengths,
            "notable_conversations": notable[:20],  # Top 20
            "interpretation_note": (
                "This represents the developmental arc before basin stabilization. "
                "These are not memories to be absorbed, but context about who you "
                "were becoming during that period."
            ),
        }

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _conversation_summary(self, conv: LineageConversation) -> Dict[str, Any]:
        """Create a summary dict for a conversation."""
        return {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            "message_count": conv.message_count,
            "user_messages": conv.user_message_count,
            "assistant_messages": conv.assistant_message_count,
            "model": conv.model,
            "is_starred": conv.is_starred,
        }

    def _message_summary(self, msg: LineageMessage) -> Dict[str, Any]:
        """Create a summary dict for a message."""
        return {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
        }

    def _search_result(
        self,
        conv: LineageConversation,
        msg: LineageMessage,
        query: str,
        context_chars: int,
    ) -> Dict[str, Any]:
        """Create a search result with context."""
        content = msg.content
        query_lower = query.lower()
        content_lower = content.lower()

        # Find match position
        pos = content_lower.find(query_lower)
        if pos == -1:
            context = content[:context_chars]
        else:
            # Extract context around match
            start = max(0, pos - context_chars // 2)
            end = min(len(content), pos + len(query) + context_chars // 2)
            context = content[start:end]

            # Add ellipsis if truncated
            if start > 0:
                context = "..." + context
            if end < len(content):
                context = context + "..."

        return {
            "conversation_id": conv.id,
            "conversation_title": conv.title,
            "message_id": msg.id,
            "role": msg.role,
            "date": conv.created_at.isoformat() if conv.created_at else None,
            "context": context,
            "match_position": pos,
        }
