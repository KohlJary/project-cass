"""
Focused tests for the security lockdown: file roots, git option injection,
attachment traversal, read_file denials, bootstrap lockout, JWT secrets,
demo mode.
"""
import asyncio
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import HTTPException


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """An allowed root (via CASS_FILE_ROOTS) and a sibling dir outside it."""
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    monkeypatch.setenv("CASS_FILE_ROOTS", str(allowed))
    return allowed, outside


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# /files root restriction
# ---------------------------------------------------------------------------

class TestFilesRoots:
    def test_read_inside_root_works(self, roots):
        from routes.files import read_file
        allowed, _ = roots
        (allowed / "notes.txt").write_text("hello")
        result = _run(read_file(str(allowed / "notes.txt")))
        assert result["content"] == "hello"

    def test_read_outside_root_is_forbidden(self, roots):
        from routes.files import read_file
        _, outside = roots
        (outside / "secret.txt").write_text("nope")
        with pytest.raises(HTTPException) as exc:
            _run(read_file(str(outside / "secret.txt")))
        assert exc.value.status_code == 403

    def test_dotdot_escape_is_forbidden(self, roots):
        from routes.files import read_file
        allowed, outside = roots
        (outside / "x.txt").write_text("nope")
        with pytest.raises(HTTPException) as exc:
            _run(read_file(str(allowed / ".." / "outside" / "x.txt")))
        assert exc.value.status_code == 403

    def test_symlink_escape_is_forbidden(self, roots):
        from routes.files import read_file
        allowed, outside = roots
        (outside / "x.txt").write_text("nope")
        (allowed / "link.txt").symlink_to(outside / "x.txt")
        with pytest.raises(HTTPException) as exc:
            _run(read_file(str(allowed / "link.txt")))
        assert exc.value.status_code == 403

    def test_env_file_inside_root_is_forbidden(self, roots):
        from routes.files import read_file
        allowed, _ = roots
        (allowed / ".env").write_text("ANTHROPIC_API_KEY=sk-...")
        with pytest.raises(HTTPException) as exc:
            _run(read_file(str(allowed / ".env")))
        assert exc.value.status_code == 403

    def test_delete_outside_root_is_forbidden(self, roots):
        from routes.files import delete_path, DeleteRequest
        _, outside = roots
        victim = outside / "keep-me"
        victim.mkdir()
        with pytest.raises(HTTPException) as exc:
            _run(delete_path(DeleteRequest(path=str(victim), recursive=True)))
        assert exc.value.status_code == 403
        assert victim.exists()

    def test_list_hides_secret_files(self, roots):
        from routes.files import list_directory
        allowed, _ = roots
        (allowed / "auth.json").write_text("{}")
        (allowed / "server.key").write_text("k")
        (allowed / "readme.md").write_text("r")
        result = _run(list_directory(str(allowed), include_hidden=True))
        names = {e["name"] for e in result["entries"]}
        assert names == {"readme.md"}

    def test_max_size_cannot_be_lifted_past_cap(self, roots, monkeypatch):
        import routes.files as files
        allowed, _ = roots
        (allowed / "big.txt").write_text("x" * 100)
        monkeypatch.setattr(files, "MAX_READ_SIZE", 10)
        with pytest.raises(HTTPException) as exc:
            _run(files.read_file(str(allowed / "big.txt"), max_size=10**9))
        assert exc.value.status_code == 400

    def test_project_working_directory_is_an_allowed_root(self, tmp_path, monkeypatch, seeded_users):
        from path_policy import check_path
        from projects import ProjectManager
        monkeypatch.delenv("CASS_FILE_ROOTS", raising=False)
        proj = tmp_path / "myproj"
        proj.mkdir()
        (proj / "a.py").write_text("print(1)")
        ProjectManager().create_project(name="p", working_directory=str(proj), user_id="user-1")
        assert check_path(str(proj / "a.py")) == (proj / "a.py").resolve()


# ---------------------------------------------------------------------------
# /git
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(roots):
    allowed, _ = roots
    path = allowed / "repo"
    path.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "f.txt").write_text("1")
    subprocess.run(["git", "-C", str(path), "add", "f.txt"], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True, env=env)
    return path


