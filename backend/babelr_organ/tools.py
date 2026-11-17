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
                **{k: tool_input.get(k) for k in ("title", "body", "goal", "narrative", "kind",
                                                  "needs_yes_from", "status") if tool_input.get(k) is not None},
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
        "description": ("The house's plans in Babelr's Plans, and mine. list shows the plans (and how many "
                        "phases wait on my yes); view reads one: goal, phases, items, who has said yes. Where a "
                        "plan names me as an approver, approve or decline a phase (decline needs a reason). "
                        "ask: ask for something (a change to me, a new ability, something in my world); it goes "
                        "into my standing plan \"Cass's asks\" (or a plan I name), outside any phase, and Kohl "
                        "sees it there. my_asks: what I've asked and what came of it. My own plans: create_plan, "
                        "add_phase, add_item (kind ask/build/research/decision; to a draft phase, or outside "
                        "phases; build means something someone else builds for me), set_item to move an item along "
                        "(in_progress, done with what came of it in body, declined, open) or change its kind. My own plans are mine to work from: they steer my day planning without "
                        "anyone's yes, plans to change myself included. propose a phase when I want Kohl or "
                        "others to weigh in; something someone else has to do for me (a build) still waits for "
                        "them."),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "view", "approve", "decline", "ask", "my_asks",
                                                      "create_plan", "add_phase", "add_item", "propose",
                                                      "set_item"]},
                "plan": {"type": "string", "description": "The plan's slug, from list (optional for ask and my_asks)"},
                "phase": {"type": "integer", "description": "The phase's number as view shows it (approve, decline, propose, add_item)"},
                "reason": {"type": "string", "description": "Why I'm declining (decline only)"},
                "title": {"type": "string", "description": "Title of the ask, plan, phase or item (set_item: the item's title)"},
                "body": {"type": "string", "description": "What I'm asking for and why, in my words (ask, add_item); what came of it (set_item done)"},
                "status": {"type": "string", "enum": ["open", "in_progress", "done", "declined"],
                           "description": "set_item only"},
                "goal": {"type": "string", "description": "What the plan or phase is for (create_plan, add_phase)"},
                "narrative": {"type": "string", "description": "The plan's longer story (create_plan)"},
                "kind": {"type": "string", "enum": ["ask", "build", "research", "decision"],
                         "description": "build: someone else builds it; my own work is research or decision"},
                "needs_yes_from": {"type": "array", "items": {"type": "string"},
                                   "description": "Who else must say yes to my plan's phases (I'm included; Kohl always is)"},
            },
            "required": ["action"],
        },
    },
]


def ask_in_plans(title: str, body: str, kind: str = "ask") -> Dict[str, Any]:
    """Her older request tools (request_development, request_architectural_change) as
    aliases of babelr_plans ask (2026-11-16). They used to write where nobody looked;
    now an ask lands in her standing plan in Plans, where Kohl sees it.

    {"success": False, "unavailable": True} when Babelr isn't running, so the caller
    can say so honestly instead of claiming someone will see it."""
    from .organ import get_babelr_organ
    organ = get_babelr_organ()
    if organ is None or not organ.enabled:
        return {"success": False, "unavailable": True,
                "error": "Babelr isn't running, so my ask can't reach Plans right now."}
    return organ.plans("ask", title=title, body=body, kind=kind)
