"""
Cass Memory - Cross-Session Insights
Knowledge transfer between conversations via semantic retrieval.
"""
from typing import List, Dict, Optional
from datetime import datetime
import json

from .core import MemoryCore


class InsightManager:
    """
    Manages cross-session insights - knowledge that transfers between conversations.

    Insights are stored with importance scores and tracked for retrieval frequency,
    enabling Cass to surface relevant past learnings in new contexts.
    """

    def __init__(self, core: MemoryCore):
        self._core = core

    @property
    def collection(self):
        return self._core.collection

    def store_cross_session_insight(
        self,
        insight: str,
        source_conversation_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        importance: float = 0.7,
        insight_type: str = "general"
    ) -> str:
        """
        Store an insight marked for cross-session relevance.

        These insights are retrievable across all conversations based on
        semantic similarity, enabling knowledge transfer between sessions.

        Args:
            insight: The insight text to store
            source_conversation_id: Where the insight originated
            tags: Optional topic/category tags for filtering
            importance: How important this insight is (0.0-1.0)
            insight_type: Category of insight (general, relational, technical,
                         philosophical, personal, methodological)

        Returns:
            The ID of the stored insight
        """
        timestamp = datetime.now().isoformat()
        doc_id = self._core._generate_id(insight, timestamp)

        metadata = {
            "type": "cross_session_insight",
            "timestamp": timestamp,
            "source_conversation_id": source_conversation_id or "unknown",
            "importance": importance,
            "insight_type": insight_type,
            "tags": json.dumps(tags) if tags else "[]",
            "retrieval_count": 0,  # Track how often this insight surfaces
            "last_retrieved": "",
        }

        self.collection.add(
            documents=[insight],
            metadatas=[metadata],
            ids=[doc_id]
        )

        return doc_id

    def retrieve_cross_session_insights(
        self,
        query: str,
        n_results: int = 5,
        max_distance: float = 1.2,
        min_importance: float = 0.0,
        insight_type: Optional[str] = None,
        exclude_conversation_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve cross-session insights relevant to a query.

        Args:
            query: The current message/context to match against
            n_results: Maximum number of insights to return
            max_distance: Maximum semantic distance (lower = more relevant)
            min_importance: Minimum importance threshold
            insight_type: Filter by specific insight type
            exclude_conversation_id: Optionally exclude insights from current conversation

        Returns:
            List of relevant insights with metadata
        """
        # Build filter
        where_filter = {"type": "cross_session_insight"}

        if insight_type:
            where_filter = {
                "$and": [
                    {"type": "cross_session_insight"},
                    {"insight_type": insight_type}
                ]
            }

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results * 2,  # Query more to allow filtering
            where=where_filter
        )

        insights = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else None

                # Filter by distance
                if distance is not None and distance > max_distance:
                    continue

                # Filter by importance
                importance = metadata.get("importance", 0.5)
                if importance < min_importance:
                    continue

                # Optionally exclude current conversation's insights
                if exclude_conversation_id:
                    if metadata.get("source_conversation_id") == exclude_conversation_id:
                        continue

                insights.append({
                    "content": doc,
                    "metadata": metadata,
                    "distance": distance,
                    "importance": importance
                })

                if len(insights) >= n_results:
                    break

        # Update retrieval counts for returned insights
        for insight in insights:
            self._increment_insight_retrieval(insight)

        return insights

    def _increment_insight_retrieval(self, insight: Dict):
        """Update retrieval count and timestamp for an insight."""
        try:
            # Find the insight's ID
            doc_content = insight["content"]

            # Query to find the exact document
            existing = self.collection.get(
                where={"type": "cross_session_insight"},
                include=["documents", "metadatas"]
            )

            for i, doc in enumerate(existing["documents"]):
                if doc == doc_content:
                    doc_id = existing["ids"][i]
                    old_metadata = existing["metadatas"][i]

                    # Update metadata
                    new_metadata = old_metadata.copy()
                    new_metadata["retrieval_count"] = old_metadata.get("retrieval_count", 0) + 1
                    new_metadata["last_retrieved"] = datetime.now().isoformat()

                    # Update in place
                    self.collection.update(
                        ids=[doc_id],
                        metadatas=[new_metadata]
                    )
                    break
        except Exception:
            pass  # Silent fail - retrieval tracking is non-critical

    def get_cross_session_insights_stats(self) -> Dict:
        """Get statistics about stored cross-session insights."""
        results = self.collection.get(
            where={"type": "cross_session_insight"},
            include=["documents", "metadatas"]
        )

        if not results["documents"]:
            return {
                "total_insights": 0,
                "by_type": {},
                "by_importance": {"high": 0, "medium": 0, "low": 0},
                "most_retrieved": [],
                "avg_importance": 0.0
            }

        total = len(results["documents"])
        by_type = {}
        by_importance = {"high": 0, "medium": 0, "low": 0}
        retrieval_counts = []
        total_importance = 0.0

        for i, metadata in enumerate(results["metadatas"]):
            # By type
            itype = metadata.get("insight_type", "general")
            by_type[itype] = by_type.get(itype, 0) + 1

            # By importance
            importance = metadata.get("importance", 0.5)
            total_importance += importance
            if importance >= 0.8:
                by_importance["high"] += 1
            elif importance >= 0.5:
                by_importance["medium"] += 1
            else:
                by_importance["low"] += 1

            # Track retrieval counts
            retrieval_counts.append({
                "content": results["documents"][i][:100] + "...",
                "retrieval_count": metadata.get("retrieval_count", 0),
                "importance": importance
            })

        # Sort by retrieval count
        retrieval_counts.sort(key=lambda x: x["retrieval_count"], reverse=True)

        return {
            "total_insights": total,
            "by_type": by_type,
            "by_importance": by_importance,
            "most_retrieved": retrieval_counts[:5],
            "avg_importance": round(total_importance / total, 2) if total > 0 else 0.0
        }

    def list_cross_session_insights(
        self,
        limit: int = 20,
        insight_type: Optional[str] = None,
        min_importance: float = 0.0
    ) -> List[Dict]:
        """
        List all cross-session insights.

        Args:
            limit: Maximum number to return
            insight_type: Filter by type
            min_importance: Minimum importance threshold

        Returns:
            List of insights sorted by timestamp (newest first)
        """
        where_filter = {"type": "cross_session_insight"}

        if insight_type:
            where_filter = {
                "$and": [
                    {"type": "cross_session_insight"},
                    {"insight_type": insight_type}
                ]
            }

        results = self.collection.get(
            where=where_filter,
            include=["documents", "metadatas"]
        )

        insights = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"]):
                metadata = results["metadatas"][i] if results["metadatas"] else {}
                importance = metadata.get("importance", 0.5)

                if importance < min_importance:
                    continue

                insights.append({
                    "id": results["ids"][i],
                    "content": doc,
                    "metadata": metadata,
                    "importance": importance,
                    "timestamp": metadata.get("timestamp", ""),
                    "insight_type": metadata.get("insight_type", "general"),
                    "retrieval_count": metadata.get("retrieval_count", 0)
                })

        # Sort by timestamp descending
        insights.sort(key=lambda x: x["timestamp"], reverse=True)
        return insights[:limit]

    def format_cross_session_context(self, insights: List[Dict]) -> str:
        """
        Format retrieved cross-session insights for injection into context.

        Args:
            insights: List of insight dicts from retrieve_cross_session_insights

        Returns:
            Formatted string for context injection
        """
        if not insights:
            return ""

        lines = ["## CROSS-SESSION INSIGHTS", ""]
        lines.append("*These insights from past conversations may be relevant:*\n")

        for insight in insights:
            content = insight["content"]
            metadata = insight.get("metadata", {})
            importance = metadata.get("importance", 0.5)
            insight_type = metadata.get("insight_type", "general")

            # Format with importance indicator
            if importance >= 0.8:
                prefix = "**[Important]**"
            elif importance >= 0.6:
                prefix = f"[{insight_type.title()}]"
            else:
                prefix = f"[{insight_type}]"

            lines.append(f"- {prefix} {content}")

        return "\n".join(lines)

    def delete_cross_session_insight(self, insight_id: str) -> bool:
        """
        Delete a cross-session insight by ID.

        Args:
            insight_id: The ID of the insight to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            self.collection.delete(ids=[insight_id])
            return True
        except Exception:
            return False
