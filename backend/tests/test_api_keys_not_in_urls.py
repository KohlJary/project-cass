"""API keys travel in headers, not URLs: httpx logs request URLs, so a key in
the query string ends up in the service journal."""
import asyncio

import httpx
import pytest


class _Resp:
    status_code = 200

    def json(self):
        return {"status": "ok", "articles": []}


class _Client:
    calls = []

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None, **kw):
        _Client.calls.append((url, dict(params or {}), dict(headers or {})))
        return _Resp()


@pytest.mark.unit
@pytest.mark.parametrize("ctx", [{"topic": "tides"}, {}])
def test_news_action_sends_key_as_header(monkeypatch, ctx):
    from scheduler.actions.world_handlers import fetch_news_action
    monkeypatch.setenv("NEWS_API_KEY", "k-123")
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    _Client.calls.clear()
    asyncio.run(fetch_news_action(ctx))
    assert _Client.calls, "no request made"
    for url, params, headers in _Client.calls:
        assert "k-123" not in url and "k-123" not in params.values()
        assert headers.get("X-Api-Key") == "k-123"


@pytest.mark.unit
def test_world_state_source_sends_news_key_as_header(monkeypatch):
    pytest.importorskip("networkx")  # sources/ pulls it in; CI's fast job lacks it
    from sources.world_state_source import WorldStateSource
    monkeypatch.setenv("NEWS_API_KEY", "k-456")
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    _Client.calls.clear()
    source = WorldStateSource.__new__(WorldStateSource)  # no daemon or DB needed for the fetch
    asyncio.run(source._fetch_headlines(["science"]))
    asyncio.run(source.search_headlines("tides"))
    urls = {url for url, _p, _h in _Client.calls}
    assert any("top-headlines" in u for u in urls) and any("everything" in u for u in urls), urls
    for url, params, headers in _Client.calls:
        assert "k-456" not in url and "k-456" not in params.values()
        assert headers.get("X-Api-Key") == "k-456"


@pytest.mark.unit
def test_httpx_request_logging_is_quiet_in_the_service():
    """OpenWeather and WikiArt keys can only go in the URL, so the service keeps
    httpx/httpcore request logs (which print URLs) below INFO."""
    pytest.importorskip("multipart")
    import logging
    import main_sdk  # noqa: F401  (sets the levels at import)
    for name in ("httpx", "httpcore"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
