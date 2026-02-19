"""
Image Generation Tool Handler

Handles Cass's image generation tool calls via ComfyUI.
Supports text-to-image, image refinement, variations, and upscaling.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

from database import get_db, json_serialize

logger = logging.getLogger(__name__)

# Aspect ratio presets for convenience
ASPECT_RATIOS = {
    "square": (1024, 1024),
    "portrait": (896, 1152),
    "landscape": (1152, 896),
    "wide": (1344, 768),
}


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
            - steps: Generation steps (optional, 10-50)
            - cfg_scale: Prompt adherence (optional, 1-20)
            - sampler: Sampling method (optional)
            - scheduler: Scheduler type (optional)
            - seed: Seed for reproducibility (optional)
            - lora: LoRA to apply (optional)
            - lora_strength: LoRA strength (optional, 0-1)
        daemon_id: The daemon making the request
        **kwargs: Additional context (state_bus, etc.)

    Returns:
        Dict with image info or error
    """
    from image_generation.comfyui_client import ComfyUIClient
    from image_generation.prompt_builder import build_image_prompt
    from image_generation.generation_params import GenerationParams, LoRAConfig
    from image_generation.param_resolver import resolve_params

    prompt_text = params.get("prompt")
    if not prompt_text:
        return {"error": "prompt is required"}

    style = params.get("style", "digital_art")
    aspect_ratio = params.get("aspect_ratio", "square")
    purpose = params.get("purpose", "autonomous")
    context_id = params.get("context_id")
    mood = params.get("mood")
    user_negative = params.get("negative_prompt", "")

    # Get dimensions from aspect ratio
    width, height = ASPECT_RATIOS.get(aspect_ratio, ASPECT_RATIOS["square"])

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

    # Build LoRA list if specified
    loras = []
    if params.get("lora"):
        loras.append(LoRAConfig(
            name=params["lora"],
            strength=params.get("lora_strength", 0.8),
            clip_strength=params.get("lora_strength", 0.8),
        ))

    # Resolve parameters (combines style defaults, house style, explicit overrides)
    gen_params = resolve_params(
        prompt=positive_prompt,
        negative_prompt=negative_prompt,
        style=style,
        mood=mood,
        daemon_id=daemon_id,
        use_house_style=True,
        use_house_lora=params.get("use_house_lora", False),
        width=width,
        height=height,
        steps=params.get("steps"),
        cfg_scale=params.get("cfg_scale"),
        sampler=params.get("sampler"),
        scheduler=params.get("scheduler"),
        seed=params.get("seed", -1),
        loras=loras if loras else None,
    )

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

        # Generate the image using new params-based method
        result = await client.generate_from_params(
            params=gen_params,
            category=purpose,
            subcategory=None,
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
                    generation_time_ms, seed, emotional_state_json,
                    generation_type, iteration_number, params_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    result.get("generation_type", "txt2img"),
                    result.get("iteration_number", 1),
                    json_serialize(result.get("params")),
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
            "seed": result["seed"],
            "style": style,
            "purpose": purpose,
        }

    except TimeoutError as e:
        logger.error(f"Image generation timed out: {e}")
        return {"error": "Image generation timed out. Try again or use a simpler prompt."}
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return {"error": f"Image generation failed: {str(e)}"}


async def handle_refine_image(
    params: Dict[str, Any],
    daemon_id: str = "cass",
    **kwargs,
) -> Dict[str, Any]:
    """
    Handle refine_image tool call - img2img refinement.

    Args:
        params: Tool parameters:
            - image_id: ID of image to refine (required)
            - prompt: New/modified prompt (required)
            - strength: How much to change (0.1=subtle, 0.8=major, default 0.5)
            - negative_prompt: What to avoid (optional)
        daemon_id: The daemon making the request

    Returns:
        Dict with refined image info or error
    """
    from image_generation.comfyui_client import ComfyUIClient

    image_id = params.get("image_id")
    prompt = params.get("prompt")

    if not image_id:
        return {"error": "image_id is required"}
    if not prompt:
        return {"error": "prompt is required"}

    strength = params.get("strength", 0.5)
    negative_prompt = params.get("negative_prompt", "")

    # Look up the source image
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT image_path, style, purpose FROM generated_images WHERE id = ?",
            (image_id,)
        )
        row = cursor.fetchone()
        if not row:
            return {"error": f"Image not found: {image_id}"}

        source_path = row[0]
        style = row[1]
        purpose = row[2]

    client = ComfyUIClient()

    try:
        is_healthy = await client.check_health()
        if not is_healthy:
            return {
                "error": "ComfyUI server is not available. Is it running?",
            }

        result = await client.refine_image(
            source_image_path=source_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            denoise=strength,
            category=purpose,
            parent_id=image_id,
        )

        # Store in database
        new_image_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO generated_images (
                    id, daemon_id, prompt, negative_prompt, style,
                    purpose, image_path, width, height,
                    generation_time_ms, seed, generation_type,
                    iteration_number, parent_id, params_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_image_id,
                    daemon_id,
                    prompt,
                    negative_prompt,
                    style,
                    purpose,
                    result["path"],
                    result.get("width"),
                    result.get("height"),
                    result["generation_time_ms"],
                    result.get("seed"),
                    "img2img",
                    result.get("iteration_number", 2),
                    image_id,
                    json_serialize(result.get("params")),
                    now,
                )
            )

        logger.info(f"Refined image {image_id} -> {new_image_id}")

        return {
            "success": True,
            "image_id": new_image_id,
            "path": result["path"],
            "parent_id": image_id,
            "generation_time_ms": result["generation_time_ms"],
            "refinement_strength": strength,
        }

    except Exception as e:
        logger.error(f"Image refinement failed: {e}")
        return {"error": f"Image refinement failed: {str(e)}"}


