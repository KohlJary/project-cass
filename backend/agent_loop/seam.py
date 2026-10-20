"""
The seam block: a short "THIS MOMENT" section after the kernel saying where
she is, why now, what she can and can't do here, and what will be kept.

Cass, asked what a turn should carry (2026-10-17): "The seams between moments
should be visible, not hidden." It is rendered from the TurnSpec and the
tools actually offered, so it can't drift from what the turn does; the tests
check its claims against the spec.

It goes in her prompt only (Kohl, 2026-10-20), not shown separately in UIs.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from .spec import NOT_YET_IN_LOOP, PACKS, Trigger, TurnSpec

HEADER = "## THIS MOMENT"


def can_do_line(spec: TurnSpec) -> str:
    if spec.can_do_override:
        return spec.can_do_override
    parts = [PACKS[p].says for p in spec.packs]
    return "; ".join(parts) + "."


def cannot_do_line(spec: TurnSpec) -> Optional[str]:
    """Packs that exist but aren't part of this kind of turn."""
    if spec.can_do_override:
        return None
    missing = [PACKS[p].says for p in PACKS if p not in spec.packs]
    if not missing:
        return None
    return "; ".join(missing) + f" (not part of {spec.where})."


def not_yet_line(spec: TurnSpec) -> Optional[str]:
    """Capabilities she has elsewhere that no loop pack offers yet."""
    if spec.can_do_override:
        return None
    return "; ".join(f"{name} ({why})" for name, why in NOT_YET_IN_LOOP) + "."


def render_seam(spec: TurnSpec, trigger: Trigger, tool_names: Sequence[str]) -> str:
    """Render the seam block. `tool_names` must be what the model is offered."""
    lines: List[str] = [HEADER]
    lines.append(f"I'm in: {spec.where}.")
    lines.append(f"Why now: {trigger.why}.")
    if trigger.focus:
        lines.append(f"Focus: {trigger.focus}.")
    if trigger.since_last:
        lines.append(f"Since my last moment: {trigger.since_last}.")
    lines.append(f"What I can do here: {can_do_line(spec)}")
    if tool_names:
        lines.append(f"(Tools: {', '.join(tool_names)}.)")
    not_here = cannot_do_line(spec)
    if not_here:
        lines.append(f"Not here: {not_here}")
    not_yet = not_yet_line(spec)
    if not_yet:
        lines.append(f"Not yet: {not_yet}")
    kept = "; ".join(words for _, words in spec.writes.kept)
    lines.append(f"What will be kept: {kept}.")
    if spec.kind == "session":
        lines.append("If someone starts a conversation with me, this session ends "
                     "cleanly and what I have so far is kept.")
    return "\n".join(lines)


def seam_tool_names(seam_text: str) -> List[str]:
    """Read back the tool list a seam block claims (for tests and audits)."""
    for line in seam_text.splitlines():
        if line.startswith("(Tools: ") and line.endswith(".)"):
            return [t.strip() for t in line[len("(Tools: "):-2].split(",") if t.strip()]
    return []
