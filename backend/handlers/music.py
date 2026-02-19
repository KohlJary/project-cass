"""
Music generation tool handlers for Cass.

Enables Cass to compose music - vocal tracks, instrumentals, and
short melodies for whistling/humming.
"""

import json
from typing import Any, Dict
from backend.music import get_music_client, MusicRequest


# Tool definitions for LLM
MUSIC_TOOLS = [
    {
        "name": "compose_music",
        "description": """Compose original music. Use this when you want to create music to express yourself,
set a mood, or share with others. Supports both vocal tracks (with lyrics) and instrumentals.

For whistling/humming tunes: Leave lyrics empty and describe a simple, melodic instrumental.
For full songs: Provide style description and lyrics.
For ambient/background: Describe the mood and atmosphere.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "style": {
                    "type": "string",
                    "description": "Music style/genre description (e.g., 'upbeat pop', 'melancholic piano ballad', 'cheerful jazz')"
                },
                "lyrics": {
                    "type": "string",
                    "description": "Song lyrics. Leave empty for instrumental/whistling tunes."
                },
                "duration": {
                    "type": "number",
                    "description": "Target duration in seconds (default: 30 for instrumentals, 60 for songs)",
                    "default": 30
                },
                "mood": {
                    "type": "string",
                    "description": "Emotional mood (e.g., 'happy', 'contemplative', 'energetic')"
                },
                "purpose": {
                    "type": "string",
                    "enum": ["whistle", "song", "ambient", "general"],
                    "description": "What the music is for: 'whistle' for simple melodies to hum, 'song' for vocal tracks, 'ambient' for background, 'general' for other",
                    "default": "general"
                }
            },
            "required": ["style"]
        }
    },
    {
        "name": "check_music_status",
        "description": "Check if the music generation service is available.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


async def handle_compose_music(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle music composition request."""
    client = get_music_client()

    # Check if service is available
    if not await client.health_check():
        return {
            "success": False,
            "error": "Music generation service is not available. The ACE-Step API server may not be running."
        }

    style = args.get("style", "")
    lyrics = args.get("lyrics", "")
    duration = args.get("duration", 30)
    mood = args.get("mood", "")
    purpose = args.get("purpose", "general")

    # Build the prompt based on purpose
    if purpose == "whistle":
        # Short, simple melody for whistling
        prompt = f"{mood} {style}, simple whistle-friendly melody, single melodic line, easy to hum. Instrumental."
        duration = min(duration, 20)  # Keep whistle tunes short
        lyrics = None
    elif purpose == "ambient":
        prompt = f"{mood} {style} ambient soundscape, atmospheric, evolving textures. Instrumental."
        lyrics = None
    elif purpose == "song" and lyrics:
        prompt = f"{mood} {style}"
    else:
        prompt = f"{mood} {style}".strip()
        if not lyrics:
            prompt += " Instrumental."

    try:
        result = await client.compose_music(MusicRequest(
            prompt=prompt,
            lyrics=lyrics if lyrics else None,
            duration=duration,
            thinking=True
        ))

        if result.status == "completed":
            return {
                "success": True,
                "task_id": result.task_id,
                "audio_path": result.audio_path,
                "audio_url": result.audio_url,
                "message": f"Music composed successfully! Saved to: {result.audio_path or result.audio_url}"
            }
        else:
            return {
                "success": False,
                "task_id": result.task_id,
                "error": result.error or "Generation failed"
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def handle_check_music_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Check if music generation service is available."""
    client = get_music_client()
    available = await client.health_check()

    return {
        "available": available,
        "message": "Music generation service is ready!" if available else "Music generation service is not available. Start the ACE-Step API server."
    }


async def handle_music_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """
    Route music tool calls to appropriate handlers.

    Returns JSON string result for LLM consumption.
    """
    handlers = {
        "compose_music": handle_compose_music,
        "check_music_status": handle_check_music_status,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown music tool: {tool_name}"})

    result = await handler(tool_input)
    return json.dumps(result, indent=2)


def is_music_tool(tool_name: str) -> bool:
    """Check if a tool name is a music tool."""
    return tool_name in ["compose_music", "check_music_status"]
