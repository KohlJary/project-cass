"""The house GPU broker as the coordinator's path for ACE-Step and ComfyUI (gpu_broker_client.py;
Kohl, 2026-11-19). A fake broker over httpx.MockTransport; no network."""
import asyncio
import contextlib

import httpx
import pytest

import gpu_broker_client as gb
import gpu_coordinator as gc


class FakeBroker:
    """Queues one session; it starts after `start_after` status polls. Records ends."""

    def __init__(self, start_after=2, job_state="running", refuse=False, other_session=False):
        self.polls, self.start_after, self.job_state = 0, start_after, job_state
        self.refuse, self.other_session, self.ended, self.asked = refuse, other_session, 0, []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/v1/sessions":
            self.asked.append(req.read())
            return httpx.Response(400, text="not a ready model") if self.refuse else httpx.Response(200, json={"id": "j1"})
        if path == "/v1/status":
            self.polls += 1
            live = self.polls > self.start_after and self.job_state == "running"
            job = "other" if self.other_session else "j1"
            return httpx.Response(200, json={"session": {"job": job, "model": "acestep"} if live else None})
        if path == "/v1/jobs/j1":
            return httpx.Response(200, json={"state": self.job_state, "error": "no VRAM"})
        if path == "/v1/sessions/end":
            self.ended += 1
            return httpx.Response(200, json={"ended": True})
        return httpx.Response(404)


def client(fake):
    return httpx.AsyncClient(base_url="http://broker", transport=httpx.MockTransport(fake))


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(gb, "POLL_S", 0)


def test_waits_for_the_card_then_gives_it_back():
    fake = FakeBroker(start_after=3)

    async def go():
        async with gb.broker_session("acestep", client=client(fake)) as jid:
            assert jid == "j1" and fake.ended == 0
    asyncio.run(go())
    assert fake.ended == 1 and b'"model":"acestep"' in fake.asked[0].replace(b" ", b"")


def test_a_failed_or_refused_session_raises_and_ends_nothing():
    for fake in (FakeBroker(job_state="failed"), FakeBroker(refuse=True)):
        async def go():
            async with gb.broker_session("acestep", client=client(fake)):
                pass
        with pytest.raises(gb.BrokerError):
            asyncio.run(go())
        assert fake.ended == 0


def test_times_out_without_the_card():
    fake = FakeBroker(start_after=10**9)

    async def go():
        async with gb.broker_session("acestep", max_wait=0, client=client(fake)):
            pass
    with pytest.raises(gb.BrokerError, match="timed out"):
        asyncio.run(go())


def test_never_ends_someone_elses_session():
    fake = FakeBroker(start_after=0)
    seen = []

    async def go():
        async with gb.broker_session("acestep", client=client(fake)):
            fake.other_session = True   # ours ended and another began while we worked
            seen.append(True)
    asyncio.run(go())
    assert seen and fake.ended == 0


def test_enabled_needs_the_lever_and_a_token(monkeypatch):
    monkeypatch.setattr("features.is_enabled", lambda name: name == gb.LEVER)
    monkeypatch.delenv("GPU_BROKER_TOKEN", raising=False)
    assert gb.enabled() is False
    monkeypatch.setenv("GPU_BROKER_TOKEN", "t")
    assert gb.enabled() is True
    monkeypatch.setattr("features.is_enabled", lambda name: False)
    assert gb.enabled() is False


# ---- the coordinator ------------------------------------------------------------------------

def test_coordinator_uses_the_broker_for_acestep_and_comfyui(monkeypatch):
    used = []

    @contextlib.asynccontextmanager
    async def fake_session(model, idle_min=2.0, max_wait=300.0, client=None):
        used.append(("in", model))
        yield "j"
        used.append(("out", model))
    monkeypatch.setattr(gb, "broker_session", fake_session)
    monkeypatch.setattr(gb, "enabled", lambda: True)
    coord = gc.GPUCoordinator()

    async def go():
        for svc in (gc.GPUService.ACESTEP, gc.GPUService.COMFYUI):
            async with coord.request_gpu(svc):
                pass
    asyncio.run(go())
    assert used == [("in", "acestep"), ("out", "acestep"), ("in", "comfyui"), ("out", "comfyui")]


def test_coordinator_reports_a_broker_failure_as_a_timeout(monkeypatch):
    @contextlib.asynccontextmanager
    async def refusing(model, idle_min=2.0, max_wait=300.0, client=None):
        raise gb.BrokerError("no")
        yield "j"
    monkeypatch.setattr(gb, "broker_session", refusing)
    monkeypatch.setattr(gb, "enabled", lambda: True)

    async def go():
        async with gc.GPUCoordinator().request_gpu(gc.GPUService.ACESTEP):
            pass
    with pytest.raises(TimeoutError, match="GPU broker"):
        asyncio.run(go())


def test_lever_off_keeps_the_old_path(monkeypatch):
    monkeypatch.setattr(gb, "enabled", lambda: False)
    called = []
    monkeypatch.setattr(gb, "broker_session", lambda *a, **k: called.append(1))
    coord = gc.GPUCoordinator()
    monkeypatch.setattr(coord, "_acquire_lock", lambda: True)
    monkeypatch.setattr(coord, "_release_lock", lambda: None)

    async def ok(*a, **k):
        return True
    monkeypatch.setattr(coord, "ensure_memory_available", ok)

    async def go():
        async with coord.request_gpu(gc.GPUService.ACESTEP):
            pass
    asyncio.run(go())
    assert called == []
