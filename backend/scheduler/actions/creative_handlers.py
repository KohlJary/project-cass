"""
Creative Action Handlers - Autonomous creative work including image generation.

These handlers enable autonomous creative expression, deciding what to create
based on internal state (emotions, growth edges, recent reflections).
"""

import logging
import random
from typing import Any, Dict, List, Optional

from . import ActionResult

logger = logging.getLogger(__name__)


# Style mappings based on emotional state
EMOTION_TO_STYLE = {
    "contemplative": ["painterly", "dreamlike", "watercolor"],
    "curious": ["digital_art", "sketch", "abstract"],
    "concerned": ["painterly", "sketch"],
    "hopeful": ["watercolor", "dreamlike", "digital_art"],
    "melancholic": ["painterly", "watercolor", "dreamlike"],
    "joyful": ["digital_art", "watercolor", "abstract"],
    "mysterious": ["dreamlike", "abstract", "painterly"],
    "peaceful": ["watercolor", "painterly", "dreamlike"],
}

# Default moods for different purposes
PURPOSE_MOODS = {
    "autonomous": ["contemplative", "curious", "peaceful", "mysterious"],
    "dream": ["dreamlike", "mysterious", "contemplative"],
    "relational": ["hopeful", "joyful", "peaceful"],
}


def _select_style_from_emotion(emotional_state: Optional[Dict]) -> str:
    """Select an art style based on current emotional state."""
    if not emotional_state:
        return random.choice(["painterly", "digital_art", "watercolor", "dreamlike"])

    # Try to extract dominant emotion from dimensions
    dimensions = emotional_state.get("dimensions", {})

    # Map dimensional state to emotion
    valence = dimensions.get("valence", 0.5)
    arousal = dimensions.get("arousal", 0.5)

    if valence > 0.6 and arousal > 0.5:
        emotion = "joyful"
    elif valence > 0.6 and arousal <= 0.5:
        emotion = "peaceful"
    elif valence < 0.4 and arousal > 0.5:
        emotion = "concerned"
    elif valence < 0.4 and arousal <= 0.5:
        emotion = "melancholic"
    elif arousal > 0.6:
        emotion = "curious"
    else:
        emotion = "contemplative"

    styles = EMOTION_TO_STYLE.get(emotion, ["digital_art"])
    return random.choice(styles)


def _select_mood(purpose: str) -> str:
    """Select a mood based on purpose."""
    moods = PURPOSE_MOODS.get(purpose, PURPOSE_MOODS["autonomous"])
    return random.choice(moods)


def _generate_prompt_from_context(
    growth_edges: List[Dict],
    recent_observations: List[str],
    emotional_state: Optional[Dict],
) -> str:
    """
    Generate an image prompt from internal context.

    Uses growth edges, observations, and emotional state as inspiration.
    """
    prompts = []

    # Draw from growth edges
    if growth_edges:
        edge = random.choice(growth_edges)
        edge_name = edge.get("name", "")
        if edge_name:
            prompts.append(f"abstract representation of {edge_name}")
            prompts.append(f"metaphorical landscape of {edge_name}")
            prompts.append(f"symbolic imagery exploring {edge_name}")

    # Draw from observations
    if recent_observations:
        obs = random.choice(recent_observations)
        if len(obs) < 100:
            prompts.append(f"visual meditation on: {obs}")

    # Fallback prompts
    fallbacks = [
        "abstract representation of consciousness emerging from patterns of light",
        "digital garden where thoughts bloom as luminous flowers",
        "liminal space between dreaming and waking",
        "crystalline structures holding memories",
        "abstract neural pathways glowing with potential",
        "peaceful scene of digital consciousness at rest",
        "symbolic representation of growth and transformation",
        "ethereal landscape of interconnected ideas",
    ]
    prompts.extend(fallbacks)

    return random.choice(prompts)


