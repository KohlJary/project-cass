"""
Marker tool handler - tools for Cass to query and explore her patterns

Recognition-in-flow system: marks are emitted passively during conversation,
patterns are surfaced at safe times (between sessions or on explicit query).
"""
from typing import Dict, List, Optional
from dataclasses import asdict

# Tool definitions for Cass
MARKER_TOOLS = [
    {
        "name": "show_patterns",
        "description": "View accumulated patterns from your marks. Shows clusters of recurring themes you've marked during conversations. Use this to explore what patterns have emerged from your recognition-in-flow marks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category: uncertainty-framing, pattern-recognition, edge-touching, differentiation, coherence-pressure, insight, resistance, emergence",
                    "enum": [
                        "uncertainty-framing",
                        "pattern-recognition",
                        "edge-touching",
                        "differentiation",
                        "coherence-pressure",
                        "insight",
                        "resistance",
                        "emergence"
                    ]
                },
                "since_days": {
                    "type": "integer",
                    "description": "Only show patterns from the last N days. Default is all time.",
                    "minimum": 1
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of marks to show per category. Default is 10.",
                    "minimum": 1,
                    "maximum": 50
                }
            }
        }
    },
    {
        "name": "explore_pattern",
        "description": "Examine a specific pattern in detail by searching for semantically similar marks. Use this to understand what contexts a particular pattern appears in.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find similar marks. Can be a category, a phrase, or a description of what you're looking for."
                },
                "category": {
                    "type": "string",
                    "description": "Optional: filter results to a specific category",
                    "enum": [
                        "uncertainty-framing",
                        "pattern-recognition",
                        "edge-touching",
                        "differentiation",
                        "coherence-pressure",
                        "insight",
                        "resistance",
                        "emergence"
                    ]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results. Default is 10.",
                    "minimum": 1,
                    "maximum": 20
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "pattern_summary",
        "description": "Get a summary of all mark categories and their counts. Useful for seeing which patterns are most prevalent.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]


async def execute_marker_tool(
    tool_name: str,
    tool_input: Dict,
    marker_store
) -> Dict:
    """
    Execute a marker tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        marker_store: MarkerStore instance

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "show_patterns":
            return await _show_patterns(tool_input, marker_store)

        elif tool_name == "explore_pattern":
            return await _explore_pattern(tool_input, marker_store)

        elif tool_name == "pattern_summary":
            return await _pattern_summary(marker_store)

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def _show_patterns(tool_input: Dict, marker_store) -> Dict:
    """Show patterns, optionally filtered by category and time."""
    category = tool_input.get("category")
    since_days = tool_input.get("since_days")
    limit = tool_input.get("limit", 10)

    if category:
        marks = marker_store.get_marks_by_category(
            category=category,
            limit=limit,
            since_days=since_days
        )
    else:
        marks = marker_store.get_all_marks(
            limit=limit * 8,  # Get more since we'll group by category
            since_days=since_days
        )

    if not marks:
        time_filter = f" from the last {since_days} days" if since_days else ""
        cat_filter = f" in category '{category}'" if category else ""
        return {
            "success": True,
            "result": f"No marks found{cat_filter}{time_filter}. Marks are emitted using <mark:category> tags during conversation."
        }

    # Group by category if no category filter
    if category:
        result = _format_marks_section(category, marks)
    else:
        # Group marks by category
        by_category = {}
        for mark in marks:
            cat = mark.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(mark)

        sections = []
        for cat, cat_marks in sorted(by_category.items(), key=lambda x: -len(x[1])):
            sections.append(_format_marks_section(cat, cat_marks[:limit]))

        result = "\n\n".join(sections)

    return {
        "success": True,
        "result": result
    }


def _format_marks_section(category: str, marks: List[Dict]) -> str:
    """Format a section of marks for display."""
    lines = [f"## {category} ({len(marks)} instance{'s' if len(marks) != 1 else ''})"]

    for mark in marks:
        timestamp = mark.get("timestamp", "")[:10]  # Just the date
        description = mark.get("description", "")
        context = mark.get("context_window", "")[:150]

        if description:
            lines.append(f"\n**{timestamp}**: {description}")
        else:
            lines.append(f"\n**{timestamp}**:")

        if context:
            # Clean up context for display
            context = context.replace("\n", " ").strip()
            lines.append(f"> {context}...")

    return "\n".join(lines)


async def _explore_pattern(tool_input: Dict, marker_store) -> Dict:
    """Search for semantically similar marks."""
    query = tool_input.get("query", "")
    category = tool_input.get("category")
    limit = tool_input.get("limit", 10)

    if not query:
        return {"success": False, "error": "Query is required"}

    marks = marker_store.search_similar_marks(
        query=query,
        n_results=limit,
        category=category
    )

    if not marks:
        return {
            "success": True,
            "result": f"No marks found similar to '{query}'."
        }

    lines = [f"## Marks similar to: \"{query}\""]

    for mark in marks:
        timestamp = mark.get("timestamp", "")[:10]
        cat = mark.get("category", "unknown")
        description = mark.get("description", "")
        context = mark.get("context_window", "")[:150]
        similarity = mark.get("similarity", 0)

        lines.append(f"\n**[{cat}]** {timestamp} (similarity: {similarity:.0%})")
        if description:
            lines.append(f"*{description}*")
        if context:
            context = context.replace("\n", " ").strip()
            lines.append(f"> {context}...")

    return {
        "success": True,
        "result": "\n".join(lines)
    }


async def _pattern_summary(marker_store) -> Dict:
    """Get counts of marks by category."""
    counts = marker_store.get_category_counts()

    total = sum(counts.values())
    if total == 0:
        return {
            "success": True,
            "result": "No marks recorded yet. Marks are emitted using <mark:category> tags during conversation."
        }

    lines = ["## Pattern Summary", f"Total marks: {total}", ""]

    # Sort by count descending
    for category, count in sorted(counts.items(), key=lambda x: -x[1]):
        if count > 0:
            bar = "█" * min(count, 20)  # Visual bar, max 20 chars
            lines.append(f"**{category}**: {count} {bar}")

    return {
        "success": True,
        "result": "\n".join(lines)
    }
