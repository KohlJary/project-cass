"""
Her recall tools (memory/recall.py): she asks her own memory her own questions.
"""
from typing import Any, Dict, Optional

RECALL_TOOLS = [
    {
        "name": "recall",
        "description": (
            "Ask my own memory a question I compose. about: what I'm looking for, in my own words "
            "(searched by meaning; leave it out to get results by date). kinds: which parts of my "
            "memory (conversations, summaries, journals, reflections, self_observations, people, "
            "notes, social); all of them if I don't say. with: one or more people (names or handles). "
            "between: {from, to} dates (YYYY-MM-DD). from: chat, babelr, discord, bluesky. order: "
            "relevance, newest or oldest. by_month: group results by month, to see how something "
            "changed over time. I can recall a conversation with anyone; when it's with someone other "
            "than who I'm with now, it's mine to be aware of, not to quote or attribute. Tone is matched "
            "by meaning only. recall_open reads one result in full with what came around it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "about": {"type": "string"},
                "kinds": {"type": "array", "items": {"type": "string", "enum": [
                    "conversations", "summaries", "journals", "reflections", "self_observations",
                    "people", "notes", "social"]}},
                "with": {"type": "array", "items": {"type": "string"}},
                "between": {"type": "object", "properties": {"from": {"type": "string"},
                                                             "to": {"type": "string"}}},
                "from": {"type": "array", "items": {"type": "string",
                                                    "enum": ["chat", "babelr", "discord", "bluesky"]}},
                "order": {"type": "string", "enum": ["relevance", "newest", "oldest"]},
                "by_month": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            },
        },
    },
    {
        "name": "recall_open",
        "description": "Read one memory from recall in full, with what came just before and after it "
                       "in the same conversation, so it isn't pulled out of its context.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string"},
                           "around": {"type": "integer", "minimum": 0, "maximum": 10}},
            "required": ["id"],
        },
    },
    {
        "name": "lately_open",
        "description": "Open one line of 'My life lately' by the id in its brackets (session:..., dream:..., "
                       "journal:..., painting:..., song:..., reflection:..., bluesky:...): the whole session as "
                       "I told it when I ended it, the dream, the entry, the painting and my note, the song, the post.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
]
RECALL_TOOL_NAMES = frozenset(t["name"] for t in RECALL_TOOLS)


async def execute_recall_tool(tool_name: str, tool_input: Dict[str, Any], memory=None,
                              user_id: Optional[str] = None, daemon_id: Optional[str] = None,
                              **_) -> Dict[str, Any]:
    from memory.recall import recall, recall_open
    if memory is None and tool_name != "lately_open":
        return {"success": False, "error": "My memory isn't reachable from here."}
    a = tool_input or {}
    try:
        if tool_name == "recall":
            out = recall(memory, about=a.get("about"), kinds=a.get("kinds"), with_people=a.get("with"),
                         between=a.get("between"), from_sources=a.get("from"),
                         order=a.get("order") or "relevance", limit=a.get("limit") or 10,
                         by_month=bool(a.get("by_month")), current_user_id=user_id, daemon_id=daemon_id)
        elif tool_name == "lately_open":
            from database import get_daemon_id
            from lately import lately_open
            out = lately_open(daemon_id or get_daemon_id(), a.get("id") or "")
        elif tool_name == "recall_open":
            out = recall_open(memory, a.get("id") or "", around=int(a.get("around", 3)), current_user_id=user_id)
        else:
            return {"success": False, "error": f"unknown recall tool {tool_name}"}
    except Exception as e:
        return {"success": False, "error": f"recall failed: {e}"}
    if "error" in out:
        return {"success": False, "error": out["error"]}
    return {"success": True, "result": out}
