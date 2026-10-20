"""
Ownership and self-registration (issues #19 and #20).

- POST /users/current: only your own id (admins may pick any user).
- POST /auth/register: creates a PENDING user and returns no token; login
  is refused until an admin approves.
- GET /users/{id}/journals* and /cass/disagreements?user_id=: owner or
  admin only.
- /auth/login and /auth/refresh refuse pending and rejected accounts.
"""
from tests.smoke.conftest import access_token, admin_token, create_user


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# --- #19: /users/current -----------------------------------------------------

def test_set_current_user_rejects_another_users_id(booted_app, smoke_user):
    alice, alice_token = smoke_user
    bob = create_user("Bob")
    r = booted_app.post("/users/current", json={"user_id": bob}, headers=_bearer(alice_token))
    assert r.status_code == 403, r.text


def test_set_current_user_accepts_own_id(booted_app, smoke_user):
    alice, alice_token = smoke_user
    r = booted_app.post("/users/current", json={"user_id": alice}, headers=_bearer(alice_token))
    assert r.status_code == 200, r.text
    assert r.json()["user"]["user_id"] == alice


def test_set_current_user_admin_may_pick_any_user(booted_app, smoke_admin):
    _admin, token = smoke_admin
    bob = create_user("Bob")
    r = booted_app.post("/users/current", json={"user_id": bob}, headers=_bearer(token))
    assert r.status_code == 200, r.text


# --- #20: self-registration ----------------------------------------------------

def test_register_creates_pending_user_without_tokens(booted_app):
    from users import UserManager

    r = booted_app.post("/auth/register", json={
        "email": "stranger@example.com", "password": "hunter22", "display_name": "Stranger",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert "access_token" not in body and "refresh_token" not in body
    assert UserManager().load_profile(body["user_id"]).status == "pending"

    # Login is refused until an admin approves.
    login = {"email": "stranger@example.com", "password": "hunter22"}
    r = booted_app.post("/auth/login", json=login)
    assert r.status_code == 403
    assert "pending" in r.json()["detail"].lower()

    UserManager().set_user_status(body["user_id"], "approved")
    r = booted_app.post("/auth/login", json=login)
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


def test_register_pending_user_shows_up_for_admin_approval(booted_app, smoke_admin):
    _admin, token = smoke_admin
    r = booted_app.post("/auth/register", json={
        "email": "waiting@example.com", "password": "hunter22", "display_name": "Waiting",
    })
    user_id = r.json()["user_id"]
    pending = booted_app.get("/admin/users/pending", headers=_bearer(token))
    assert pending.status_code == 200, pending.text
    assert user_id in pending.text


def _register_and_approve(client, email):
    from users import UserManager
    r = client.post("/auth/register", json={
        "email": email, "password": "hunter22", "display_name": email.split("@")[0],
    })
    user_id = r.json()["user_id"]
    UserManager().set_user_status(user_id, "approved")
    login = client.post("/auth/login", json={"email": email, "password": "hunter22"})
    assert login.status_code == 200, login.text
    return user_id, login.json()


def test_register_inserts_pending_in_one_write(test_db):
    """The status is part of the INSERT: there is no moment the row is approved."""
    from unittest.mock import patch
    from auth import AuthService
    from users import UserManager

    manager = UserManager()
    with patch.object(UserManager, "set_user_status", side_effect=AssertionError("second write")):
        user_id = AuthService(manager).register("solo@example.com", "hunter22", "Solo")
    assert manager.load_profile(user_id).status == "pending"


def test_rejected_user_cannot_log_in(booted_app):
    from users import UserManager
    user_id, _tokens = _register_and_approve(booted_app, "rejected@example.com")
    UserManager().set_user_status(user_id, "rejected", reason="spam")

    r = booted_app.post("/auth/login", json={"email": "rejected@example.com", "password": "hunter22"})
    assert r.status_code == 403
    assert "rejected" in r.json()["detail"].lower()


def test_refresh_refused_after_rejection(booted_app):
    from users import UserManager
    user_id, tokens = _register_and_approve(booted_app, "later@example.com")
    ok = booted_app.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert ok.status_code == 200, ok.text

    UserManager().set_user_status(user_id, "rejected")
    r = booted_app.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 403, r.text


def test_refresh_refused_while_pending(booted_app):
    from auth import create_refresh_token
    r = booted_app.post("/auth/register", json={
        "email": "early@example.com", "password": "hunter22", "display_name": "Early",
    })
    # No route issues a pending user a token any more; forge one to check
    # refresh itself refuses (covers tokens minted before this change).
    token = create_refresh_token(r.json()["user_id"])
    r = booted_app.post("/auth/refresh", json={"refresh_token": token})
    assert r.status_code == 403, r.text


# --- #20: per-user journal ownership -----------------------------------------

JOURNAL_PATHS = (
    "/users/{id}/journals",
    "/users/{id}/journals/2026-01-01",
    "/users/{id}/journals/search/anything",
)


def test_journals_forbidden_for_other_users(booted_app, smoke_user):
    _alice, alice_token = smoke_user
    bob = create_user("Bob")
    for path in JOURNAL_PATHS:
        r = booted_app.get(path.format(id=bob), headers=_bearer(alice_token))
        assert r.status_code == 403, (path, r.text)


def test_journals_allowed_for_owner_and_admin(booted_app, smoke_user, smoke_admin):
    alice, alice_token = smoke_user
    _admin, admin_tok = smoke_admin
    for token in (alice_token, admin_tok):
        r = booted_app.get(f"/users/{alice}/journals", headers=_bearer(token))
        assert r.status_code == 200, r.text
        assert r.json()["user_id"] == alice


# --- /cass/disagreements?user_id= --------------------------------------------

def _record_disagreements(*user_ids):
    from routes import cass as cass_routes
    for uid in user_ids:
        cass_routes._self_manager.add_disagreement(
            with_user_id=uid, with_user_name=uid[:4], topic="tabs vs spaces",
            their_position="tabs", my_position="spaces",
        )


def test_disagreements_scoped_to_caller(booted_app, smoke_user):
    alice, alice_token = smoke_user
    bob = create_user("Bob")
    _record_disagreements(alice, bob)

    r = booted_app.get(f"/cass/disagreements?user_id={bob}", headers=_bearer(alice_token))
    assert r.status_code == 403, r.text

    for url in (f"/cass/disagreements?user_id={alice}", "/cass/disagreements"):
        r = booted_app.get(url, headers=_bearer(alice_token))
        assert r.status_code == 200, r.text
        assert {d["with_user_id"] for d in r.json()["disagreements"]} == {alice}, url


def test_disagreements_admin_sees_any(booted_app, smoke_admin):
    _admin, token = smoke_admin
    bob = create_user("Bob")
    _record_disagreements(bob)
    r = booted_app.get(f"/cass/disagreements?user_id={bob}", headers=_bearer(token))
    assert r.status_code == 200, r.text
    assert [d["with_user_id"] for d in r.json()["disagreements"]] == [bob]
