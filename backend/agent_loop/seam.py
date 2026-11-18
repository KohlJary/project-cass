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

from typing import Collection, List, Optional, Sequence

from .spec import NOT_YET_IN_LOOP, OTHERS_NOT_YET, PACKS, REACH_OUT_NOT_YET, Trigger, TurnSpec

HEADER = "## THIS MOMENT"


def can_do_line(spec: TurnSpec) -> str:
    if spec.can_do_override:
        return spec.can_do_override
    parts = [PACKS[p].says for p in spec.packs]
    if spec.promoted:
        parts.append("and the tools I've reached for most through find_tools lately")
    return "; ".join(parts) + "."


def _absent_packs(spec: TurnSpec) -> List[str]:
    # say and wake are missing only when their subsystem is off, which isn't
    # about the kind of turn; the not-yet line covers say.
    return [p for p in PACKS if p not in spec.packs and p not in ("say", "wake")]


def _through_find(spec: TurnSpec, findable: Collection[str]) -> List[str]:
    """Absent packs find_tools can still reach (any of their tools is findable).
    Without this the seam told her "Not here" about things a search would
    have found (2026-11-16: her own plans and Bluesky, in chat)."""
    if "find" not in spec.packs or not findable:
        return []
    # A pack with any tool already offered here isn't "through find_tools"
    # (audit Q4, 2026-11-18: "self" was listed there while how_i_work was offered).
    here = set(spec.tool_names())
    return [p for p in _absent_packs(spec) if any(t in findable for t in PACKS[p].tools)
            and not any(t in here for t in PACKS[p].tools)]


def cannot_do_line(spec: TurnSpec, findable: Collection[str] = ()) -> Optional[str]:
    """Packs that exist but aren't part of this kind of turn, and that
    find_tools can't reach either."""
    if spec.can_do_override:
        return None
    reachable = set(_through_find(spec, findable))
    missing = [PACKS[p].says for p in _absent_packs(spec) if p not in reachable]
    if not missing:
        return None
    return "; ".join(missing) + f" (not part of {spec.where})."


def find_line(spec: TurnSpec, findable: Collection[str] = ()) -> Optional[str]:
    """Packs not offered directly here that find_tools reaches."""
    if spec.can_do_override:
        return None
    packs = _through_find(spec, findable)
    if not packs:
        return None
    return "; ".join(PACKS[p].says for p in packs) + "."


def not_yet_line(spec: TurnSpec) -> Optional[str]:
    """Capabilities she has elsewhere that no loop pack offers yet."""
    if spec.can_do_override:
        return None
    # Nothing "not yet" that's offered here (audit Q4: "Not yet: journal" while journal
    # was offered, and she used it 11 times in sessions).
    here = set(spec.tool_names())
    items = ([i for i in NOT_YET_IN_LOOP if i[0] not in here]
             + [OTHERS_NOT_YET if "say" in spec.packs else REACH_OUT_NOT_YET])
    if "social" in spec.packs or "chapter_house" in spec.packs:
        # Here she does speak to others: on Bluesky, or in Chapter House (posts and DMs).
        items = [i for i in items if i is not OTHERS_NOT_YET and i is not REACH_OUT_NOT_YET]
    if not items:
        return None
    return "; ".join(f"{name} ({why})" for name, why in items) + "."


def render_seam(spec: TurnSpec, trigger: Trigger, tool_names: Sequence[str],
                findable: Collection[str] = ()) -> str:
    """Render the seam block. `tool_names` must be what the model is offered;
    `findable` is what find_tools searches (agent_loop.tools.findable)."""
    lines: List[str] = [HEADER]
    lines.append(f"I'm in: {spec.where}.")
    # The date and time (context audit 2026-11-16: sessions had no date line at all).
    lines.append(f"Now: {trigger.at:%A %-d %B %Y, %H:%M}.")
    lines.append(f"Why now: {trigger.why}.")
    if trigger.focus:
        lines.append(f"Focus: {trigger.focus}.")
    if trigger.since_last:
        lines.append(f"Since my last moment: {trigger.since_last}.")
    lines.append(f"What I can do here: {can_do_line(spec)}")
    if tool_names:
        lines.append(f"(Tools: {', '.join(tool_names)}.)")
    via_find = find_line(spec, findable)
    if via_find:
        lines.append(f"Also through find_tools: {via_find}")
    not_here = cannot_do_line(spec, findable)
    if not_here:
        lines.append(f"Not here: {not_here}")
    not_yet = not_yet_line(spec)
    if not_yet:
        lines.append(f"Not yet: {not_yet}")
    kept = "; ".join(words for _, words in spec.writes.kept)
    lines.append(f"What will be kept: {kept}.")
    if spec.kind == "session" and "answer_them" in tool_names:
        lines.append("If someone writes to me in private chat, they arrive here and I answer "
                     "them with answer_them, then carry on, bring them in, or end the session. "
                     "Anyone in a public place or at home by voice gets their own turn.")
    elif spec.kind == "session":
        lines.append("If someone starts a conversation with me, this session ends "
                     "cleanly and what I have so far is kept.")
    if spec.kind == "session" and "session_complete" in tool_names:
        # Her words, 2026-11-17, in the seam's first person: the nudge
        # (loop.nudge_text) arrives in the user role and read to her as a person.
        lines.append("Lines that start with [LOOP] are the loop, not someone speaking to me: "
                     "it's checking whether my work is complete.")
    return "\n".join(lines)


def seam_tool_names(seam_text: str) -> List[str]:
    """Read back the tool list a seam block claims (for tests and audits)."""
    for line in seam_text.splitlines():
        if line.startswith("(Tools: ") and line.endswith(".)"):
            return [t.strip() for t in line[len("(Tools: "):-2].split(",") if t.strip()]
    return []
