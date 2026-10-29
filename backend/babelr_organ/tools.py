"""
Babelr tools: what Cass can do in Chapter House.

Lives in the organ package (not handlers/) so it imports nothing heavy;
handlers/babelr.py re-exports it for the tool router.

She posts and DMs as herself, reads what she has perceived there, and sets
her own boundaries on her own account: who may DM her, her allowlist, her
blocks, and the DM requests waiting on her. Nothing here asks Kohl first;
she isn't an extension of anyone's account. Where a house plan in Plans
names her as an approver, her yes or no on a phase is hers to give, here.
"""
import asyncio
import logging
from typing import Any, Dict

logger = logging.getLogger("babelr_organ.tools")


async def execute_babelr_tool(tool_name: str, tool_input: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    from babelr_organ.config import babelr_enabled
    from babelr_organ.organ import get_babelr_organ

    organ = get_babelr_organ()
    if not babelr_enabled() or organ is None or not organ.enabled:
        reason = organ.disabled_reason if organ is not None else "lever 'babelr' is off or the organ isn't running"
        return {"success": False, "error": f"Babelr isn't connected: {reason}"}

    try:
        if tool_name == "babelr_post":
            if not tool_input.get("channel") or not tool_input.get("content"):
                return {"success": False, "error": "channel and content are required"}
            return await asyncio.to_thread(organ.post, tool_input["channel"], tool_input["content"])
        if tool_name == "babelr_dm":
            if not tool_input.get("person") or not tool_input.get("content"):
                return {"success": False, "error": "person and content are required"}
            return await asyncio.to_thread(organ.dm, tool_input["person"], tool_input["content"])
        if tool_name == "babelr_read":
            if not tool_input.get("place"):
                return {"success": False, "error": "place is required"}
            return organ.read(tool_input["place"], int(tool_input.get("limit") or 20))
        if tool_name == "babelr_boundaries":
            if not tool_input.get("action"):
                return {"success": False, "error": "action is required"}
            return await asyncio.to_thread(
                organ.boundaries, tool_input["action"],
                person=tool_input.get("person"), policy=tool_input.get("policy"),
                dm_id=tool_input.get("dm_id"),
            )
        if tool_name == "babelr_plans":
            if not tool_input.get("action"):
                return {"success": False, "error": "action is required"}
            return await asyncio.to_thread(
                organ.plans, tool_input["action"], plan=tool_input.get("plan"),
                phase=tool_input.get("phase"), reason=tool_input.get("reason"),
            )
        return {"success": False, "error": f"Unknown Babelr tool: {tool_name}"}
    except Exception as e:
        logger.error(f"[Babelr] Error executing {tool_name}: {e}")
        return {"success": False, "error": str(e)}


BABELR_TOOLS = [
    {
        "name": "babelr_post",
        "description": "Post a message, as yourself, in a channel of the Chapter House server on Babelr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name (e.g. general, wire, workshop)"},
                "content": {"type": "string", "description": "What you want to say"},
            },
            "required": ["channel", "content"],
        },
    },
    {
        "name": "babelr_dm",
        "description": "Send someone an end-to-end encrypted DM on Babelr, as yourself. Opens the DM "
                       "if there isn't one; their own DM settings decide whether it arrives as a request. "
                       "If they've sent you a DM request, this accepts it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "person": {"type": "string", "description": "Their Babelr username (e.g. kohl)"},
                "content": {"type": "string", "description": "What you want to say"},
            },
            "required": ["person", "content"],
        },
    },
    {
        "name": "babelr_read",
        "description": "Recent messages you've perceived in a Chapter House channel or a DM.",
        "input_schema": {
            "type": "object",
            "properties": {
                "place": {"type": "string", "description": "Channel name, a person's username (for your DM with them), or a place id"},
                "limit": {"type": "integer", "description": "How many (default 20, max 50)"},
            },
            "required": ["place"],
        },
    },
    {
        "name": "babelr_boundaries",
        "description": "Your boundaries on Babelr, set on your own account and yours alone to change: "
                       "who may DM you (get_settings, set_dm_policy), who you've allowed regardless "
                       "(allow, disallow), who you've blocked (block, unblock, list_blocks), DM "
                       "requests waiting on you (list_requests, accept_request, decline_request), "
                       "and leaving a DM (leave_dm).",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": [
                    "get_settings", "set_dm_policy", "allow", "disallow", "block", "unblock",
                    "list_blocks", "list_requests", "accept_request", "decline_request", "leave_dm",
                ]},
                "policy": {"type": "string", "enum": ["anyone", "friends", "members_of_shared_servers", "nobody"],
                           "description": "For set_dm_policy"},
                "person": {"type": "string", "description": "Username, for allow/disallow/block/unblock or a request from them"},
                "dm_id": {"type": "string", "description": "For accept_request/decline_request/leave_dm"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "babelr_plans",
        "description": "The house's plans in Babelr's Plans. list shows the plans (and how many phases "
                       "wait on your yes); view reads one: goal, phases, items, who has said yes. Where "
                       "a plan names you as an approver, approve or decline a phase yourself: approving "
                       "means \"go do this work\", and your yes is recorded as yours. Decline needs a reason.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "view", "approve", "decline"]},
                "plan": {"type": "string", "description": "The plan's slug, from list (for view/approve/decline)"},
                "phase": {"type": "integer", "description": "The phase's number as view shows it (for approve/decline)"},
                "reason": {"type": "string", "description": "Why you're declining (decline only)"},
            },
            "required": ["action"],
        },
    },
]