async def handle_create_variations(
    params: Dict[str, Any],
    daemon_id: str = "cass",
    **kwargs,
) -> Dict[str, Any]:
    """
    Handle create_variations tool call.

    Args:
        params: Tool parameters:
            - image_id: Source image ID (required)
            - count: Number of variations (1-4, default 1)
            - variation_strength: How different (0.2-0.6, default 0.3)
        daemon_id: The daemon making the request

    Returns:
        Dict with list of variation image info or error
    """
    from image_generation.comfyui_client import ComfyUIClient

    image_id = params.get("image_id")
    if not image_id:
        return {"error": "image_id is required"}

    count = min(4, max(1, params.get("count", 1)))  # Clamp to 1-4
    variation_strength = params.get("variation_strength", 0.3)

    # Look up the source image
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT image_path, prompt, negative_prompt, style, purpose FROM generated_images WHERE id = ?",
            (image_id,)
        )
        row = cursor.fetchone()
        if not row:
            return {"error": f"Image not found: {image_id}"}

        source_path, prompt, negative_prompt, style, purpose = row

    client = ComfyUIClient()

    try:
        is_healthy = await client.check_health()
        if not is_healthy:
            return {"error": "ComfyUI server is not available. Is it running?"}

        results = await client.create_variations(
            source_image_path=source_path,
            prompt=prompt,
            negative_prompt=negative_prompt or "",
            variation_strength=variation_strength,
            count=count,
            category=purpose,
            parent_id=image_id,
        )

        # Store all variations in database
        variation_ids = []
        now = datetime.now().isoformat()

        for result in results:
            new_image_id = str(uuid.uuid4())

            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO generated_images (
                        id, daemon_id, prompt, negative_prompt, style,
                        purpose, image_path, width, height,
                        generation_time_ms, seed, generation_type,
                        parent_id, params_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_image_id,
                        daemon_id,
                        prompt,
                        negative_prompt,
                        style,
                        purpose,
                        result["path"],
                        result.get("width"),
                        result.get("height"),
                        result["generation_time_ms"],
                        result.get("seed"),
                        "variation",
                        image_id,
                        json_serialize(result.get("params")),
                        now,
                    )
                )

            variation_ids.append({
                "image_id": new_image_id,
                "path": result["path"],
            })

        logger.info(f"Created {len(variation_ids)} variations of {image_id}")

        return {
            "success": True,
            "source_id": image_id,
            "variations": variation_ids,
            "count": len(variation_ids),
            "variation_strength": variation_strength,
        }

    except Exception as e:
        logger.error(f"Variation creation failed: {e}")
        return {"error": f"Variation creation failed: {str(e)}"}


