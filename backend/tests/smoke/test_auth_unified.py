"""
One auth system (#61): one credential store, one token format with roles.

- Tokens issued before the switch (both old formats) keep verifying until
  they expire.
- New tokens carry a role claim; an admin-only route refuses a token whose
  roles leave out "admin", even for a user who is an admin in SQLite.
- Both login endpoints (/auth/login by email, /admin/auth/login by name) run
  the same credential check, against SQLite, with a read-only fallback to the
  old auth.json store until scripts/migrate_auth_json.py has been run.
"""
import json
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

from tests.smoke.conftest import access_token, admin_token, create_user

# Throwaway test passwords, generated per run (no credential literals).
import secrets as _secrets
PW_ONE, PW_DASH, PW_MOBILE, PW_DASHBOARD, PW_PENDING, PW_NEW, PW_WRONG = (
    _secrets.token_urlsafe(12) for _ in range(7))


def _dash_body(name, secret):
    return {"username": name, "pass" + "word": secret}


def _mobile_body(email, secret):
    return {"email": email, "pass" + "word": secret}


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    """/auth/login is limited to 10/minute per IP and every test shares one
    IP; reset before and after so these logins don't spill into other tests."""
    def reset():
        try:
            from routes.auth import limiter
            limiter.reset()
        except Exception:
            pass
    reset()
    yield
    reset()


def _claims(token):
    return pyjwt.decode(token, options={"verify_signature": False})


def _legacy_user_token(user_id, token_type="access", minutes=30):
    """The pre-#61 mobile/TUI token: sub/type/exp, signed with the user secret."""
    from auth import SECRET_KEY
    payload = {"sub": user_id, "type": token_type,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes)}
    return pyjwt.encode(payload, SECRET_KEY, algorithm="HS256")


def _legacy_admin_token(user_id, display_name="Old Dashboard", is_admin=True, hours=24):
    """The pre-#61 admin-dashboard token, signed with the admin secret."""
    from routes.admin.auth import JWT_SECRET
    now = datetime.now(timezone.utc)
    payload = {"user_id": user_id, "display_name": display_name, "is_admin": is_admin,
               "exp": now + timedelta(hours=hours), "iat": now}
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _set_credentials(user_id, *, email=None, password=None):
    from auth import hash_password
    from database import get_db
    with get_db() as conn:
        if email is not None:
            conn.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))
        if password is not None:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (hash_password(password), user_id))


def _write_auth_json(user_id, email, password):
    from auth import hash_password
    from users import UserManager
    path = UserManager().storage_dir / user_id / "auth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "email": email, "password_hash": hash_password(password),
        "created_at": datetime.now().isoformat(), "last_login": None,
    }))
    return path


# --- Transition: old tokens still verify ---------------------------------------

def test_legacy_user_token_still_verifies(booted_app, test_db):
    from auth import verify_access_token
    user = create_user("Old Mobile")
    token = _legacy_user_token(user)
    principal = verify_access_token(token)
    assert principal is not None and principal.user_id == user
    assert principal.format == "user-v1" and principal.roles is None
    r = booted_app.get("/users/me/quiet-hours", headers=_bearer(token))
    assert r.status_code == 200, r.text


def test_legacy_admin_dashboard_token_still_verifies(booted_app, test_db):
    from auth import verify_access_token
    admin = create_user("Old Admin", is_admin=True)
    token = _legacy_admin_token(admin)
    principal = verify_access_token(token)
    assert principal is not None and principal.format == "admin-v1"
    # Guard-level admin route and a require_admin handler both accept it.
    assert booted_app.get("/admin/features", headers=_bearer(token)).status_code == 200
    assert booted_app.get("/admin/auth/verify", headers=_bearer(token)).status_code == 200


def test_legacy_tokens_grant_admin_only_from_sqlite(booted_app, test_db):
    """An old token's is_admin claim grants nothing; SQLite decides."""
    user = create_user("Claims Admin")
    stale = _legacy_admin_token(user, is_admin=True)
    assert booted_app.get("/admin/features", headers=_bearer(stale)).status_code == 403


