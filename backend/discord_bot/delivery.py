"""
Discord as a delivery channel for her reach-outs (reach_out.py).

Not an action of its own: when and whether she reaches out is decided by her
reach-out rules (ReachOutManager.can_send), and what she says is written by
her (reach_out._ask_her). This module only carries the message: it DMs the
Discord account linked to the person, and stores her message in the
"Discord DM: <name>" conversation her Discord wake turn uses, so when they
reply there she sees what she wrote.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _get_bot():
    """The running bot, never a new one (sending needs a connected client)."""
    try:
        from discord_bot import bot as bot_module
    except ImportError:
        return None
    return getattr(bot_module, "_bot_instance", None)


def availability(user_id: str) -> Optional[str]:
    """None if a DM to this user could go out now, else why not."""
    bot = _get_bot()
    if bot is None or not bot.client or not bot.client.is_ready():
        return "Discord bot not connected"
    if not bot.parser.registry.get_by_user_id(user_id):
        return "no Discord account linked to them"
    return None


async def deliver_dm(user_id: str, body: str, conversation_manager=None) -> Dict[str, Any]:
    """DM `body` to the user's linked Discord account. Returns a delivered_via entry."""
    why_not = availability(user_id)
    if why_not:
        return {"channel": "discord", "ok": False, "reason": why_not}
    bot = _get_bot()
    entity = bot.parser.registry.get_by_user_id(user_id)[0]
    result = await bot.send_dm(entity.discord_id, body)
    if not result.get("success"):
        return {"channel": "discord", "ok": False, "error": result.get("error") or "send failed"}

    entry: Dict[str, Any] = {"channel": "discord", "ok": True, "message_id": result.get("message_id")}
    if conversation_manager is not None:
        try:
            from discord_bot.conversations import discord_conversation_id, dm_conversation_title
            title = dm_conversation_title(result["display_name"])
            conv_id = discord_conversation_id(conversation_manager, user_id, title)
            conversation_manager.add_message(conversation_id=conv_id, role="assistant",
                                             content=body, user_id=user_id)
            conversation_manager.update_title(conv_id, title)
            entry["discord_conversation_id"] = conv_id
        except Exception as e:
            logger.warning(f"[ReachOut/discord] sent, but storing it in the DM conversation failed: {e}")
    return entry
