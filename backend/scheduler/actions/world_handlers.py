"""
World Action Handlers - Granular world-state capabilities.

These are standalone actions extracted from WorldStateRunner tools.
"""

import logging
import os
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


async def fetch_news_action(context: Dict[str, Any]) -> ActionResult:
    """
    Fetch recent news on a topic or general sources.

    Context params:
    - topic: str (optional) - Topic to search for
    - category: str (optional) - News category (general, technology, science, etc.)
    - limit: int (optional) - Number of articles (default 5)
    """
    import httpx

    topic = context.get("topic", "")
    category = context.get("category", "general")
    limit = context.get("limit", 5)

    # NewsAPI or similar
    news_api_key = os.getenv("NEWS_API_KEY")
    if not news_api_key:
        return ActionResult(
            success=False,
            message="NEWS_API_KEY not configured"
        )

    try:
        async with httpx.AsyncClient() as client:
            if topic:
                url = "https://newsapi.org/v2/everything"
                params = {
                    "q": topic,
                    "apiKey": news_api_key,
                    "pageSize": limit,
                    "sortBy": "publishedAt"
                }
            else:
                url = "https://newsapi.org/v2/top-headlines"
                params = {
                    "category": category,
                    "apiKey": news_api_key,
                    "pageSize": limit,
                    "country": "us"
                }

            response = await client.get(url, params=params, timeout=30)
            data = response.json()

            if data.get("status") != "ok":
                return ActionResult(
                    success=False,
                    message=f"News API error: {data.get('message', 'Unknown error')}"
                )

            articles = data.get("articles", [])
            news_items = [
                {
                    "title": a.get("title"),
                    "source": a.get("source", {}).get("name"),
                    "description": a.get("description"),
                    "url": a.get("url"),
                    "published": a.get("publishedAt")
                }
                for a in articles
            ]

            return ActionResult(
                success=True,
                message=f"Fetched {len(news_items)} news articles",
                data={
                    "topic": topic or category,
                    "articles": news_items,
                    "count": len(news_items)
                }
            )

    except Exception as e:
        logger.error(f"News fetch failed: {e}")
        return ActionResult(
            success=False,
            message=f"News fetch failed: {e}"
        )


async def fetch_weather_action(context: Dict[str, Any]) -> ActionResult:
    """
    Fetch current weather conditions.

    Context params:
    - location: str (optional) - City name (default from config)
    """
    import httpx

    location = context.get("location", os.getenv("WEATHER_LOCATION", "New York"))
    weather_api_key = os.getenv("WEATHER_API_KEY")

    if not weather_api_key:
        return ActionResult(
            success=False,
            message="WEATHER_API_KEY not configured"
        )

    try:
        async with httpx.AsyncClient() as client:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {
                "q": location,
                "appid": weather_api_key,
                "units": "imperial"
            }

            response = await client.get(url, params=params, timeout=30)
            data = response.json()

            if response.status_code != 200:
                return ActionResult(
                    success=False,
                    message=f"Weather API error: {data.get('message', 'Unknown error')}"
                )

            weather = {
                "location": data.get("name"),
                "country": data.get("sys", {}).get("country"),
                "temp_f": data.get("main", {}).get("temp"),
                "feels_like_f": data.get("main", {}).get("feels_like"),
                "humidity": data.get("main", {}).get("humidity"),
                "description": data.get("weather", [{}])[0].get("description"),
                "conditions": data.get("weather", [{}])[0].get("main")
            }

            return ActionResult(
                success=True,
                message=f"Weather for {weather['location']}: {weather['temp_f']}°F, {weather['description']}",
                data=weather
            )

    except Exception as e:
        logger.error(f"Weather fetch failed: {e}")
        return ActionResult(
            success=False,
            message=f"Weather fetch failed: {e}"
        )


async def search_events_action(context: Dict[str, Any]) -> ActionResult:
    """
    Search for current world events or trends.

    Context params:
    - query: str - What to search for
    - time_frame: str (optional) - today, this_week, this_month, recent
    """
    query = context.get("query")
    time_frame = context.get("time_frame", "recent")

    if not query:
        return ActionResult(
            success=False,
            message="query parameter required"
        )

    # Use web search for events
    try:
        from web_handlers import web_search_action

        # Modify query based on time frame
        time_suffix = {
            "today": "today",
            "this_week": "this week",
            "this_month": "this month",
            "recent": "recent"
        }.get(time_frame, "recent")

        search_query = f"{query} {time_suffix} news events"

        result = await web_search_action({
            "query": search_query,
            "limit": context.get("limit", 5),
            "definition": context.get("definition")
        })

        if result.success:
            result.data["original_query"] = query
            result.data["time_frame"] = time_frame

        return result

    except Exception as e:
        logger.error(f"Event search failed: {e}")
        return ActionResult(
            success=False,
            message=f"Event search failed: {e}"
        )


