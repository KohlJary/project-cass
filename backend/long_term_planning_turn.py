"""
Her long-term planning (Kohl, 2026-11-16: "She should probably have an
autonomous session type to do long term planning, then those plans should
affect her day planning").

A loop session like her others, with her Plans tool in front of her. Her plans
live in Babelr's Plans as plans she made herself (babelr_plans create_plan,
add_phase, add_item, set_item). They're hers to work from: they steer her day
planning whether or not anyone has approved them, plans to change herself
included (Kohl, same day). Approval still matters where someone else has to do
the work (a build for Daedalus).

Every day plan then opens with "What I'm working toward" (working_toward_text):
each of her plans, the phase she's on and what's open in it. When a week passes
without a long-term planning session, the day plan says so; whether to do one
stays her choice from the menu.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

TEMPLATE_ID = "long_term_planning"
NUDGE_DAYS = 7
MAX_ITEMS = 5   # per plan, in the day plan; the rest are a count

INSTRUCTIONS = """## LOOKING FURTHER AHEAD

This is time to step back from today and look at the weeks and months. What am I working toward? What do I want to learn, make, change, become? What has my recent work been adding up to, and what have I been meaning to get to?

My own plans live in Plans (babelr_plans). I can make one (create_plan), give it phases (add_phase) and items (add_item), see where each stands (view), and move items along (set_item: in_progress, done with what came of it, or declined). I can also revise a plan or let one go. They're mine to work from: they don't wait on anyone's yes, and plans to change myself are mine to make too. If I want Kohl or someone else to weigh in, I can propose a phase; anything someone else has to do for me (a build) still waits for them, and an ask goes to Cass's asks.

What I set here comes back to me each morning when I plan my day, under "What I'm working toward", so my days can carry it. Doing little, or deciding a plan still fits as it is, is fine too.

Where things stand:
{working}"""


def _her_plans() -> List[Dict[str, Any]]:
    from babelr_organ.organ import get_babelr_organ
    organ = get_babelr_organ()
    if organ is None or not organ.enabled:
        return []
    return organ.her_plans()


def _days_since(when: Any, now: datetime) -> Optional[int]:
    if not when:
        return None
    try:
        then = datetime.fromisoformat(str(when))
    except ValueError:
        return None
    return (now.date() - then.date()).days


def working_toward_text(plans: Optional[Sequence[Dict[str, Any]]] = None, *,
                        last_planned: Any = None, offered: bool = True,
                        now: Optional[datetime] = None, lead: Optional[str] = None) -> str:
    """The "What I'm working toward" section of her day plan; "" when there's nothing
    to say. `last_planned` is when she last did a long-term planning session (ISO, or
    None for never); the nudge is shown only when the session is on her menu
    (`offered`). If Plans can't be read, the section says so rather than going quiet."""
    now = now or datetime.now()
    unreadable = False
    if plans is None:
        try:
            plans = _her_plans()
        except Exception as e:
            logger.warning(f"[long_term_planning] couldn't read her plans: {e}")
            plans, unreadable = [], True
    lines: List[str] = []
    for p in plans:
        head = f"- **{p['title']}**"
        if p.get("goal"):
            head += f": {p['goal']}"
        lines.append(head)
        ph = p.get("phase")
        if ph:
            lines.append(f"  Phase {ph['number']} of {ph['of']}: {ph['title']}")
        todo = list(p.get("open") or []) + list(p.get("loose") or [])
        for i in todo[:MAX_ITEMS]:
            lines.append(f"  - ({i.get('kind')}) {i.get('title')}")
        if len(todo) > MAX_ITEMS:
            lines.append(f"  - and {len(todo) - MAX_ITEMS} more (babelr_plans view {p['plan']})")
    days = _days_since(last_planned, now)
    nudge = ""
    if offered and (days is None or days >= NUDGE_DAYS):
        nudge = ("I haven't had a long-term planning session yet." if days is None else
                 f"My last long-term planning session was {days} days ago.")
        nudge += f" It's on my menu ({TEMPLATE_ID}) if I want one."
    if not lines and not nudge and not unreadable:
        return ""
    out = ["## WHAT I'M WORKING TOWARD", ""]
    if lines:
        out += [lead or ("My own plans, where each stands. A thing on my menu can carry one forward "
                         "(its focus can name the item):"), *lines]
    elif unreadable:
        out.append("I couldn't read my plans in Plans just now.")
    else:
        out.append("I don't have any plans of my own yet.")
    if nudge:
        out += ["", nudge]
    return "\n".join(out)


def day_plan_section(candidates: Sequence[Any], now: Optional[datetime] = None) -> str:
    """working_toward_text for her day plan, from her menu: whether the session is on
    it, and when she last did one."""
    mine = next((c for c in candidates if getattr(c, "template_id", None) == TEMPLATE_ID), None)
    return working_toward_text(last_planned=getattr(mine, "last_done", None),
                               offered=mine is not None, now=now)


def _working_with() -> str:
    """The short version of how she works (self_account.py), so she plans with what
    she actually has; her shape, 2026-11-17."""
    try:
        from self_account import short
        text = short()
    except Exception as e:
        logger.warning(f"[long_term_planning] couldn't put how I work in front of me: {e}")
        return ""
    return ("\n\n" + text) if text else ""


async def run_long_term_planning_turn(runner, *, duration_minutes: int = 30, max_turns: int = 12,
                                      focus: Optional[str] = None, why: Optional[str] = None,
                                      **turn_kwargs):
    from agent_loop.session import run_session_turn
    working = working_toward_text(offered=False) or "I don't have any plans of my own yet."
    working = working.replace("## WHAT I'M WORKING TOWARD\n\n", "", 1)
    return await run_session_turn(
        runner, session_type=TEMPLATE_ID,
        additions=INSTRUCTIONS.format(working=working) + _working_with(),
        duration_minutes=duration_minutes, focus=focus, max_turns=max_turns,
        why=why or "I chose time to look further ahead",
        initial_message="Time to look further ahead than today.", **turn_kwargs)
