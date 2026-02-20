"""
RSS Feed Monitoring

Allows Cass to subscribe to and monitor RSS feeds,
triggering news analysis workflows when new articles arrive.
"""

from .models import RSSFeed, RSSItem, ParsedFeedItem, FeedCheckResult
from .parser import parse_feed
from .persistence import (
    # Feeds
    save_feed,
    get_feed,
    get_feed_by_url,
    list_feeds,
    list_feeds_due_for_check,
    update_feed_checked,
    deactivate_feed,
    delete_feed,
    # Items
    save_item,
    store_new_items,
    get_item,
    list_unprocessed_items,
    count_unprocessed_items,
    mark_item_processed,
    get_recent_items,
)
from .triage import (
    TriageDecision,
    TriageResult,
    prefilter,
    llm_triage,
    triage_item,
    triage_batch,
    content_hash,
)

__all__ = [
    # Models
    "RSSFeed",
    "RSSItem",
    "ParsedFeedItem",
    "FeedCheckResult",
    # Parser
    "parse_feed",
    # Persistence - Feeds
    "save_feed",
    "get_feed",
    "get_feed_by_url",
    "list_feeds",
    "list_feeds_due_for_check",
    "update_feed_checked",
    "deactivate_feed",
    "delete_feed",
    # Persistence - Items
    "save_item",
    "store_new_items",
    "get_item",
    "list_unprocessed_items",
    "count_unprocessed_items",
    "mark_item_processed",
    "get_recent_items",
    # Triage
    "TriageDecision",
    "TriageResult",
    "prefilter",
    "llm_triage",
    "triage_item",
    "triage_batch",
    "content_hash",
]
