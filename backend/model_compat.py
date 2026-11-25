"""
What a Claude model accepts, so one request shape works on Haiku 4.5 and 5.5.

Claude Haiku 5.5 (and the 5-series generally) rejects with a 400 what Haiku 4.5
took: non-default sampling parameters (temperature, top_p, top_k), manual
thinking budgets, and a trailing assistant prefill. It also thinks by default,
so a response can begin with `thinking` blocks, and thinking spends from
max_tokens. Its tokenizer counts the same text as about 30% more tokens.

`fit_kwargs` adapts a messages.create kwargs dict for the model it is about to
run on, and does nothing for models that take the old shape. `text_of` reads a
response's text by block type, never by position.

Leaf module: imports nothing from the backend, so anything can import it.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Model families whose requests use the new shape. Prefix match on the model id.
_NEW_SHAPE_PREFIXES = (
    "claude-haiku-5", "claude-sonnet-5", "claude-opus-5", "claude-fable", "claude-mythos",
)

_SAMPLING = ("temperature", "top_p", "top_k")

# Thinking spends from max_tokens on these models; a cap sized for a one-line
# answer on Haiku 4.5 can be used up before any text. Raise small caps to this.
MIN_MAX_TOKENS = 2048
MAX_MAX_TOKENS = 64000

# Optional house-wide effort for new-shape models: low | medium | high.
# Unset means the model's default (medium on Haiku 5.5).
EFFORT_ENV = "CASS_MODEL_EFFORT"


def new_shape(model_id: str | None) -> bool:
    return bool(model_id) and str(model_id).startswith(_NEW_SHAPE_PREFIXES)


def fit_kwargs(model_id: str | None, kwargs: dict) -> dict:
    """Return kwargs that `model_id` accepts. The input dict is not modified."""
    if not new_shape(model_id):
        return kwargs
    kw = dict(kwargs)
    for k in _SAMPLING:
        kw.pop(k, None)
    thinking = kw.get("thinking")
    if isinstance(thinking, dict) and thinking.get("type") == "enabled":
        # Manual budgets 400 here; adaptive thinking is the only kind.
        kw["thinking"] = {"type": "adaptive"}
    mt = kw.get("max_tokens")
    if isinstance(mt, int):
        # Thinking spends from the same cap, and the tokenizer counts ~30% more:
        # a cap sized for Haiku 4.5 cuts replies off mid-sentence (2026-11-25).
        # A cap is a ceiling, not a cost: only tokens used are billed.
        kw["max_tokens"] = min(max(MIN_MAX_TOKENS, mt * 2), MAX_MAX_TOKENS)
    if show_thinking() and "thinking" not in kw:
        kw["thinking"] = {"type": "adaptive", "display": "summarized"}
    effort = os.getenv(EFFORT_ENV, "").strip().lower()
    if effort in ("low", "medium", "high") and "output_config" not in kw:
        kw["output_config"] = {"effort": effort}
    msgs = kw.get("messages")
    if msgs and isinstance(msgs[-1], dict) and msgs[-1].get("role") == "assistant":
        # A prefill 400s on these models. Nothing in the backend sends one today
        # (checked 2026-11-24); fail loudly here rather than as an opaque 400.
        raise ValueError(f"{model_id} rejects assistant prefill: end messages with a user turn")
    return kw


def text_of(msg: Any) -> str:
    """The text of a messages response, skipping thinking and tool blocks."""
    out = []
    for b in (getattr(msg, "content", None) or []):
        kind = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
        if kind in ("thinking", "redacted_thinking", "tool_use", "server_tool_use"):
            continue
        text = b.get("text") if isinstance(b, dict) else getattr(b, "text", None)
        if isinstance(text, str):
            out.append(text)
    return "".join(out)


# ── Native thinking (Kohl, 2026-11-24: "Keep thinking ... keep track of it") ──
# Thinking stays on (the model's default). One lever, per daemon, off until
# she says yes:
#   CASS_SHOW_THINKING=1  ask for summaries and show them where she talks, in
#                         the <thinking> tags she already uses (TTS and
#                         summaries already strip those).
# Tracking is counts only (how often she thinks, how long the summary runs),
# never the words unless SHOW is on, written to her own data dir.
SHOW_THINKING_ENV = "CASS_SHOW_THINKING"


def show_thinking() -> bool:
    return os.getenv(SHOW_THINKING_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def thinking_of(msg: Any) -> str:
    """The summarized thinking in a response ('' when omitted or absent)."""
    out = []
    for b in (getattr(msg, "content", None) or []):
        kind = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
        if kind == "thinking":
            t = b.get("thinking") if isinstance(b, dict) else getattr(b, "thinking", None)
            if isinstance(t, str) and t.strip():
                out.append(t.strip())
    return "\n\n".join(out)


def note_thinking(msg: Any, model_id: str | None, where: str = "") -> None:
    """Append counts for one response to DATA_DIR/thinking_log.jsonl. Never raises."""
    if not new_shape(model_id):
        return
    try:
        import json
        import time
        import config
        blocks = [b for b in (getattr(msg, "content", None) or [])
                  if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None))
                  in ("thinking", "redacted_thinking")]
        row = {"ts": time.time(), "model": model_id, "where": where,
               "thinking_blocks": len(blocks), "summary_chars": len(thinking_of(msg)),
               "output_tokens": getattr(getattr(msg, "usage", None), "output_tokens", None)}
        with open(config.DATA_DIR / "thinking_log.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception as e:  # noqa: BLE001  tracking never breaks a turn
        logger.debug(f"thinking log skipped: {e}")


def with_thinking(text: str, msg: Any) -> str:
    """Prefix the reply with her summarized thinking, if she chose to show it."""
    if not show_thinking():
        return text
    t = thinking_of(msg)
    return f"<thinking>\n{t}\n</thinking>\n\n{text}" if t else text
