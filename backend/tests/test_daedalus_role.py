"""Daedalus's narrower admin role (Cass and Kohl, 2026-11-17): a token with only
the daedalus role reaches DAEDALUS_ROUTES and nothing else, so it can never
write to her data; each call is logged."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from auth import ROLE_DAEDALUS, create_access_token
from routes.admin.auth import DAEDALUS_ROUTES, require_admin


def _admin_routes():
    from admin_api import router
    out = set()
    for r in router.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/admin/"):
            out |= {(m, r.path[len("/admin"):]) for m in r.methods}
    return out


def _request(method, path):
    full = "/admin" + path
    return Request({"type": "http", "method": method, "path": full, "headers": [],
                    "query_string": b"", "route": SimpleNamespace(path=full)})


def _call(method, path, token):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    return asyncio.run(require_admin(_request(method, path), creds))


@pytest.fixture
def token(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return create_access_token("daedalus-test", roles=[ROLE_DAEDALUS], display_name="Daedalus",
                               expires_delta=timedelta(minutes=5))


def test_every_allowed_route_exists_and_only_two_are_writes():
    routes = _admin_routes()
    assert DAEDALUS_ROUTES <= routes, f"stale: {DAEDALUS_ROUTES - routes}"
    writes = {r for r in DAEDALUS_ROUTES if r[0] != "GET"}
    assert writes == {("POST", "/scheduler/run-session/{template_id}"), ("POST", "/scheduler/replan-day")}


def test_the_role_reaches_its_routes_and_is_never_admin(token, tmp_path):
    got = _call("POST", "/scheduler/run-session/{template_id}", token)
    assert got["daedalus"] is True and got["is_admin"] is False
    assert '"allowed": true' in (tmp_path / "daedalus_access.jsonl").read_text()


def test_every_other_admin_route_is_refused(token, tmp_path):
    refused = 0
    for method, path in sorted(_admin_routes() - DAEDALUS_ROUTES):
        if method in ("HEAD", "OPTIONS"):
            continue
        with pytest.raises(HTTPException) as e:
            _call(method, path, token)
        assert e.value.status_code == 403, (method, path)
        refused += 1
    assert refused > 100
    log = (tmp_path / "daedalus_access.jsonl").read_text()
    assert '"route": "/self-model"' in log or '"route": "/memory"' in log
    assert '"allowed": false' in log
