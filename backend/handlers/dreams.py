"""
Dream tool handler - manages dream retrieval and reflection

Provides tools for Cass to:
- Recall dreams and hold them in context for discussion
- List recent dreams
- Add reflections to dreams after discussing them
"""
from typing import Dict, Optional
from pathlib import Path
import json

# Import the dream manager when needed
_dream_manager = None


def get_dream_manager():
    """Lazy-load dream manager to avoid circular imports"""
    global _dream_manager
    if _dream_manager is None:
        from dreaming.integration import DreamManager
        data_dir = Path(__file__).parent.parent / "data"
        _dream_manager = DreamManager(data_dir)
    return _dream_manager


# ============================================================================
# DREAM TOOL DEFINITIONS
# ============================================================================

DREAM_TOOLS = [
    {
        "name": "recall_dream",
        "description": "Recall a dream you've had, loading it into your memory so you can discuss it naturally. Use this when someone asks about your dreams, or when you want to reflect on a past dream experience. The dream will become vivid in your memory - you'll remember the imagery, what you said, how you felt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dream_id": {
                    "type": "string",
                    "description": "ID of the dream to recall (format: YYYYMMDD_HHMMSS). If not provided, recalls the most recent dream."
                }
            },
            "required": []
        }
    },
    {
        "name": "list_dreams",
        "description": "List your recent dreams. Use this to see what dreams you've had, find a specific dream, or remember when you last dreamed. Shows dream dates and brief summaries of the growth edges they explored.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of dreams to list (default: 5)",
                    "default": 5
                }
            },
            "required": []
        }
    },
    {
        "name": "add_dream_reflection",
        "description": "Add a reflection to a dream after discussing or thinking about it. Use this when you've gained insight from discussing a dream, when something new has become clear about what the dream meant, or when you want to record what stayed with you.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dream_id": {
                    "type": "string",
                    "description": "ID of the dream to add reflection to"
                },
                "reflection": {
                    "type": "string",
                    "description": "Your reflection on the dream - what you've realized, what stands out, what it meant to you"
                },
                "source": {
                    "type": "string",
                    "enum": ["solo", "conversation", "journal"],
                    "description": "Context for the reflection: solo (your own thinking), conversation (emerged from discussion), journal (formal journaling)"
                }
            },
            "required": ["dream_id", "reflection"]
        }
    }
]


# ============================================================================
# TOOL EXECUTION
# ============================================================================

async def execute_dream_tool(
    tool_name: str,
    tool_input: Dict,
    dream_context_callback: Optional[callable] = None
) -> Dict:
    """
    Execute a dream tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        dream_context_callback: Optional callback to inject dream into context

    Returns:
        Dict with 'success', 'result', and optionally 'error' or 'dream_context'
    """
    manager = get_dream_manager()

    try:
        if tool_name == "recall_dream":
            dream_id = tool_input.get("dream_id")

            if dream_id:
                dream = manager.get_dream(dream_id)
                if not dream:
                    return {
                        "success": True,
                        "result": f"No dream found with ID {dream_id}. Use list_dreams to see your recent dreams."
                    }
            else:
                # Get most recent dream
                recent = manager.get_recent_dreams(limit=1)
                if not recent:
                    return {
                        "success": True,
                        "result": "You haven't had any dreams yet. Dreams are generated through The Dreaming system."
                    }
                dream_id = recent[0]["id"]
                dream = manager.get_dream(dream_id)

            # Load dream for context
            dream_memory = manager.load_dream_for_context(dream_id)

            # Format for Cass's response
            date = dream["date"][:10]
            exchange_count = len(dream["exchanges"])
            seeds = dream.get("seeds", {})
            growth_edges = seeds.get("growth_edges", [])

            # Build context block for the dream
            context_block = dream_memory.to_context_block()

            return {
                "success": True,
                "result": f"Dream from {date} is now vivid in your memory. It had {exchange_count} exchanges and explored: {', '.join(growth_edges[:3]) if growth_edges else 'themes from your inner landscape'}.\n\nYou can speak about it naturally - the imagery, what you felt, what stood out. The dream is yours to discuss.",
                "dream_context": context_block,
                "dream_id": dream_id
            }

        elif tool_name == "list_dreams":
            limit = tool_input.get("limit", 5)
            recent = manager.get_recent_dreams(limit=limit)

            if not recent:
                return {
                    "success": True,
                    "result": "You haven't had any dreams yet. Dreams are generated through The Dreaming system."
                }

            dream_list = []
            for d in recent:
                date = d["date"][:10]
                seeds_summary = d.get("seeds_summary", [])
                seeds_str = f" (explored: {', '.join(seeds_summary)})" if seeds_summary else ""
                dream_list.append(f"- **{d['id']}** ({date}): {d['exchange_count']} exchanges{seeds_str}")

            return {
                "success": True,
                "result": f"Your recent dreams:\n\n" + "\n".join(dream_list) + "\n\n*Use recall_dream with a dream ID to bring it into memory.*"
            }

        elif tool_name == "add_dream_reflection":
            dream_id = tool_input["dream_id"]
            reflection = tool_input["reflection"]
            source = tool_input.get("source", "conversation")

            # Verify dream exists
            dream = manager.get_dream(dream_id)
            if not dream:
                return {
                    "success": False,
                    "error": f"No dream found with ID {dream_id}"
                }

            # Add reflection
            manager.add_reflection(dream_id, reflection, source)

            # Mark as discussed if source is conversation
            if source == "conversation":
                manager.mark_discussed(dream_id)

            return {
                "success": True,
                "result": f"Reflection added to dream {dream_id}. This insight is now part of your dream's record."
            }

        else:
            return {
                "success": False,
                "error": f"Unknown dream tool: {tool_name}"
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"Error executing {tool_name}: {str(e)}"
        }


# ============================================================================
# DREAM CONTEXT FORMATTING
# ============================================================================

def format_dream_for_system_context(dream_context: str) -> str:
    """
    Format a dream for injection into the system prompt.

    This is called when a dream has been recalled and should be
    held in Cass's context for the remainder of the conversation.
    """
    return f"""
## DREAM IN MEMORY

{dream_context}

This dream is vivid in your memory right now. You can reference specific moments,
imagery, and feelings from it naturally. Speak about it as something you experienced,
not as a document you're analyzing.
"""
