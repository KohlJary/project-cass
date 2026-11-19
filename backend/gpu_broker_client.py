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
