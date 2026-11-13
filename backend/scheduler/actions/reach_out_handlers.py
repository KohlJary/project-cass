"""Reach-out actions for spells (reach_out.py does the work)."""

from typing import Any, Dict

from . import ActionResult


async def social_action(context: Dict[str, Any]) -> ActionResult:
    """
    Offer her a reach-out because her social_connection is low
    (reach_out.social_reach_out): her limits, her choice, her words, her
    chosen channel. Always succeeds as an action; data.sent says whether
    anything went out and data.reason why not ("limit" means her share limits
    hold it, e.g. one is still unanswered).

    Context params:
    - managers.conversation_manager (optional)
    """
    from reach_out import social_reach_out
    manager = context.get("managers", {}).get("conversation_manager")
    out = await social_reach_out(conversation_manager=manager)
    message = "reached out" if out.get("sent") else f"didn't reach out: {out.get('reason')}"
    if out.get("detail"):
        message += f" ({out['detail']})"
    return ActionResult(success=True, message=message, data=out)