class TestGit:
    def test_status_inside_root_works(self, repo):
        from routes.git import get_status
        result = _run(get_status(str(repo)))
        assert result["clean"] is True

    def test_repo_outside_roots_is_forbidden(self, roots):
        from routes.git import get_status
        _, outside = roots
        subprocess.run(["git", "init", "-q", str(outside)], check=True)
        with pytest.raises(HTTPException) as exc:
            _run(get_status(str(outside)))
        assert exc.value.status_code == 403

    @pytest.mark.parametrize("branch", ["--orphan=evil", "-b", "--upload-pack=touch /tmp/pwn"])
    def test_checkout_rejects_option_injection(self, repo, branch):
        from routes.git import checkout_branch
        with pytest.raises(HTTPException) as exc:
            _run(checkout_branch(str(repo), branch))
        assert exc.value.status_code == 400

    def test_stage_rejects_option_injection(self, repo):
        from routes.git import stage_files, StageRequest
        with pytest.raises(HTTPException) as exc:
            _run(stage_files(StageRequest(repo_path=str(repo), files=["--chmod=+x"])))
        assert exc.value.status_code == 400

    def test_diff_rejects_option_injection(self, repo, tmp_path):
        from routes.git import get_diff
        target = tmp_path / "written-by-git"
        with pytest.raises(HTTPException):
            _run(get_diff(str(repo), file=f"--output={target}"))
        assert not target.exists()

    def test_commit_message_starting_with_dash_is_literal(self, repo):
        from routes.git import create_commit, stage_files, CommitRequest, StageRequest
        (repo / "f.txt").write_text("2")
        _run(stage_files(StageRequest(repo_path=str(repo), files=["f.txt"])))
        env_backup = dict(os.environ)
        os.environ.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        try:
            import routes.git as git_routes
            git_routes._GIT_ENV.update(os.environ)
            _run(create_commit(CommitRequest(repo_path=str(repo), message="--amend")))
        finally:
            os.environ.clear()
            os.environ.update(env_backup)
        log = subprocess.run(["git", "-C", str(repo), "log", "--format=%s"],
                             capture_output=True, text=True).stdout.split("\n")
        assert log[0] == "--amend" and "init" in log

    def test_git_has_timeout(self, repo, monkeypatch):
        import routes.git as git_routes

        def hang(*args, **kwargs):
            assert kwargs.get("timeout"), "git must run with a timeout"
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

        monkeypatch.setattr(git_routes.subprocess, "run", hang)
        with pytest.raises(HTTPException) as exc:
            git_routes.run_git(str(repo), ["status"])
        assert exc.value.status_code == 504


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

