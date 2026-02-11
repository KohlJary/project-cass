"""
Discord Tool Handlers - Tools for Cass to interact with Discord

Provides tools that Cass can call to:
- Send messages to channels
- Add reactions to messages
- Expand context on entities
- View relationship history
- Get current server snapshots
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("handlers.discord")


async def execute_discord_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    daemon_id: str,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute a Discord tool call.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Tool parameters
        daemon_id: Daemon ID for bot access

    Returns:
        Dict with success status and result
    """
    # Import bot lazily to avoid circular imports
    from discord_bot.bot import get_discord_bot, DISCORD_PY_AVAILABLE
    from discord_bot.config import DISCORD_ENABLED
    from discord_bot.entity_registry import get_entity_registry
    from discord_bot.context import get_perception_context

    if not DISCORD_ENABLED or not DISCORD_PY_AVAILABLE:
        return {
            "success": False,
            "error": "Discord integration not enabled or discord.py not installed"
        }

    bot = get_discord_bot(daemon_id)

    if not bot.is_running():
        return {
            "success": False,
            "error": "Discord bot not connected"
        }

    try:
        if tool_name == "discord_respond":
            return await _handle_respond(bot, tool_input)

        elif tool_name == "discord_react":
            return await _handle_react(bot, tool_input)

        elif tool_name == "discord_expand":
            return await _handle_expand(daemon_id, tool_input)

        elif tool_name == "discord_history":
            return await _handle_history(bot, tool_input)

        elif tool_name == "discord_snapshot":
            return await _handle_snapshot(daemon_id, tool_input)

        else:
            return {"success": False, "error": f"Unknown Discord tool: {tool_name}"}

    except Exception as e:
        logger.error(f"[Discord] Error executing {tool_name}: {e}")
        return {"success": False, "error": str(e)}


