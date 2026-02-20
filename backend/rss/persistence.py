"""
RSS Feed Persistence

Database operations for RSS feeds and items.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from .models import RSSFeed, RSSItem, ParsedFeedItem

logger = logging.getLogger(__name__)


def _get_db():
    """Get database connection context manager."""
    from database import get_db
    return get_db()


# =============================================================================
# FEEDS
# =============================================================================

def save_feed(feed: RSSFeed) -> None:
    """Save or update an RSS feed."""
    with _get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO rss_feeds (
                id, daemon_id, url, title, description, category,
                check_interval_minutes, last_checked_at, last_item_at,
                error_count, last_error, active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            feed.id,
            feed.daemon_id,
            feed.url,
            feed.title,
            feed.description,
            feed.category,
            feed.check_interval_minutes,
            feed.last_checked_at,
            feed.last_item_at,
            feed.error_count,
            feed.last_error,
            1 if feed.active else 0,
            feed.created_at,
        ))


def get_feed(feed_id: str) -> Optional[RSSFeed]:
    """Get a feed by ID."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM rss_feeds WHERE id = ?", (feed_id,)
        ).fetchone()

        if not row:
            return None

        return _row_to_feed(row)


def get_feed_by_url(daemon_id: str, url: str) -> Optional[RSSFeed]:
    """Get a feed by URL for a specific daemon."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM rss_feeds WHERE daemon_id = ? AND url = ?",
            (daemon_id, url)
        ).fetchone()

        if not row:
            return None

        return _row_to_feed(row)


def list_feeds(daemon_id: str, active_only: bool = True) -> list[RSSFeed]:
    """List all feeds for a daemon."""
    with _get_db() as conn:
        if active_only:
            rows = conn.execute(
                "SELECT * FROM rss_feeds WHERE daemon_id = ? AND active = 1 ORDER BY title",
                (daemon_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM rss_feeds WHERE daemon_id = ? ORDER BY title",
                (daemon_id,)
            ).fetchall()

        return [_row_to_feed(row) for row in rows]


def list_feeds_due_for_check(daemon_id: str) -> list[RSSFeed]:
    """List feeds that are due for checking."""
    with _get_db() as conn:
        # Get all active feeds
        rows = conn.execute(
            "SELECT * FROM rss_feeds WHERE daemon_id = ? AND active = 1",
            (daemon_id,)
        ).fetchall()

        feeds = [_row_to_feed(row) for row in rows]

        # Filter to those due for check
        return [f for f in feeds if f.is_due_for_check()]


def update_feed_checked(
    feed_id: str,
    last_item_at: Optional[str] = None,
    error: Optional[str] = None,
    title: Optional[str] = None,
) -> None:
    """Update feed after checking it."""
    now = datetime.utcnow().isoformat()

    with _get_db() as conn:
        if error:
            # Increment error count
            conn.execute("""
                UPDATE rss_feeds
                SET last_checked_at = ?,
                    error_count = error_count + 1,
                    last_error = ?
                WHERE id = ?
            """, (now, error, feed_id))
        else:
            # Success - reset error count
            updates = ["last_checked_at = ?", "error_count = 0", "last_error = NULL"]
            params = [now]

            if last_item_at:
                updates.append("last_item_at = ?")
                params.append(last_item_at)

            if title:
                updates.append("title = ?")
                params.append(title)

            params.append(feed_id)

            conn.execute(
                f"UPDATE rss_feeds SET {', '.join(updates)} WHERE id = ?",
                params
            )


def deactivate_feed(feed_id: str) -> None:
    """Deactivate a feed (soft delete)."""
    with _get_db() as conn:
        conn.execute(
            "UPDATE rss_feeds SET active = 0 WHERE id = ?",
            (feed_id,)
        )


def delete_feed(feed_id: str) -> None:
    """Hard delete a feed and its items."""
    with _get_db() as conn:
        conn.execute("DELETE FROM rss_items WHERE feed_id = ?", (feed_id,))
        conn.execute("DELETE FROM rss_feeds WHERE id = ?", (feed_id,))


def _row_to_feed(row) -> RSSFeed:
    """Convert a database row to an RSSFeed."""
    return RSSFeed(
        id=row[0],
        daemon_id=row[1],
        url=row[2],
        title=row[3],
        description=row[4],
        category=row[5],
        check_interval_minutes=row[6] or 60,
        last_checked_at=row[7],
        last_item_at=row[8],
        error_count=row[9] or 0,
        last_error=row[10],
        active=bool(row[11]),
        created_at=row[12],
    )


# =============================================================================
# ITEMS
# =============================================================================

def save_item(item: RSSItem) -> None:
    """Save an RSS item."""
    with _get_db() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO rss_items (
                id, feed_id, guid, title, link, summary, author,
                published_at, seen_at, processed, processed_at, skip_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.id,
            item.feed_id,
            item.guid,
            item.title,
            item.link,
            item.summary,
            item.author,
            item.published_at,
            item.seen_at,
            1 if item.processed else 0,
            item.processed_at,
            item.skip_reason,
        ))


def store_new_items(feed_id: str, items: list[ParsedFeedItem]) -> int:
    """
    Store new items from a feed check, skipping duplicates.

    Returns number of new items stored.
    """
    now = datetime.utcnow().isoformat()
    stored = 0

    with _get_db() as conn:
        for parsed in items:
            item_id = str(uuid4())
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO rss_items (
                        id, feed_id, guid, title, link, summary, author,
                        published_at, seen_at, processed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    item_id,
                    feed_id,
                    parsed.guid,
                    parsed.title,
                    parsed.link,
                    parsed.summary,
                    parsed.author,
                    parsed.published_at,
                    now,
                ))
                # Check if row was inserted (not a duplicate)
                if conn.execute("SELECT changes()").fetchone()[0] > 0:
                    stored += 1
            except Exception as e:
                logger.warning(f"Failed to store item {parsed.guid}: {e}")

    return stored


def get_item(item_id: str) -> Optional[RSSItem]:
    """Get an item by ID."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM rss_items WHERE id = ?", (item_id,)
        ).fetchone()

        if not row:
            return None

        return _row_to_item(row)


