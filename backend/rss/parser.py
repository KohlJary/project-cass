"""
RSS Feed Parser

Parses RSS and Atom feeds using feedparser.
"""

import logging
from datetime import datetime
from typing import Optional
from time import mktime

from .models import ParsedFeedItem

logger = logging.getLogger(__name__)


def parse_feed(url: str, timeout: int = 30) -> tuple[list[ParsedFeedItem], Optional[str], Optional[str]]:
    """
    Parse an RSS/Atom feed from a URL.

    Args:
        url: The feed URL
        timeout: Request timeout in seconds

    Returns:
        Tuple of (items, feed_title, error_message)
        If error_message is set, items will be empty.
    """
    try:
        import feedparser
    except ImportError:
        return [], None, "feedparser not installed"

    try:
        # Parse the feed
        feed = feedparser.parse(url, request_headers={
            'User-Agent': 'Cass-RSS-Monitor/1.0 (+https://github.com/KohlJary/project-cass)'
        })

        # Check for errors
        if feed.bozo and feed.bozo_exception:
            # feedparser sets bozo=True for any parsing issues
            # Some are recoverable (e.g., encoding issues), some aren't
            exception = feed.bozo_exception
            if hasattr(exception, 'getcode') and exception.getcode() >= 400:
                return [], None, f"HTTP error: {exception.getcode()}"
            # For other bozo exceptions, try to continue if we have entries
            if not feed.entries:
                return [], None, f"Parse error: {str(exception)[:100]}"
            logger.warning(f"Feed {url} had parse warning: {exception}")

        # Extract feed title
        feed_title = feed.feed.get('title') if hasattr(feed, 'feed') else None

        # Parse entries
        items = []
        for entry in feed.entries:
            item = _parse_entry(entry)
            if item:
                items.append(item)

        return items, feed_title, None

    except Exception as e:
        logger.error(f"Error parsing feed {url}: {e}")
        return [], None, str(e)[:200]


def _parse_entry(entry: dict) -> Optional[ParsedFeedItem]:
    """Parse a single feed entry into a ParsedFeedItem."""
    # Get GUID - use id, guid, or link as fallback
    guid = entry.get('id') or entry.get('guid') or entry.get('link')
    if not guid:
        return None

    # Get published date
    published_at = None
    if 'published_parsed' in entry and entry.published_parsed:
        try:
            published_at = datetime.fromtimestamp(mktime(entry.published_parsed)).isoformat()
        except Exception:
            pass
    elif 'updated_parsed' in entry and entry.updated_parsed:
        try:
            published_at = datetime.fromtimestamp(mktime(entry.updated_parsed)).isoformat()
        except Exception:
            pass

    # Get summary/description
    summary = None
    if 'summary' in entry:
        summary = entry.summary
    elif 'description' in entry:
        summary = entry.description

    # Clean up summary (remove HTML, truncate)
    if summary:
        summary = _clean_html(summary)
        if len(summary) > 1000:
            summary = summary[:997] + "..."

    # Get author
    author = entry.get('author')
    if not author and 'authors' in entry and entry.authors:
        author = entry.authors[0].get('name')

    return ParsedFeedItem(
        guid=guid,
        title=entry.get('title'),
        link=entry.get('link'),
        summary=summary,
        author=author,
        published_at=published_at,
    )


def _clean_html(text: str) -> str:
    """Remove HTML tags and clean up text."""
    import re

    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', text)

    # Decode common HTML entities
    clean = clean.replace('&nbsp;', ' ')
    clean = clean.replace('&amp;', '&')
    clean = clean.replace('&lt;', '<')
    clean = clean.replace('&gt;', '>')
    clean = clean.replace('&quot;', '"')
    clean = clean.replace('&#39;', "'")

    # Normalize whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()

    return clean
