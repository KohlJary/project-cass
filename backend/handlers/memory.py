"""
Memory tool handler - manages memory operations for Cass
Includes summary regeneration for better narrative quality
"""
from typing import Dict, Any
from config import ANTHROPIC_API_KEY

# Tool definitions (Anthropic format)
MEMORY_TOOLS = [
    {
        "name": "regenerate_summary",
        "description": "Regenerate the working summary for the current conversation. Use this when you feel your memory of the conversation feels disconnected or needs refreshing. This will rebuild your working memory from the stored summary chunks using the improved narrative system.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Optional: why you want to regenerate the summary"
                }
            },
            "required": []
        }
    },
    {
        "name": "view_memory_chunks",
        "description": "View the individual memory chunks that make up your memory of this conversation. Use this to understand how your memory is structured or to see what details you've captured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of chunks to return (default 5)",
                    "default": 5
                }
            },
            "required": []
        }
    }
]


async def execute_memory_tool(
    tool_name: str,
    tool_input: Dict,
    memory,
    conversation_id: str,
    conversation_manager,
    token_tracker=None
) -> Dict[str, Any]:
    """
    Execute a memory tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        memory: CassMemory instance
        conversation_id: ID of current conversation
        conversation_manager: ConversationManager instance
        token_tracker: Optional TokenUsageTracker

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "regenerate_summary":
            return await _regenerate_summary(
                tool_input, memory, conversation_id,
                conversation_manager, token_tracker
            )

        elif tool_name == "view_memory_chunks":
            return await _view_memory_chunks(
                tool_input, memory, conversation_id
            )

        else:
            return {"success": False, "error": f"Unknown memory tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def _regenerate_summary(
    tool_input: Dict,
    memory,
    conversation_id: str,
    conversation_manager,
    token_tracker=None
) -> Dict[str, Any]:
    """Regenerate the working summary for a conversation."""
    reason = tool_input.get("reason", "")

    # Get conversation for title
    conversation = conversation_manager.load_conversation(conversation_id)
    if not conversation:
        return {
            "success": False,
            "error": "Could not load conversation"
        }

    # Check if there are any summaries to regenerate from
    summaries = memory.get_summaries_for_conversation(conversation_id)
    if not summaries:
        return {
            "success": True,
            "result": "No memory chunks found to regenerate from. Your conversation may not have been summarized yet."
        }

    # Regenerate (full rebuild mode - no new_chunk or existing_summary)
    new_working_summary = await memory.generate_working_summary(
        conversation_id=conversation_id,
        conversation_title=conversation.title,
        new_chunk=None,
        existing_summary=None,
        anthropic_api_key=ANTHROPIC_API_KEY,
        token_tracker=token_tracker
    )

    if not new_working_summary:
        return {
            "success": False,
            "error": "Failed to generate working summary"
        }

    # Update the conversation's working summary
    conversation_manager.update_working_summary(conversation_id, new_working_summary)

    result_msg = f"Successfully regenerated working memory from {len(summaries)} memory chunk(s)."
    if reason:
        result_msg += f"\n\nReason for regeneration: {reason}"
    result_msg += f"\n\nNew working memory ({len(new_working_summary)} characters):\n\n{new_working_summary}"

    return {
        "success": True,
        "result": result_msg
    }


async def _view_memory_chunks(
    tool_input: Dict,
    memory,
    conversation_id: str
) -> Dict[str, Any]:
    """View memory chunks for the conversation."""
    limit = tool_input.get("limit", 5)

    summaries = memory.get_summaries_for_conversation(conversation_id)

    if not summaries:
        return {
            "success": True,
            "result": "No memory chunks found for this conversation yet."
        }

    # Get the most recent chunks
    recent = summaries[-limit:] if len(summaries) > limit else summaries

    chunks_text = []
    for i, s in enumerate(recent, 1):
        metadata = s.get("metadata", {})
        timeframe_start = metadata.get("timeframe_start", "unknown")
        timeframe_end = metadata.get("timeframe_end", "unknown")
        message_count = metadata.get("message_count", "?")

        chunks_text.append(
            f"**Chunk {i}** ({timeframe_start} to {timeframe_end}, {message_count} messages):\n{s['content']}"
        )

    return {
        "success": True,
        "result": f"Found {len(summaries)} total memory chunk(s). Showing {len(recent)} most recent:\n\n" +
                  "\n\n---\n\n".join(chunks_text)
    }
