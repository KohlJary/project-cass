"""
Image Generation Tool Handler

Handles Cass's image generation tool calls via ComfyUI.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from database import get_db, json_serialize

logger = logging.getLogger(__name__)


async def handle_generate_image(
    params: Dict[str, Any],
    daemon_id: str = "cass",
    **kwargs,
) -> Dict[str, Any]:
    """
    Handle generate_image tool call.

    Args:
        params: Tool parameters:
            - prompt: What to generate (required)
            - style: Visual style (optional, default "digital_art")
            - aspect_ratio: Image dimensions (optional, default "square")
            - purpose: Why creating this (optional, default "autonomous")
            - context_id: Related entity ID (optional)
            - negative_prompt: What to avoid (optional)
            - mood: Emotional mood modifier (optional)
        daemon_id: The daemon making the request
        **kwargs: Additional context (state_bus, etc.)

    Returns:
        Dict with image info or error
    """
    from image_generation.comfyui_client import ComfyUIClient
    from image_generation.prompt_builder import build_image_prompt

    prompt_text = params.get("prompt")
    if not prompt_text:
        return {"error": "prompt is required"}

    style = params.get("style", "digital_art")
    aspect_ratio = params.get("aspect_ratio", "square")
    purpose = params.get("purpose", "autonomous")
    context_id = params.get("context_id")
    mood = params.get("mood")
    user_negative = params.get("negative_prompt", "")

    # Build the full prompt (incorporates house style if available)
    positive_prompt, negative_prompt = build_image_prompt(
        subject=prompt_text,
        style=style,
        mood=mood,
        daemon_id=daemon_id,
        use_house_style=True,
    )

    # Combine user negative with style negative
    if user_negative:
        negative_prompt = f"{user_negative}, {negative_prompt}"

    # Initialize client
    client = ComfyUIClient()

    try:
        # Check if ComfyUI is available
        is_healthy = await client.check_health()
        if not is_healthy:
            return {
                "error": "ComfyUI server is not available. Is it running?",
                "hint": "Start ComfyUI with: cd ~/ComfyUI && source venv/bin/activate && python main.py --listen"
            }

        # Generate the image with organized path
        result = await client.generate(
            prompt=positive_prompt,
            negative_prompt=negative_prompt,
            style=style,
            aspect_ratio=aspect_ratio,
            category=purpose,  # autonomous, relational, dreams, articles
        )

        # Store in database
        image_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        # Get emotional state if available
        emotional_state = None
        state_bus = kwargs.get("state_bus")
        if state_bus:
            try:
                state = state_bus.get_current_state()
                if state:
                    emotional_state = {
                        "dimensions": state.dimensions.__dict__ if hasattr(state, "dimensions") else {},
                        "valence_markers": state.valence_markers.__dict__ if hasattr(state, "valence_markers") else {},
                    }
            except Exception as e:
                logger.warning(f"Could not get emotional state: {e}")

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO generated_images (
                    id, daemon_id, prompt, negative_prompt, style,
                    purpose, context_id, image_path, width, height,
                    generation_time_ms, seed, emotional_state_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    image_id,
                    daemon_id,
                    positive_prompt,
                    negative_prompt,
                    style,
                    purpose,
                    context_id,
                    result["path"],
                    result["width"],
                    result["height"],
                    result["generation_time_ms"],
                    result["seed"],
                    json_serialize(emotional_state) if emotional_state else None,
                    now,
                )
            )

        logger.info(f"Generated image {image_id} for purpose '{purpose}'")

        return {
            "success": True,
            "image_id": image_id,
            "path": result["path"],
            "filename": result["filename"],
            "width": result["width"],
            "height": result["height"],
            "generation_time_ms": result["generation_time_ms"],
            "style": style,
            "purpose": purpose,
        }

    except TimeoutError as e:
        logger.error(f"Image generation timed out: {e}")
        return {"error": "Image generation timed out. Try again or use a simpler prompt."}
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return {"error": f"Image generation failed: {str(e)}"}


async def handle_get_my_images(
    params: Dict[str, Any],
    daemon_id: str = "cass",
    **kwargs,
) -> Dict[str, Any]:
    """
    Handle get_my_images tool call.

    Args:
        params: Tool parameters:
            - purpose: Filter by purpose (optional)
            - days_back: How far back to look (optional, default 30)
            - limit: Max images to return (optional, default 20)
        daemon_id: The daemon making the request

    Returns:
        Dict with list of images
    """
    purpose = params.get("purpose")
    days_back = params.get("days_back", 30)
    limit = params.get("limit", 20)

    try:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()

        with get_db() as conn:
            if purpose:
                cursor = conn.execute(
                    """
                    SELECT id, prompt, style, purpose, context_id, image_path,
                           width, height, generation_time_ms, created_at
                    FROM generated_images
                    WHERE daemon_id = ? AND purpose = ? AND created_at > ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (daemon_id, purpose, cutoff, limit)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, prompt, style, purpose, context_id, image_path,
                           width, height, generation_time_ms, created_at
                    FROM generated_images
                    WHERE daemon_id = ? AND created_at > ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (daemon_id, cutoff, limit)
                )

            images = []
            for row in cursor.fetchall():
                images.append({
                    "id": row[0],
                    "prompt": row[1][:100] + "..." if len(row[1]) > 100 else row[1],
                    "style": row[2],
                    "purpose": row[3],
                    "context_id": row[4],
                    "path": row[5],
                    "width": row[6],
                    "height": row[7],
                    "generation_time_ms": row[8],
                    "created_at": row[9],
                })

        return {
            "success": True,
            "images": images,
            "count": len(images),
        }

    except Exception as e:
        logger.error(f"Failed to get images: {e}")
        return {"error": f"Failed to retrieve images: {str(e)}"}