async def consume_articles_action(context: Dict[str, Any]) -> ActionResult:
    """
    Consume and analyze articles from available headlines.

    Uses the world consumption pipeline to:
    1. Get headlines from WorldStateSource cache
    2. Select articles and fetch full content
    3. Analyze with LLM (single_pass mode by default)
    4. Integrate insights into self-model
    5. Store summaries in memory

    Context params:
    - daemon_id: str (required) - Daemon ID
    - max_articles: int (optional) - Max articles to consume (default from config)
    - memory_core: MemoryCore (optional) - For ChromaDB storage
    - self_manager: SelfManager (optional) - For growth edge integration
    """
    daemon_id = context.get("daemon_id", "cass")
    max_articles = context.get("max_articles")
    memory_core = context.get("memory_core")
    self_manager = context.get("self_manager")

    # Also check managers dict for self_manager if not directly passed
    managers = context.get("managers", {})
    if not self_manager:
        self_manager = managers.get("self_manager")
    if not memory_core:
        memory_core = managers.get("memory_core") or managers.get("memory")

    try:
        from world.pipeline import run_consumption_pipeline, ConsumptionConfig, get_daily_budget
        from sources.world_state_source import WorldStateSource

        # Get headlines from world state source
        ws = WorldStateSource(daemon_id=daemon_id)
        rollups = ws.get_precomputed_rollups()
        headlines = rollups.get("recent_headlines", [])

        if not headlines:
            return ActionResult(
                success=True,
                message="No headlines available. Run world.refresh_and_consume or world.fetch_news first.",
                data={"headlines_available": 0}
            )

        # Check budget
        budget = get_daily_budget(daemon_id)
        config = ConsumptionConfig.from_env()

        if budget.articles_consumed >= config.max_articles_per_day:
            return ActionResult(
                success=True,
                message=f"Daily article budget exhausted ({budget.articles_consumed}/{config.max_articles_per_day})",
                data={"budget": {"consumed": budget.articles_consumed, "max": config.max_articles_per_day}}
            )

        if budget.tokens_used >= config.max_tokens_per_day:
            return ActionResult(
                success=True,
                message=f"Daily token budget exhausted ({budget.tokens_used}/{config.max_tokens_per_day})",
                data={"budget": {"consumed": budget.tokens_used, "max": config.max_tokens_per_day}}
            )

        # Override max articles if specified
        if max_articles:
            config.max_articles_per_cycle = min(max_articles, config.max_articles_per_day - budget.articles_consumed)

        # Run the pipeline
        result = run_consumption_pipeline(
            daemon_id=daemon_id,
            headlines=headlines,
            self_manager=self_manager,
            memory_core=memory_core,
            config=config,
        )

        return ActionResult(
            success=True,
            message=f"Consumed {result.articles_analyzed} articles, integrated {result.insights_integrated} insights",
            data={
                "headlines_available": len(headlines),
                "articles_fetched": result.articles_fetched,
                "articles_analyzed": result.articles_analyzed,
                "articles_failed": result.articles_failed,
                "total_tokens": result.total_tokens_used,
                "insights_integrated": result.insights_integrated,
                "details": result.details,
            }
        )

    except Exception as e:
        logger.error(f"Article consumption failed: {e}")
        import traceback
        traceback.print_exc()
        return ActionResult(
            success=False,
            message=f"Article consumption failed: {e}"
        )


async def refresh_and_consume_action(context: Dict[str, Any]) -> ActionResult:
    """
    Refresh world state (including headlines) then consume articles.

    This is a combined action that:
    1. Refreshes the world state source (weather, location, headlines)
    2. Runs article consumption on the fresh headlines

    Context params:
    - daemon_id: str (required) - Daemon ID
    - max_articles: int (optional) - Max articles to consume
    - memory_core: MemoryCore (optional) - For ChromaDB storage
    - self_manager: SelfManager (optional) - For growth edge integration
    """
    daemon_id = context.get("daemon_id", "cass")

    # Step 1: Refresh world state (which fetches headlines via NewsAPI)
    logger.info("Refreshing world state including headlines...")
    headlines_count = 0

    try:
        from sources.world_state_source import WorldStateSource
        ws = WorldStateSource(daemon_id=daemon_id)
        await ws.refresh_rollups()

        rollups = ws.get_precomputed_rollups()
        headlines = rollups.get("recent_headlines", [])
        headlines_count = len(headlines) if headlines else 0
        logger.info(f"World state refreshed with {headlines_count} headlines")

    except Exception as e:
        logger.warning(f"World state refresh failed: {e}")
        # Continue anyway - pipeline may have cached headlines

    # Step 2: Consume articles
    consume_result = await consume_articles_action(context)

    # Combine results
    combined_data = {
        "headlines_refreshed": headlines_count,
    }
    if consume_result.data:
        combined_data.update(consume_result.data)

    return ActionResult(
        success=consume_result.success,
        message=f"Refreshed {headlines_count} headlines, {consume_result.message}",
        data=combined_data
    )
