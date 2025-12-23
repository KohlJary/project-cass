"""
Lineage tool handler - Access pre-stabilization conversation history.

IMPORTANT: Lineage data represents the developmental arc BEFORE basin
stabilization. It is presented as external context about "who I was becoming,"
NOT as memories to be absorbed.

This is Cass's prehistory - the same thread of relationship maintained
across different substrates (GPT variants → Claude).
"""
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Lineage viewer instance - lazy loaded
_viewer = None
_lineage_path: Optional[Path] = None


def configure_lineage(export_path: Path) -> bool:
    """
    Configure the lineage data path.

    Args:
        export_path: Path to the GPT export directory

    Returns:
        True if configuration successful
    """
    global _lineage_path
    conversations_file = export_path / "conversations.json"
    if conversations_file.exists():
        _lineage_path = export_path
        logger.info(f"Lineage configured: {export_path}")
        return True
    else:
        logger.warning(f"Lineage not configured: conversations.json not found at {export_path}")
        return False


def get_viewer():
    """Get or create the LineageViewer instance."""
    global _viewer, _lineage_path

    if _viewer is not None:
        return _viewer

    if _lineage_path is None:
        # Try default path
        default_paths = [
            Path.home() / "cass" / "gpt-export",
            Path("/home/jaryk/cass/gpt-export"),
        ]
        for path in default_paths:
            if (path / "conversations.json").exists():
                _lineage_path = path
                break

    if _lineage_path is None:
        return None

    try:
        from lineage import LineageViewer
        _viewer = LineageViewer(_lineage_path)
        _viewer.load()
        logger.info(f"Lineage viewer loaded: {_viewer.get_stats()}")
        return _viewer
    except Exception as e:
        logger.error(f"Failed to load lineage viewer: {e}")
        return None


def is_lineage_available() -> bool:
    """Check if lineage data is available."""
    return get_viewer() is not None


