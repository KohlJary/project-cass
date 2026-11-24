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
"""
from __future__ import annotations

import contextvars
import time
from typing import Any, Dict, List, Optional

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
