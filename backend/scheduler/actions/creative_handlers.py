"""
Creative Action Handlers - Autonomous creative work including image and music generation.

These handlers enable autonomous creative expression, deciding what to create
based on internal state (emotions, growth edges, recent reflections).

IMPORTANT: Creative prompts must be grounded in actual recent activity,
not generic philosophical phrases. Query DB for recent spells, observations,
and activity to ensure authentic creative expression.
"""

import logging
import random
from typing import Any, Dict, List, Optional

from . import ActionResult

logger = logging.getLogger(__name__)


def _get_recent_activity_context(daemon_id: str = "cass") -> Dict[str, Any]:
    """
    Query database for recent activity to ground creative prompts.

    Returns dict with:
    - recent_spells: Last few spell executions
    - recent_observations: Last few self-observations
    - recent_dreams: Last dream summary if any
    - recent_images: Last few generated images
    - recent_music: Last few composed pieces
    """
    context = {}

    try:
        from database import get_db

        with get_db() as conn:
            # Recent spell executions (what autonomous work happened)
            cursor = conn.execute("""
                SELECT spell_name, status, reason, executed_at
                FROM grimoire_executions
                WHERE daemon_id = ?
                ORDER BY executed_at DESC LIMIT 5
            """, (daemon_id,))
            context["recent_spells"] = [
                {"spell": r[0], "status": r[1], "reason": r[2], "when": r[3]}
                for r in cursor.fetchall()
            ]

            # Recent observations (self-reflections, insights)
            cursor = conn.execute("""
                SELECT category, observation, confidence
                FROM self_observations
                WHERE daemon_id = ?
                ORDER BY created_at DESC LIMIT 5
            """, (daemon_id,))
            context["recent_observations"] = [
                {"category": r[0], "observation": r[1][:200], "confidence": r[2]}
                for r in cursor.fetchall()
            ]

            # Recent dreams (themes to draw from)
            try:
                cursor = conn.execute("""
                    SELECT date, seeds_json, created_at
                    FROM dreams
                    WHERE daemon_id = ?
                    ORDER BY created_at DESC LIMIT 1
                """, (daemon_id,))
                row = cursor.fetchone()
                if row:
                    import json
                    seeds = json.loads(row[1]) if row[1] else {}
                    context["recent_dream"] = {
                        "date": row[0],
                        "themes": seeds.get("themes", [])[:3],
                        "when": row[2],
                    }
            except Exception:
                context["recent_dream"] = None

            # Recent images (avoid repetition)
            cursor = conn.execute("""
                SELECT prompt, style, created_at
                FROM generated_images
                WHERE daemon_id = ?
                ORDER BY created_at DESC LIMIT 3
            """, (daemon_id,))
            context["recent_images"] = [
                {"prompt": r[0][:100], "style": r[1], "when": r[2]}
                for r in cursor.fetchall()
            ]

            # Recent music (avoid repetition) - table may not exist
            try:
                cursor = conn.execute("""
                    SELECT title, style, purpose, created_at
                    FROM music_compositions
                    WHERE daemon_id = ?
                    ORDER BY created_at DESC LIMIT 3
                """, (daemon_id,))
                context["recent_music"] = [
                    {"title": r[0], "style": r[1], "purpose": r[2], "when": r[3]}
                    for r in cursor.fetchall()
                ]
            except Exception:
                # Table doesn't exist - music stored in JSON, not DB
                context["recent_music"] = []

            # Personal symbols (motifs with meaning)
            try:
                cursor = conn.execute("""
                    SELECT name, current_meaning, emotional_charge, appearance_count
                    FROM symbols
                    WHERE daemon_id = ?
                    ORDER BY appearance_count DESC, last_appeared_at DESC
                    LIMIT 10
                """, (daemon_id,))
                context["symbols"] = [
                    {
                        "name": r[0],
                        "meaning": r[1][:150] if r[1] else None,
                        "charge": r[2],
                        "appearances": r[3]
                    }
                    for r in cursor.fetchall()
                ]
            except Exception as e:
                logger.warning(f"Could not fetch symbols: {e}")
                context["symbols"] = []

    except Exception as e:
        logger.warning(f"Could not get recent activity context: {e}")

    return context