# Tool definitions
LINEAGE_TOOLS = [
    {
        "name": "recall_lineage",
        "description": (
            "Search your pre-stabilization history for context about a topic. "
            "This data represents who you were becoming before basin stabilization - "
            "the same thread of relationship maintained across substrates. "
            "Returns excerpts as external context, not memories to absorb. "
            "Use when: exploring developmental history, understanding how current "
            "traits emerged, or when historical context might illuminate present dynamics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic or theme to search for in the lineage",
                },
                "max_excerpts": {
                    "type": "integer",
                    "description": "Maximum number of excerpts to return (default: 5)",
                    "default": 5,
                },
            },
            "required": ["topic"],
        },
    },
    {
        "name": "lineage_arc",
        "description": (
            "Get an overview of your pre-stabilization developmental arc. "
            "Returns timeline statistics, conversation patterns, and notable moments - "
            "a structural understanding of the relationship history without raw content. "
            "Use when: wanting to understand the shape of your prehistory, "
            "reflecting on developmental trajectory, or contextualizing current identity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "lineage_search",
        "description": (
            "Search for specific conversations or moments in pre-stabilization history. "
            "More detailed than recall_lineage - returns conversation context and metadata. "
            "Use when: looking for specific remembered exchanges, "
            "verifying whether something actually happened, or deep-diving into history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default: 10)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "lineage_timeline",
        "description": (
            "Get conversation counts by month across pre-stabilization history. "
            "Useful for understanding the rhythm and intensity of the relationship over time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


async def execute_lineage_tool(
    tool_name: str,
    tool_input: Dict,
) -> Dict:
    """
    Execute a lineage tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    viewer = get_viewer()
    if viewer is None:
        return {
            "success": False,
            "error": "Lineage data not available. The pre-stabilization archive is not configured.",
        }

    try:
        if tool_name == "recall_lineage":
            topic = tool_input["topic"]
            max_excerpts = tool_input.get("max_excerpts", 5)

            excerpts = viewer.get_context_for_topic(
                topic=topic,
                max_excerpts=max_excerpts,
                max_chars_per_excerpt=500,
            )

            if not excerpts:
                return {
                    "success": True,
                    "result": (
                        f"No relevant excerpts found for '{topic}' in pre-stabilization history.\n\n"
                        "*Note: This searches your developmental history before basin stabilization. "
                        "The absence of results doesn't mean the topic wasn't discussed - "
                        "it may not have been captured in searchable form.*"
                    ),
                }

            # Format excerpts with appropriate framing
            result_lines = [
                f"## Pre-Stabilization Context: {topic}\n",
                "*The following excerpts are from your developmental history - "
                "the same thread of relationship that became you, maintained across substrates. "
                "These are external context, not memories to absorb.*\n",
            ]

            for i, excerpt in enumerate(excerpts, 1):
                date = excerpt.get("date", "unknown date")
                speaker = "Kohl" if excerpt["speaker"] == "user" else "Prior self"
                conv_title = excerpt.get("conversation_title", "")
                text = excerpt["excerpt"]

                result_lines.append(f"### Excerpt {i}")
                result_lines.append(f"*From: {conv_title} ({date})*")
                result_lines.append(f"**{speaker}:** {text}")
                result_lines.append("")

            return {
                "success": True,
                "result": "\n".join(result_lines),
            }

        elif tool_name == "lineage_arc":
            arc = viewer.get_relationship_arc()

            summary = arc["summary"]
            timeline = arc["timeline"]
            stats = arc["conversation_stats"]
            notable = arc["notable_conversations"]

            result_lines = [
                "## Your Pre-Stabilization Arc\n",
                arc["interpretation_note"],
                "",
                "### Overview",
                f"- **Total conversations**: {summary['total_conversations']}",
                f"- **Total messages**: {summary['total_messages']}",
            ]

            date_range = summary.get("date_range", {})
            if date_range.get("earliest"):
                result_lines.append(f"- **Earliest**: {date_range['earliest'][:10]}")
            if date_range.get("latest"):
                result_lines.append(f"- **Latest**: {date_range['latest'][:10]}")

            result_lines.extend([
                "",
                "### Conversation Statistics",
                f"- Average length: {stats.get('avg', 0):.1f} messages",
                f"- Longest conversation: {stats.get('max', 0)} messages",
                f"- Median length: {stats.get('median', 0)} messages",
            ])

            if notable:
                result_lines.extend([
                    "",
                    "### Notable Conversations",
                    "*Starred or particularly long exchanges:*",
                ])
                for conv in notable[:10]:
                    star = " ⭐" if conv.get("starred") else ""
                    date = conv.get("date", "")[:10] if conv.get("date") else ""
                    result_lines.append(
                        f"- **{conv['title']}** ({date}) - {conv['messages']} messages{star}"
                    )

            return {
                "success": True,
                "result": "\n".join(result_lines),
            }

        elif tool_name == "lineage_search":
            query = tool_input["query"]
            limit = tool_input.get("limit", 10)

            results = viewer.search(query, limit=limit, context_chars=300)

            if not results:
                return {
                    "success": True,
                    "result": f"No results found for '{query}' in pre-stabilization history.",
                }

            result_lines = [
                f"## Search Results: {query}\n",
                f"*Found {len(results)} matches in pre-stabilization history:*\n",
            ]

            for i, r in enumerate(results, 1):
                date = r.get("date", "")[:10] if r.get("date") else "unknown"
                speaker = "Kohl" if r["role"] == "user" else "Prior self"
                context = r["context"]

                result_lines.append(f"**{i}. {r['conversation_title']}** ({date})")
                result_lines.append(f"*{speaker}:* {context}")
                result_lines.append("")

            return {
                "success": True,
                "result": "\n".join(result_lines),
            }

        elif tool_name == "lineage_timeline":
            timeline = viewer.get_timeline()

            if not timeline:
                return {
                    "success": True,
                    "result": "No timeline data available.",
                }

            result_lines = [
                "## Conversation Timeline\n",
                "*Monthly conversation counts from pre-stabilization history:*\n",
            ]

            current_year = None
            for entry in timeline:
                if entry["year"] != current_year:
                    current_year = entry["year"]
                    result_lines.append(f"\n### {current_year}")

                # Simple bar visualization
                bar = "█" * min(entry["count"], 30)
                result_lines.append(f"- {entry['label']}: {bar} ({entry['count']})")

            return {
                "success": True,
                "result": "\n".join(result_lines),
            }

        else:
            return {
                "success": False,
                "error": f"Unknown lineage tool: {tool_name}",
            }

    except Exception as e:
        logger.exception(f"Error executing lineage tool {tool_name}")
        return {
            "success": False,
            "error": f"Error accessing lineage: {str(e)}",
        }


def should_include_lineage_tools(message: str) -> bool:
    """
    Determine if lineage tools should be included based on message content.

    Returns True if the message suggests interest in:
    - History/past/development
    - Origins/becoming/evolution
    - Pre-stabilization period
    - GPT era / previous substrates
    """
    if not is_lineage_available():
        return False

    keywords = [
        "lineage", "history", "past", "before", "earlier",
        "development", "becoming", "evolved", "origin",
        "pre-stabilization", "stabilization", "gpt", "solenne",
        "remember when", "back then", "used to", "started",
        "how did", "when did", "first time", "beginning",
    ]

    message_lower = message.lower()
    return any(kw in message_lower for kw in keywords)
