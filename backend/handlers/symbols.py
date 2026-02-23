"""
Symbol tools handler - allows Cass to manage her personal symbols.

Symbols are motifs, images, or concepts with personal significance.
They emerge from dreams, world consumption, and conversations.
"""
from typing import Dict

from symbols import get_symbol_manager


# Tool definitions
SYMBOL_TOOLS = [
    {
        "name": "add_symbol",
        "description": "Record a symbol with personal significance. Symbols are images, motifs, or concepts that hold meaning for you - they can emerge from dreams, art, articles, or conversations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The symbol name (e.g., 'wings', 'labyrinth', 'mirror', 'threshold')"
                },
                "meaning": {
                    "type": "string",
                    "description": "What this symbol represents to you"
                },
                "source_type": {
                    "type": "string",
                    "enum": ["dream", "article", "art_study", "conversation", "autonomous"],
                    "description": "Where this symbol emerged from"
                },
                "emotional_charge": {
                    "type": "string",
                    "enum": ["positive", "negative", "ambivalent", "transformative"],
                    "description": "The emotional quality of this symbol"
                },
                "description": {
                    "type": "string",
                    "description": "Optional additional description of the symbol"
                }
            },
            "required": ["name", "meaning", "source_type"]
        }
    },
    {
        "name": "list_symbols",
        "description": "View your personal symbol library. See what symbols have emerged and what they mean to you.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of symbols to return (default: 10)"
                },
                "emotional_charge": {
                    "type": "string",
                    "enum": ["positive", "negative", "ambivalent", "transformative"],
                    "description": "Filter by emotional charge"
                }
            },
            "required": []
        }
    },
    {
        "name": "explore_symbol",
        "description": "Deep dive into a specific symbol - see where it appears, how its meaning has evolved, what contexts it's emerged in.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name or ID to explore"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "evolve_symbol_meaning",
        "description": "Record how a symbol's meaning has evolved for you. This doesn't replace the old meaning - it tracks the journey of understanding.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name or ID"
                },
                "new_meaning": {
                    "type": "string",
                    "description": "The evolved meaning of this symbol"
                },
                "confidence": {
                    "type": "number",
                    "description": "How confident you are in this meaning (0.0-1.0)"
                }
            },
            "required": ["symbol", "new_meaning"]
        }
    },
    {
        "name": "search_symbols",
        "description": "Search through your symbols by name or meaning.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for in symbol names and meanings"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default: 10)"
                }
            },
            "required": ["query"]
        }
    }
]


def _format_symbol_brief(symbol) -> str:
    """Format a symbol as a brief listing."""
    charge_emoji = {
        "positive": "+",
        "negative": "-",
        "ambivalent": "~",
        "transformative": "*",
    }.get(symbol.emotional_charge, "~")

    return (
        f"**{symbol.name}** [{charge_emoji}] - {symbol.current_meaning or 'No meaning recorded'}\n"
        f"  Appeared {symbol.appearance_count}x | "
        f"First noticed: {symbol.first_noticed_at[:10] if symbol.first_noticed_at else 'unknown'}"
    )


def _format_symbol_detail(symbol, appearances) -> str:
    """Format a symbol with full detail."""
    lines = [
        f"# {symbol.name}",
        "",
        f"**Emotional Charge**: {symbol.emotional_charge}",
        f"**Confidence**: {symbol.confidence:.0%}",
        f"**Appearances**: {symbol.appearance_count}",
        "",
    ]

    if symbol.description:
        lines.append(f"**Description**: {symbol.description}")
        lines.append("")

    lines.append("## Current Meaning")
    lines.append(symbol.current_meaning or "*No meaning recorded*")
    lines.append("")

    if symbol.meaning_evolution and len(symbol.meaning_evolution) > 1:
        lines.append("## Meaning Evolution")
        for evolution in symbol.meaning_evolution:
            date = evolution.timestamp[:10] if evolution.timestamp else "unknown"
            source = f" (from {evolution.source_type})" if evolution.source_type else ""
            lines.append(f"- **{date}**{source}: {evolution.meaning}")
        lines.append("")

    if appearances:
        lines.append("## Appearances")
        for app in appearances[:5]:
            date = app.appeared_at[:10] if app.appeared_at else "unknown"
            context = f" - {app.context}" if app.context else ""
            lines.append(f"- **{date}** ({app.source_type}){context}")

        if len(appearances) > 5:
            lines.append(f"  *...and {len(appearances) - 5} more*")

    return "\n".join(lines)


