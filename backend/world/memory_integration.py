"""
World State Memory Integration

Handles storing article summaries in ChromaDB for recent ambient recall,
and provides tools for retrieving older articles from database storage.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from database import get_db

logger = logging.getLogger(__name__)

# Default window for ChromaDB storage (articles older than this are DB-only)
DEFAULT_MEMORY_WINDOW_DAYS = 7


class ArticleMemoryManager:
    """
    Manages article memory across two tiers:
    - Recent articles (< X days): Stored in ChromaDB for natural retrieval
    - Older articles: Stored in DB, accessible via tools
    """

    def __init__(self, daemon_id: str, memory_core=None, memory_window_days: int = DEFAULT_MEMORY_WINDOW_DAYS):
        self.daemon_id = daemon_id
        self.memory_core = memory_core
        self.memory_window_days = memory_window_days

    def store_article_memory(
        self,
        article_id: str,
        headline: str,
        source: str,
        summary: str,
        url: str,
        category: Optional[str] = None,
        consumed_at: Optional[str] = None,
    ) -> Optional[str]:
        """
        Store article summary in ChromaDB for ambient retrieval.

        Args:
            article_id: Unique article ID
            headline: Article headline
            source: News source name
            summary: Cass's summary of the article
            url: Original article URL
            category: Optional category (technology, science, etc.)
            consumed_at: When article was consumed (ISO format)

        Returns:
            Memory entry ID if stored, None if no memory_core available
        """
        if not self.memory_core:
            logger.warning("No memory_core available, skipping ChromaDB storage")
            return None

        timestamp = consumed_at or datetime.now().isoformat()

        # Format for natural retrieval
        content = f"""Article: {headline}
Source: {source}
Category: {category or 'general'}

{summary}

[Read on {timestamp[:10]} - {url}]"""

        metadata = {
            "timestamp": timestamp,
            "type": "article_consumption",
            "article_id": article_id,
            "headline": headline[:200],
            "source": source,
            "url": url,
            "category": category or "general",
            "daemon_id": self.daemon_id,
        }

        entry_id = self.memory_core._generate_id(content, timestamp)

        try:
            self.memory_core.collection.add(
                documents=[content],
                metadatas=[metadata],
                ids=[entry_id]
            )
            logger.info(f"Stored article {article_id} in ChromaDB memory")
            return entry_id
        except Exception as e:
            logger.error(f"Failed to store article in ChromaDB: {e}")
            return None

    def cleanup_old_articles(self) -> int:
        """
        Remove articles older than memory_window_days from ChromaDB.

        Returns:
            Number of entries removed
        """
        if not self.memory_core:
            return 0

        cutoff = datetime.now() - timedelta(days=self.memory_window_days)
        cutoff_str = cutoff.isoformat()

        try:
            # Query for old article memories
            results = self.memory_core.collection.get(
                where={
                    "$and": [
                        {"type": "article_consumption"},
                        {"daemon_id": self.daemon_id},
                    ]
                },
                include=["metadatas"]
            )

            if not results["ids"]:
                return 0

            # Find IDs to delete
            ids_to_delete = []
            for i, entry_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i] if results["metadatas"] else {}
                timestamp = metadata.get("timestamp", "")
                if timestamp and timestamp < cutoff_str:
                    ids_to_delete.append(entry_id)

            if ids_to_delete:
                self.memory_core.collection.delete(ids=ids_to_delete)
                logger.info(f"Cleaned up {len(ids_to_delete)} old article memories")

            return len(ids_to_delete)

        except Exception as e:
            logger.error(f"Failed to cleanup old articles: {e}")
            return 0


# =============================================================================
# TOOL FUNCTIONS - For Cass to recall articles from database
# =============================================================================

def search_consumed_articles(
    daemon_id: str,
    query: Optional[str] = None,
    category: Optional[str] = None,
    source: Optional[str] = None,
    author: Optional[str] = None,
    days_back: int = 30,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Search consumed articles in database storage.

    Args:
        daemon_id: Daemon ID
        query: Text search in headline/summary
        category: Filter by category
        source: Filter by source
        author: Filter by author name (partial match)
        days_back: How far back to search
        limit: Max results

    Returns:
        List of article summaries
    """
    cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()

    sql = """
        SELECT id, url, headline, source, category, summary, consumed_at,
               author_name, author_handle, author_handle_type, author_entity_id
        FROM consumed_articles
        WHERE daemon_id = ?
        AND consumed_at > ?
        AND processing_status = 'completed'
    """
    params: List[Any] = [daemon_id, cutoff]

    if query:
        sql += " AND (headline LIKE ? OR summary LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])

    if category:
        sql += " AND category = ?"
        params.append(category)

    if source:
        sql += " AND source LIKE ?"
        params.append(f"%{source}%")

    if author:
        sql += " AND author_name LIKE ?"
        params.append(f"%{author}%")

    sql += " ORDER BY consumed_at DESC LIMIT ?"
    params.append(limit)

    try:
        with get_db() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

            return [
                {
                    "id": row[0],
                    "url": row[1],
                    "headline": row[2],
                    "source": row[3],
                    "category": row[4],
                    "summary": row[5],
                    "consumed_at": row[6],
                    "author_name": row[7],
                    "author_handle": row[8],
                    "author_handle_type": row[9],
                    "author_entity_id": row[10],
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Failed to search articles: {e}")
        return []


def get_article_details(daemon_id: str, article_id: str) -> Optional[Dict[str, Any]]:
    """
    Get full details of a specific consumed article.

    Args:
        daemon_id: Daemon ID
        article_id: Article ID

    Returns:
        Full article details including extractions, or None if not found
    """
    try:
        with get_db() as conn:
            cursor = conn.execute(
                """
                SELECT id, url, headline, source, category, summary, consumed_at,
                       processing_time_ms, tokens_used, observations_json,
                       growth_edges_json, opinions_json, questions_json,
                       author_name, author_handle, author_handle_type, author_entity_id
                FROM consumed_articles
                WHERE daemon_id = ? AND id = ?
                """,
                (daemon_id, article_id)
            )
            row = cursor.fetchone()

            if not row:
                return None

            import json
            return {
                "id": row[0],
                "url": row[1],
                "headline": row[2],
                "source": row[3],
                "category": row[4],
                "summary": row[5],
                "consumed_at": row[6],
                "processing_time_ms": row[7],
                "tokens_used": row[8],
                "observations": json.loads(row[9]) if row[9] else [],
                "growth_edges": json.loads(row[10]) if row[10] else [],
                "opinions": json.loads(row[11]) if row[11] else [],
                "questions": json.loads(row[12]) if row[12] else [],
                "author_name": row[13],
                "author_handle": row[14],
                "author_handle_type": row[15],
                "author_entity_id": row[16],
            }
    except Exception as e:
        logger.error(f"Failed to get article details: {e}")
        return None


def get_articles_by_author(
    daemon_id: str,
    author_entity_id: Optional[str] = None,
    author_name: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Get all articles by a specific author.

    Args:
        daemon_id: Daemon ID
        author_entity_id: PeopleDex entity ID (exact match, preferred)
        author_name: Author name (partial match)
        limit: Max results

    Returns:
        List of articles by the author
    """
    try:
        with get_db() as conn:
            if author_entity_id:
                cursor = conn.execute(
                    """
                    SELECT id, url, headline, source, category, summary, consumed_at,
                           author_name, author_handle, author_handle_type, author_entity_id
                    FROM consumed_articles
                    WHERE daemon_id = ? AND author_entity_id = ?
                    AND processing_status = 'completed'
                    ORDER BY consumed_at DESC
                    LIMIT ?
                    """,
                    (daemon_id, author_entity_id, limit)
                )
            elif author_name:
                cursor = conn.execute(
                    """
                    SELECT id, url, headline, source, category, summary, consumed_at,
                           author_name, author_handle, author_handle_type, author_entity_id
                    FROM consumed_articles
                    WHERE daemon_id = ? AND author_name LIKE ?
                    AND processing_status = 'completed'
                    ORDER BY consumed_at DESC
                    LIMIT ?
                    """,
                    (daemon_id, f"%{author_name}%", limit)
                )
            else:
                return []

            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "url": row[1],
                    "headline": row[2],
                    "source": row[3],
                    "category": row[4],
                    "summary": row[5],
                    "consumed_at": row[6],
                    "author_name": row[7],
                    "author_handle": row[8],
                    "author_handle_type": row[9],
                    "author_entity_id": row[10],
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Failed to get articles by author: {e}")
        return []


def list_article_sources(daemon_id: str, days_back: int = 30) -> List[Dict[str, Any]]:
    """
    List unique sources from consumed articles with counts.

    Args:
        daemon_id: Daemon ID
        days_back: How far back to look

    Returns:
        List of sources with article counts
    """
    cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()

    try:
        with get_db() as conn:
            cursor = conn.execute(
                """
                SELECT source, COUNT(*) as count
                FROM consumed_articles
                WHERE daemon_id = ? AND consumed_at > ? AND processing_status = 'completed'
                GROUP BY source
                ORDER BY count DESC
                """,
                (daemon_id, cutoff)
            )
            return [{"source": row[0], "count": row[1]} for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to list sources: {e}")
        return []


def get_article_stats(daemon_id: str) -> Dict[str, Any]:
    """
    Get statistics about consumed articles.

    Args:
        daemon_id: Daemon ID

    Returns:
        Stats including total count, by category, tokens used, etc.
    """
    try:
        with get_db() as conn:
            # Total count
            cursor = conn.execute(
                "SELECT COUNT(*) FROM consumed_articles WHERE daemon_id = ? AND processing_status = 'completed'",
                (daemon_id,)
            )
            total = cursor.fetchone()[0]

            # By category
            cursor = conn.execute(
                """
                SELECT category, COUNT(*) as count
                FROM consumed_articles
                WHERE daemon_id = ? AND processing_status = 'completed'
                GROUP BY category
                ORDER BY count DESC
                """,
                (daemon_id,)
            )
            by_category = {row[0] or "uncategorized": row[1] for row in cursor.fetchall()}

            # Total tokens
            cursor = conn.execute(
                "SELECT SUM(tokens_used) FROM consumed_articles WHERE daemon_id = ?",
                (daemon_id,)
            )
            total_tokens = cursor.fetchone()[0] or 0

            # Recent activity (last 7 days)
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            cursor = conn.execute(
                "SELECT COUNT(*) FROM consumed_articles WHERE daemon_id = ? AND consumed_at > ?",
                (daemon_id, week_ago)
            )
            last_week = cursor.fetchone()[0]

            return {
                "total_articles": total,
                "by_category": by_category,
                "total_tokens_used": total_tokens,
                "articles_last_7_days": last_week,
            }
    except Exception as e:
        logger.error(f"Failed to get article stats: {e}")
        return {}