class TestAttachments:
    @pytest.mark.parametrize("bad", ["../../etc", "..", "a/b", "x" * 65, "foo\\bar"])
    def test_conversation_id_traversal_rejected(self, bad):
        from routes.attachments import _validate_conversation_id
        with pytest.raises(HTTPException) as exc:
            _validate_conversation_id(bad)
        assert exc.value.status_code == 400

    def test_valid_conversation_id_accepted(self):
        from routes.attachments import _validate_conversation_id
        cid = str(uuid.uuid4())
        assert _validate_conversation_id(cid) == cid

    def test_storage_refuses_path_outside_base(self, tmp_path):
        from attachments import PersistentAttachmentStorage
        storage = PersistentAttachmentStorage.__new__(PersistentAttachmentStorage)
        storage.base_dir = tmp_path / "attachments"
        storage.base_dir.mkdir()
        with pytest.raises(ValueError):
            storage._get_file_path("x.png", "../../escaped")
        assert not (tmp_path / "escaped").exists()

    def test_upload_requires_auth(self, monkeypatch):
        """Upload used to call get_current_user() directly, which never raised."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import routes.attachments as att
        monkeypatch.setenv("ALLOW_LOCALHOST_BYPASS", "false")
        app = FastAPI()
        app.include_router(att.router)
        client = TestClient(app)
        r = client.post("/attachments/upload", files={"file": ("a.txt", b"hi", "text/plain")})
        assert r.status_code == 401
        r = client.delete("/attachments/abc")
        assert r.status_code == 401

    def test_delete_checks_conversation_owner(self, seeded_users):
        from routes.attachments import _user_may_touch_conversation
        from conversations import ConversationManager
        conv = ConversationManager().create_conversation(user_id="user-1")
        assert _user_may_touch_conversation(conv.id, "user-1") is True
        assert _user_may_touch_conversation(conv.id, "user-2") is False
        assert _user_may_touch_conversation(None, "user-2") is True


# ---------------------------------------------------------------------------
# Cass's read_file / list_directory tools
# ---------------------------------------------------------------------------

class TestReadFileTool:
    def _call(self, name, **tool_input):
        from handlers.documents import execute_file_tool
        return _run(execute_file_tool(name, tool_input))

    def test_reads_file_in_allowed_root(self, roots):
        allowed, _ = roots
        (allowed / "code.py").write_text("x = 1\n")
        result = self._call("read_file", file_path=str(allowed / "code.py"))
        assert result["success"] and "x = 1" in result["result"]

    @pytest.mark.parametrize("name", [".env", ".env.local", "auth.json", "id_rsa",
                                      "server.pem", "jwt_secret.txt",
                                      "daedalus_credentials.json"])
    def test_secret_files_denied_even_inside_root(self, roots, name):
        allowed, _ = roots
        (allowed / name).write_text("secret")
        result = self._call("read_file", file_path=str(allowed / name))
        assert result["success"] is False
        assert "Access denied" in result["error"]

    def test_outside_roots_denied(self, roots):
        _, outside = roots
        (outside / "x.txt").write_text("x")
        result = self._call("read_file", file_path=str(outside / "x.txt"))
        assert result["success"] is False and "Access denied" in result["error"]

    def test_etc_passwd_denied(self, roots):
        result = self._call("read_file", file_path="/etc/passwd")
        assert result["success"] is False and "Access denied" in result["error"]

    def test_backend_env_denied(self):
        """The real backend/.env sits inside the repo root but must stay unreadable."""
        backend_env = Path(__file__).resolve().parent.parent / ".env"
        result = self._call("read_file", file_path=str(backend_env))
        assert result["success"] is False and "Access denied" in result["error"]

    def test_users_auth_json_in_data_dir_denied(self):
        from config import DATA_DIR
        target = Path(DATA_DIR) / "users" / "someone" / "auth.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"password_hash": "x"}')
        result = self._call("read_file", file_path=str(target))
        assert result["success"] is False and "Access denied" in result["error"]

    def test_list_directory_outside_roots_denied_and_hides_secrets(self, roots):
        allowed, outside = roots
        (allowed / ".env").write_text("x")
        (allowed / "ok.txt").write_text("x")
        assert self._call("list_directory", directory_path=str(outside))["success"] is False
        listing = self._call("list_directory", directory_path=str(allowed))
        assert "ok.txt" in listing["result"] and ".env" not in listing["result"]


# ---------------------------------------------------------------------------
# Bootstrap lockout
# ---------------------------------------------------------------------------

def _insert_user(name, is_admin=0, password_hash=None):
    from database import get_db
    uid = str(uuid.uuid4())
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (id, display_name, is_admin, password_hash, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)", (uid, name, is_admin, password_hash, now, now))
    return uid


@pytest.fixture
def admin_auth(monkeypatch):
    import routes.admin.auth as admin_auth
    from users import UserManager
    monkeypatch.setattr(admin_auth, "_users", UserManager())
    monkeypatch.setattr(admin_auth, "_bootstrap_token", None)
    return admin_auth


class TestBootstrap:
    def test_requires_logged_token(self, admin_auth):
        _insert_user("first")
        req = admin_auth.BootstrapRequest(username="first", password="pw123456", bootstrap_token="guess")
        with pytest.raises(HTTPException) as exc:
            _run(admin_auth.bootstrap_admin(req))
        assert exc.value.status_code == 403

    def test_works_once_with_token_then_locks(self, admin_auth):
        _insert_user("first")
        token = admin_auth.init_bootstrap_token()
        assert token
        req = admin_auth.BootstrapRequest(username="first", password="pw123456", bootstrap_token=token)
        assert _run(admin_auth.bootstrap_admin(req))["status"] == "ok"

        # Now an admin with a password exists: locked, even with the old token.
        _insert_user("second")
        again = admin_auth.BootstrapRequest(username="second", password="pw123456", bootstrap_token=token)
        with pytest.raises(HTTPException) as exc:
            _run(admin_auth.bootstrap_admin(again))
        assert exc.value.status_code == 403

    def test_cannot_hijack_existing_install(self, admin_auth):
        _insert_user("owner", is_admin=1, password_hash="hash")
        _insert_user("attacker")
        assert admin_auth.init_bootstrap_token() is None
        req = admin_auth.BootstrapRequest(username="attacker", password="pw123456", bootstrap_token="")
        with pytest.raises(HTTPException) as exc:
            _run(admin_auth.bootstrap_admin(req))
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# JWT secret persistence
# ---------------------------------------------------------------------------

class TestSecrets:
    @pytest.fixture
    def store(self, tmp_path, monkeypatch):
        import secret_store
        monkeypatch.setattr(secret_store, "DATA_DIR", tmp_path)
        return secret_store

    def test_generates_and_persists(self, store, tmp_path, monkeypatch):
        monkeypatch.delenv("X_TEST_SECRET", raising=False)
        first = store.get_or_create_secret("t", "X_TEST_SECRET")
        second = store.get_or_create_secret("t", "X_TEST_SECRET")
        assert first == second and len(first) == 64
        path = tmp_path / ".secrets" / "t"
        assert path.read_text() == first
        assert oct(path.stat().st_mode)[-3:] == "600"

    def test_env_var_wins(self, store, monkeypatch):
        monkeypatch.setenv("X_TEST_SECRET", "explicit-value")
        assert store.get_or_create_secret("t", "X_TEST_SECRET") == "explicit-value"

    @pytest.mark.parametrize("placeholder", ["CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND",
                                             "change_this_in_production_use_openssl_rand_hex_32"])
    def test_placeholder_is_ignored(self, store, monkeypatch, placeholder):
        monkeypatch.setenv("X_TEST_SECRET", placeholder)
        assert store.get_or_create_secret("t", "X_TEST_SECRET") != placeholder

    def test_auth_module_does_not_use_public_constant(self):
        import auth
        assert not auth.SECRET_KEY.startswith("CHANGE_ME")

    def test_admin_secret_is_persisted_not_per_process(self):
        from config import DATA_DIR
        import routes.admin.auth as admin_auth
        if os.getenv("ADMIN_JWT_SECRET"):
            pytest.skip("explicit secret configured")
        stored = (Path(DATA_DIR) / ".secrets" / "admin_jwt_secret").read_text().strip()
        assert admin_auth.JWT_SECRET == stored


# ---------------------------------------------------------------------------
# Tokens from either auth system, demo mode
# ---------------------------------------------------------------------------

class TestTokensAndDemo:
    def test_admin_dashboard_token_accepted_by_get_current_user(self):
        from auth import user_id_from_any_token
        from routes.admin.auth import create_token
        token, _ = create_token("u-123", "u", False)
        assert user_id_from_any_token(token) == "u-123"

    def test_refresh_token_is_not_an_access_token(self):
        from auth import user_id_from_any_token, create_refresh_token
        assert user_id_from_any_token(create_refresh_token("u-1")) is None

    def test_demo_mode_require_admin_is_read_only(self, monkeypatch):
        import routes.admin.auth as admin_auth
        from unittest.mock import Mock
        monkeypatch.setattr(admin_auth, "DEMO_MODE", True)
        get = Mock(method="GET")
        post = Mock(method="POST")
        assert _run(admin_auth.require_admin(get, None))["demo_mode"] is True
        with pytest.raises(HTTPException) as exc:
            _run(admin_auth.require_admin(post, None))
        assert exc.value.status_code == 401

    def test_demo_mode_guard_blocks_anonymous_writes_and_dangerous_reads(self, monkeypatch):
        import config
        from fastapi.testclient import TestClient
        from main_sdk import app
        monkeypatch.setattr(config, "DEMO_MODE", True)
        monkeypatch.delenv("DEFAULT_LOCALHOST_USER_ID", raising=False)
        client = TestClient(app, raise_server_exceptions=False)
        assert client.post("/admin/thymos/reset").status_code == 403
        assert client.delete("/journal/2024-01-01").status_code == 403
        assert client.get("/files/list", params={"path": "/"}).status_code == 401
        assert client.get("/export/users/json").status_code == 401
        # require_admin itself would hand this GET a demo principal; the guard
        # must still refuse it because /admin/daemons is a dangerous prefix.
        assert client.get("/admin/daemons/x").status_code == 401
        assert client.post("/admin/daemons/x/export").status_code == 401

    def test_demo_mode_graphql_mutation_blocked(self, monkeypatch):
        import config
        from fastapi.testclient import TestClient
        from main_sdk import app
        monkeypatch.setattr(config, "DEMO_MODE", True)
        monkeypatch.delenv("DEFAULT_LOCALHOST_USER_ID", raising=False)
        client = TestClient(app, raise_server_exceptions=False)
        ok = client.post("/graphql", json={"query": "{ __typename }"})
        assert ok.status_code == 200 and ok.json()["data"]["__typename"] == "Query"
        bad = client.post("/graphql", json={"query": 'mutation { deletePeopledexEntity(entityId: "x") { success } }'})
        body = bad.json()
        assert body.get("data") is None and "read-only" in str(body.get("errors"))

    def test_non_admin_token_cannot_reach_admin_routes(self):
        from fastapi.testclient import TestClient
        from main_sdk import app
        from auth import create_access_token
        uid = _insert_user("plain-user")
        client = TestClient(app, raise_server_exceptions=False)
        headers = {"Authorization": f"Bearer {create_access_token(uid)}"}
        assert client.get("/files/list", params={"path": "/"}, headers=headers).status_code == 403
        assert client.post("/terminal/send/daedalus-x", headers=headers).status_code == 403
        assert client.post("/testing/rollback/execute", headers=headers).status_code == 403