def list_unprocessed_items(
    feed_id: Optional[str] = None,
    limit: int = 10,
    max_age_hours: int = 72,
) -> list[RSSItem]:
    """
    List unprocessed items, optionally filtered by feed.

    Args:
        feed_id: Optional feed ID to filter by
        limit: Maximum number of items to return
        max_age_hours: Don't return items older than this

    Returns:
        List of unprocessed items, oldest first
    """
    cutoff = datetime.utcnow()
    # Calculate cutoff time
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(hours=max_age_hours)).isoformat()

    with _get_db() as conn:
        if feed_id:
            rows = conn.execute("""
                SELECT * FROM rss_items
                WHERE feed_id = ? AND processed = 0 AND seen_at > ?
                ORDER BY published_at ASC, seen_at ASC
                LIMIT ?
            """, (feed_id, cutoff, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM rss_items
                WHERE processed = 0 AND seen_at > ?
                ORDER BY published_at ASC, seen_at ASC
                LIMIT ?
            """, (cutoff, limit)).fetchall()

        return [_row_to_item(row) for row in rows]


def count_unprocessed_items(daemon_id: Optional[str] = None) -> int:
    """Count total unprocessed items."""
    with _get_db() as conn:
        if daemon_id:
            row = conn.execute("""
                SELECT COUNT(*) FROM rss_items i
                JOIN rss_feeds f ON i.feed_id = f.id
                WHERE f.daemon_id = ? AND i.processed = 0
            """, (daemon_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM rss_items WHERE processed = 0"
            ).fetchone()

        return row[0] if row else 0


def mark_item_processed(item_id: str, skip_reason: Optional[str] = None) -> None:
    """Mark an item as processed."""
    now = datetime.utcnow().isoformat()

    with _get_db() as conn:
        conn.execute("""
            UPDATE rss_items
            SET processed = 1, processed_at = ?, skip_reason = ?
            WHERE id = ?
        """, (now, skip_reason, item_id))


def get_recent_items(
    daemon_id: str,
    limit: int = 20,
    processed_only: bool = False,
) -> list[RSSItem]:
    """Get recent items across all feeds for a daemon."""
    with _get_db() as conn:
        if processed_only:
            rows = conn.execute("""
                SELECT i.* FROM rss_items i
                JOIN rss_feeds f ON i.feed_id = f.id
                WHERE f.daemon_id = ? AND i.processed = 1
                ORDER BY i.processed_at DESC
                LIMIT ?
            """, (daemon_id, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT i.* FROM rss_items i
                JOIN rss_feeds f ON i.feed_id = f.id
                WHERE f.daemon_id = ?
                ORDER BY i.seen_at DESC
                LIMIT ?
            """, (daemon_id, limit)).fetchall()

        return [_row_to_item(row) for row in rows]


def _row_to_item(row) -> RSSItem:
    """Convert a database row to an RSSItem."""
    return RSSItem(
        id=row[0],
        feed_id=row[1],
        guid=row[2],
        title=row[3],
        link=row[4],
        summary=row[5],
        author=row[6],
        published_at=row[7],
        seen_at=row[8],
        processed=bool(row[9]),
        processed_at=row[10],
        skip_reason=row[11] if len(row) > 11 else None,
    )