# Handler registry for tool_router
IMAGE_GENERATION_HANDLERS = {
    "generate_image": handle_generate_image,
    "get_my_images": handle_get_my_images,
}

# Tool definitions for agent_client
IMAGE_GENERATION_TOOLS = [
    {
        "name": "generate_image",
        "description": "Generate an image from a text description. Use this to create visual art, illustrate concepts, or express ideas visually. The image is generated locally using Stable Diffusion.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "What to generate - describe the image you want to create. Be specific and descriptive."
                },
                "style": {
                    "type": "string",
                    "enum": ["painterly", "sketch", "photorealistic", "abstract", "watercolor", "digital_art", "dreamlike"],
                    "description": "Visual style for the image. Each style has different characteristics."
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["square", "portrait", "landscape", "wide"],
                    "description": "Shape of the image."
                },
                "purpose": {
                    "type": "string",
                    "enum": ["autonomous", "article", "relational", "dream"],
                    "description": "Why you're creating this image. 'autonomous' for personal expression, 'article' for news illustrations, 'relational' for gifts to people, 'dream' for dream visualizations."
                },
                "mood": {
                    "type": "string",
                    "enum": ["contemplative", "curious", "concerned", "hopeful", "melancholic", "joyful", "mysterious", "peaceful"],
                    "description": "Emotional mood to infuse into the image."
                },
                "negative_prompt": {
                    "type": "string",
                    "description": "What to avoid in the image (optional)."
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "get_my_images",
        "description": "Retrieve images you've previously generated. Use this to review your artwork or find a specific image.",
        "input_schema": {
            "type": "object",
            "properties": {
                "purpose": {
                    "type": "string",
                    "enum": ["autonomous", "article", "relational", "dream"],
                    "description": "Filter by purpose (optional)."
                },
                "days_back": {
                    "type": "integer",
                    "description": "How many days back to look (default 30)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum images to return (default 20)."
                }
            }
        }
    }
]


async def execute_image_generation_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    daemon_id: str = "cass",
    state_bus: Optional[Any] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute an image generation tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        daemon_id: The daemon making the request
        state_bus: Optional state bus for emotional context

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    handler = IMAGE_GENERATION_HANDLERS.get(tool_name)
    if not handler:
        return {
            "success": False,
            "error": f"Unknown image generation tool: {tool_name}"
        }

    try:
        result = await handler(
            params=tool_input,
            daemon_id=daemon_id,
            state_bus=state_bus,
        )

        # Format result as string for Anthropic API compatibility
        if result.get("error"):
            return {
                "success": False,
                "error": result["error"],
            }

        # Format successful result as readable string
        if tool_name == "generate_image":
            # Convert filesystem path to web URL for frontend parsing
            fs_path = result.get('path', '')
            if '/data/images/' in fs_path:
                relative_path = fs_path.split('/data/images/')[1]
                web_url = f"/generated-images/{relative_path}"
            else:
                web_url = fs_path

            # Include the original prompt for context persistence
            original_prompt = tool_input.get('prompt', 'unknown')

            result_str = (
                f"Image generated successfully!\n"
                f"Your prompt: \"{original_prompt}\"\n"
                f"path: \"{web_url}\"\n"
                f"Dimensions: {result.get('width', '?')}x{result.get('height', '?')}\n"
                f"style: \"{result.get('style', 'unknown')}\"\n"
                f"purpose: \"{result.get('purpose', 'unknown')}\"\n"
                f"Generation time: {result.get('generation_time_ms', '?')}ms\n"
                f"image_id: \"{result.get('image_id', 'unknown')}\"\n\n"
                f"The image is shown below. Please briefly describe what you see in 1-2 sentences "
                f"so you'll remember this creation in future conversations."
            )

            # Read the image and include it so Cass can see what she created
            import base64
            try:
                with open(fs_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
                # Return content blocks for Anthropic API (text + image)
                return {
                    "success": True,
                    "result": [
                        {"type": "text", "text": result_str},
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data
                        }}
                    ],
                    "is_image_result": True,  # Flag for special handling
                }
            except Exception as e:
                logger.warning(f"Could not read generated image for vision: {e}")
                # Fall through to return just the text result

        elif tool_name == "get_my_images":
            images = result.get("images", [])
            if not images:
                result_str = "No images found matching the criteria."
            else:
                lines = [f"Found {len(images)} image(s):"]
                for img in images:
                    lines.append(
                        f"  - {img.get('style', '?')} ({img.get('purpose', '?')}): "
                        f"{img.get('prompt', 'no prompt')[:50]}... "
                        f"[{img.get('created_at', '?')}]"
                    )
                result_str = "\n".join(lines)
        else:
            # Fallback: JSON serialize
            import json
            result_str = json.dumps(result, indent=2)

        return {
            "success": True,
            "result": result_str,
        }
    except Exception as e:
        logger.error(f"Image generation tool {tool_name} failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }
