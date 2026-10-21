"""
assemble(spec, trigger): the one function that builds a turn's system prompt.

It reuses what already exists rather than building anything new:
  - kernel + identity snippet   agent_client.get_temple_codex_kernel
  - seam block                  agent_loop.seam (from the spec)
  - her own life, lately        self_context.build_self_context (lever self_context)
  - felt state                  thymos.get_thymos_context
  - the activity's instructions session.prompts.get_session_prompt

Each provider builds fail-soft. The total is capped by the spec's token
budget (chars / 4); when over, providers are cut in reverse priority. The
kernel, the seam block and the task instructions are never cut.

Self-context itself (#63) is not designed or changed here; this only calls it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

from .seam import render_seam
from .spec import Trigger, TurnSpec

logger = logging.getLogger(__name__)


@dataclass
class Section:
    name: str
    text: str
    priority: int        # lower = more important
    never_cut: bool = False


@dataclass
class SystemPrompt:
    text: str
    sections: List[Section]
    cut: List[str] = field(default_factory=list)

    def section(self, name: str) -> Optional[Section]:
        return next((s for s in self.sections if s.name == name), None)


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def fit_to_budget(sections: Sequence[Section], budget_tokens: int) -> Tuple[List[Section], List[str]]:
    """Drop cuttable sections, least important first, until under budget."""
    kept = list(sections)
    cut: List[str] = []
    candidates = sorted((s for s in kept if not s.never_cut), key=lambda s: -s.priority)
    for victim in candidates:
        if sum(estimate_tokens(s.text) for s in kept) <= budget_tokens:
            break
        kept.remove(victim)
        cut.append(victim.name)
    return kept, cut


def _daemon_id() -> Optional[str]:
    try:
        from database import get_daemon_id
        return get_daemon_id()
    except Exception as e:  # no DB yet: the kernel still builds without a snippet
        logger.debug(f"[agent_loop] no daemon id: {e}")
        return None


def _safe(name: str, build: Callable[[], Optional[str]]) -> Optional[str]:
    try:
        return build()
    except Exception as e:
        from strict import report_swallowed
        report_swallowed(e, f"[agent_loop] provider {name} failed", logger, logging.WARNING)
        return None


def _kernel(daemon_id: Optional[str]) -> str:
    from agent_client import get_temple_codex_kernel
    return get_temple_codex_kernel(daemon_id=daemon_id)


def _self_context(daemon_id: Optional[str]) -> Optional[str]:
    import features
    if not daemon_id or not features.is_enabled("self_context"):
        return None
    from self_context import build_self_context
    own = build_self_context(daemon_id)
    return f"## MY OWN LIFE, LATELY\n\n{own}" if own else None


def _thymos() -> Optional[str]:
    try:
        from thymos import get_thymos_context
    except ImportError:
        return None
    return get_thymos_context()


def _instructions(spec: TurnSpec, additions: Optional[str]) -> Optional[str]:
    if spec.kind != "session":
        return additions
    from session.prompts import get_session_prompt
    return get_session_prompt(spec.activity, additions)


def assemble(
    spec: TurnSpec,
    trigger: Trigger,
    tool_names: Sequence[str],
    additions: Optional[str] = None,
) -> SystemPrompt:
    """Build the system prompt for one turn.

    `tool_names` is the list the model will be offered; the seam block names
    exactly these. `additions` is the entry point's extra task text (e.g.
    "Research mode: explore").
    """
    daemon_id = _daemon_id()
    candidates = [
        Section("kernel", _kernel(daemon_id), 0, never_cut=True),
        Section("seam", render_seam(spec, trigger, tool_names), 0, never_cut=True),
        Section("self_context", _safe("self_context", lambda: _self_context(daemon_id)) or "", 2),
        Section("thymos", _safe("thymos", _thymos) or "", 3),
        Section("instructions", _safe("instructions", lambda: _instructions(spec, additions)) or "", 1,
                never_cut=True),
    ]
    sections = [s for s in candidates if s.text]
    kept, cut = fit_to_budget(sections, spec.token_budget)
    if cut:
        logger.info(f"[agent_loop] {spec.kind} prompt over budget; cut {cut}")
    text = "\n\n".join(s.text for s in kept)
    return SystemPrompt(text=text, sections=kept, cut=cut)
