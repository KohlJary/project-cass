"""
RSS Feed Models

Data classes for RSS feeds and items.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RSSFeed:
    """An RSS feed subscription."""
    id: str
    daemon_id: str
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None  # "tech", "ai", "art", "news"
    check_interval_minutes: int = 60
    last_checked_at: Optional[str] = None
    last_item_at: Optional[str] = None
    error_count: int = 0
    last_error: Optional[str] = None
    active: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def is_due_for_check(self) -> bool:
        """Check if this feed is due for a refresh."""
        if not self.active:
            return False
        if not self.last_checked_at:
            return True

        last_check = datetime.fromisoformat(self.last_checked_at)
        now = datetime.utcnow()
        minutes_since = (now - last_check).total_seconds() / 60
        return minutes_since >= self.check_interval_minutes


@dataclass
class RSSItem:
    """An item (article) from an RSS feed."""
    id: str
    feed_id: str
    guid: str  # RSS guid for deduplication
    title: Optional[str] = None
    link: Optional[str] = None
    summary: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[str] = None
    seen_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    processed: bool = False
    processed_at: Optional[str] = None
    skip_reason: Optional[str] = None


@dataclass
class ParsedFeedItem:
    """A parsed item from feedparser, before storage."""
    guid: str
    title: Optional[str] = None
    link: Optional[str] = None
    summary: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[str] = None


@dataclass
class FeedCheckResult:
    """Result of checking a feed for new items."""
    feed_id: str
    feed_title: Optional[str]
    success: bool
    new_items: list[ParsedFeedItem] = field(default_factory=list)
    error: Optional[str] = None
    items_stored: int = 0
