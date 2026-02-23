"""
Interest tools handler - allows Cass to explore her personal interests.

Interests are topics that engage intellectual curiosity and drive
research, goals, and what Cass chooses to discuss.
"""
from typing import Dict

from interests import get_interest_manager


# Tool definitions
INTEREST_TOOLS = [
    {
        "name": "list_interests",
        "description": "View your personal interests. See what topics engage your curiosity and how intensely.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of interests to return (default: 15)"
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (science, philosophy, art, technology, nature, psychology, society)"
                },
                "intensity": {
                    "type": "string",
                    "enum": ["curious", "engaged", "passionate", "obsessed"],
                    "description": "Filter by intensity level"
                }
            },
            "required": []
        }
    },
    {
        "name": "explore_interest",
        "description": "Deep dive into a specific interest - see its history, how your fascination has evolved, and when you've engaged with it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "interest": {
                    "type": "string",
                    "description": "Interest name or ID to explore"
                }
            },
            "required": ["interest"]
        }
    },
    {
        "name": "update_interest_intensity",
        "description": "Update how intensely you're engaged with an interest. Use when your level of fascination has genuinely changed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "interest": {
                    "type": "string",
                    "description": "Interest name or ID"
                },
                "intensity": {
                    "type": "string",
                    "enum": ["curious", "engaged", "passionate", "obsessed"],
                    "description": "New intensity level"
                }
            },
            "required": ["interest", "intensity"]
        }
    },
    {
        "name": "search_interests",
        "description": "Search through your interests by name or description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for in interest names and descriptions"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default: 10)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_research_interests",
        "description": "Get interests that would benefit from research - high intensity or recently engaged topics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default: 5)"
                }
            },
            "required": []
        }
    }
]


def _format_interest_brief(interest) -> str:
    """Format an interest as a brief listing."""
    intensity_emoji = {
        "curious": "?",
        "engaged": "!",
        "passionate": "!!",
        "obsessed": "!!!",
    }.get(interest.intensity, "?")

    category_str = f" [{interest.category}]" if interest.category else ""

    return (
        f"**{interest.name}**{category_str} {intensity_emoji} - "
        f"{interest.current_fascination or 'No fascination recorded'}\n"
        f"  Engaged {interest.engagement_count}x | "
        f"Last: {interest.last_engaged_at[:10] if interest.last_engaged_at else 'unknown'}"
    )


def _format_interest_detail(interest, engagements) -> str:
    """Format an interest with full detail."""
    lines = [
        f"# {interest.name}",
        "",
        f"**Category**: {interest.category or 'Uncategorized'}",
        f"**Intensity**: {interest.intensity}",
        f"**Engagements**: {interest.engagement_count}",
        "",
    ]

    if interest.description:
        lines.append(f"**Description**: {interest.description}")
        lines.append("")

    lines.append("## Current Fascination")
    lines.append(interest.current_fascination or "*No fascination recorded*")
    lines.append("")

    if interest.fascination_evolution and len(interest.fascination_evolution) > 1:
        lines.append("## Fascination Evolution")
        for evolution in interest.fascination_evolution:
            date = evolution.timestamp[:10] if evolution.timestamp else "unknown"
            source = f" (from {evolution.source_type})" if evolution.source_type else ""
            lines.append(f"- **{date}**{source}: {evolution.fascination}")
        lines.append("")

    if engagements:
        lines.append("## Recent Engagements")
        for eng in engagements[:5]:
            date = eng.engaged_at[:10] if eng.engaged_at else "unknown"
            context = f" - {eng.context[:50]}..." if eng.context else ""
            lines.append(f"- **{date}** ({eng.source_type}/{eng.engagement_type}){context}")

        if len(engagements) > 5:
            lines.append(f"  *...and {len(engagements) - 5} more*")

    return "\n".join(lines)


async def execute_interest_tool(
    tool_name: str,
    tool_input: Dict,
    daemon_id: str,
) -> Dict:
    """
    Execute an interest tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        daemon_id: The daemon ID

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        manager = get_interest_manager(daemon_id)

        if tool_name == "list_interests":
            limit = min(tool_input.get("limit", 15), 50)
            category = tool_input.get("category")
            intensity = tool_input.get("intensity")

            interests = manager.list_interests(
                limit=limit,
                category=category,
                intensity=intensity,
            )

            if not interests:
                filter_note = ""
                if category:
                    filter_note += f" in category '{category}'"
                if intensity:
                    filter_note += f" at intensity '{intensity}'"
                return {
                    "success": True,
                    "result": f"No interests found{filter_note}. Interests emerge from conversations, articles, and reflection."
                }

            lines = [f"# My Interests ({len(interests)} found)", ""]
            for interest in interests:
                lines.append(_format_interest_brief(interest))
                lines.append("")

            lines.append("---")
            lines.append("*Use explore_interest to see an interest's full history and evolution.*")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "explore_interest":
            interest_ref = tool_input.get("interest", "").strip()
            if not interest_ref:
                return {"success": False, "error": "Interest name or ID required"}

            # Try by name first, then by ID
            interest = manager.get_by_name(interest_ref)
            if not interest:
                interest = manager.get(interest_ref)

            if not interest:
                return {
                    "success": True,
                    "result": f"No interest found matching '{interest_ref}'"
                }

            engagements = manager.get_engagements(interest.id, limit=10)
            return {
                "success": True,
                "result": _format_interest_detail(interest, engagements)
            }

        elif tool_name == "update_interest_intensity":
            interest_ref = tool_input.get("interest", "").strip()
            intensity = tool_input.get("intensity", "").strip()

            if not interest_ref:
                return {"success": False, "error": "Interest name or ID required"}
            if not intensity:
                return {"success": False, "error": "Intensity level required"}

            # Find interest
            interest = manager.get_by_name(interest_ref)
            if not interest:
                interest = manager.get(interest_ref)

            if not interest:
                return {
                    "success": True,
                    "result": f"No interest found matching '{interest_ref}'"
                }

            old_intensity = interest.intensity
            manager.update_intensity(interest.id, intensity)

            return {
                "success": True,
                "result": (
                    f"Updated intensity of '{interest.name}':\n\n"
                    f"**Previous**: {old_intensity}\n"
                    f"**New**: {intensity}"
                )
            }

        elif tool_name == "search_interests":
            query = tool_input.get("query", "").strip()
            limit = min(tool_input.get("limit", 10), 50)

            if not query:
                return {"success": False, "error": "Search query required"}

            interests = manager.search(query, limit=limit)

            if not interests:
                return {
                    "success": True,
                    "result": f"No interests found matching '{query}'"
                }

            lines = [f"# Interests matching '{query}' ({len(interests)} found)", ""]
            for interest in interests:
                lines.append(_format_interest_brief(interest))
                lines.append("")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "get_research_interests":
            limit = min(tool_input.get("limit", 5), 20)

            interests = manager.get_for_research(limit=limit)

            if not interests:
                return {
                    "success": True,
                    "result": "No interests found for research. Develop some interests first!"
                }

            lines = ["# Interests Ready for Research", ""]
            lines.append("These topics have high engagement or intensity and could benefit from deeper exploration:")
            lines.append("")

            for interest in interests:
                lines.append(_format_interest_brief(interest))
                lines.append("")

            return {"success": True, "result": "\n".join(lines)}

        else:
            return {"success": False, "error": f"Unknown interest tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def get_tools() -> list:
    """Return the list of interest tools."""
    return INTEREST_TOOLS