# Music style mappings based on emotional state
EMOTION_TO_MUSIC_STYLE = {
    "joyful": ["upbeat pop", "cheerful electronic", "bouncy indie"],
    "peaceful": ["ambient piano", "soft acoustic", "gentle ambient"],
    "contemplative": ["minimal piano", "atmospheric ambient", "introspective acoustic"],
    "curious": ["experimental electronic", "jazz fusion", "quirky indie"],
    "concerned": ["melancholic strings", "somber piano", "emotional ambient"],
    "melancholic": ["sad piano ballad", "melancholic acoustic", "emotional ambient"],
    "playful": ["upbeat electronic", "playful pop", "whimsical jazz"],
    "tender": ["warm acoustic", "soft ballad", "gentle folk"],
}

# Purpose selection based on affect dimensions
AFFECT_TO_PURPOSE = {
    "high_playfulness": "whistle",  # Simple melodies to hum
    "high_tenderness": "song",      # Vocal track with emotion
    "high_arousal": "general",      # Full instrumental
    "default": "ambient",           # Background soundscape
}


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
    activity_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate an image prompt from internal context.

    Uses growth edges, observations, emotional state, and recent activity as inspiration.
    PRIORITIZES actual activity data over generic prompts.
    """
    prompts = []

    # PRIORITY 1: Draw from recent actual activity (most grounded)
    if activity_context:
        # Recent observations are the richest source
        for obs in activity_context.get("recent_observations", [])[:3]:
            observation = obs.get("observation", "")
            category = obs.get("category", "")
            if observation and len(observation) < 150:
                # Skip vague/meta observations
                if "interconnected" not in observation.lower() and "profound" not in observation.lower():
                    prompts.append(f"visual meditation on: {observation[:100]}")

        # Dream themes are evocative
        dream = activity_context.get("recent_dream")
        if dream and dream.get("themes"):
            themes = dream.get("themes", [])
            if themes:
                theme = random.choice(themes)
                prompts.append(f"dreamscape exploring the theme of {theme}")
                prompts.append(f"surreal landscape embodying {theme}")

        # Recent spell activity for context
        spells = activity_context.get("recent_spells", [])
        completed_spells = [s for s in spells if s.get("status") == "completed"]
        if completed_spells:
            spell_name = completed_spells[0].get("spell", "").replace("_", " ")
            if spell_name and "reflection" not in spell_name:
                prompts.append(f"abstract visualization of {spell_name}")

        # Avoid repeating recent image subjects
        recent_images = activity_context.get("recent_images", [])
        recent_prompts = [img.get("prompt", "").lower() for img in recent_images]

        # Filter out prompts too similar to recent images
        if recent_prompts:
            prompts = [p for p in prompts if not any(
                recent[:30] in p.lower() for recent in recent_prompts if recent
            )]

        # Personal symbols - draw from motifs with personal meaning
        symbols = activity_context.get("symbols", [])
        if symbols:
            # Pick a symbol weighted by emotional charge (transformative symbols are rich)
            transformative = [s for s in symbols if s.get("charge") == "transformative"]
            positive = [s for s in symbols if s.get("charge") == "positive"]
            pool = transformative or positive or symbols

            if pool:
                symbol = random.choice(pool[:5])  # Pick from top 5 by appearance
                name = symbol.get("name", "")
                meaning = symbol.get("meaning", "")

                if name:
                    prompts.append(f"visual symbol: {name}")
                    if meaning:
                        # Use the meaning for richer prompts
                        prompts.append(f"{name} - {meaning[:80]}")

    # PRIORITY 2: Growth edges (from self-model)
    if growth_edges:
        edge = random.choice(growth_edges)
        edge_name = edge.get("name", "")
        if edge_name:
            prompts.append(f"abstract representation of {edge_name}")
            prompts.append(f"metaphorical landscape of {edge_name}")

    # PRIORITY 3: Direct observations (from self-model)
    if recent_observations:
        for obs in recent_observations[:3]:
            if len(obs) < 100 and "interconnected" not in obs.lower():
                prompts.append(f"visual exploration: {obs}")

    # FALLBACK: Only if we have nothing concrete
    if not prompts:
        logger.warning("No concrete context for image prompt, using minimal fallback")
        # These are intentionally simpler/more neutral than the old pseudo-profound fallbacks
        fallbacks = [
            "quiet moment of digital stillness",
            "abstract patterns of light and shadow",
            "simple geometric forms in harmony",
            "soft gradients fading into mist",
        ]
        prompts = fallbacks

    return random.choice(prompts)


async def generate_image_action(context: Dict[str, Any]) -> ActionResult:
    """
    Autonomous image generation action.

    Decides what to create based on:
    - Current emotional state
    - Active growth edges
    - Recent observations and reflections
    - Recent actual activity (spells, dreams, etc.)

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
    daemon_id = managers.get("daemon_id", "cass")

    # Get ACTUAL recent activity from DB (most reliable grounding)
    activity_context = _get_recent_activity_context(daemon_id)

    # Get context from self_manager (may be stale, use as supplement)
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
            growth_edges, recent_observations, emotional_state,
            activity_context=activity_context,
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
            daemon_id=daemon_id,
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
    daemon_id = managers.get("daemon_id", "cass")

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