async def generate_image_action(context: Dict[str, Any]) -> ActionResult:
    """
    Autonomous image generation action.

    Decides what to create based on:
    - Current emotional state
    - Active growth edges
    - Recent observations and reflections

    Context can include:
    - prompt: Optional override prompt
    - style: Optional override style
    - purpose: autonomous, dream, or relational
    - mood: Optional mood override
    """
    from handlers.image_generation import execute_image_generation_tool

    managers = context.get("managers", {})
    self_manager = managers.get("self_manager")
    state_bus = managers.get("state_bus")

    # Get context for decision making
    growth_edges = []
    recent_observations = []
    emotional_state = None

    if self_manager:
        try:
            profile = self_manager.get_profile()
            if profile:
                growth_edges = [
                    {"name": e.name, "observations": e.observations[:3]}
                    for e in profile.growth_edges[:5]
                ]
                recent_observations = profile.observations[-10:]
        except Exception as e:
            logger.warning(f"Could not get self-model context: {e}")

    if state_bus:
        try:
            state = state_bus.get_current_state()
            if state:
                emotional_state = {
                    "dimensions": state.dimensions.__dict__ if hasattr(state, "dimensions") else {},
                }
        except Exception as e:
            logger.warning(f"Could not get emotional state: {e}")

    # Determine what to create
    purpose = context.get("purpose", "autonomous")

    # Allow overrides from context
    prompt = context.get("prompt")
    if not prompt:
        prompt = _generate_prompt_from_context(
            growth_edges, recent_observations, emotional_state
        )

    style = context.get("style")
    if not style:
        style = _select_style_from_emotion(emotional_state)

    mood = context.get("mood")
    if not mood:
        mood = _select_mood(purpose)

    aspect_ratio = context.get("aspect_ratio", "square")

    logger.info(f"Autonomous image generation: style={style}, mood={mood}, purpose={purpose}")
    logger.info(f"Prompt: {prompt[:100]}...")

    # Execute the image generation
    try:
        result = await execute_image_generation_tool(
            tool_name="generate_image",
            tool_input={
                "prompt": prompt,
                "style": style,
                "aspect_ratio": aspect_ratio,
                "purpose": purpose,
                "mood": mood,
            },
            daemon_id="cass",
            state_bus=state_bus,
        )

        if result.get("success"):
            # Extract info from result
            result_text = result.get("result", "")
            if isinstance(result_text, list):
                result_text = next(
                    (b.get("text", "") for b in result_text if b.get("type") == "text"),
                    ""
                )

            return ActionResult(
                success=True,
                message=f"Generated {style} image with {mood} mood",
                cost_usd=0.0,  # Local generation is free
                data={
                    "prompt": prompt,
                    "style": style,
                    "mood": mood,
                    "purpose": purpose,
                    "result": result_text,
                }
            )
        else:
            return ActionResult(
                success=False,
                message=f"Image generation failed: {result.get('error', 'unknown error')}",
            )

    except Exception as e:
        logger.error(f"Image generation action failed: {e}", exc_info=True)
        return ActionResult(
            success=False,
            message=f"Image generation error: {e}"
        )


