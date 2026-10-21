"""
scripts/cass_chat.py: authenticate as the Daedalus user with a live token.

After the ownership checks (#73), `cass_chat.py list` got 403: it sent an
expired token (so the server saw the localhost default user) and asked for
the Daedalus user's conversations by id. It now refreshes an expiring token
and lets the server scope requests to the token's own user.
"""
import importlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def cass_chat(tmp_path, monkeypatch):
    pytest.importorskip("requests")
    pytest.importorskip("jwt")
    monkeypatch.syspath_prepend(str(SCRIPTS))
    mod = importlib.import_module("cass_chat")
    import daedalus_auth
    creds_file = tmp_path / "daedalus_credentials.json"
    for m in (mod, daedalus_auth):
        monkeypatch.setattr(m, "CREDENTIALS_FILE", creds_file)
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(daedalus_auth, "get_jwt_secret", lambda: "test-secret")
    mod._creds_file = creds_file
    return mod


class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def _write_creds(path, **extra):
    creds = {"user_id": "daedalus-id", "display_name": "Daedalus", "password": "x", **extra}
    path.write_text(json.dumps(creds))


def test_expired_token_is_refreshed_before_use(cass_chat, monkeypatch):
    expired = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    _write_creds(cass_chat._creds_file, token="old", token_expires=expired)

    headers = cass_chat.get_auth_headers()

    assert headers["Authorization"] != "Bearer old"
    stored = json.loads(cass_chat._creds_file.read_text())
    assert headers["Authorization"] == f"Bearer {stored['token']}"
    assert datetime.fromisoformat(stored["token_expires"]) > datetime.utcnow()


def test_valid_token_is_reused(cass_chat):
    later = (datetime.utcnow() + timedelta(hours=10)).isoformat()
    _write_creds(cass_chat._creds_file, token="good", token_expires=later)
    assert cass_chat.get_auth_headers() == {"Authorization": "Bearer good"}


def test_list_lets_the_server_scope_to_the_token_user(cass_chat, monkeypatch):
    later = (datetime.utcnow() + timedelta(hours=10)).isoformat()
    _write_creds(cass_chat._creds_file, token="good", token_expires=later)
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers))
        return _Resp({"conversations": [{"id": "c1", "title": "t"}], "count": 1})

    monkeypatch.setattr(cass_chat.requests, "get", fake_get)
    result = cass_chat.list_conversations(limit=5)

    assert result == {"success": True, "conversations": [{"id": "c1", "title": "t"}]}
    url, params, headers = calls[0]
    assert url.endswith("/conversations")
    assert "user_id" not in params
    assert headers == {"Authorization": "Bearer good"}


def test_ensure_user_set_sends_own_id_with_token(cass_chat, monkeypatch):
    later = (datetime.utcnow() + timedelta(hours=10)).isoformat()
    _write_creds(cass_chat._creds_file, token="good", token_expires=later)
    posts = []
    monkeypatch.setattr(cass_chat.requests, "get",
                        lambda url, headers=None, timeout=None: _Resp({"user_id": "daedalus-id"}))
    monkeypatch.setattr(cass_chat.requests, "post",
                        lambda url, json=None, headers=None, timeout=None: posts.append((url, json, headers)) or _Resp({}))

    cass_chat.ensure_user_set()

    url, body, headers = posts[0]
    assert url.endswith("/users/current")
    assert body == {"user_id": "daedalus-id"}
    assert headers == {"Authorization": "Bearer good"}