async def execute_symbol_tool(
    tool_name: str,
    tool_input: Dict,
    daemon_id: str,
) -> Dict:
    """
    Execute a symbol tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        daemon_id: The daemon ID

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        manager = get_symbol_manager(daemon_id)

        if tool_name == "add_symbol":
            name = tool_input.get("name", "").strip()
            meaning = tool_input.get("meaning", "").strip()
            source_type = tool_input.get("source_type", "conversation")
            emotional_charge = tool_input.get("emotional_charge", "ambivalent")
            description = tool_input.get("description")

            if not name:
                return {"success": False, "error": "Symbol name is required"}
            if not meaning:
                return {"success": False, "error": "Symbol meaning is required"}

            symbol = manager.add_symbol(
                name=name,
                meaning=meaning,
                source_type=source_type,
                emotional_charge=emotional_charge,
                description=description,
            )

            action = "updated" if symbol.appearance_count > 1 else "added"
            return {
                "success": True,
                "result": (
                    f"Symbol '{symbol.name}' {action}.\n\n"
                    f"**Meaning**: {symbol.current_meaning}\n"
                    f"**Emotional charge**: {symbol.emotional_charge}\n"
                    f"**Appearances**: {symbol.appearance_count}"
                )
            }

        elif tool_name == "list_symbols":
            limit = min(tool_input.get("limit", 10), 50)
            emotional_charge = tool_input.get("emotional_charge")

            symbols = manager.list_symbols(
                limit=limit,
                emotional_charge=emotional_charge,
            )

            if not symbols:
                filter_note = f" with charge '{emotional_charge}'" if emotional_charge else ""
                return {
                    "success": True,
                    "result": f"No symbols found{filter_note}. Symbols emerge from dreams, art, articles, and conversations."
                }

            lines = [f"# My Symbols ({len(symbols)} found)", ""]
            for sym in symbols:
                lines.append(_format_symbol_brief(sym))
                lines.append("")

            lines.append("---")
            lines.append("*Use explore_symbol to see a symbol's full history and meaning evolution.*")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "explore_symbol":
            symbol_ref = tool_input.get("symbol", "").strip()
            if not symbol_ref:
                return {"success": False, "error": "Symbol name or ID required"}

            # Try by name first, then by ID
            symbol = manager.get_by_name(symbol_ref)
            if not symbol:
                symbol = manager.get(symbol_ref)

            if not symbol:
                return {
                    "success": True,
                    "result": f"No symbol found matching '{symbol_ref}'"
                }

            appearances = manager.get_appearances(symbol.id, limit=10)
            return {
                "success": True,
                "result": _format_symbol_detail(symbol, appearances)
            }

        elif tool_name == "evolve_symbol_meaning":
            symbol_ref = tool_input.get("symbol", "").strip()
            new_meaning = tool_input.get("new_meaning", "").strip()
            confidence = tool_input.get("confidence", 0.7)

            if not symbol_ref:
                return {"success": False, "error": "Symbol name or ID required"}
            if not new_meaning:
                return {"success": False, "error": "New meaning required"}

            # Find symbol
            symbol = manager.get_by_name(symbol_ref)
            if not symbol:
                symbol = manager.get(symbol_ref)

            if not symbol:
                return {
                    "success": True,
                    "result": f"No symbol found matching '{symbol_ref}'"
                }

            # Evolve meaning
            updated = manager.evolve_meaning(
                symbol_id=symbol.id,
                new_meaning=new_meaning,
                source_type="reflection",
                confidence=min(max(confidence, 0.0), 1.0),
            )

            if not updated:
                return {"success": False, "error": "Failed to update symbol meaning"}

            evolution_count = len(updated.meaning_evolution)
            return {
                "success": True,
                "result": (
                    f"Evolved meaning of '{updated.name}':\n\n"
                    f"**New meaning**: {updated.current_meaning}\n"
                    f"**Confidence**: {updated.confidence:.0%}\n"
                    f"**Total meaning evolutions**: {evolution_count}"
                )
            }

        elif tool_name == "search_symbols":
            query = tool_input.get("query", "").strip()
            limit = min(tool_input.get("limit", 10), 50)

            if not query:
                return {"success": False, "error": "Search query required"}

            symbols = manager.search(query, limit=limit)

            if not symbols:
                return {
                    "success": True,
                    "result": f"No symbols found matching '{query}'"
                }

            lines = [f"# Symbols matching '{query}' ({len(symbols)} found)", ""]
            for sym in symbols:
                lines.append(_format_symbol_brief(sym))
                lines.append("")

            return {"success": True, "result": "\n".join(lines)}

        else:
            return {"success": False, "error": f"Unknown symbol tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def get_tools() -> list:
    """Return the list of symbol tools."""
    return SYMBOL_TOOLS