async def handle_upscale_image(
    params: Dict[str, Any],
    daemon_id: str = "cass",
    **kwargs,
) -> Dict[str, Any]:
    """
    Handle upscale_image tool call.

    Args:
        params: Tool parameters:
            - image_id: Image to upscale (required)
            - scale: Upscale factor (2 or 4, default 2)
        daemon_id: The daemon making the request

    Returns:
        Dict with upscaled image info or error
    """
    from image_generation.comfyui_client import ComfyUIClient

    image_id = params.get("image_id")
    if not image_id:
        return {"error": "image_id is required"}

    scale = params.get("scale", 2)
    if scale not in [2, 4]:
        scale = 2

    # Look up the source image
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT image_path, purpose FROM generated_images WHERE id = ?",
            (image_id,)
        )
        row = cursor.fetchone()
        if not row:
            return {"error": f"Image not found: {image_id}"}

        source_path, purpose = row

    client = ComfyUIClient()

    try:
        is_healthy = await client.check_health()
        if not is_healthy:
            return {"error": "ComfyUI server is not available. Is it running?"}

        result = await client.upscale_image(
            source_image_path=source_path,
            scale=float(scale),
            category=purpose,
            parent_id=image_id,
        )

        # Store in database
        new_image_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO generated_images (
                    id, daemon_id, prompt, style, purpose, image_path,
                    generation_time_ms, generation_type, parent_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_image_id,
                    daemon_id,
                    f"Upscaled {scale}x",
                    "upscale",
                    purpose,
                    result["path"],
                    result["generation_time_ms"],
                    "upscale",
                    image_id,
                    now,
                )
            )

        logger.info(f"Upscaled image {image_id} -> {new_image_id} ({scale}x)")

        return {
            "success": True,
            "image_id": new_image_id,
            "path": result["path"],
            "parent_id": image_id,
            "scale": scale,
            "generation_time_ms": result["generation_time_ms"],
        }

    except Exception as e:
        logger.error(f"Image upscale failed: {e}")
        return {"error": f"Image upscale failed: {str(e)}"}


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


async def handle_save_recipe(
    params: Dict[str, Any],
    daemon_id: str = "cass",
    **kwargs,
) -> Dict[str, Any]:
    """
    Handle save_recipe tool call.

    Saves the generation parameters from a successful image as a reusable recipe.

    Args:
        params: Tool parameters:
            - name: Recipe name (required)
            - description: What this recipe is good for (required)
            - from_image_id: Image ID whose params to save (required)
            - tags: Categorization tags (optional)
        daemon_id: The daemon making the request

    Returns:
        Dict with recipe info or error
    """
    import json

    name = params.get("name")
    description = params.get("description", "")
    from_image_id = params.get("from_image_id")
    tags = params.get("tags", [])

    if not name:
        return {"error": "name is required"}
    if not from_image_id:
        return {"error": "from_image_id is required"}

    try:
        from image_generation.generation_params import GenerationParams
        from image_generation.recipes import get_recipe_manager

        # Look up the source image and its params
        with get_db() as conn:
            cursor = conn.execute(
                """
                SELECT params_json, prompt, style, loras_json
                FROM generated_images
                WHERE id = ? AND daemon_id = ?
                """,
                (from_image_id, daemon_id)
            )
            row = cursor.fetchone()

            if not row:
                return {"error": f"Image not found: {from_image_id}"}

            params_json, prompt, style, loras_json = row

            # Reconstruct GenerationParams
            if params_json:
                gen_params = GenerationParams.from_dict(json.loads(params_json))
            else:
                # Fallback for older images without full params
                gen_params = GenerationParams(
                    prompt=prompt or "",
                    style_preset=style,
                )

        # Save the recipe
        recipe_manager = get_recipe_manager()
        recipe = recipe_manager.save_recipe(
            name=name,
            daemon_id=daemon_id,
            params=gen_params,
            description=description,
            from_image_id=from_image_id,
            tags=tags,
        )

        logger.info(f"Saved recipe '{name}' (id={recipe.id}) from image {from_image_id}")

        return {
            "success": True,
            "recipe_id": recipe.id,
            "name": recipe.name,
            "description": recipe.description,
            "tags": recipe.tags,
            "source_image_id": from_image_id,
        }

    except Exception as e:
        logger.error(f"Failed to save recipe: {e}")
        return {"error": f"Failed to save recipe: {str(e)}"}


async def handle_list_recipes(
    params: Dict[str, Any],
    daemon_id: str = "cass",
    **kwargs,
) -> Dict[str, Any]:
    """
    Handle list_recipes tool call.

    Lists saved generation recipes.

    Args:
        params: Tool parameters:
            - tags: Filter by tags (optional)
            - limit: Max recipes to return (optional, default 20)
        daemon_id: The daemon making the request

    Returns:
        Dict with list of recipes
    """
    tags = params.get("tags", [])
    limit = params.get("limit", 20)

    try:
        from image_generation.recipes import get_recipe_manager

        recipe_manager = get_recipe_manager()
        recipes = recipe_manager.list_recipes(
            daemon_id=daemon_id,
            tags=tags if tags else None,
            limit=limit,
        )

        return {
            "success": True,
            "recipes": [
                {
                    "id": r.id,
                    "name": r.name,
                    "description": r.description,
                    "tags": r.tags,
                    "use_count": r.use_count,
                    "source_image_id": r.created_from_image_id,
                    "created_at": r.created_at,
                }
                for r in recipes
            ],
            "count": len(recipes),
        }

    except Exception as e:
        logger.error(f"Failed to list recipes: {e}")
        return {"error": f"Failed to list recipes: {str(e)}"}


