"""
The house GPU broker (gpu-broker, Kohl's fork with `runner: service`; Kohl, 2026-11-19).

One 16 GB card, shared by Ollama, ComfyUI and ACE-Step. With the `gpu_broker` lever on, the
coordinator asks the broker for a session instead of freeing memory itself: the broker stops the
resident LLM, frees ComfyUI, starts the program's unit if it's a service (ACE-Step), and hands the
card back when the session ends. ACE-Step's and ComfyUI's own APIs are still called directly; the
broker only decides who holds the card.

    async with broker_session("acestep"):
        ...render...

Config: GPU_BROKER_URL (default http://127.0.0.1:8095) and GPU_BROKER_TOKEN in the environment.
The broker's catalog names the programs (acestep, comfyui); see ~/gpu-broker-house/catalog.yaml.

Ollama is not behind the broker yet: while a session holds the card Ollama is stopped, so a direct
local call in that window fails like any Ollama outage. Routing those calls through the broker is
the next step.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from typing import AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)

LEVER = "gpu_broker"
DEFAULT_URL = "http://127.0.0.1:8095"
POLL_S = 1.0
REQUEST_TIMEOUT_S = 10.0
TERMINAL = {"done", "failed", "rejected", "cancelled"}


class BrokerError(RuntimeError):
    """The broker refused, failed, or didn't hand over the card in time."""


def enabled() -> bool:
    try:
        from features import is_enabled
        if not is_enabled(LEVER):
            return False
    except Exception:
        return False
    return bool(os.environ.get("GPU_BROKER_TOKEN"))


def _url() -> str:
    return os.environ.get("GPU_BROKER_URL", DEFAULT_URL).rstrip("/")


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ.get('GPU_BROKER_TOKEN', '')}"}


@contextlib.asynccontextmanager
async def broker_session(model: str, idle_min: float = 2.0, max_wait: float = 300.0,
                         client: Optional[httpx.AsyncClient] = None) -> AsyncIterator[str]:
    """Hold the card for `model` (a broker catalog key) for the duration of the block.

    Waits until the broker reports the session running (it may queue behind other work and has to
    stop and start units), then yields the session's job id. On exit the session is ended at once,
    if it is still ours, so the card goes back without waiting out the idle timer. The broker has no
    cancel: a session that starts after we gave up waiting ends on its own after `idle_min`."""
    own = client is None
    c = client or httpx.AsyncClient(base_url=_url(), headers=_headers(), timeout=REQUEST_TIMEOUT_S)
    jid: Optional[str] = None
    try:
        r = await c.post("/v1/sessions", json={"model": model, "idle_min": idle_min, "requester": "cass-vessel"})
        if r.status_code != 200:
            raise BrokerError(f"broker refused a {model} session: {r.status_code} {r.text[:200]}")
        session_id: str = r.json()["id"]
        jid = session_id
        start = time.monotonic()
        while True:
            st = (await c.get("/v1/status")).json()
            if (st.get("session") or {}).get("job") == jid:
                break
            job = (await c.get(f"/v1/jobs/{jid}")).json()
            if job.get("state") in TERMINAL:
                raise BrokerError(f"{model} session {job.get('state')}: {job.get('error') or ''}".strip())
            if time.monotonic() - start > max_wait:
                raise BrokerError(f"timed out after {max_wait:.0f}s waiting for the card for {model}")
            await asyncio.sleep(POLL_S)
        logger.info(f"[gpu_broker] {model} has the card (waited {time.monotonic() - start:.1f}s)")
        yield session_id
    finally:
        if jid is not None:
            with contextlib.suppress(Exception):
                st = (await c.get("/v1/status")).json()
                if (st.get("session") or {}).get("job") == jid:
                    await c.post("/v1/sessions/end")
        if own:
            await c.aclose()


# --- Her local model, behind the broker (2026-11-24) ------------------------------------------
#
# Ollama is the broker's resident: always up, stopped only while a ComfyUI or ACE-Step session
# holds the card. Her Ollama calls used to go straight to :11434, so during her own image or song
# work they failed (and her local-first jobs quietly fell back to Haiku), and a session starting
# mid-call could kill one. Now every Ollama call holds a shared LLM lease: the first call opens a
# broker session for LLM_KEY, calls running at the same time share it (nothing of hers queues
# behind another of her calls), and it's released GRACE_S after the last one ends. Image and song
# work waits for her calls; her calls wait (up to LLM_MAX_WAIT_S) for a running image or song job.
# Lever off or no token: a no-op.

LLM_KEY = os.environ.get("GPU_BROKER_LLM_KEY", "llama31")
LLM_MAX_WAIT_S = float(os.environ.get("GPU_BROKER_LLM_MAX_WAIT", "240"))
GRACE_S = float(os.environ.get("GPU_BROKER_LLM_GRACE", "10"))


class _LLMLease:
    def __init__(self, session=None):
        self._session = session or broker_session
        self._ctx = None
        self._count = 0
        self._lock: Optional[asyncio.Lock] = None
        self._release: Optional[asyncio.Task] = None
        self.opened = 0  # broker sessions opened (for tests and logs)

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @contextlib.asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        if not enabled():
            yield
            return
        async with self._get_lock():
            if self._release is not None:
                self._release.cancel()
                self._release = None
            if self._ctx is None:
                ctx = self._session(LLM_KEY, idle_min=2.0, max_wait=LLM_MAX_WAIT_S)
                await ctx.__aenter__()  # BrokerError if the card isn't ours in time
                self._ctx = ctx
                self.opened += 1
            self._count += 1
        try:
            yield
        finally:
            async with self._get_lock():
                self._count -= 1
                if self._count == 0:
                    self._release = asyncio.ensure_future(self._release_later())

    async def _release_later(self) -> None:
        try:
            await asyncio.sleep(GRACE_S)
        except asyncio.CancelledError:
            return
        async with self._get_lock():
            if self._count == 0 and self._ctx is not None:
                ctx, self._ctx = self._ctx, None
                with contextlib.suppress(Exception):
                    await ctx.__aexit__(None, None, None)


_lease = _LLMLease()


def llm_lease():
    """`async with llm_lease():` around an Ollama call."""
    return _lease.hold()


NON_LLM_KINDS = ("comfyui", "acestep")


def wait_for_llm_sync(max_wait: Optional[float] = None, sleep=time.sleep, get=None) -> None:
    """For blocking callers (threads): wait while an image or song session holds the card.
    Raises BrokerError if it's still held after max_wait. Lever off or no token: returns at once."""
    if not enabled():
        return
    max_wait = LLM_MAX_WAIT_S if max_wait is None else max_wait
    if get is None:
        def get():
            r = httpx.get(f"{_url()}/v1/status", headers=_headers(), timeout=REQUEST_TIMEOUT_S)
            return r.json()
    start = time.monotonic()
    while True:
        try:
            st = get()
        except Exception as e:  # the broker down shouldn't stop her thinking
            logger.warning(f"[gpu_broker] status unreachable ({e}); calling Ollama anyway")
            return
        model = ((st.get("session") or {}).get("model") or "")
        if model not in NON_LLM_KINDS:
            return
        if time.monotonic() - start > max_wait:
            raise BrokerError(f"the card is still held by {model} after {max_wait:.0f}s")
        sleep(POLL_S)
