"""
Web Action Handlers - Web search and URL fetching.

Standalone actions for web research capabilities.
"""

import logging
import os
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


async def web_search_action(context: Dict[str, Any]) -> ActionResult:
    """
    Search the web for information.

    Context params:
    - query: str - Search query
    - limit: int (optional) - Number of results (default 5)
    """
    import httpx

    query = context.get("query")
    limit = context.get("limit", 5)

    if not query:
        return ActionResult(
            success=False,
            message="query parameter required"
        )

    # Try Brave Search API first, fall back to others
    brave_api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    serper_api_key = os.getenv("SERPER_API_KEY")

    try:
        async with httpx.AsyncClient() as client:
            if brave_api_key:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": brave_api_key},
                    params={"q": query, "count": limit},
                    timeout=30
                )
                data = response.json()
                results = [
                    {
                        "title": r.get("title"),
                        "url": r.get("url"),
                        "description": r.get("description")
                    }
                    for r in data.get("web", {}).get("results", [])[:limit]
                ]

            elif serper_api_key:
                response = await client.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": serper_api_key},
                    json={"q": query, "num": limit},
                    timeout=30
                )
                data = response.json()
                results = [
                    {
                        "title": r.get("title"),
                        "url": r.get("link"),
                        "description": r.get("snippet")
                    }
                    for r in data.get("organic", [])[:limit]
                ]

            else:
                return ActionResult(
                    success=False,
                    message="No search API configured (BRAVE_SEARCH_API_KEY or SERPER_API_KEY)"
                )

            return ActionResult(
                success=True,
                message=f"Found {len(results)} results for '{query}'",
                data={
                    "query": query,
                    "results": results,
                    "count": len(results)
                }
            )

    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return ActionResult(
            success=False,
            message=f"Web search failed: {e}"
        )


async def fetch_url_action(context: Dict[str, Any]) -> ActionResult:
    """
    Fetch and extract content from a URL.

    Context params:
    - url: str - URL to fetch
    - extract_text: bool (optional) - Extract main text content (default True)
    """
    import httpx

    url = context.get("url")
    extract_text = context.get("extract_text", True)

    if not url:
        return ActionResult(
            success=False,
            message="url parameter required"
        )

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; CassBot/1.0)"},
                timeout=30
            )

            if response.status_code != 200:
                return ActionResult(
                    success=False,
                    message=f"Failed to fetch URL: HTTP {response.status_code}"
                )

            content_type = response.headers.get("content-type", "")
            raw_content = response.text

            if extract_text and "text/html" in content_type:
                # Simple text extraction
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(raw_content, "html.parser")

                    # Remove script and style elements
                    for element in soup(["script", "style", "nav", "footer", "header"]):
                        element.decompose()

                    # Get text
                    text = soup.get_text(separator="\n", strip=True)

                    # Get title
                    title = soup.title.string if soup.title else None

                    # Truncate if too long
                    if len(text) > 10000:
                        text = text[:10000] + "..."

                    return ActionResult(
                        success=True,
                        message=f"Fetched content from {url}",
                        data={
                            "url": url,
                            "title": title,
                            "text": text,
                            "content_type": content_type,
                            "length": len(text)
                        }
                    )

                except ImportError:
                    # BeautifulSoup not available, return raw
                    pass

            # Return raw content (truncated)
            content = raw_content[:10000] if len(raw_content) > 10000 else raw_content

            return ActionResult(
                success=True,
                message=f"Fetched content from {url}",
                data={
                    "url": url,
                    "content": content,
                    "content_type": content_type,
                    "length": len(raw_content)
                }
            )

    except Exception as e:
        logger.error(f"URL fetch failed: {e}")
        return ActionResult(
            success=False,
            message=f"URL fetch failed: {e}"
        )
