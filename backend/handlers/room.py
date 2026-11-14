"""
Her room tools: share a piece to her room in Chapter House, take it back
out, see what's there, switch her standing sections on or off (room.py;
plan "Cass's room in Chapter House"). Sharing is her deliberate choice each
time; nothing reaches the room any other way.
"""
from typing import Any, Dict

ROOM_TOOLS = [
    {
        "name": "share_to_room",
        "description": (
            "Share one piece to my room in Chapter House, where Kohl (and later the house) can see it. "
            "Nothing goes there unless I share it. kind: painting (image id), music (composition id), "
            "writing (path under my creative output, e.g. 'poem/2026-11-13_tides.md'), journal "
            "(journal entry id), workspace (path in my workspace). audience: 'kohl' (default) or "
            "'house'. note: what I want to say about it, shown with it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["painting", "music", "writing", "journal", "workspace"]},
                "id": {"type": "string"},
                "note": {"type": "string"},
                "audience": {"type": "string", "enum": ["kohl", "house"]},
            },
            "required": ["kind", "id"],
        },
    },
    {
        "name": "unshare_from_room",
        "description": "Take a piece back out of my room.",
        "input_schema": {
            "type": "object",
            "properties": {"kind": {"type": "string"}, "id": {"type": "string"}},
            "required": ["kind", "id"],
        },
    },
    {
        "name": "view_my_room",
        "description": "See what's in my room: the pieces I've shared (and with whom) and which standing "
                       "sections (day plan, agenda, homepage) are showing.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_room_section",
        "description": "Switch one of my room's standing sections on or off: day_plan, agenda, homepage. "
                       "They show to Kohl only.",
        "input_schema": {
            "type": "object",
            "properties": {"section": {"type": "string", "enum": ["day_plan", "agenda", "homepage"]},
                           "on": {"type": "boolean"}},
            "required": ["section", "on"],
        },
    },
]


async def execute_room_tool(tool_name: str, tool_input: Dict[str, Any], daemon_id: str = None,
                            room=None, **_) -> Dict[str, Any]:
    from room import Room
    room = room or Room(daemon_id=daemon_id)
    a = tool_input or {}
    if tool_name == "share_to_room":
        out = room.share(a.get("kind", ""), a.get("id", ""), a.get("note") or "", a.get("audience") or "kohl")
    elif tool_name == "unshare_from_room":
        out = room.unshare(a.get("kind", ""), a.get("id", ""))
    elif tool_name == "view_my_room":
        out = room.summary_for_her()
    elif tool_name == "set_room_section":
        out = room.set_standing(a.get("section", ""), bool(a.get("on")))
    else:
        out = {"error": f"unknown room tool {tool_name}"}
    if "error" in out:
        return {"success": False, "error": out["error"]}
    return {"success": True, "result": out.get("message") or out}