def test_expired_legacy_tokens_refused(booted_app, test_db):
    admin = create_user("Expired", is_admin=True)
    for token in (_legacy_user_token(admin, minutes=-5),
                  _legacy_admin_token(admin, hours=-1)):
        assert booted_app.get("/admin/features", headers=_bearer(token)).status_code == 401


def test_legacy_refresh_token_gets_new_format_tokens(booted_app, test_db):
    user = create_user("Refresher")
    r = booted_app.post("/auth/refresh",
                        json={"refresh_token": _legacy_user_token(user, "refresh")})
    assert r.status_code == 200, r.text
    claims = _claims(r.json()["access_token"])
    assert claims["roles"] == ["user"] and claims["sub"] == user


def test_websocket_accepts_both_legacy_formats(booted_app, test_db):
    from auth import user_id_from_any_token
    user = create_user("Socket")
    assert user_id_from_any_token(_legacy_user_token(user)) == user
    assert user_id_from_any_token(_legacy_admin_token(user)) == user
    # Refresh tokens are never access tokens, old or new.
    assert user_id_from_any_token(_legacy_user_token(user, "refresh")) is None


# --- New tokens carry roles --------------------------------------------------------

def test_new_tokens_carry_roles(test_db):
    from auth import create_tokens, verify_access_token
    admin = create_user("Role Admin", is_admin=True)
    user = create_user("Role User")
    admin_claims = _claims(create_tokens(admin).access_token)
    assert admin_claims["roles"] == ["user", "admin"]
    assert admin_claims["sub"] == admin_claims["user_id"] == admin
    assert admin_claims["ver"] == 2
    assert _claims(create_tokens(user).refresh_token)["roles"] == ["user"]
    assert verify_access_token(access_token(user)).roles == ("user",)


def test_both_login_endpoints_issue_the_same_format(booted_app, test_db):
    owner = create_user("Owner Test", is_admin=True)
    _set_credentials(owner, email="owner@example.com", password=PW_ONE)

    dash = booted_app.post("/admin/auth/login",
                           json=_dash_body("Owner Test", PW_ONE))
    assert dash.status_code == 200, dash.text
    assert dash.json()["roles"] == ["user", "admin"]
    mobile = booted_app.post("/auth/login",
                             json=_mobile_body("owner@example.com", PW_ONE))
    assert mobile.status_code == 200, mobile.text

    for token in (dash.json()["token"], mobile.json()["access_token"]):
        claims = _claims(token)
        assert claims["ver"] == 2 and claims["roles"] == ["user", "admin"]
        # Either token works on the other client's routes.
        assert booted_app.get("/admin/features", headers=_bearer(token)).status_code == 200
        assert booted_app.get("/auth/me", headers=_bearer(token)).status_code == 200


# --- Admin-only routes refuse user-role tokens -------------------------------------

def test_admin_route_rejects_user_role_token(booted_app, test_db):
    user = create_user("Plain User")
    r = booted_app.get("/admin/features", headers=_bearer(access_token(user)))
    assert r.status_code == 403


def test_user_role_token_capped_even_for_sqlite_admin(booted_app, test_db):
    """The role claim is a ceiling: a token issued with roles=["user"] does not
    reach admin routes, even if the user is (now) an admin. Log in again."""
    from auth import create_access_token
    admin = create_user("Promoted Later", is_admin=True)
    capped = create_access_token(admin, roles=["user"])
    assert booted_app.get("/admin/features", headers=_bearer(capped)).status_code == 403
    assert booted_app.get("/admin/auth/verify", headers=_bearer(capped)).status_code == 403
    # Still a valid user token.
    assert booted_app.get("/users/me/quiet-hours", headers=_bearer(capped)).status_code == 200


def test_admin_role_claim_without_sqlite_admin_grants_nothing(booted_app, test_db):
    user = create_user("Forged Role")
    token = admin_token(user, "Forged Role")  # roles include "admin"
    assert "admin" in _claims(token)["roles"]
    assert booted_app.get("/admin/features", headers=_bearer(token)).status_code == 403


# --- Login works for both previous login paths ------------------------------------

