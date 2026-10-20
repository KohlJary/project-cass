"""
The /admin area is admin-only (route_guard.ADMIN_AREA_USER_ROUTES).

Every /admin/* route needs users.is_admin, whichever auth dependency its
handler declares, except the routes the admin frontend's non-admin pages call
(Genesis, Profile, Feedback, the daemon picker, Self-Development's self-model
reads) and the dashboard's public auth endpoints. Those stay open to any
approved user and are scoped to the caller's own data.
"""
import re

import pytest

from tests.smoke.conftest import access_token, admin_token, create_user


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _dashboard_token(user_id, display_name="Plain User"):
    """A dashboard token (what /admin/auth/login issues) for a non-admin."""
    from routes.admin.auth import create_token
    token, _expires = create_token(user_id, display_name, is_admin=False)
    return token


@pytest.fixture
def plain_user(test_db):
    """(user_id, dashboard token) for an approved, non-admin user."""
    user_id = create_user("Plain User")
    return user_id, _dashboard_token(user_id)


# Routes reported reachable by any dashboard token before this change.
FORMERLY_OPEN = [
    ("GET", "/admin/users"),
    ("GET", "/admin/users/{other}"),
    ("GET", "/admin/users/{other}/relationship"),
    ("GET", "/admin/conversations?user_id={other}"),
    ("GET", "/admin/conversations/system"),
    ("GET", "/admin/conversations/x/messages"),
    ("GET", "/admin/narrative/threads?user_id={other}"),
    ("POST", "/admin/narrative/threads"),
    ("GET", "/admin/narrative/questions"),
    ("GET", "/admin/memory"),
    ("GET", "/admin/memory/search?query=x"),
    ("GET", "/admin/memory/vectors"),
    ("GET", "/admin/journals"),
    ("GET", "/admin/journals/calendar"),
    ("GET", "/admin/daemons"),
    ("GET", "/admin/research/sessions"),
    ("GET", "/admin/world-state/observations"),
    ("GET", "/admin/genesis/eligible"),
    ("GET", "/admin/genesis/x"),
    ("GET", "/admin/feedback"),
    ("GET", "/admin/self-model/architectural-requests"),
]


def test_non_admin_dashboard_token_refused_on_formerly_open_routes(booted_app, plain_user):
    _me, token = plain_user
    other = create_user("Someone Else")
    for method, url in FORMERLY_OPEN:
        r = booted_app.request(method, url.format(other=other), headers=_bearer(token))
        assert r.status_code == 403, (method, url, r.status_code, r.text)


def test_non_admin_mobile_token_refused_too(booted_app, test_db):
    me = create_user("Mobile User")
    other = create_user("Someone Else")
    r = booted_app.get(f"/admin/users/{other}", headers=_bearer(access_token(me)))
    assert r.status_code == 403, r.text


def test_admin_still_reaches_formerly_open_routes(booted_app, smoke_admin):
    _admin, token = smoke_admin
    other = create_user("Someone Else")
    for method, url in FORMERLY_OPEN:
        if method != "GET":
            continue
        r = booted_app.get(url.format(other=other), headers=_bearer(token))
        assert r.status_code not in (401, 403), (url, r.status_code, r.text)


def test_admin_still_writes_through_formerly_self_checked_routes(booted_app, smoke_admin):
    """POSTs on routes whose handlers declare require_auth: the guard's
    admin check and the handler's own check both pass for an admin."""
    _admin, token = smoke_admin
    h = _bearer(token)
    r = booted_app.post("/admin/narrative/threads", json={"title": "A thread"}, headers=h)
    assert r.status_code == 200, r.text
    thread_id = r.json()["id"]
    r = booted_app.post(f"/admin/narrative/threads/{thread_id}/resolve",
                        json={"resolution_summary": "settled"}, headers=h)
    assert r.status_code == 200, r.text
    r = booted_app.post("/admin/narrative/questions", json={"question": "Why?"}, headers=h)
    assert r.status_code == 200, r.text
    r = booted_app.post("/admin/feedback", json={"message": "from an admin"}, headers=h)
    assert r.status_code == 200, r.text


# --- every /admin route, from the route table ---------------------------------

# The /admin routes a non-admin may call, spelled out. route_guard's
# ADMIN_AREA_USER_ROUTES must expand to exactly this set over the mounted
# routes; adding to it is a deliberate decision.
EXPECTED_NON_ADMIN = {
    ("GET", "/admin/daemons/mine"),
    ("GET", "/admin/genesis/active"),
    ("POST", "/admin/genesis/start"),
    ("POST", "/admin/genesis/{session_id}/message"),
    ("POST", "/admin/genesis/{session_id}/complete"),
    ("POST", "/admin/genesis/{session_id}/abandon"),
    ("GET", "/admin/users/{user_id}/model"),
    ("GET", "/admin/users/{user_id}/observations"),
    ("POST", "/admin/feedback"),
    ("GET", "/admin/self-model/stakes"),
    ("GET", "/admin/self-model/stakes/stats"),
    ("GET", "/admin/self-model/preference-tests"),
    ("GET", "/admin/self-model/preference-consistency"),
    ("GET", "/admin/self-model/narration-contexts"),
    ("GET", "/admin/self-model/narration-patterns"),
    ("POST", "/admin/stt/transcribe"),
    ("GET", "/admin/stt/status"),
}


