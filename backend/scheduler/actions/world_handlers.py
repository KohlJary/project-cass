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
