"""
One web-search interface for research (#60).

Before this, research searched the web three ways:

* Tavily (TAVILY_API_KEY): ResearchManager.web_search, used by chat's
  web_search tool, research sessions (both session runners) and the
  research.* session tools.
* DuckDuckGo's keyless instant-answer API: the wiki research queue
  (red_link / question tasks), the wiki "research this page" route
  (PageResearcher) and the curiosity runner.
* Brave (BRAVE_SEARCH_API_KEY), else Serper (SERPER_API_KEY): the
  `web.search` scheduler action.

Now every one of those asks `web_search()` here. Backends are tried in the
order RESEARCH_SEARCH_ORDER gives (default: tavily, brave, serper,
duckduckgo), and a backend is only in the list when it is configured: the
keyed ones need their key in the environment, DuckDuckGo needs nothing. The
first backend that answers successfully wins; the others are fallbacks.

Tests swap the backends with `use_backends([...])` so nothing reaches the
network.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Protocol

logger = logging.getLogger(__name__)

DEFAULT_ORDER = ("tavily", "brave", "serper", "duckduckgo")
ORDER_ENV = "RESEARCH_SEARCH_ORDER"


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    score: Optional[float] = None
    source: str = ""          # site / provider label, when the backend gives one


@dataclass
class SearchResponse:
    success: bool
    backend: str
    results: List[SearchHit]
    answer: Optional[str] = None
    error: Optional[str] = None


class SearchBackend(Protocol):
    name: str

    async def search(self, query: str, num_results: int = 10, **opts) -> SearchResponse: ...


def _http_client(timeout: float):
    import httpx
    return httpx.AsyncClient(timeout=timeout)


class TavilyBackend:
    name = "tavily"
    env_key = "TAVILY_API_KEY"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, num_results: int = 10, search_depth: str = "basic",
                     include_domains=None, exclude_domains=None, **_) -> SearchResponse:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": min(num_results, 20),
            "search_depth": search_depth,
            "include_answer": True,
        }
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains
        async with _http_client(30.0) as client:
            response = await client.post("https://api.tavily.com/search", json=payload)
        if response.status_code != 200:
            return SearchResponse(False, self.name, [], error=f"Search API error: {response.status_code}")
        data = response.json()
        hits = [SearchHit(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("content", ""),
                          score=r.get("score"))
                for r in data.get("results", [])]
        return SearchResponse(True, self.name, hits, answer=data.get("answer"))


class BraveBackend:
    name = "brave"
    env_key = "BRAVE_SEARCH_API_KEY"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, num_results: int = 10, **_) -> SearchResponse:
        async with _http_client(30.0) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": self.api_key},
                params={"q": query, "count": num_results},
            )
        if response.status_code != 200:
            return SearchResponse(False, self.name, [], error=f"Search API error: {response.status_code}")
        data = response.json()
        hits = [SearchHit(title=r.get("title") or "", url=r.get("url") or "", snippet=r.get("description") or "")
                for r in data.get("web", {}).get("results", [])[:num_results]]
        return SearchResponse(True, self.name, hits)


class SerperBackend:
    name = "serper"
    env_key = "SERPER_API_KEY"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, num_results: int = 10, **_) -> SearchResponse:
        async with _http_client(30.0) as client:
            response = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": self.api_key},
                json={"q": query, "num": num_results},
            )
        if response.status_code != 200:
            return SearchResponse(False, self.name, [], error=f"Search API error: {response.status_code}")
        data = response.json()
        hits = [SearchHit(title=r.get("title") or "", url=r.get("link") or "", snippet=r.get("snippet") or "")
                for r in data.get("organic", [])[:num_results]]
        return SearchResponse(True, self.name, hits)


class DuckDuckGoBackend:
    """DuckDuckGo's instant-answer API: no key, an abstract plus related topics.

    It returns little or nothing for most queries; it is what the wiki queue
    used, and it stays as the keyless last resort.
    """
    name = "duckduckgo"
    env_key = None

    async def search(self, query: str, num_results: int = 10, **_) -> SearchResponse:
        async with _http_client(10.0) as client:
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
        if response.status_code != 200:
            return SearchResponse(False, self.name, [], error=f"Search returned status {response.status_code}")
        data = response.json()
        hits = []
        if data.get("Abstract"):
            hits.append(SearchHit(title=data.get("Heading", "") or query, url=data.get("AbstractURL", ""),
                                  snippet=data.get("Abstract", ""),
                                  source=data.get("AbstractSource", "DuckDuckGo")))
        for topic in data.get("RelatedTopics", []):
            if len(hits) >= num_results:
                break
            if isinstance(topic, dict) and topic.get("Text"):
                hits.append(SearchHit(title=topic.get("Text", "")[:80], url=topic.get("FirstURL", ""),
                                      snippet=topic.get("Text", ""), source="Related"))
        return SearchResponse(True, self.name, hits)


_KEYED = {"tavily": TavilyBackend, "brave": BraveBackend, "serper": SerperBackend}

_override: Optional[List[SearchBackend]] = None


def search_order(env=None) -> List[str]:
    env = os.environ if env is None else env
    raw = env.get(ORDER_ENV)
    if not raw:
        return list(DEFAULT_ORDER)
    return [n.strip().lower() for n in raw.split(",") if n.strip()]


def configured_backends(env=None) -> List[SearchBackend]:
    """The backends that can run, in order. Keyed ones need their key set."""
    if _override is not None:
        return list(_override)
    env = os.environ if env is None else env
    out: List[SearchBackend] = []
    for name in search_order(env):
        if name == "duckduckgo":
            out.append(DuckDuckGoBackend())
        elif name in _KEYED:
            cls = _KEYED[name]
            key = env.get(cls.env_key)
            if key:
                out.append(cls(key))
        else:
            logger.warning(f"research search: unknown backend {name!r} in {ORDER_ENV}")
    return out


def describe_backends(env=None) -> List[str]:
    """Names of the configured backends, primary first (for status pages/logs)."""
    return [b.name for b in configured_backends(env)]


@contextmanager
def use_backends(backends: List[SearchBackend]) -> Iterator[None]:
    """Replace the configured backends (tests)."""
    global _override
    previous = _override
    _override = list(backends)
    try:
        yield
    finally:
        _override = previous


async def search(query: str, num_results: int = 10, **opts) -> SearchResponse:
    """Search with the primary backend, falling back down the configured list."""
    backends = configured_backends()
    if not backends:
        return SearchResponse(False, "none", [], error="No search backend configured (set TAVILY_API_KEY)")
    errors = []
    for backend in backends:
        try:
            resp = await backend.search(query, num_results=num_results, **opts)
        except Exception as e:
            resp = SearchResponse(False, backend.name, [], error=str(e))
        if resp.success:
            return resp
        errors.append(f"{backend.name}: {resp.error}")
        logger.info(f"research search: {backend.name} failed ({resp.error}); trying next backend")
    return SearchResponse(False, backends[-1].name, [], error="; ".join(errors))


async def web_search(query: str, num_results: int = 10, **opts) -> Dict:
    """`search()` in the dict shape ResearchManager.web_search returned."""
    resp = await search(query, num_results=num_results, **opts)
    if not resp.success:
        return {"success": False, "error": resp.error, "results": [], "backend": resp.backend}
    return {
        "success": True,
        "query": query,
        "answer": resp.answer,
        "results": [{"title": h.title, "url": h.url, "snippet": h.snippet, "score": h.score} for h in resp.results],
        "result_count": len(resp.results),
        "backend": resp.backend,
    }


async def context_snippets(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """`search()` in the {source, url, text} shape the wiki research code reads."""
    resp = await search(query, num_results=num_results)
    if not resp.success:
        return []
    return [{"source": h.source or h.title or resp.backend, "url": h.url, "text": h.snippet}
            for h in resp.results if h.snippet]


__all__ = [
    "SearchHit", "SearchResponse", "SearchBackend",
    "TavilyBackend", "BraveBackend", "SerperBackend", "DuckDuckGoBackend",
    "configured_backends", "describe_backends", "search_order", "use_backends",
    "search", "web_search", "context_snippets",
]