def _admin_area_routes():
    import main_sdk
    from route_guard import iter_mounted_routes
    seen = set()
    for method, path, route, _endpoint in iter_mounted_routes(main_sdk.app):
        if (path == "/admin" or path.startswith("/admin/")) and (method, path) not in seen:
            seen.add((method, path))
            yield method, path, route


def _exempt(method, path):
    from route_guard import PUBLIC_ROUTES, _matches
    return _matches(PUBLIC_ROUTES, method, path) or (method, path) in EXPECTED_NON_ADMIN


def test_every_admin_route_is_admin_level_unless_exempt():
    from route_guard import level_for, ADMIN
    routes = list(_admin_area_routes())
    assert len(routes) > 300  # the whole admin router, not a stub
    wrong = [(m, p, level_for(m, p, r)) for m, p, r in routes
             if not _exempt(m, p) and level_for(m, p, r) != ADMIN]
    assert not wrong, wrong


def test_every_non_exempt_admin_route_refuses_a_non_admin(booted_app, plain_user):
    """Walk the route table: a non-admin dashboard token gets 403 everywhere
    under /admin except the exemption list."""
    from starlette.websockets import WebSocketDisconnect
    _me, token = plain_user
    failures = []
    checked = 0
    for method, path, _route in _admin_area_routes():
        if _exempt(method, path):
            continue
        url = re.sub(r"\{[^}]+\}", "x", path)
        checked += 1
        if method == "WS":
            try:
                with booted_app.websocket_connect(f"{url}?token={token}") as ws:
                    ws.receive_text()
                failures.append((method, path, "accepted"))
            except WebSocketDisconnect as exc:
                if exc.code != 1008:
                    failures.append((method, path, exc.code))
            continue
        r = booted_app.request(method, url, headers=_bearer(token))
        if r.status_code != 403:
            failures.append((method, path, r.status_code))
    assert checked > 300
    assert not failures, failures


def test_exemption_list_matches_exactly_the_intended_routes():
    """Each guard exemption matches exactly one mounted route, and together
    they are EXPECTED_NON_ADMIN: no stale entry, and no pattern that would
    quietly open a route added later."""
    import route_guard
    rules = getattr(route_guard, "ADMIN_AREA_USER_ROUTES", [])
    mounted = [(m, p) for m, p, _r in _admin_area_routes()]
    matched = set()
    for rule in rules:
        hits = [mp for mp in mounted if route_guard._matches([rule], *mp)]
        assert len(hits) == 1, (rule, hits)
        matched.update(hits)
    assert matched == EXPECTED_NON_ADMIN


# --- exempted pages still work for a non-admin, scoped to their own data ------

def test_profile_routes_own_data_only(booted_app, plain_user, smoke_admin):
    from users import UserManager
    me, token = plain_user
    other = create_user("Someone Else")
    UserManager().add_observation(me, "likes tea")
    UserManager().add_observation(other, "likes coffee")

    for suffix in ("model", "observations"):
        r = booted_app.get(f"/admin/users/{me}/{suffix}", headers=_bearer(token))
        assert r.status_code == 200, (suffix, r.text)
        r = booted_app.get(f"/admin/users/{other}/{suffix}", headers=_bearer(token))
        assert r.status_code == 403, (suffix, r.text)

    mine = booted_app.get(f"/admin/users/{me}/observations", headers=_bearer(token)).json()
    assert [o["observation"] for o in mine["observations"]] == ["likes tea"]

    _admin, admin_tok = smoke_admin
    r = booted_app.get(f"/admin/users/{other}/observations", headers=_bearer(admin_tok))
    assert r.status_code == 200, r.text
    assert [o["observation"] for o in r.json()["observations"]] == ["likes coffee"]


def test_profile_check_uses_database_not_token_claim(booted_app, test_db):
    """A token minted with is_admin=True for a user who is not (or no longer)
    an admin gets no more than their own profile."""
    from routes.admin.auth import create_token
    me = create_user("Demoted")
    other = create_user("Someone Else")
    token, _ = create_token(me, "Demoted", is_admin=True)
    assert booted_app.get(f"/admin/users/{me}/model", headers=_bearer(token)).status_code == 200
    assert booted_app.get(f"/admin/users/{other}/model", headers=_bearer(token)).status_code == 403
    assert booted_app.get("/admin/users", headers=_bearer(token)).status_code == 403


def test_feedback_submit_records_caller(booted_app, plain_user):
    from database import get_db
    me, token = plain_user
    r = booted_app.post("/admin/feedback", json={"message": "nice"}, headers=_bearer(token))
    assert r.status_code == 200, r.text
    with get_db() as conn:
        rows = conn.execute("SELECT user_id, message FROM feedback").fetchall()
    assert [(row[0], row[1]) for row in rows] == [(me, "nice")]


