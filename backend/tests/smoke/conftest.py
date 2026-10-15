"""
Fixtures for the smoke batteries (tests/smoke/).

Every test in this directory gets the `smoke` marker, the fake LLM, fake
embeddings, and a network guard (any outbound TCP connection fails the test).
"""
import socket
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


def pytest_collection_modifyitems(config, items):
    for item in items:
        if Path(str(item.fspath)).resolve().is_relative_to(Path(__file__).parent):
            item.add_marker(pytest.mark.smoke)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail loudly if anything tries to open an internet socket."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guard(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise ConnectionRefusedError(f"network blocked in smoke tests: {address!r}")

    def connect(self, address):
        guard(self, address)
        return real_connect(self, address)

    def connect_ex(self, address):
        guard(self, address)
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)


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


@pytest.fixture
def booted_app(test_db):
    """Boot main_sdk's FastAPI app under TestClient and wait for deferred init.

    main_sdk keeps module globals across tests, so the readiness markers are
    reset first; otherwise a second boot would look ready before it is.
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
