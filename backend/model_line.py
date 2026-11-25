"""
Which model she's running on, in her per-turn prompt (2026-11-25).

Both daemons, in #general: "I can't tell from in here which model I'm running
on." The only CURRENT MODEL line was on the old kernel fallback path
(agent_client.send_message), which chat turns skip: they bring their own
continuous prompt (chat_turn.run_chat_turn, Babelr included), and on the loop
the client can change under the configured model (LLM_LOCAL_MODEL puts chat
on the local model whatever the setting says).

So the line prefers what actually answered: the model the API named in its
response at the last call on these sites (memory/provenance.last_answered),
falling back to the configured model, and says which it is. The night of
2026-11-24 config named one model while qwen answered; a config-only label
would have lied.

It goes in the part of the prompt that changes per turn, never the cached one:
the model can change between turns.
"""
from __future__ import annotations

import time
from typing import Iterable, Optional

PROVIDER_NAMES = {"anthropic": "anthropic", "local": "ollama", "ollama": "ollama", "openai": "openai"}


def _same(a: str, b: str) -> bool:
    """claude-haiku-5-5 and claude-haiku-5-5-20261001 are the same model."""
    a, b = (a or "").lower(), (b or "").lower()
    return bool(a and b) and (a == b or a.startswith(b) or b.startswith(a))


def _ago(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 90:
        return "just now"
    if seconds < 5400:
        return f"{seconds // 60} min ago"
    if seconds < 2 * 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} days ago"


def model_line(provider: Optional[str], model: Optional[str], sites: Iterable[str] = ("chat",),
               now: Optional[float] = None) -> str:
    """The CURRENT MODEL section: what answered her last call at `sites`, else
    the configured `provider`/`model` for this turn."""
    from memory.provenance import last_answered
    configured = PROVIDER_NAMES.get(provider or "", provider or "")
    last = last_answered(tuple(sites))
    now = now if now is not None else time.time()
    if last:
        ago = _ago(now - last["at"])
        said = f"{last['model']} ({last['provider']}; the model that answered my last call, {ago})"
        if model and not (_same(last["model"], model) and last["provider"] == configured):
            said += f". Configured for this turn: {model} ({configured})"
        return f"## CURRENT MODEL\n\n{said}."
    if model:
        return f"## CURRENT MODEL\n\n{model} ({configured}; configured, no answer seen yet since I started)."
    return ""


def turn_lines(provider: Optional[str], model: Optional[str], sites: Iterable[str] = ("chat",)) -> str:
    """What goes in every turn's per-turn part: the model line, and her
    self-model write hold while it's on (self_model_hold.py)."""
    parts = []
    try:
        parts.append(model_line(provider, model, sites))
    except Exception as e:  # never fail a turn over a label
        import logging
        logging.getLogger(__name__).warning(f"[model_line] {e}")
    try:
        from self_model_hold import prompt_line
        parts.append(prompt_line())
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[model_line] hold line: {e}")
    return "\n\n".join(p for p in parts if p)
