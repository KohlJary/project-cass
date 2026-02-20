"""
RSS Feed Management API

Admin endpoints for managing RSS feed subscriptions.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from uuid import uuid4

router = APIRouter(prefix="/rss", tags=["admin-rss"])

# Module-level daemon_id reference
_daemon_id: str = "cass"


def init_rss_routes(daemon_id: str):
    """Initialize RSS routes with daemon ID."""
    global _daemon_id
    _daemon_id = daemon_id


# =============================================================================
# MODELS
# =============================================================================

class FeedCreate(BaseModel):
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    check_interval_minutes: int = 60


class FeedUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    check_interval_minutes: Optional[int] = None
    active: Optional[bool] = None


class FeedResponse(BaseModel):
    id: str
    url: str
    title: Optional[str]
    description: Optional[str]
    category: Optional[str]
    check_interval_minutes: int
    last_checked_at: Optional[str]
    last_item_at: Optional[str]
    error_count: int
    last_error: Optional[str]
    active: bool
    created_at: str


class ItemResponse(BaseModel):
    id: str
    feed_id: str
    guid: str
    title: Optional[str]
    link: Optional[str]
    summary: Optional[str]
    author: Optional[str]
    published_at: Optional[str]
    seen_at: str
    processed: bool
    processed_at: Optional[str]
    skip_reason: Optional[str]


class RSSStatusResponse(BaseModel):
    active_feeds: int
    total_feeds: int
    unprocessed_items: int
    error_feeds: int


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/status", response_model=RSSStatusResponse)
async def get_rss_status():
    """Get overall RSS monitoring status."""
    from rss import list_feeds, count_unprocessed_items

    active = list_feeds(_daemon_id, active_only=True)
    total = list_feeds(_daemon_id, active_only=False)
    unprocessed = count_unprocessed_items(_daemon_id)
    errors = len([f for f in active if f.error_count > 0])

    return RSSStatusResponse(
        active_feeds=len(active),
        total_feeds=len(total),
        unprocessed_items=unprocessed,
        error_feeds=errors,
    )


@router.get("/feeds", response_model=List[FeedResponse])
async def list_feeds_endpoint(
    active_only: bool = Query(True, description="Only show active feeds"),
    category: Optional[str] = Query(None, description="Filter by category"),
):
    """List all RSS feed subscriptions."""
    from rss import list_feeds

    feeds = list_feeds(_daemon_id, active_only=active_only)

    if category:
        feeds = [f for f in feeds if f.category == category]

    return [
        FeedResponse(
            id=f.id,
            url=f.url,
            title=f.title,
            description=f.description,
            category=f.category,
            check_interval_minutes=f.check_interval_minutes,
            last_checked_at=f.last_checked_at,
            last_item_at=f.last_item_at,
            error_count=f.error_count,
            last_error=f.last_error,
            active=f.active,
            created_at=f.created_at,
        )
        for f in feeds
    ]


@router.post("/feeds", response_model=FeedResponse)
async def create_feed(feed: FeedCreate):
    """Subscribe to a new RSS feed."""
    from rss import RSSFeed, save_feed, get_feed_by_url, parse_feed

    # Check for duplicate
    existing = get_feed_by_url(_daemon_id, feed.url)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Already subscribed to this feed: {existing.title or feed.url}"
        )

    # Validate the feed
    items, feed_title, error = parse_feed(feed.url)
    if error and not items:
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse feed: {error}"
        )

    # Create feed
    title = feed.title or feed_title or feed.url
    new_feed = RSSFeed(
        id=str(uuid4()),
        daemon_id=_daemon_id,
        url=feed.url,
        title=title,
        description=feed.description,
        category=feed.category,
        check_interval_minutes=feed.check_interval_minutes,
    )
    save_feed(new_feed)

    return FeedResponse(
        id=new_feed.id,
        url=new_feed.url,
        title=new_feed.title,
        description=new_feed.description,
        category=new_feed.category,
        check_interval_minutes=new_feed.check_interval_minutes,
        last_checked_at=new_feed.last_checked_at,
        last_item_at=new_feed.last_item_at,
        error_count=new_feed.error_count,
        last_error=new_feed.last_error,
        active=new_feed.active,
        created_at=new_feed.created_at,
    )


@router.get("/feeds/{feed_id}", response_model=FeedResponse)
async def get_feed(feed_id: str):
    """Get a specific feed by ID."""
    from rss import get_feed

    feed = get_feed(feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    return FeedResponse(
        id=feed.id,
        url=feed.url,
        title=feed.title,
        description=feed.description,
        category=feed.category,
        check_interval_minutes=feed.check_interval_minutes,
        last_checked_at=feed.last_checked_at,
        last_item_at=feed.last_item_at,
        error_count=feed.error_count,
        last_error=feed.last_error,
        active=feed.active,
        created_at=feed.created_at,
    )


@router.patch("/feeds/{feed_id}", response_model=FeedResponse)
async def update_feed(feed_id: str, update: FeedUpdate):
    """Update a feed's settings."""
    from rss import get_feed, save_feed

    feed = get_feed(feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    # Apply updates
    if update.title is not None:
        feed.title = update.title
    if update.description is not None:
        feed.description = update.description
    if update.category is not None:
        feed.category = update.category
    if update.check_interval_minutes is not None:
        feed.check_interval_minutes = update.check_interval_minutes
    if update.active is not None:
        feed.active = update.active

    save_feed(feed)

    return FeedResponse(
        id=feed.id,
        url=feed.url,
        title=feed.title,
        description=feed.description,
        category=feed.category,
        check_interval_minutes=feed.check_interval_minutes,
        last_checked_at=feed.last_checked_at,
        last_item_at=feed.last_item_at,
        error_count=feed.error_count,
        last_error=feed.last_error,
        active=feed.active,
        created_at=feed.created_at,
    )


@router.delete("/feeds/{feed_id}")
async def delete_feed(
    feed_id: str,
    hard: bool = Query(False, description="Permanently delete (vs deactivate)"),
):
    """Delete or deactivate a feed."""
    from rss import get_feed, deactivate_feed, delete_feed as hard_delete_feed

    feed = get_feed(feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    if hard:
        hard_delete_feed(feed_id)
        return {"message": f"Deleted feed: {feed.title or feed.url}"}
    else:
        deactivate_feed(feed_id)
        return {"message": f"Deactivated feed: {feed.title or feed.url}"}


@router.post("/feeds/{feed_id}/check")
async def check_feed(feed_id: str):
    """Manually trigger a feed check."""
    from rss import get_feed, parse_feed, store_new_items, update_feed_checked

    feed = get_feed(feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    items, feed_title, error = parse_feed(feed.url)

    if error:
        update_feed_checked(feed_id, error=error)
        raise HTTPException(status_code=400, detail=f"Feed check failed: {error}")

    # Store new items
    new_count = store_new_items(feed_id, items)

    # Update feed metadata
    last_item_at = None
    if items and items[0].published_at:
        last_item_at = items[0].published_at

    update_feed_checked(
        feed_id,
        last_item_at=last_item_at,
        title=feed_title if feed_title and not feed.title else None,
    )

    return {
        "message": f"Checked feed, found {new_count} new item(s)",
        "items_found": len(items),
        "new_items": new_count,
    }


@router.get("/items", response_model=List[ItemResponse])
async def list_items(
    feed_id: Optional[str] = Query(None, description="Filter by feed"),
    processed: Optional[bool] = Query(None, description="Filter by processed status"),
    limit: int = Query(50, le=200, description="Max items to return"),
):
    """List RSS items with optional filters."""
    from rss import get_recent_items, list_unprocessed_items

    if processed is False:
        # Get unprocessed items
        items = list_unprocessed_items(feed_id=feed_id, limit=limit)
    else:
        # Get recent items (all or processed only)
        items = get_recent_items(
            _daemon_id,
            limit=limit,
            processed_only=(processed is True),
        )
        # Filter by feed_id if specified
        if feed_id:
            items = [i for i in items if i.feed_id == feed_id]

    return [
        ItemResponse(
            id=i.id,
            feed_id=i.feed_id,
            guid=i.guid,
            title=i.title,
            link=i.link,
            summary=i.summary[:300] + "..." if i.summary and len(i.summary) > 300 else i.summary,
            author=i.author,
            published_at=i.published_at,
            seen_at=i.seen_at,
            processed=i.processed,
            processed_at=i.processed_at,
            skip_reason=i.skip_reason,
        )
        for i in items
    ]


@router.post("/items/{item_id}/skip")
async def skip_item(item_id: str, reason: str = Query("manually_skipped")):
    """Mark an item as processed/skipped."""
    from rss import get_item, mark_item_processed

    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    mark_item_processed(item_id, skip_reason=reason)

    return {"message": f"Skipped item: {item.title}"}


@router.post("/check-all")
async def check_all_feeds():
    """Check all feeds due for refresh."""
    from rss import list_feeds_due_for_check, parse_feed, store_new_items, update_feed_checked

    feeds = list_feeds_due_for_check(_daemon_id)

    if not feeds:
        return {"message": "No feeds due for checking", "feeds_checked": 0, "new_items": 0}

    total_new = 0
    results = []

    for feed in feeds:
        items, feed_title, error = parse_feed(feed.url)

        if error:
            update_feed_checked(feed.id, error=error)
            results.append({
                "feed_id": feed.id,
                "title": feed.title,
                "error": error,
            })
            continue

        new_count = store_new_items(feed.id, items)
        total_new += new_count

        last_item_at = None
        if items and items[0].published_at:
            last_item_at = items[0].published_at

        update_feed_checked(
            feed.id,
            last_item_at=last_item_at,
            title=feed_title if feed_title and not feed.title else None,
        )

        results.append({
            "feed_id": feed.id,
            "title": feed.title or feed_title,
            "items_found": len(items),
            "new_items": new_count,
        })

    return {
        "message": f"Checked {len(feeds)} feed(s), found {total_new} new item(s)",
        "feeds_checked": len(feeds),
        "new_items": total_new,
        "results": results,
    }