# Handler registry for tool_router
IMAGE_GENERATION_HANDLERS = {
    "generate_image": handle_generate_image,
    "refine_image": handle_refine_image,
    "create_variations": handle_create_variations,
    "upscale_image": handle_upscale_image,
    "get_my_images": handle_get_my_images,
    "save_recipe": handle_save_recipe,
    "list_recipes": handle_list_recipes,
}

# Tool definitions for agent_client
IMAGE_GENERATION_TOOLS = [
    {
        "name": "generate_image",
        "description": "Generate an image from a text description. Use this to create visual art, illustrate concepts, or express ideas visually. The image is generated locally using Stable Diffusion. You can control generation parameters for fine-tuned results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "What to generate - describe the image you want to create. Be specific and descriptive."
                },
                "style": {
                    "type": "string",
                    "enum": ["painterly", "sketch", "photorealistic", "abstract", "watercolor", "digital_art", "dreamlike", "fine_art"],
                    "description": "Visual style for the image. Each style has different default parameters."
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["square", "portrait", "landscape", "wide"],
                    "description": "Shape of the image."
                },
                "purpose": {
                    "type": "string",
                    "enum": ["autonomous", "article", "relational", "dream", "art_study"],
                    "description": "Why you're creating this image. 'autonomous' for personal expression, 'article' for news illustrations, 'relational' for gifts to people, 'dream' for dream visualizations, 'art_study' for artistic exploration."
                },
                "mood": {
                    "type": "string",
                    "enum": ["contemplative", "curious", "concerned", "hopeful", "melancholic", "joyful", "mysterious", "peaceful"],
                    "description": "Emotional mood to infuse into the image."
                },
                "negative_prompt": {
                    "type": "string",
                    "description": "What to avoid in the image (optional)."
                },
                "steps": {
                    "type": "integer",
                    "description": "Number of generation steps (10-50). Higher = more detail but slower. Default varies by style."
                },
                "cfg_scale": {
                    "type": "number",
                    "description": "Prompt adherence strength (1-20). Higher = follows prompt more strictly. Default varies by style."
                },
                "sampler": {
                    "type": "string",
                    "enum": ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_sde"],
                    "description": "Sampling algorithm. Different samplers produce different qualities."
                },
                "scheduler": {
                    "type": "string",
                    "enum": ["normal", "karras", "exponential"],
                    "description": "Noise scheduling method. 'karras' often produces sharper results."
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducibility. Use -1 for random. Same seed + same params = same image."
                },
                "lora": {
                    "type": "string",
                    "description": "Name of LoRA adapter to apply (e.g., 'house_style'). Optional."
                },
                "lora_strength": {
                    "type": "number",
                    "description": "LoRA influence strength (0.0-1.0). Default 0.8."
                },
                "use_house_lora": {
                    "type": "boolean",
                    "description": "Whether to apply your house style LoRA if trained. Default false."
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "refine_image",
        "description": "Refine an existing image with modifications. Use this to iterate on previous work - adjust details, change elements, or evolve the image. Uses img2img to preserve structure while applying changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_id": {
                    "type": "string",
                    "description": "ID of the image to refine (from previous generation)."
                },
                "prompt": {
                    "type": "string",
                    "description": "New or modified prompt describing what you want. Can reference the original or describe changes."
                },
                "strength": {
                    "type": "number",
                    "description": "How much to change (0.1=subtle touch-ups, 0.5=moderate changes, 0.8=major rework). Default 0.5."
                },
                "negative_prompt": {
                    "type": "string",
                    "description": "What to avoid in the refinement (optional)."
                }
            },
            "required": ["image_id", "prompt"]
        }
    },
    {
        "name": "create_variations",
        "description": "Generate variations of an existing image. Creates similar but different versions while preserving the overall composition and style. Useful for exploring different takes on a concept.",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_id": {
                    "type": "string",
                    "description": "ID of the source image to create variations from."
                },
                "count": {
                    "type": "integer",
                    "description": "Number of variations to generate (1-4). Default 1."
                },
                "variation_strength": {
                    "type": "number",
                    "description": "How different each variation should be (0.2=very similar, 0.4=moderate, 0.6=quite different). Default 0.3."
                }
            },
            "required": ["image_id"]
        }
    },
    {
        "name": "upscale_image",
        "description": "Upscale an image to higher resolution using AI upscaling. Increases detail and clarity without changing the content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_id": {
                    "type": "string",
                    "description": "ID of the image to upscale."
                },
                "scale": {
                    "type": "integer",
                    "enum": [2, 4],
                    "description": "Upscale factor. 2x doubles dimensions, 4x quadruples. Default 2."
                }
            },
            "required": ["image_id"]
        }
    },
    {
        "name": "get_my_images",
        "description": "Retrieve images you've previously generated. Use this to review your artwork, find a specific image, or check your creative history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "purpose": {
                    "type": "string",
                    "enum": ["autonomous", "article", "relational", "dream", "art_study"],
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
    },
    {
        "name": "save_recipe",
        "description": "Save the generation settings from a successful image as a reusable recipe. Use this when you find parameter combinations that work well for a particular style or mood. Recipes can be reused to quickly recreate similar effects.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "A memorable name for this recipe (e.g., 'Moody Portrait', 'Dreamy Landscape')."
                },
                "description": {
                    "type": "string",
                    "description": "What this recipe is good for - helps you remember when to use it."
                },
                "from_image_id": {
                    "type": "string",
                    "description": "The ID of the image whose settings you want to save."
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for organizing and finding recipes later (e.g., ['portrait', 'moody', 'low-light'])."
                }
            },
            "required": ["name", "from_image_id"]
        }
    },
    {
        "name": "list_recipes",
        "description": "List your saved generation recipes. Use this to find a recipe to apply to a new image or to review what settings you've saved.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by tags (returns recipes matching any of these tags)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum recipes to return (default 20)."
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

        elif tool_name == "refine_image":
            # Refinement result - show the refined image to Cass
            fs_path = result.get('path', '')
            if '/data/images/' in fs_path:
                relative_path = fs_path.split('/data/images/')[1]
                web_url = f"/generated-images/{relative_path}"
            else:
                web_url = fs_path

            result_str = (
                f"Image refined successfully!\n"
                f"path: \"{web_url}\"\n"
                f"parent_id: \"{result.get('parent_id', 'unknown')}\"\n"
                f"image_id: \"{result.get('image_id', 'unknown')}\"\n"
                f"Refinement strength: {result.get('refinement_strength', '?')}\n"
                f"Generation time: {result.get('generation_time_ms', '?')}ms\n\n"
                f"The refined image is shown below."
            )

            import base64
            try:
                with open(fs_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
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
                    "is_image_result": True,
                }
            except Exception as e:
                logger.warning(f"Could not read refined image for vision: {e}")

        elif tool_name == "create_variations":
            variations = result.get("variations", [])
            result_str = (
                f"Created {result.get('count', len(variations))} variation(s) of image {result.get('source_id', 'unknown')}\n"
                f"Variation strength: {result.get('variation_strength', '?')}\n\n"
            )
            for i, var in enumerate(variations):
                fs_path = var.get('path', '')
                if '/data/images/' in fs_path:
                    relative_path = fs_path.split('/data/images/')[1]
                    web_url = f"/generated-images/{relative_path}"
                else:
                    web_url = fs_path
                result_str += f"Variation {i+1}: image_id=\"{var.get('image_id', 'unknown')}\", path=\"{web_url}\"\n"

            # Show first variation image
            if variations:
                first_path = variations[0].get('path', '')
                import base64
                try:
                    with open(first_path, 'rb') as f:
                        image_data = base64.b64encode(f.read()).decode('utf-8')
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
                        "is_image_result": True,
                    }
                except Exception as e:
                    logger.warning(f"Could not read variation image for vision: {e}")

        elif tool_name == "upscale_image":
            fs_path = result.get('path', '')
            if '/data/images/' in fs_path:
                relative_path = fs_path.split('/data/images/')[1]
                web_url = f"/generated-images/{relative_path}"
            else:
                web_url = fs_path

            result_str = (
                f"Image upscaled successfully!\n"
                f"path: \"{web_url}\"\n"
                f"parent_id: \"{result.get('parent_id', 'unknown')}\"\n"
                f"image_id: \"{result.get('image_id', 'unknown')}\"\n"
                f"Scale: {result.get('scale', '?')}x\n"
                f"Generation time: {result.get('generation_time_ms', '?')}ms\n"
            )

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
