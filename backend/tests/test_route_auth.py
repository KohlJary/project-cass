"""
Regression guard: every mounted route requires auth unless explicitly public.

Walks the real route table of main_sdk.app and calls each route with no
credentials. A new route fails this test unless it is protected (the
app-wide route_guard does that by default) or added to route_guard.PUBLIC_ROUTES
on purpose.
"""
import os
import re

import pytest


# Routes allowed to answer without credentials. Keep this in sync with
# route_guard.PUBLIC_ROUTES; adding to it is a deliberate security decision.
PUBLIC_ALLOWLIST = {
    ("GET", "/health"),
    ("GET", "/"),
    ("GET", "/status"),
    ("POST", "/auth/login"),
    ("POST", "/auth/register"),
    ("POST", "/auth/refresh"),
    ("POST", "/admin/auth/login"),
    ("POST", "/admin/auth/register"),
    ("GET", "/admin/auth/status"),
    ("POST", "/admin/auth/bootstrap"),
    ("GET", "/admin/homepage/{daemon_label}/page/{page}"),
    ("GET", "/attachments/{attachment_id}"),
    ("GET", "/music/audio/{filename}"),
    ("GET", "/{full_path:path}"),
    # FastAPI's own docs pages are added by FastAPI(), not by a router.
    ("GET", "/openapi.json"),
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
    ("HEAD", "/openapi.json"),
    ("HEAD", "/docs"),
    ("HEAD", "/docs/oauth2-redirect"),
    ("HEAD", "/redoc"),
}

# /ws authenticates per message (auth message or ?token=); tested separately.
SELF_AUTHENTICATING_WS = {"/ws"}


@pytest.fixture(scope="module")
def app():
    # No bypass user: an anonymous request must not be treated as anyone.
    os.environ.pop("DEFAULT_LOCALHOST_USER_ID", None)
    from main_sdk import app
    return app


@pytest.fixture(scope="module")
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=False)


def _concrete(path: str) -> str:
    """Fill path params with a harmless value."""
    return re.sub(r"\{[^}]+\}", "x", path)


def _mounted_routes():
    os.environ.pop("DEFAULT_LOCALHOST_USER_ID", None)
    from main_sdk import app
    from route_guard import iter_mounted_routes
    seen = set()
    for method, path, _route, _endpoint in iter_mounted_routes(app):
        if (method, path) in seen:
            continue
        seen.add((method, path))
        yield method, path


ALL_ROUTES = sorted(_mounted_routes(), key=lambda mp: (mp[1], mp[0]))


def test_route_table_is_large():
    """Sanity check that we're actually walking the full app (~800 routes)."""
    assert len(ALL_ROUTES) > 500


@pytest.mark.parametrize("method,path", [r for r in ALL_ROUTES if r[0] != "WS"],
                         ids=lambda v: str(v))
def test_http_route_requires_auth(client, method, path):
    if (method, path) in PUBLIC_ALLOWLIST:
        pytest.skip("public by design")
    response = client.request(method, _concrete(path))
    assert response.status_code in (401, 403), (
        f"{method} {path} answered {response.status_code} without credentials. "
        f"Protect it, or add it to route_guard.PUBLIC_ROUTES and this allowlist on purpose."
    )


@pytest.mark.parametrize("path", [p for m, p in ALL_ROUTES if m == "WS"])
def test_websocket_route_requires_auth(client, path):
    from starlette.websockets import WebSocketDisconnect
    if path in SELF_AUTHENTICATING_WS:
        pytest.skip("authenticates per message; see test_ws_rejects_anonymous_chat")
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(_concrete(path)) as ws:
            ws.receive_text()
    assert exc.value.code == 1008


def test_allowlist_matches_route_guard():
    """The test allowlist and route_guard.PUBLIC_ROUTES must not drift apart."""
    from route_guard import PUBLIC_ROUTES
    guard = {(m, p) for m, p in PUBLIC_ROUTES}
    test = {(m, p) for m, p in PUBLIC_ALLOWLIST if m != "HEAD" and p not in
            ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc")}
    assert guard == test


def test_docs_endpoints_are_the_only_unlisted_public_routes(app):
    """FastAPI's /docs and /openapi.json are added outside route_guard. They
    expose the schema only (no data); every other route goes through the guard."""
    from route_guard import iter_mounted_routes, _ENDPOINT_LEVELS, PUBLIC
    unguarded = set()
    for method, path, _route, endpoint in iter_mounted_routes(app):
        if endpoint not in _ENDPOINT_LEVELS:
            unguarded.add(path)
    assert unguarded <= {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def test_relayed_localhost_request_gets_no_bypass(client, monkeypatch):
    """The relay proxies remote traffic from 127.0.0.1; it must not be 'local'."""
    from fastapi.testclient import TestClient
    from main_sdk import app
    from database import get_db
    from datetime import datetime
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, display_name, is_admin, created_at, updated_at) "
            "VALUES ('bypass-admin', 'bypass-admin', 1, ?, ?)", (now, now))
    monkeypatch.setenv("ALLOW_LOCALHOST_BYPASS", "true")
    monkeypatch.setenv("DEFAULT_LOCALHOST_USER_ID", "bypass-admin")
    local = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 5000))

    # Direct local call: bypass applies (keeps TUI dev convenience).
    assert local.get("/files/exists", params={"path": "/nonexistent-outside-roots"}).status_code == 403
    assert local.get("/files/exists", params={"path": "/nonexistent-outside-roots"}).json()["detail"].startswith("Path is outside")

    # Same call marked as relayed / proxied: no bypass.
    for header in ({"X-Cass-Relayed": "1"}, {"X-Forwarded-For": "8.8.8.8"}):
        r = local.get("/files/exists", params={"path": "/x"}, headers=header)
        assert r.status_code == 401, header

    # Browser on this machine visiting a hostile site: Origin is not local.
    r = local.get("/files/exists", params={"path": "/x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 401


def test_ws_rejects_anonymous_chat(client):
    """An unauthenticated /ws connection can't chat (it used to spend tokens)."""
    import websocket_handlers
    from unittest.mock import MagicMock
    from connection_manager import ConnectionManager
    state = websocket_handlers._state
    saved = dict(state)
    try:
        state["memory"] = MagicMock()
        state["conversation_manager"] = MagicMock()
        state["connection_manager"] = ConnectionManager()
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "connected"
            ws.send_json({"type": "chat", "message": "hi"})
            reply = ws.receive_json()
            assert reply["type"] == "auth_error"
            state["conversation_manager"].create_conversation.assert_not_called()
    finally:
        state.clear()
        state.update(saved)