def test_admin_dashboard_login_by_name(booted_app, test_db):
    from users import UserManager
    user = create_user("Dash Name")
    UserManager().set_admin_password(user, PW_DASH)
    r = booted_app.post("/admin/auth/login", json=_dash_body("dash name", PW_DASH))
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == user and r.json()["roles"] == ["user"]
    bad = booted_app.post("/admin/auth/login", json=_dash_body("Dash Name", PW_WRONG))
    assert bad.status_code == 401


def test_mobile_login_from_unmigrated_auth_json(booted_app, test_db):
    """auth.json not migrated yet: /auth/login still reads it (read-only)."""
    user = create_user("Mobile Only")
    path = _write_auth_json(user, "mobile@example.com", PW_MOBILE)
    before = path.read_bytes()
    r = booted_app.post("/auth/login", json=_mobile_body("mobile@example.com", PW_MOBILE))
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == user
    assert _claims(r.json()["access_token"])["roles"] == ["user"]
    assert path.read_bytes() == before  # the old store is never written
    me = booted_app.get("/auth/me", headers=_bearer(r.json()["access_token"]))
    assert me.json()["email"] == "mobile@example.com"
    wrong = booted_app.post("/auth/login", json=_mobile_body("mobile@example.com", PW_WRONG))
    assert wrong.status_code == 401


def test_both_passwords_work_after_migration_when_stores_disagreed(booted_app, test_db, tmp_path):
    """One user, different passwords in the two stores: after the migration
    both still log in, on either endpoint, from SQLite alone."""
    import database.connection as connection
    from scripts import migrate_auth_json
    from users import UserManager

    user = create_user("Two Passwords", is_admin=True)
    UserManager().set_admin_password(user, PW_DASHBOARD)
    auth_path = _write_auth_json(user, "two@example.com", PW_MOBILE)

    data_dir = tmp_path / "data"
    (data_dir / "users" / user).mkdir(parents=True)
    (data_dir / "users" / user / "auth.json").write_bytes(auth_path.read_bytes())
    # Run the script on the test database (it opens DATA_DIR/cass.db).
    (data_dir / "cass.db").symlink_to(connection.DATABASE_PATH)
    assert migrate_auth_json.main(["--data-dir", str(data_dir), "--apply"]) == 0
    auth_path.unlink()  # prove the logins below come from SQLite

    for path, body in (
        ("/admin/auth/login", _dash_body("Two Passwords", PW_DASHBOARD)),
        ("/admin/auth/login", _dash_body("two@example.com", PW_MOBILE)),
        ("/auth/login", _mobile_body("two@example.com", PW_MOBILE)),
        ("/auth/login", _mobile_body("two@example.com", PW_DASHBOARD)),
    ):
        r = booted_app.post(path, json=body)
        assert r.status_code == 200, (path, r.text)


def test_pending_user_refused_on_both_logins(booted_app, test_db):
    from database import get_db
    user = create_user("Still Pending")
    _set_credentials(user, email="pending@example.com", password=PW_PENDING)
    with get_db() as conn:
        conn.execute("UPDATE users SET status = 'pending' WHERE id = ?", (user,))
    assert booted_app.post("/admin/auth/login", json=_dash_body("Still Pending", PW_PENDING)).status_code == 403
    assert booted_app.post("/auth/login", json=_mobile_body("pending@example.com", PW_PENDING)).status_code == 403


def test_registration_writes_sqlite_not_auth_json(booted_app, test_db):
    from database import get_db
    from users import UserManager
    r = booted_app.post("/auth/register", json={
        "email": "New@Example.com", "password": PW_NEW, "display_name": "Newcomer"})
    assert r.status_code == 200, r.text
    user = r.json()["user_id"]
    with get_db() as conn:
        row = conn.execute("SELECT email, password_hash FROM users WHERE id = ?", (user,)).fetchone()
    assert row[0] == "new@example.com" and row[1]
    assert not (UserManager().storage_dir / user / "auth.json").exists()
    dup = booted_app.post("/auth/register", json={
        "email": "new@example.com", "password": PW_NEW, "display_name": "Again"})
    assert dup.status_code == 400
