"""
RSS Feed Action Handlers - Autonomous RSS feed monitoring.

Enables Cass to:
- Subscribe to and manage RSS feeds
- Poll feeds for new articles
- Process new items through the news workflow
- Maintain awareness of curated information sources
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from . import ActionResult

logger = logging.getLogger(__name__)


async def add_feed_action(context: Dict[str, Any]) -> ActionResult:
    """
    Subscribe to a new RSS feed.

    Context:
    - url: Feed URL (required)
    - title: Optional title (will be fetched from feed if not provided)
    - description: Optional description
    - category: Feed category (tech, ai, art, news, etc.)
    - check_interval_minutes: How often to check (default 60)
    - daemon_id: Required
    """
    from rss import (
        RSSFeed, save_feed, get_feed_by_url, parse_feed
    )

    url = context.get("url")
    daemon_id = context.get("daemon_id")

    if not url:
        return ActionResult(
            success=False,
            message="No URL provided for feed subscription"
        )

    if not daemon_id:
        return ActionResult(
            success=False,
            message="No daemon_id in context"
        )

    # Check if already subscribed
    existing = get_feed_by_url(daemon_id, url)
    if existing:
        return ActionResult(
            success=False,
            message=f"Already subscribed to this feed: {existing.title or url}",
            data={"feed_id": existing.id, "already_subscribed": True}
        )

    # Try to parse the feed to validate and get title
    items, feed_title, error = parse_feed(url)
    if error and not items:
        return ActionResult(
            success=False,
            message=f"Failed to parse feed: {error}"
        )

    # Create the feed
    title = context.get("title") or feed_title or url
    feed = RSSFeed(
        id=str(uuid4()),
        daemon_id=daemon_id,
        url=url,
        title=title,
        description=context.get("description"),
        category=context.get("category"),
        check_interval_minutes=context.get("check_interval_minutes", 60),
    )

    save_feed(feed)

    logger.info(f"Subscribed to RSS feed: {title} ({url})")

    return ActionResult(
        success=True,
        message=f"Subscribed to feed: {title}",
        data={
            "feed_id": feed.id,
            "title": title,
            "url": url,
            "initial_items": len(items),
        }
    )


async def remove_feed_action(context: Dict[str, Any]) -> ActionResult:
    """
    Unsubscribe from an RSS feed.

    Context:
    - feed_id: Feed ID to remove (optional if url provided)
    - url: Feed URL to remove (optional if feed_id provided)
    - daemon_id: Required if using url
    - hard_delete: If True, delete feed and all items. Default False (deactivate).
    """
    from rss import get_feed, get_feed_by_url, deactivate_feed, delete_feed

    feed_id = context.get("feed_id")
    url = context.get("url")
    daemon_id = context.get("daemon_id")
    hard = context.get("hard_delete", False)

    feed = None
    if feed_id:
        feed = get_feed(feed_id)
    elif url and daemon_id:
        feed = get_feed_by_url(daemon_id, url)

    if not feed:
        return ActionResult(
            success=False,
            message="Feed not found"
        )

    if hard:
        delete_feed(feed.id)
        message = f"Deleted feed: {feed.title or feed.url}"
    else:
        deactivate_feed(feed.id)
        message = f"Unsubscribed from feed: {feed.title or feed.url}"

    logger.info(message)

    return ActionResult(
        success=True,
        message=message,
        data={"feed_id": feed.id, "title": feed.title, "deleted": hard}
    )


async def list_feeds_action(context: Dict[str, Any]) -> ActionResult:
    """
    List current RSS subscriptions.

    Context:
    - daemon_id: Required
    - active_only: Whether to only list active feeds (default True)
    - category: Optional category filter
    """
    from rss import list_feeds

    daemon_id = context.get("daemon_id")
    if not daemon_id:
        return ActionResult(
            success=False,
            message="No daemon_id in context"
        )

    active_only = context.get("active_only", True)
    category_filter = context.get("category")

    feeds = list_feeds(daemon_id, active_only=active_only)

    # Apply category filter if specified
    if category_filter:
        feeds = [f for f in feeds if f.category == category_filter]

    feed_data = []
    for feed in feeds:
        feed_data.append({
            "id": feed.id,
            "title": feed.title,
            "url": feed.url,
            "category": feed.category,
            "check_interval_minutes": feed.check_interval_minutes,
            "last_checked_at": feed.last_checked_at,
            "error_count": feed.error_count,
            "active": feed.active,
        })

    return ActionResult(
        success=True,
        message=f"Found {len(feeds)} feed(s)",
        data={"feeds": feed_data, "count": len(feeds)}
    )


async def check_feeds_action(context: Dict[str, Any]) -> ActionResult:
    """
    Check all feeds due for polling and store new items.

    Context:
    - daemon_id: Required
    - force: If True, check all active feeds regardless of schedule (default False)
    """
    from rss import (
        list_feeds, list_feeds_due_for_check, parse_feed,
        store_new_items, update_feed_checked
    )

    daemon_id = context.get("daemon_id")
    if not daemon_id:
        return ActionResult(
            success=False,
            message="No daemon_id in context"
        )

    force = context.get("force", False)

    # Get feeds to check
    if force:
        feeds = list_feeds(daemon_id, active_only=True)
    else:
        feeds = list_feeds_due_for_check(daemon_id)

    if not feeds:
        return ActionResult(
            success=True,
            message="No feeds due for checking",
            data={"feeds_checked": 0, "new_items": 0}
        )

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

        # Store new items
        new_count = store_new_items(feed.id, items)
        total_new += new_count

        # Update feed metadata
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

    logger.info(f"Checked {len(feeds)} feeds, found {total_new} new items")

    return ActionResult(
        success=True,
        message=f"Checked {len(feeds)} feed(s), found {total_new} new item(s)",
        data={
            "feeds_checked": len(feeds),
            "new_items": total_new,
            "results": results,
        }
    )


async def get_status_action(context: Dict[str, Any]) -> ActionResult:
    """
    Get RSS monitoring status - feed counts, unprocessed items, etc.

    Context:
    - daemon_id: Required
    """
    from rss import (
        list_feeds, count_unprocessed_items, list_unprocessed_items
    )

    daemon_id = context.get("daemon_id")
    if not daemon_id:
        return ActionResult(
            success=False,
            message="No daemon_id in context"
        )

    # Get feed counts
    active_feeds = list_feeds(daemon_id, active_only=True)
    all_feeds = list_feeds(daemon_id, active_only=False)

    # Get unprocessed count
    unprocessed_count = count_unprocessed_items(daemon_id)

    # Get preview of unprocessed items
    unprocessed_preview = []
    if unprocessed_count > 0:
        items = list_unprocessed_items(limit=5)
        for item in items:
            unprocessed_preview.append({
                "id": item.id,
                "title": item.title,
                "link": item.link,
                "published_at": item.published_at,
            })

    # Check for feeds with errors
    error_feeds = [f for f in active_feeds if f.error_count > 0]

    return ActionResult(
        success=True,
        message=f"{len(active_feeds)} active feeds, {unprocessed_count} unprocessed items",
        data={
            "active_feeds": len(active_feeds),
            "total_feeds": len(all_feeds),
            "inactive_feeds": len(all_feeds) - len(active_feeds),
            "unprocessed_items": unprocessed_count,
            "error_feeds": len(error_feeds),
            "unprocessed_preview": unprocessed_preview,
            # Flat values for spell access
            "has_unprocessed": unprocessed_count > 0,
            "next_item_id": unprocessed_preview[0]["id"] if unprocessed_preview else None,
            "next_item_title": unprocessed_preview[0]["title"] if unprocessed_preview else None,
        }
    )


async def triage_items_action(context: Dict[str, Any]) -> ActionResult:
    """
    Run triage on unprocessed RSS items to filter before full processing.

    Uses two-stage triage:
    1. Pre-filter: Fast rule-based checks (length, duplicates, blocklist)
    2. LLM triage: Local model evaluates relevance

    Context:
    - daemon_id: Required
    - limit: Max items to triage (default 20)
    - skip_llm: If True, only run pre-filter (default False)
    - feed_id: Optional - only triage items from this feed
    """
    from rss import (
        list_unprocessed_items, mark_item_processed, get_feed,
        triage_item, TriageDecision
    )

    daemon_id = context.get("daemon_id")
    if not daemon_id:
        return ActionResult(
            success=False,
            message="No daemon_id in context"
        )

    limit = context.get("limit", 20)
    feed_id = context.get("feed_id")
    skip_llm = context.get("skip_llm", False)

    # Get unprocessed items
    items = list_unprocessed_items(feed_id=feed_id, limit=limit)

    if not items:
        return ActionResult(
            success=True,
            message="No items to triage",
            data={"triaged": 0}
        )

    results = {
        "process": [],
        "skip": [],
        "defer": [],
        "duplicate": [],
    }
    seen_hashes: set = set()

    for item in items:
        feed = get_feed(item.feed_id) if item.feed_id else None
        source_name = feed.title if feed else None

        triage_result = await triage_item(
            item,
            source_name=source_name,
            seen_hashes=seen_hashes,
            skip_llm=skip_llm,
        )

        entry = {
            "id": item.id,
            "title": item.title,
            "reason": triage_result.reason,
            "relevance": triage_result.relevance_score,
            "topics": triage_result.topics,
        }

        if triage_result.decision == TriageDecision.PROCESS:
            results["process"].append(entry)
            # Add to seen_hashes to catch duplicates in this batch
            from rss import content_hash
            seen_hashes.add(content_hash(item.title or "", item.summary or ""))
        elif triage_result.decision == TriageDecision.SKIP:
            results["skip"].append(entry)
            # Mark as processed with skip reason
            mark_item_processed(item.id, skip_reason=f"triage_skip: {triage_result.reason[:80]}")
        elif triage_result.decision == TriageDecision.DUPLICATE:
            results["duplicate"].append(entry)
            mark_item_processed(item.id, skip_reason="triage_duplicate")
        else:  # DEFER
            results["defer"].append(entry)
            # Leave for later - don't mark as processed

    logger.info(
        f"Triaged {len(items)} items: "
        f"{len(results['process'])} process, {len(results['skip'])} skip, "
        f"{len(results['defer'])} defer, {len(results['duplicate'])} duplicate"
    )

    return ActionResult(
        success=True,
        message=(
            f"Triaged {len(items)} items: "
            f"{len(results['process'])} to process, {len(results['skip'])} skipped"
        ),
        data={
            "triaged": len(items),
            "to_process": len(results["process"]),
            "skip_count": len(results["skip"]),
            "deferred": len(results["defer"]),
            "duplicates": len(results["duplicate"]),
            "process_items": results["process"],
            "skip_items": results["skip"],
        }
    )


async def process_items_action(context: Dict[str, Any]) -> ActionResult:
    """
    Process unprocessed RSS items through news analysis workflow.

    Context:
    - daemon_id: Required
    - limit: Max items to process (default 5)
    - feed_id: Optional - only process items from this feed
    - use_triage: Run triage before processing (default True)
    - skip_llm_triage: If True, only use pre-filter for triage (default False)
    """
    from rss import (
        list_unprocessed_items, mark_item_processed, get_feed,
        triage_item, TriageDecision
    )

    daemon_id = context.get("daemon_id")
    if not daemon_id:
        return ActionResult(
            success=False,
            message="No daemon_id in context"
        )

    limit = context.get("limit", 5)
    feed_id = context.get("feed_id")
    use_triage = context.get("use_triage", True)
    skip_llm_triage = context.get("skip_llm_triage", False)

    # Get more items than limit if triaging (some will be filtered)
    fetch_limit = limit * 3 if use_triage else limit
    items = list_unprocessed_items(feed_id=feed_id, limit=fetch_limit)

    if not items:
        return ActionResult(
            success=True,
            message="No unprocessed items to process",
            data={"processed": 0}
        )

    # Import news consumption machinery
    try:
        from world.article_consumer import ArticleConsumer
        from world.content_analyzer import ContentAnalyzer
        from world.integrator import InsightIntegrator
        from world.pipeline import ConsumptionConfig
    except ImportError as e:
        # Fallback - mark as processed with skip reason
        logger.warning(f"World consumption imports failed: {e}")
        for item in items:
            mark_item_processed(item.id, skip_reason="news_handler_unavailable")
        return ActionResult(
            success=False,
            message=f"News consumption handler not available: {e}",
            data={"skip_count": len(items)}
        )

    # Initialize consumption components
    config = ConsumptionConfig.from_env()
    consumer = ArticleConsumer(daemon_id)
    analyzer = ContentAnalyzer(
        daemon_id=daemon_id,
        reading_mode=config.reading_mode,
        model=config.analysis_model,
    )
    integrator = InsightIntegrator(daemon_id, config.min_confidence)

    processed = []
    skipped = []
    triaged_out = 0
    seen_hashes: set = set()

    for item in items:
        # Stop if we've processed enough
        if len(processed) >= limit:
            break

        # Get feed info for context
        feed = get_feed(item.feed_id) if item.feed_id else None
        source_name = feed.title if feed else "RSS"

        # Triage if enabled
        if use_triage:
            triage_result = await triage_item(
                item,
                source_name=source_name,
                seen_hashes=seen_hashes,
                skip_llm=skip_llm_triage,
            )

            if triage_result.decision == TriageDecision.SKIP:
                mark_item_processed(item.id, skip_reason=f"triage: {triage_result.reason[:80]}")
                triaged_out += 1
                continue
            elif triage_result.decision == TriageDecision.DUPLICATE:
                mark_item_processed(item.id, skip_reason="triage_duplicate")
                triaged_out += 1
                continue
            elif triage_result.decision == TriageDecision.DEFER:
                # Skip but don't mark - will process later
                continue

            # Add to seen hashes
            from rss import content_hash
            seen_hashes.add(content_hash(item.title or "", item.summary or ""))

        try:
            # Convert RSS item to headline format for consumer
            headline = {
                "title": item.title,
                "url": item.link,
                "source": source_name,
                "summary": item.summary,
                "author": item.author,
                "published_at": item.published_at,
            }

            # Consume the article (fetches full content)
            articles = consumer.consume_headlines([headline], max_articles=1)

            if not articles or not articles[0].full_content:
                mark_item_processed(item.id, skip_reason="failed_to_fetch_content")
                skipped.append({
                    "id": item.id,
                    "title": item.title,
                    "reason": "Failed to fetch article content",
                })
                continue

            article = articles[0]

            # Analyze the article
            insights = analyzer.analyze(article)

            # Update article with results
            article.summary = insights.summary
            article.observations = insights.observations
            article.questions = insights.questions
            article.opinions = insights.opinions
            article.growth_edges = insights.growth_edges
            article.tokens_used = insights.tokens_used

            # Integrate insights
            integration = integrator.integrate(article, insights)

            # Save the article
            consumer._save_article(article)

            mark_item_processed(item.id)
            processed.append({
                "id": item.id,
                "title": item.title,
                "observations": len(insights.observations),
                "questions": len(insights.questions),
                "tokens": insights.tokens_used,
            })

        except Exception as e:
            logger.warning(f"Error processing RSS item {item.id}: {e}")
            import traceback
            traceback.print_exc()
            mark_item_processed(item.id, skip_reason=str(e)[:100])
            skipped.append({
                "id": item.id,
                "title": item.title,
                "reason": str(e)[:100],
            })

    logger.info(
        f"Processed {len(processed)} RSS items, "
        f"skipped {len(skipped)}, triaged out {triaged_out}"
    )

    return ActionResult(
        success=True,
        message=f"Processed {len(processed)} item(s), skipped {len(skipped)}, triaged out {triaged_out}",
        data={
            "processed": len(processed),
            "skip_count": len(skipped),
            "triaged_out": triaged_out,
            "processed_items": processed,
            "skip_items": skipped,
        }
    )


async def check_and_process_action(context: Dict[str, Any]) -> ActionResult:
    """
    Combined action: check feeds for new items, then process them.

    This is the primary autonomous action - called periodically to
    maintain awareness of subscribed information sources.

    Context:
    - daemon_id: Required
    - process_limit: Max items to process (default 10)
    """
    daemon_id = context.get("daemon_id")
    if not daemon_id:
        return ActionResult(
            success=False,
            message="No daemon_id in context"
        )

    # First, check feeds
    check_result = await check_feeds_action(context)

    if not check_result.success:
        return check_result

    new_items = check_result.data.get("new_items", 0)

    # Then process any unprocessed items
    process_context = {
        **context,
        "limit": context.get("process_limit", 10),
    }
    process_result = await process_items_action(process_context)

    # Combine results
    feeds_checked = check_result.data.get("feeds_checked", 0)
    processed = process_result.data.get("processed", 0)

    return ActionResult(
        success=True,
        message=f"Checked {feeds_checked} feed(s), {new_items} new, processed {processed}",
        data={
            "feeds_checked": feeds_checked,
            "new_items_found": new_items,
            "items_processed": processed,
            "check_results": check_result.data.get("results", []),
            "process_results": process_result.data,
        }
    )


async def get_recent_items_action(context: Dict[str, Any]) -> ActionResult:
    """
    Get recent RSS items (for review or display).

    Context:
    - daemon_id: Required
    - limit: Max items to return (default 20)
    - processed_only: If True, only show processed items (default False)
    """
    from rss import get_recent_items

    daemon_id = context.get("daemon_id")
    if not daemon_id:
        return ActionResult(
            success=False,
            message="No daemon_id in context"
        )

    limit = context.get("limit", 20)
    processed_only = context.get("processed_only", False)

    items = get_recent_items(daemon_id, limit=limit, processed_only=processed_only)

    item_data = []
    for item in items:
        item_data.append({
            "id": item.id,
            "feed_id": item.feed_id,
            "title": item.title,
            "link": item.link,
            "summary": item.summary[:200] + "..." if item.summary and len(item.summary) > 200 else item.summary,
            "author": item.author,
            "published_at": item.published_at,
            "seen_at": item.seen_at,
            "processed": item.processed,
            "processed_at": item.processed_at,
        })

    return ActionResult(
        success=True,
        message=f"Found {len(items)} recent item(s)",
        data={"items": item_data, "count": len(items)}
    )