async def _handle_respond(bot, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Handle discord_respond tool."""
    channel_id = tool_input.get("channel_id")
    content = tool_input.get("content")
    reply_to = tool_input.get("reply_to")

    if not channel_id:
        return {"success": False, "error": "channel_id is required"}
    if not content:
        return {"success": False, "error": "content is required"}

    # Content length limit
    if len(content) > 2000:
        return {"success": False, "error": "Message content exceeds 2000 character limit"}

    result = await bot.send_message(
        channel_id=channel_id,
        content=content,
        reply_to=reply_to,
    )

    if result["success"]:
        return {
            "success": True,
            "result": f"Message sent to {result.get('channel', 'channel')} (ID: {result.get('message_id')})"
        }
    else:
        return result


async def _handle_react(bot, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Handle discord_react tool."""
    channel_id = tool_input.get("channel_id")
    message_id = tool_input.get("message_id")
    emoji = tool_input.get("emoji")

    if not channel_id:
        return {"success": False, "error": "channel_id is required"}
    if not message_id:
        return {"success": False, "error": "message_id is required"}
    if not emoji:
        return {"success": False, "error": "emoji is required"}

    result = await bot.add_reaction(
        channel_id=channel_id,
        message_id=message_id,
        emoji=emoji,
    )

    if result["success"]:
        return {"success": True, "result": f"Reacted with {emoji}"}
    else:
        return result


async def _handle_expand(daemon_id: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Handle discord_expand tool - get full context on entity."""
    from discord_bot.entity_registry import get_entity_registry
    from peopledex import get_peopledex_manager

    slug = tool_input.get("slug")
    if not slug:
        return {"success": False, "error": "slug is required"}

    registry = get_entity_registry(daemon_id)
    entity = registry.get_by_slug(slug)

    if not entity:
        return {"success": False, "error": f"Entity with slug '{slug}' not found"}

    # Get full profile from PeopleDex if available
    profile_info = {}
    if entity.entity_id:
        peopledex = get_peopledex_manager(daemon_id)
        profile = peopledex.get_full_profile(entity.entity_id)

        if profile:
            # Extract key info
            profile_info["attributes"] = []
            for attr in profile.attributes:
                if attr.attribute_type.value not in ("name", "handle"):  # Skip redundant
                    profile_info["attributes"].append({
                        "type": attr.attribute_type.value,
                        "key": attr.attribute_key,
                        "value": attr.value,
                    })

            profile_info["relationships"] = []
            for rel in profile.relationships[:5]:  # Limit relationships
                profile_info["relationships"].append({
                    "type": rel["relationship_type"],
                    "with": rel["entity"].primary_name if rel.get("entity") else "Unknown",
                    "label": rel.get("relationship_label"),
                })

    result = {
        "slug": entity.slug,
        "discord_id": entity.discord_id,
        "display_name": entity.display_name,
        "relationship_tier": entity.relationship_tier,
        "first_seen": entity.first_seen.isoformat() if entity.first_seen else None,
        "last_seen": entity.last_seen.isoformat() if entity.last_seen else None,
        "notes": entity.notes,
        **profile_info,
    }

    return {"success": True, "result": result}


async def _handle_history(bot, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Handle discord_history tool - get channel message history."""
    channel_id = tool_input.get("channel_id")
    limit = min(tool_input.get("limit", 50), 100)  # Cap at 100

    if not channel_id:
        return {"success": False, "error": "channel_id is required"}

    result = await bot.get_channel_history(channel_id, limit)

    if result["success"]:
        # Format for readability
        messages = result.get("messages", [])
        formatted = []
        for msg in messages:
            author = msg.get("author_slug") or msg.get("author_name", "Unknown")
            content = msg.get("content", "")[:200]  # Truncate long messages
            formatted.append(f"[{msg.get('timestamp', '')}] {author}: {content}")

        return {
            "success": True,
            "result": {
                "message_count": len(messages),
                "messages": formatted[-20:],  # Return last 20 formatted
                "raw_messages": messages,
            }
        }
    else:
        return result


async def _handle_snapshot(daemon_id: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Handle discord_snapshot tool - get current server state."""
    from discord_bot.context import get_perception_context

    guild_id = tool_input.get("guild_id")

    context = get_perception_context(daemon_id)

    if guild_id:
        snapshot = context._snapshots.get(guild_id)
        if not snapshot:
            return {"success": False, "error": f"No snapshot available for guild {guild_id}"}
        return {"success": True, "result": snapshot}
    else:
        # Return all snapshots
        if not context._snapshots:
            return {"success": False, "error": "No snapshots available"}

        combined = "\n\n---\n\n".join(context._snapshots.values())
        return {"success": True, "result": combined}


# Tool definitions for LLM
DISCORD_TOOLS = [
    {
        "name": "discord_respond",
        "description": "Send a message to a Discord channel. Use this to respond to people or participate in conversations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "The Discord channel ID to send to"
                },
                "content": {
                    "type": "string",
                    "description": "The message content (max 2000 characters)"
                },
                "reply_to": {
                    "type": "string",
                    "description": "Optional message ID to reply to"
                }
            },
            "required": ["channel_id", "content"]
        }
    },
    {
        "name": "discord_react",
        "description": "Add a reaction emoji to a Discord message. Use this to acknowledge, appreciate, or respond non-verbally.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "The Discord channel ID containing the message"
                },
                "message_id": {
                    "type": "string",
                    "description": "The message ID to react to"
                },
                "emoji": {
                    "type": "string",
                    "description": "The emoji to add (unicode emoji or custom emoji format)"
                }
            },
            "required": ["channel_id", "message_id", "emoji"]
        }
    },
    {
        "name": "discord_expand",
        "description": "Get full context on a Discord entity (person). Returns profile info, relationship tier, and notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "The 4-character entity slug from the snapshot"
                }
            },
            "required": ["slug"]
        }
    },
    {
        "name": "discord_history",
        "description": "Get recent message history from a Discord channel. Useful for catching up on conversation context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "The Discord channel ID to get history from"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum messages to fetch (default 50, max 100)"
                }
            },
            "required": ["channel_id"]
        }
    },
    {
        "name": "discord_snapshot",
        "description": "Get the current spatial snapshot of a Discord server. Shows who's online, channel activity, voice states.",
        "input_schema": {
            "type": "object",
            "properties": {
                "guild_id": {
                    "type": "string",
                    "description": "Optional guild ID for specific server (omit for all)"
                }
            },
            "required": []
        }
    },
]