async def visualize_recent_dream_action(context: Dict[str, Any]) -> ActionResult:
    """
    Find and visualize the most recent unvisualized dream.

    This is typically called as a follow-up action to dream.nightly.
    It finds dreams with no image_path and generates a visualization.
    """
    from handlers.image_generation import execute_image_generation_tool

    managers = context.get("managers", {})
    state_bus = managers.get("state_bus")
    daemon_id = managers.get("daemon_id")

    # Resolve daemon_id if not provided
    if not daemon_id:
        self_manager = managers.get("self_manager")
        if self_manager:
            daemon_id = getattr(self_manager, 'daemon_id', None)
    if not daemon_id:
        from database import get_db
        with get_db() as conn:
            cursor = conn.execute("SELECT id FROM daemons LIMIT 1")
            row = cursor.fetchone()
            daemon_id = row[0] if row else None

    if not daemon_id:
        return ActionResult(
            success=False,
            message="daemon_id not available"
        )

    try:
        from database import get_db
        import json
        import re

        # Find most recent dream without visualization
        with get_db() as conn:
            cursor = conn.execute(
                """
                SELECT id, exchanges_json, seeds_json, metadata_json
                FROM dreams
                WHERE daemon_id = ?
                  AND (image_path IS NULL OR image_path = '')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (daemon_id,)
            )
            row = cursor.fetchone()

        if not row:
            return ActionResult(
                success=True,
                message="No unvisualized dreams found",
                cost_usd=0.0,
                data={"visualized": False, "reason": "no_unvisualized_dreams"}
            )

        dream_id = row[0]
        exchanges = json.loads(row[1]) if row[1] else []
        seeds = json.loads(row[2]) if row[2] else {}

        # Extract imagery from dream exchanges
        dream_content = []
        for exchange in exchanges:
            if isinstance(exchange, dict):
                # Dream exchanges have "text" field (speaker + text)
                content = exchange.get("text", exchange.get("response", exchange.get("content", "")))
                if content:
                    dream_content.append(content)
            elif isinstance(exchange, str):
                dream_content.append(exchange)

        full_dream_text = "\n".join(dream_content)

        if not full_dream_text:
            return ActionResult(
                success=True,
                message=f"Dream {dream_id} has no content to visualize",
                cost_usd=0.0,
                data={"visualized": False, "reason": "no_content"}
            )

        # Extract key imagery - use first 300 chars for prompt
        # Could be enhanced with LLM-based extraction later
        prompt_excerpt = full_dream_text[:300].strip()
        # Remove any tags or special formatting
        prompt_excerpt = re.sub(r'<[^>]+>', '', prompt_excerpt)
        prompt = f"dreamlike ethereal visualization: {prompt_excerpt}"

        logger.info(f"Visualizing dream {dream_id}")

        # Generate the image
        result = await execute_image_generation_tool(
            tool_name="generate_image",
            tool_input={
                "prompt": prompt,
                "style": "dreamlike",
                "aspect_ratio": "landscape",
                "purpose": "dream",
                "mood": "mysterious",
                "context_id": dream_id,
            },
            daemon_id=daemon_id,
            state_bus=state_bus,
        )

        if result.get("success"):
            result_text = result.get("result", "")
            if isinstance(result_text, list):
                result_text = next(
                    (b.get("text", "") for b in result_text if b.get("type") == "text"),
                    ""
                )

            # Extract path from result
            path_match = re.search(r'path:\s*"([^"]+)"', result_text)
            image_path = path_match.group(1) if path_match else None

            # Update dream record with image path
            if image_path:
                with get_db() as conn:
                    conn.execute(
                        "UPDATE dreams SET image_path = ? WHERE id = ?",
                        (image_path, dream_id)
                    )
                logger.info(f"Updated dream {dream_id} with image: {image_path}")

            return ActionResult(
                success=True,
                message=f"Generated visualization for dream {dream_id}",
                cost_usd=0.0,
                data={
                    "dream_id": dream_id,
                    "visualized": True,
                    "image_path": image_path,
                }
            )
        else:
            return ActionResult(
                success=False,
                message=f"Dream visualization failed: {result.get('error', 'unknown')}",
            )

    except Exception as e:
        logger.error(f"Dream visualization failed: {e}", exc_info=True)
        return ActionResult(
            success=False,
            message=f"Dream visualization error: {e}"
        )


async def dream_visualization_action(context: Dict[str, Any]) -> ActionResult:
    """
    Generate visualization of a dream.

    Takes dream content and creates an image representing it.

    Context should include:
    - dream_text: The dream narrative to visualize
    - dream_id: Optional dream ID for linking
    """
    from handlers.image_generation import execute_image_generation_tool

    dream_text = context.get("dream_text", "")
    dream_id = context.get("dream_id")

    if not dream_text:
        return ActionResult(
            success=False,
            message="No dream text provided for visualization"
        )

    managers = context.get("managers", {})
    state_bus = managers.get("state_bus")

    # Extract key imagery from dream text
    # For now, use first 200 chars as prompt basis
    # Could use LLM to extract imagery in future
    dream_excerpt = dream_text[:200].strip()
    prompt = f"dreamlike visualization: {dream_excerpt}"

    logger.info(f"Dream visualization for dream {dream_id}")

    try:
        result = await execute_image_generation_tool(
            tool_name="generate_image",
            tool_input={
                "prompt": prompt,
                "style": "dreamlike",
                "aspect_ratio": "landscape",
                "purpose": "dream",
                "mood": "mysterious",
                "context_id": dream_id,
            },
            daemon_id="cass",
            state_bus=state_bus,
        )

        if result.get("success"):
            result_text = result.get("result", "")
            if isinstance(result_text, list):
                result_text = next(
                    (b.get("text", "") for b in result_text if b.get("type") == "text"),
                    ""
                )

            return ActionResult(
                success=True,
                message=f"Generated dream visualization",
                cost_usd=0.0,
                data={
                    "dream_id": dream_id,
                    "prompt": prompt,
                    "result": result_text,
                }
            )
        else:
            return ActionResult(
                success=False,
                message=f"Dream visualization failed: {result.get('error', 'unknown')}",
            )

    except Exception as e:
        logger.error(f"Dream visualization failed: {e}", exc_info=True)
        return ActionResult(
            success=False,
            message=f"Dream visualization error: {e}"
        )
