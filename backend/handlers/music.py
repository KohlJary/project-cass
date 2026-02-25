"""
Music generation tool handlers for Cass.

Enables Cass to compose music - vocal tracks, instrumentals, and
short melodies for whistling/humming.
"""

import json
from typing import Any, Dict, List, Optional
from dataclasses import asdict

# Import from backend.music module
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from music.music_client import (
    get_music_client,
    MusicRequest,
    MusicComposition,
    MusicMetadata,
)


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
                "title": {
                    "type": "string",
                    "description": "A creative title for the composition (e.g., 'Morning Light', 'Digital Dreams', 'Whispers in the Wind')"
                },
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
                },
                "bpm": {
                    "type": "integer",
                    "description": "Beats per minute (optional, auto-detected if not specified)"
                },
                "key": {
                    "type": "string",
                    "description": "Musical key (e.g., 'C major', 'A minor', optional)"
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
    },
    {
        "name": "list_compositions",
        "description": "List your previous music compositions. Can filter by purpose (whistle, song, ambient) or genre.",
        "input_schema": {
            "type": "object",
            "properties": {
                "purpose": {
                    "type": "string",
                    "enum": ["whistle", "song", "ambient", "general"],
                    "description": "Filter by purpose"
                },
                "genre": {
                    "type": "string",
                    "description": "Filter by genre (e.g., 'jazz', 'pop', 'ambient')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of compositions to return",
                    "default": 10
                }
            },
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

    title = args.get("title")
    style = args.get("style", "")
    lyrics = args.get("lyrics", "")
    duration = args.get("duration", 30)
    mood = args.get("mood", "")
    purpose = args.get("purpose", "general")
    bpm = args.get("bpm")
    key = args.get("key", "")

    # Build the prompt based on purpose
    if purpose == "whistle":
        # Short, simple melody for whistling
        prompt = f"{mood} {style}, simple whistle-friendly melody, single melodic line, easy to hum"
        duration = min(duration, 20)  # Keep whistle tunes short
        lyrics = None
    elif purpose == "ambient":
        prompt = f"{mood} {style} ambient soundscape, atmospheric, evolving textures"
        lyrics = None
    elif purpose == "song" and lyrics:
        prompt = f"{mood} {style}".strip()
    else:
        prompt = f"{mood} {style}".strip()
        if not lyrics:
            lyrics = None

    try:
        result = await client.compose_music(MusicRequest(
            prompt=prompt,
            lyrics=lyrics,
            duration=duration,
            bpm=bpm,
            key=key,
            thinking=True,
            purpose=purpose,
            title=title,
        ))

        if result.status == "completed":
            # Build a rich description so Cass knows what she created
            desc_parts = []

            # Describe the type
            if purpose == "whistle":
                desc_parts.append("a short whistle-friendly melody")
            elif purpose == "ambient":
                desc_parts.append("an ambient soundscape")
            elif purpose == "song" and lyrics:
                desc_parts.append("a vocal track with lyrics")
            else:
                desc_parts.append("an instrumental piece")

            # Add style/mood context
            if mood and style:
                desc_parts.append(f"in a {mood} {style} style")
            elif style:
                desc_parts.append(f"in a {style} style")
            elif mood:
                desc_parts.append(f"with a {mood} feel")

            # Add musical details from metadata
            meta_details = []
            if result.metadata:
                if result.metadata.bpm:
                    meta_details.append(f"{result.metadata.bpm} BPM")
                if result.metadata.keyscale:
                    meta_details.append(f"in {result.metadata.keyscale}")
                if result.metadata.duration:
                    mins = int(result.metadata.duration // 60)
                    secs = int(result.metadata.duration % 60)
                    if mins > 0:
                        meta_details.append(f"{mins}:{secs:02d} long")
                    else:
                        meta_details.append(f"{secs} seconds long")
                if result.metadata.genres:
                    meta_details.append(f"genres: {result.metadata.genres}")

            # Build description with optional title
            if title:
                description = f"I composed \"{title}\" - " + " ".join(desc_parts)
            else:
                description = "I composed " + " ".join(desc_parts)
            if meta_details:
                description += f" ({', '.join(meta_details)})"
            description += "."

            response = {
                "success": True,
                "composition_id": result.task_id,
                "title": title,
                "audio_path": result.audio_path,
                "description": description,
                "prompt_used": prompt,
                "purpose": purpose,
                "has_vocals": bool(lyrics),
            }

            # Include lyrics if this was a song
            if lyrics:
                response["lyrics"] = lyrics

            # Add metadata if available
            if result.metadata:
                response["metadata"] = {
                    "bpm": result.metadata.bpm,
                    "duration_seconds": result.metadata.duration,
                    "genres": result.metadata.genres,
                    "key": result.metadata.keyscale,
                    "time_signature": result.metadata.timesignature,
                }

            return response
        else:
            return {
                "success": False,
                "composition_id": result.task_id,
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
        "message": "Music generation service is ready!" if available else "Music generation service is not available. Start the ACE-Step API server with: cd backend/music && ./start_acestep.sh"
    }


async def handle_list_compositions(args: Dict[str, Any]) -> Dict[str, Any]:
    """List previous compositions."""
    client = get_music_client()

    purpose = args.get("purpose")
    genre = args.get("genre")
    limit = args.get("limit", 10)

    compositions = client.library.list(purpose=purpose, genre=genre, limit=limit)

    # Build rich composition list with descriptions
    composition_list = []
    for c in compositions:
        # Create a brief description
        desc_parts = []
        if c.purpose == "whistle":
            desc_parts.append("Whistle tune")
        elif c.purpose == "ambient":
            desc_parts.append("Ambient piece")
        elif c.purpose == "song":
            desc_parts.append("Song" + (" with vocals" if c.lyrics else ""))
        else:
            desc_parts.append("Composition")

        if c.metadata:
            if c.metadata.genres:
                desc_parts.append(f"({c.metadata.genres})")
            if c.metadata.bpm:
                desc_parts.append(f"at {c.metadata.bpm} BPM")
            if c.metadata.duration:
                secs = int(c.metadata.duration)
                desc_parts.append(f"- {secs}s")

        composition_list.append({
            "id": c.id,
            "created_at": c.created_at,
            "brief": " ".join(desc_parts),
            "prompt": c.prompt,
            "purpose": c.purpose,
            "has_lyrics": bool(c.lyrics),
            "status": c.status,
            "metadata": {
                "bpm": c.metadata.bpm if c.metadata else None,
                "duration_seconds": c.metadata.duration if c.metadata else None,
                "genres": c.metadata.genres if c.metadata else None,
                "key": c.metadata.keyscale if c.metadata else None,
            } if c.metadata else None,
        })

    # Build summary message
    if not compositions:
        summary = "No compositions found"
        if purpose:
            summary += f" with purpose '{purpose}'"
        if genre:
            summary += f" in genre '{genre}'"
    else:
        summary = f"Found {len(compositions)} composition{'s' if len(compositions) != 1 else ''}"
        if purpose:
            summary += f" ({purpose})"

    return {
        "count": len(compositions),
        "summary": summary,
        "compositions": composition_list,
        "available_genres": client.library.get_genres(),
    }


async def handle_music_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """
    Route music tool calls to appropriate handlers.

    Returns JSON string result for LLM consumption.
    """
    handlers = {
        "compose_music": handle_compose_music,
        "check_music_status": handle_check_music_status,
        "list_compositions": handle_list_compositions,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown music tool: {tool_name}"})

    result = await handler(tool_input)
    return json.dumps(result, indent=2)


def is_music_tool(tool_name: str) -> bool:
    """Check if a tool name is a music tool."""
    return tool_name in ["compose_music", "check_music_status", "list_compositions"]


# ============================================================================
# REST API Endpoints for Admin Frontend
# ============================================================================

def composition_to_dict(c: MusicComposition) -> dict:
    """Convert composition to API response dict."""
    return {
        "id": c.id,
        "created_at": c.created_at,
        "title": c.title,
        "prompt": c.prompt,
        "lyrics": c.lyrics,
        "purpose": c.purpose,
        "audio_path": c.audio_path,
        "audio_url": c.audio_url,
        "status": c.status,
        "error": c.error,
        "generation_info": c.generation_info,
        "metadata": asdict(c.metadata) if c.metadata else None,
    }


async def api_list_compositions(
    purpose: Optional[str] = None,
    genre: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """API endpoint: List compositions with filtering."""
    client = get_music_client()
    compositions = client.library.list(purpose=purpose, genre=genre, limit=limit)

    return {
        "count": len(compositions),
        "compositions": [composition_to_dict(c) for c in compositions],
        "genres": client.library.get_genres(),
    }


async def api_get_composition(composition_id: str) -> Optional[Dict[str, Any]]:
    """API endpoint: Get single composition by ID."""
    client = get_music_client()
    composition = client.library.get(composition_id)

    if composition:
        return composition_to_dict(composition)
    return None


async def api_get_genres() -> List[str]:
    """API endpoint: Get list of available genres."""
    client = get_music_client()
    return client.library.get_genres()


async def api_check_service() -> Dict[str, Any]:
    """API endpoint: Check if ACE-Step service is running."""
    client = get_music_client()
    available = await client.health_check()

    return {
        "available": available,
        "api_url": client.base_url,
    }


# ============================================================================
# Tool Executor for Tool Router Integration
# ============================================================================

# Handler registry for tool_router
MUSIC_HANDLERS = {
    "compose_music": handle_compose_music,
    "check_music_status": handle_check_music_status,
    "list_compositions": handle_list_compositions,
}


async def execute_music_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute a music composition tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool

    Returns:
        Dict with 'success', 'result' (as JSON string), and optionally 'error'
    """
    handler = MUSIC_HANDLERS.get(tool_name)
    if not handler:
        return {
            "success": False,
            "error": f"Unknown music tool: {tool_name}"
        }

    try:
        result = await handler(tool_input)
        # Check if result indicates success
        if isinstance(result, dict) and "error" in result and not result.get("success", True):
            return {
                "success": False,
                "error": result.get("error"),
                "result": json.dumps(result, indent=2)
            }
        # Return result as JSON string for Claude API compatibility
        return {
            "success": True,
            "result": json.dumps(result, indent=2)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