def _daemon_talked_to_by(label, user_id):
    from datetime import datetime
    from database import get_db
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute("INSERT INTO daemons (id, label, name, created_at) VALUES (?, ?, ?, ?)",
                     (f"d-{label}", label, label, now))
        conn.execute("INSERT INTO conversations (id, daemon_id, user_id, created_at, updated_at) "
                     "VALUES (?, ?, ?, ?, ?)", (f"c-{label}", f"d-{label}", user_id, now, now))


def test_daemon_picker_shows_only_cass_and_own(booted_app, plain_user):
    me, token = plain_user
    other = create_user("Someone Else")
    _daemon_talked_to_by("mine", me)
    _daemon_talked_to_by("theirs", other)
    r = booted_app.get("/admin/daemons/mine", headers=_bearer(token))
    assert r.status_code == 200, r.text
    labels = {d["label"] for d in r.json()["daemons"]}
    assert "mine" in labels and "theirs" not in labels, labels


def test_genesis_own_session_only(booted_app, plain_user):
    from genesis_dream import create_genesis_session
    me, token = plain_user
    other = create_user("Someone Else")
    theirs = create_genesis_session(other)
    mine = create_genesis_session(me)

    r = booted_app.get("/admin/genesis/active", headers=_bearer(token))
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True
    assert r.json()["session"]["id"] == mine.id

    for action in ("abandon", "complete"):
        r = booted_app.post(f"/admin/genesis/{theirs.id}/{action}", headers=_bearer(token))
        assert r.status_code == 403, (action, r.text)
    r = booted_app.post(f"/admin/genesis/{theirs.id}/message", json={"message": "hi"},
                        headers=_bearer(token))
    assert r.status_code == 403, r.text

    r = booted_app.post(f"/admin/genesis/{mine.id}/abandon", headers=_bearer(token))
    assert r.status_code == 200, r.text


def test_self_development_reads_open_to_non_admin(booted_app, plain_user):
    _me, token = plain_user
    for url in ("/admin/self-model/stakes", "/admin/self-model/stakes/stats",
                "/admin/self-model/preference-tests", "/admin/self-model/narration-patterns"):
        r = booted_app.get(url, headers=_bearer(token))
        assert r.status_code not in (401, 403), (url, r.status_code, r.text)


def test_dashboard_auth_flow_for_non_admin(booted_app, test_db):
    """Register -> admin approves -> login works for a non-admin, and the
    token reaches the exempt pages but not the rest of /admin."""
    from users import UserManager
    r = booted_app.post("/admin/auth/register", json={
        "username": "Newcomer", "password": "hunter22hunter22", "email": "new@example.com",
    })
    assert r.status_code == 200, r.text
    assert booted_app.get("/admin/auth/status").status_code == 200

    manager = UserManager()
    profile = manager.get_user_by_name("Newcomer")
    refused = booted_app.post("/admin/auth/login",
                              json={"username": "Newcomer", "password": "hunter22hunter22"})
    assert refused.status_code == 403  # pending
    manager.set_user_status(profile.user_id, "approved")

    login = booted_app.post("/admin/auth/login",
                            json={"username": "Newcomer", "password": "hunter22hunter22"})
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["is_admin"] is False
    token = body["token"]

    assert booted_app.get(f"/admin/users/{profile.user_id}/model", headers=_bearer(token)).status_code == 200
    assert booted_app.get("/admin/daemons/mine", headers=_bearer(token)).status_code == 200
    assert booted_app.get("/admin/users", headers=_bearer(token)).status_code == 403


# --- require_auth re-checks the account on every call -------------------------

def test_rejected_user_token_refused_on_exempt_routes(booted_app, plain_user):
    from users import UserManager
    me, token = plain_user
    assert booted_app.get("/admin/daemons/mine", headers=_bearer(token)).status_code == 200
    UserManager().set_user_status(me, "rejected", "spam")
    for method, url in (("GET", "/admin/daemons/mine"), ("GET", "/admin/genesis/active"),
                        ("POST", "/admin/feedback"), ("GET", f"/admin/users/{me}/model")):
        r = booted_app.request(method, url, json={"message": "x"}, headers=_bearer(token))
        assert r.status_code == 403, (url, r.status_code, r.text)


def test_pending_user_token_refused_on_exempt_routes(booted_app, plain_user):
    from users import UserManager
    me, token = plain_user
    UserManager().set_user_status(me, "pending")
    r = booted_app.get("/admin/genesis/active", headers=_bearer(token))
    assert r.status_code == 403, r.text


def test_deleted_user_token_refused_on_exempt_routes(booted_app, plain_user):
    from database import get_db
    me, token = plain_user
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (me,))
    for url in ("/admin/daemons/mine", "/admin/genesis/active"):
        r = booted_app.get(url, headers=_bearer(token))
        assert r.status_code == 401, (url, r.status_code, r.text)