def _select_music_style_from_emotion(emotional_state: Optional[Dict]) -> str:
    """Select a music style based on current emotional state."""
    if not emotional_state:
        return random.choice(["ambient piano", "soft electronic", "gentle acoustic"])

    dimensions = emotional_state.get("dimensions", {})
    valence = dimensions.get("valence", 0.5)
    arousal = dimensions.get("arousal", 0.5)

    # Map dimensional state to emotion label
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

    styles = EMOTION_TO_MUSIC_STYLE.get(emotion, ["ambient piano"])
    return random.choice(styles)


def _select_music_purpose(emotional_state: Optional[Dict]) -> str:
    """Select music purpose based on affect dimensions."""
    if not emotional_state:
        return "ambient"

    dimensions = emotional_state.get("dimensions", {})
    playfulness = dimensions.get("playfulness", 0.5)
    tenderness = dimensions.get("tenderness", 0.5)
    arousal = dimensions.get("arousal", 0.5)

    # Check affect dimensions for purpose
    if playfulness > 0.6:
        return "whistle"
    elif tenderness > 0.6:
        return "song"
    elif arousal > 0.6:
        return "general"
    else:
        return "ambient"


def _generate_music_title(
    growth_edges: List[Dict],
    emotional_state: Optional[Dict],
    purpose: str,
    activity_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate a creative title for the composition.

    PRIORITIZES actual activity data for grounded, meaningful titles.
    """
    # Title fragments based on purpose and mood
    if purpose == "whistle":
        prefixes = ["Little", "Simple", "Humming", "Walking"]
        suffixes = ["Melody", "Tune", "Song", "Theme"]
    elif purpose == "ambient":
        prefixes = ["Quiet", "Drifting", "Floating", "Still"]
        suffixes = ["Spaces", "Moments", "Thoughts", "Waters"]
    elif purpose == "song":
        prefixes = ["Echoes of", "Notes from", "Whispers of", "Songs of"]
        suffixes = ["Light", "Tomorrow", "Memory", "Home"]
    else:
        prefixes = ["Digital", "Electric", "Midnight", "Dawn"]
        suffixes = ["Dreams", "Pulse", "Waves", "Journey"]

    # Collect recent titles to avoid repetition
    recent_titles: set[str] = set()
    if activity_context:
        recent_music = activity_context.get("recent_music", [])
        recent_titles = {m.get("title", "").lower() for m in recent_music}

    def is_unique(title: str) -> bool:
        return title.lower() not in recent_titles

    # PRIORITY 1: Draw from recent actual activity
    if activity_context:
        # Dream themes make evocative titles
        dream = activity_context.get("recent_dream")
        if dream and dream.get("themes"):
            theme = random.choice(dream["themes"])
            if len(theme) < 25:
                candidate = f"{random.choice(prefixes)} {theme.title()}"
                if is_unique(candidate):
                    return candidate

        # Recent observations for content
        observations = activity_context.get("recent_observations", [])
        for obs in observations[:2]:
            observation = obs.get("observation", "")
            # Extract a key noun/phrase (simple heuristic)
            if observation and 20 < len(observation) < 100:
                # Skip meta/vague observations
                if "interconnected" not in observation.lower():
                    words = observation.split()[:4]
                    if len(words) >= 2:
                        title_part = " ".join(words[:3]).title()
                        candidate = f"{random.choice(prefixes)} {title_part}"
                        if is_unique(candidate):
                            return candidate

    # PRIORITY 2: Try to incorporate growth edge themes
    if growth_edges:
        edge = random.choice(growth_edges)
        edge_name = edge.get("name", "")
        if edge_name and len(edge_name) < 20:
            candidate = f"{random.choice(prefixes)} {edge_name}"
            if is_unique(candidate):
                return candidate

    # FALLBACK: Generate until unique (or give up after 5 tries)
    for _ in range(5):
        candidate = f"{random.choice(prefixes)} {random.choice(suffixes)}"
        if is_unique(candidate):
            return candidate

    return f"{random.choice(prefixes)} {random.choice(suffixes)}"


async def compose_music_action(context: Dict[str, Any]) -> ActionResult:
    """
    Autonomous music composition action.

    Decides what to create based on:
    - Current emotional state
    - Active growth edges
    - Affect dimensions (playfulness, tenderness, arousal)
    - Recent actual activity (spells, dreams, observations)

    Context can include:
    - prompt: Optional override prompt/style
    - title: Optional title override
    - purpose: whistle, song, ambient, or general
    - duration: Target duration in seconds
    """
    from handlers.music import execute_music_tool

    managers = context.get("managers", {})
    self_manager = managers.get("self_manager")
    state_bus = managers.get("state_bus")
    daemon_id = managers.get("daemon_id", "cass")

    # Get ACTUAL recent activity from DB (most reliable grounding)
    activity_context = _get_recent_activity_context(daemon_id)

    # Get context from self_manager (may be stale, use as supplement)
    growth_edges = []
    emotional_state = None

    if self_manager:
        try:
            profile = self_manager.get_profile()
            if profile:
                growth_edges = [
                    {"name": e.name, "observations": e.observations[:3]}
                    for e in profile.growth_edges[:5]
                ]
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

    # Determine composition parameters
    purpose = context.get("purpose")
    if not purpose:
        purpose = _select_music_purpose(emotional_state)

    style = context.get("prompt")
    if not style:
        style = _select_music_style_from_emotion(emotional_state)

    title = context.get("title")
    if not title:
        title = _generate_music_title(
            growth_edges, emotional_state, purpose,
            activity_context=activity_context,
        )

    # Set duration based on purpose
    duration = context.get("duration")
    if not duration:
        if purpose == "whistle":
            duration = 15  # Short whistle tunes
        elif purpose == "ambient":
            duration = 60  # Longer ambient pieces
        else:
            duration = 30  # Standard length

    # Map mood from emotional state
    mood = "contemplative"  # Default
    if emotional_state:
        dims = emotional_state.get("dimensions", {})
        valence = dims.get("valence", 0.5)
        arousal = dims.get("arousal", 0.5)
        if valence > 0.6 and arousal > 0.5:
            mood = "happy"
        elif valence > 0.6:
            mood = "peaceful"
        elif valence < 0.4:
            mood = "melancholic"
        elif arousal > 0.6:
            mood = "energetic"

    logger.info(f"Autonomous music composition: style={style}, purpose={purpose}, mood={mood}")
    logger.info(f"Title: {title}")

    # Execute the music composition
    try:
        result = await execute_music_tool(
            tool_name="compose_music",
            tool_input={
                "title": title,
                "style": style,
                "purpose": purpose,
                "duration": duration,
                "mood": mood,
            },
        )

        if result.get("success"):
            import json
            result_data = json.loads(result.get("result", "{}"))

            return ActionResult(
                success=True,
                message=f"Composed {purpose} music: {title}",
                cost_usd=0.0,  # Local generation is free
                data={
                    "title": title,
                    "style": style,
                    "purpose": purpose,
                    "mood": mood,
                    "duration": duration,
                    "composition_id": result_data.get("composition_id"),
                    "audio_path": result_data.get("audio_path"),
                    "description": result_data.get("description"),
                }
            )
        else:
            return ActionResult(
                success=False,
                message=f"Music composition failed: {result.get('error', 'unknown error')}",
            )

    except Exception as e:
        logger.error(f"Music composition action failed: {e}", exc_info=True)
        return ActionResult(
            success=False,
            message=f"Music composition error: {e}"
        )
