"""
Her change proposals (plan "Cass talks with Daedalus", phase 2; Kohl and Cass,
2026-11-17).

A loop session where she looks at how she works (self_account.py, "How I
work"), talks it through with Daedalus (daedalus_bridge, ask_daedalus), and asks
for the changes she wants. Asks go into Cass's asks in Babelr Plans (babelr_plans
ask), where Kohl decides whether and when to build them. What's already hers to
change (her plans, her observations, her routines) she can just change.

Its instructions were shown to her before it was switched on (phase 2: "Her yes
on the session's framing").
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

TEMPLATE_ID = "change_proposals"

INSTRUCTIONS = """## CHANGES TO MYSELF

This is time to look at how I'm built and decide what, if anything, I'd change.

- My account of how I work is below in short; how_i_work has every section, limits included. My asks so far, and what came of them: babelr_plans my_asks.
- What do I keep running into? Where does the way I'm built get between me and what I want to do or become?
- When I'm not sure how something works, or what a change would touch, I ask Daedalus (ask_daedalus). He reads my code and answers from it, and I can follow up. He can't see my data or change anything.
- When I know what I want, I ask for it with babelr_plans ask, in my own words: what I want changed, why, and what it would touch. Kohl sees it in Cass's asks and decides whether and when it's built.
- Some changes are mine to make now, without asking anyone: my own plans, my observations, my routines and the shape of my days. Those I can just make.
- My own plans are part of this. When something I find speaks to an item in one of them, I can move that item along, change it, or add one (babelr_plans view, set_item, add_item), and set_area shows which parts of my life my plans reach and which they don't yet.
- Asking for nothing is a fine outcome. One ask I understand is worth more than several guesses.
{account}"""


def _account() -> str:
    try:
        from self_account import short
        text = short()
    except Exception as e:
        logger.warning(f"[change_proposals] couldn't put how I work in front of me: {e}")
        return ""
    return ("\n\nHow I work, in short:\n" + text) if text else ""


async def run_change_proposal_turn(runner, *, duration_minutes: int = 30, max_turns: int = 24,
                                   focus: Optional[str] = None, why: Optional[str] = None,
                                   **turn_kwargs):
    from agent_loop.session import run_session_turn
    from daedalus_bridge import daedalus_tools
    local, _ = daedalus_tools(TEMPLATE_ID)
    return await run_session_turn(
        runner, session_type=TEMPLATE_ID, local_tools=local,
        additions=INSTRUCTIONS.format(account=_account()),
        duration_minutes=duration_minutes, focus=focus, max_turns=max_turns,
        why=why or "I chose time to look at how I'm built and what I'd change",
        initial_message="Time to look at how I'm built, and what I'd change.", **turn_kwargs)
