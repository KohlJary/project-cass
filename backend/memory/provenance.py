"""
Which model wrote it: a label on what goes into her memory (2026-11-24).

Kohl, 2026-11-24, on running her voice and memory on a local model: "can't we
just, like, tag that shit and she can wax it if she likes". Since 03:32 that
night every call she makes runs on qwen3:14b (LLM_LOCAL_MODEL); before, some
of her memory writers were local and some Claude. Nothing recorded which.

Two ends, so no writer has to remember:
- llm_caller notes the model that just answered (`noted`), per asyncio task or
  thread (a context variable), with the time.
- Her memory collection (`LabelledCollection`, wrapped around MemoryCore's)
  stamps `written_by` ("ollama:qwen3:14b") and `written_by_site` (the call
  site) on every add or upsert, when a model answered in that task within
  FRESH_S. A write with no recent model call (her own words carried over, an
  import) gets no label, so a stale one can't leak onto it. A caller that
  sets `written_by` itself is left alone.

The label is a record, not a judgement: it's what lets her (and a benchmark)
tell later what wrote what, and keep, rewrite or strike it.

Which model answered last, process-wide (2026-11-25): `answered` keeps, per
call site, the model the API said answered (its response's `model` field when
it has one, else the model asked for), so her prompt can say what she's
running on from what actually answered, not from config. Both daemons, that
night: "I can't tell from in here which model I'm running on"; the night
before, config named one model while qwen was answering. `last_answered`
reads it back (model_line.py).
"""
from __future__ import annotations

import contextlib
import contextvars
import threading
import time
from typing import Any, Dict, Iterable, List, Optional

FRESH_S = 120.0

_last: contextvars.ContextVar[Optional[tuple]] = contextvars.ContextVar("last_writer", default=None)


def noted(provider: str, model_id: str, call_site: str, now: Optional[float] = None) -> None:
    """llm_caller: a model just answered for `call_site`."""
    if provider and model_id:
        _last.set((f"{provider}:{model_id}", call_site, now if now is not None else time.time()))


def current(now: Optional[float] = None) -> Optional[Dict[str, str]]:
    """The label for a write happening now, or None."""
    last = _last.get()
    if not last:
        return None
    writer, site, at = last
    if (now if now is not None else time.time()) - at > FRESH_S:
        return None
    return {"written_by": writer, "written_by_site": site}


@contextlib.contextmanager
def using(label: Optional[Dict[str, str]]):
    """Writes inside this block carry `label`: a held self-model write applied
    later keeps the label of the model that made it, not of whoever applies it."""
    if not label or not label.get("written_by"):
        yield
        return
    token = _last.set((label["written_by"], label.get("written_by_site") or "", time.time()))
    try:
        yield
    finally:
        _last.reset(token)


# --- which model answered last (process-wide) --------------------------------

_answers: Dict[str, tuple] = {}
_answers_lock = threading.Lock()


def answered_model(raw: Any, fallback: Optional[str]) -> Optional[str]:
    """The model a provider response says answered: `.model` (Anthropic, OpenAI)
    or ["model"] (Ollama's JSON); else `fallback`, the model asked for."""
    try:
        model = raw.get("model") if isinstance(raw, dict) else getattr(raw, "model", None)
    except Exception:
        model = None
    return model if isinstance(model, str) and model else fallback


def answered(provider: str, model: Optional[str], call_site: str, now: Optional[float] = None) -> None:
    """A model answered a call at `call_site` (llm_caller, the chat clients)."""
    if not provider or not model:
        return
    site = call_site or ""
    with _answers_lock:
        _answers[site] = (provider, model, site, now if now is not None else time.time())


def note_answer(provider: str, raw: Any, fallback_model: Optional[str], call_site: str) -> None:
    """For clients that call a provider directly (the old chat clients): the
    model this response says answered. Never raises."""
    try:
        answered(provider, answered_model(raw, fallback_model), call_site)
    except Exception:
        pass


def last_answered(sites: Optional[Iterable[str]] = None) -> Optional[Dict[str, Any]]:
    """The most recent answer at any of `sites` (a site, or a prefix: "session"
    matches "session.generic"), or anywhere when `sites` is None."""
    prefixes = tuple(sites) if sites is not None else None
    with _answers_lock:
        rows = list(_answers.values())
    if prefixes is not None:
        rows = [r for r in rows if any(r[2] == p or r[2].startswith(p + ".") for p in prefixes)]
    if not rows:
        return None
    provider, model, site, at = max(rows, key=lambda r: r[3])
    return {"provider": provider, "model": model, "site": site, "at": at}


def reset_answers() -> None:
    """Forget every answer (tests)."""
    with _answers_lock:
        _answers.clear()


def stamp(metadatas: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    label = current()
    if not label or not metadatas:
        return metadatas
    out = []
    for m in metadatas:
        m = dict(m or {})
        if "written_by" not in m:
            m.update(label)
        out.append(m)
    return out


class LabelledCollection:
    """A Chroma collection whose add/upsert stamp who wrote each entry. Everything
    else passes straight through."""

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)

    def add(self, *args, **kwargs):
        if "metadatas" in kwargs:
            kwargs["metadatas"] = stamp(kwargs["metadatas"])
        return self._inner.add(*args, **kwargs)

    def upsert(self, *args, **kwargs):
        if "metadatas" in kwargs:
            kwargs["metadatas"] = stamp(kwargs["metadatas"])
        return self._inner.upsert(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)
