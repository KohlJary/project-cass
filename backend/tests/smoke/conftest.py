"""
Fixtures for the smoke batteries (tests/smoke/).

Every test in this directory gets the `smoke` marker, the fake LLM, fake
embeddings, and a network guard (any outbound TCP connection fails the test).
"""
import socket
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


def pytest_collection_modifyitems(config, items):
    for item in items:
        if Path(str(item.fspath)).resolve().is_relative_to(Path(__file__).parent):
            item.add_marker(pytest.mark.smoke)


_LOCAL_HOSTS = {None, "", "localhost", "127.0.0.1", "::1"}


def block_network(mp):
    """Make outbound internet access raise. `mp` is a pytest MonkeyPatch."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def guard(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise ConnectionRefusedError(f"network blocked in smoke tests: {address!r}")

    def connect(self, address):
        guard(self, address)
        return real_connect(self, address)

    def connect_ex(self, address):
        guard(self, address)
        return real_connect_ex(self, address)

    def getaddrinfo(host, *args, **kwargs):
        if host not in _LOCAL_HOSTS:
            raise socket.gaierror(f"DNS blocked in smoke tests: {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    mp.setattr(socket.socket, "connect", connect)
    mp.setattr(socket.socket, "connect_ex", connect_ex)
    mp.setattr(socket, "getaddrinfo", getaddrinfo)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail loudly if anything tries to reach the network."""
    block_network(monkeypatch)


@pytest.fixture(autouse=True)
def _smoke_fakes(fake_llm, fake_embeddings):
    """Every smoke test runs against the fake LLM and offline embeddings."""
    return fake_llm


def wait_until(predicate, timeout=60.0, interval=0.1, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError(f"timed out after {timeout}s waiting for {what}")


def backend_tasks(client):
    """Names of asyncio tasks in the app's loop whose code lives in backend/.

    Filters out anyio/starlette portal plumbing so what's left is Cass's own
    background work (loops, timers, fire-and-forget tasks).
    """
    import asyncio

    async def collect():
        names = []
        for task in asyncio.all_tasks():
            coro = task.get_coro()
            code = getattr(coro, "cr_code", None) or getattr(coro, "gi_code", None)
            filename = getattr(code, "co_filename", "")
            if filename and Path(filename).resolve().is_relative_to(BACKEND_DIR) \
                    and "/tests/" not in filename and not task.done():
                names.append(coro.__qualname__)
        return sorted(names)

    return client.portal.call(collect)


@contextmanager
def boot_app():
    """Boot main_sdk's FastAPI app under TestClient and wait for deferred init.

    Levers are read while booting, so wrap this in `levers(...)` to start a
    subsystem. main_sdk keeps module globals across tests, so the readiness
    markers are reset first; otherwise a second boot would look ready early.
    """
    from fastapi.testclient import TestClient
    import main_sdk
    import websocket_handlers
    from routes.admin import scheduler as scheduler_routes

    main_sdk.memory = None
    main_sdk.self_model_graph = None
    main_sdk._heavy_components_ready = False
    websocket_handlers._state["memory"] = None
    scheduler_routes._scheduler = None

    startup_tasks = ("init_heavy_background", "start_deferred_tasks")

    def startup_finished(client):
        if scheduler_routes.get_scheduler() is None:
            return False
        running = backend_tasks(client)
        return not any(name.endswith(startup_tasks) for name in running)

    with TestClient(main_sdk.app) as client:
        # Heavy init and deferred startup run as background tasks; wait until
        # both have finished so tests see the fully started app.
        wait_until(lambda: startup_finished(client), what="deferred startup")
        yield client


@pytest.fixture
def booted_app(test_db):
    """The app booted under the default CASS_PROFILE=test (every lever off)."""
    with boot_app() as client:
        yield client


@contextmanager
def module_app(template_db, tmp_path_factory, **lever_values):
    """Boot the app once for a whole test module, with some levers on.

    Use from a module-scoped fixture. Installs its own fakes and network guard
    (function fixtures aren't active yet at module scope) and points the DB at
    a module-wide copy. The module must also override `test_db` to return
    that same path, so the test thread and the app thread share one database:

        @pytest.fixture(scope="module")
        def app(template_db, tmp_path_factory):
            with module_app(template_db, tmp_path_factory, rss=True) as booted:
                yield booted

        @pytest.fixture
        def test_db(app):
            return app.db_path
    """
    import shutil
    import features
    from tests.conftest import _point_db_at
    from tests.fakes import embeddings, llm
    import database.connection as connection

    original = connection.DATABASE_PATH
    db_path = tmp_path_factory.mktemp("smoke_module") / "cass.db"
    shutil.copy(template_db, db_path)
    _point_db_at(db_path)
    try:
        with pytest.MonkeyPatch.context() as mp:
            block_network(mp)
            embeddings.install(mp)
            llm.install(llm.FakeLLM(), mp)
            with features.override(**lever_values):
                with boot_app() as client:
                    client.db_path = db_path
                    yield client
    finally:
        _point_db_at(original)


# ---------------------------------------------------------------------------
# Authentication (the app is default-deny: see route_guard.py)
# ---------------------------------------------------------------------------

def create_user(display_name="Smoke Tester", is_admin=False):
    """Insert a real user row and return its id."""
    import uuid
    from datetime import datetime
    from database import get_db

    user_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (id, display_name, is_admin, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, display_name, 1 if is_admin else 0, now, now),
        )
    return user_id


def access_token(user_id):
    """A valid access token for `user_id`, issued the way /auth/login issues it."""
    from auth import create_access_token
    return create_access_token(user_id)


@pytest.fixture
def smoke_user(test_db):
    """(user_id, token) for a regular logged-in user."""
    user_id = create_user()
    return user_id, access_token(user_id)


def admin_token(user_id, display_name="Smoke Admin"):
    """An admin-dashboard token (the kind /admin/auth/login issues).

    Routes that declare `require_admin` only accept this token family; the
    app-wide route guard accepts either family and checks users.is_admin.
    """
    from routes.admin.auth import create_token
    token, _expires = create_token(user_id, display_name, is_admin=True)
    return token


@pytest.fixture
def smoke_admin(test_db):
    """(user_id, admin-dashboard token) for an admin user."""
    user_id = create_user("Smoke Admin", is_admin=True)
    return user_id, admin_token(user_id)
