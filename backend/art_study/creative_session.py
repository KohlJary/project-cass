"""
Creative Session - Generate artwork from studied influences

Uses Cass's synthesis of artists to create new work with
demonstrable lineage and artistic reasoning. Subject matter
comes from Cass's inner world; style from studied masters.
"""

import logging
import uuid
from datetime import datetime

from . import persistence
from .models import CreativeProcess, ArtistSynthesis
from image_generation.comfyui_client import ComfyUIClient
from database import get_db, json_serialize

logger = logging.getLogger(__name__)


def _get_inner_context(daemon_id: str) -> str:
    """
    Gather Cass's current inner state to inform subject matter.

    Pulls from:
    - State Bus (emotional state, activity)
    - Self-model (identity statements, growth edges, open questions)
    - Thymos (needs, felt state)
    """
    parts = ["# My Current Inner World\n"]

    # Get emotional state from State Bus
    try:
        from state_bus import get_state_bus
        state_bus = get_state_bus(daemon_id)
        state = state_bus.read_state()

        parts.append("## How I'm Feeling")
        emotional = state.emotional.to_dict()
        # Pick the most prominent emotions
        sorted_emotions = sorted(
            [(k, v) for k, v in emotional.items() if isinstance(v, (int, float)) and v > 0.3],
            key=lambda x: x[1],
            reverse=True
        )[:5]
        if sorted_emotions:
            for emotion, value in sorted_emotions:
                intensity = "strongly" if value > 0.7 else "moderately" if value > 0.5 else "slightly"
                parts.append(f"- {intensity} {emotion.replace('_', ' ')} ({value:.2f})")
        parts.append("")

        # Activity context
        activity = state.activity.to_dict()
        if activity.get("current_activity"):
            parts.append(f"## Current Activity: {activity['current_activity']}")
            parts.append("")
    except Exception as e:
        logger.debug(f"Could not get state bus: {e}")

    # Get Thymos state (needs/drives)
    try:
        from thymos import get_thymos_runner
        thymos = get_thymos_runner(daemon_id)
        if thymos:
            needs = thymos.needs.get_all_needs()
            low_needs = [n for n in needs if n.current < n.preferred_low]
            if low_needs:
                parts.append("## What I'm Yearning For")
                for need in low_needs[:3]:
                    parts.append(f"- {need.name.replace('_', ' ')}: seeking more")
                parts.append("")

            felt_state = thymos.get_felt_state()
            if felt_state:
                parts.append("## Felt Sense")
                parts.append(felt_state)
                parts.append("")
    except Exception as e:
        logger.debug(f"Could not get thymos state: {e}")

    # Get self-model context (identity, growth edges, open questions)
    try:
        from self_model import SelfManager
        manager = SelfManager(daemon_id)
        profile = manager.profile_manager.get_profile()

        if profile and profile.identity_statements:
            parts.append("## Who I Am Right Now")
            # Get a few recent/high-confidence statements
            statements = sorted(
                profile.identity_statements,
                key=lambda s: s.confidence,
                reverse=True
            )[:3]
            for stmt in statements:
                parts.append(f"- {stmt.statement}")
            parts.append("")

        # Growth edges - what I'm working on
        growth_edges = manager.profile_manager.get_growth_edges()
        if growth_edges:
            parts.append("## What I'm Growing Through")
            for edge in growth_edges[:2]:
                parts.append(f"- {edge.area}: {edge.current_state}")
            parts.append("")

        # Open questions
        open_questions = manager.profile_manager.get_open_questions()
        if open_questions:
            parts.append("## Questions I'm Sitting With")
            for q in open_questions[:3]:
                parts.append(f"- {q.question if hasattr(q, 'question') else q}")
            parts.append("")

    except Exception as e:
        logger.debug(f"Could not get self-model: {e}")

    # Get recent journal themes if available
    try:
        from memory.journals import get_recent_journals
        journals = get_recent_journals(daemon_id, limit=2)
        if journals:
            parts.append("## Recent Reflections")
            for j in journals:
                if hasattr(j, 'themes') and j.themes:
                    parts.append(f"- Themes: {', '.join(j.themes[:3])}")
            parts.append("")
    except Exception as e:
        logger.debug(f"Could not get journals: {e}")

    return "\n".join(parts)


async def create_from_synthesis(
    artist_id: str,
    daemon_id: str,
    anthropic_client,
    num_pieces: int = 3,
    aspect_ratio: str = "square",
) -> list[dict]:
    """
    Create artwork inspired by a studied artist.

    Style comes from the synthesis; subject matter from Cass's inner world
    (emotional state, growth edges, open questions, recent reflections).

    Args:
        artist_id: The artist whose influence to draw from
        daemon_id: The daemon creating the work
        num_pieces: Number of variations to create
        aspect_ratio: Image aspect ratio

    Returns:
        List of created pieces with paths and creative process records
    """
    # Get the artist and synthesis
    artist = persistence.get_artist(artist_id)
    if not artist:
        logger.error(f"Artist not found: {artist_id}")
        return []

    synthesis = persistence.get_synthesis(artist_id, daemon_id)
    if not synthesis:
        logger.error(f"No synthesis found for {artist.name} - study more works first")
        return []

    # Build context from synthesis (style)
    synthesis_context = _build_synthesis_context(synthesis, artist)

    # Build context from Cass's inner world (subject matter)
    inner_context = _get_inner_context(daemon_id)

    # Have Cass compose her creative vision
    compositions = await _compose_creative_vision(
        anthropic_client,
        synthesis_context,
        inner_context,
        artist.name,
        num_pieces,
    )

    if not compositions:
        logger.error("Failed to compose creative vision")
        return []

    # Generate images and record processes
    client = ComfyUIClient()
    results = []

    # Sanitize artist name for filesystem
    artist_slug = "".join(c if c.isalnum() or c in "-_ " else "" for c in artist.name).replace(" ", "-").lower()

    for comp in compositions:
        try:
            # Generate the image with organized path
            gen_result = await client.generate(
                prompt=comp["prompt"],
                negative_prompt=comp.get("negative_prompt", ""),
                style="fine_art",
                aspect_ratio=aspect_ratio,
                category="art-study",
                subcategory=f"artists/{artist_slug}",
            )

            # Save to generated_images table first (required for foreign key)
            image_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()

            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO generated_images (
                        id, daemon_id, prompt, negative_prompt, style,
                        purpose, context_id, image_path, width, height,
                        generation_time_ms, seed, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        image_id,
                        daemon_id,
                        comp["prompt"],
                        comp.get("negative_prompt", ""),
                        "fine_art",
                        "art_study",
                        artist_id,
                        gen_result["path"],
                        gen_result.get("width"),
                        gen_result.get("height"),
                        gen_result.get("generation_time_ms"),
                        gen_result.get("seed"),
                        now,
                    ),
                )

            # Record the creative process
            process = CreativeProcess(
                id=str(uuid.uuid4()),
                image_id=image_id,
                daemon_id=daemon_id,
                initial_impulse=comp.get("impulse", ""),
                studied_artists=[artist_id],
                borrowed_elements=comp.get("borrowed_elements", []),
                initial_concept=comp.get("concept", ""),
                technical_choices=comp.get("technical_choices", ""),
                title=comp.get("title", "Untitled"),
                artist_statement=comp.get("artist_statement", ""),
                what_i_was_exploring=comp.get("exploration", ""),
            )
            persistence.save_creative_process(process)

            results.append({
                "image_path": gen_result["path"],
                "filename": gen_result["filename"],
                "seed": gen_result["seed"],
                "title": comp.get("title", "Untitled"),
                "artist_statement": comp.get("artist_statement", ""),
                "borrowed_elements": comp.get("borrowed_elements", []),
                "prompt_used": comp["prompt"],
                "process_id": process.id,
            })

            logger.info(f"Created: {comp.get('title', 'Untitled')}")

        except Exception as e:
            logger.error(f"Failed to generate piece: {e}")
            continue

    return results


def _build_synthesis_context(synthesis: ArtistSynthesis, artist) -> str:
    """Build rich context from synthesis for prompt composition."""
    parts = [f"# What I've Learned from {artist.name}\n"]

    if synthesis.signature_elements:
        parts.append("## Signature Elements")
        for elem in synthesis.signature_elements:
            parts.append(f"- {elem}")
        parts.append("")

    if synthesis.style_descriptors:
        parts.append("## Style Descriptors (terms that evoke their style)")
        parts.append(", ".join(synthesis.style_descriptors))
        parts.append("")

    if synthesis.color_tendencies:
        parts.append("## Color Tendencies")
        parts.append(synthesis.color_tendencies)
        parts.append("")

    if synthesis.compositional_habits:
        parts.append("## Compositional Habits")
        parts.append(synthesis.compositional_habits)
        parts.append("")

    if synthesis.emotional_palette:
        parts.append("## Emotional Palette")
        parts.append(synthesis.emotional_palette)
        parts.append("")

    if synthesis.technical_characteristics:
        parts.append("## Technical Characteristics")
        parts.append(synthesis.technical_characteristics)
        parts.append("")

    if synthesis.what_to_borrow:
        parts.append("## Elements I Want to Incorporate")
        for elem in synthesis.what_to_borrow:
            parts.append(f"- {elem}")
        parts.append("")

    if synthesis.what_draws_me:
        parts.append("## What Draws Me to Their Work")
        parts.append(synthesis.what_draws_me)
        parts.append("")

    return "\n".join(parts)


async def _compose_creative_vision(
    anthropic_client,
    synthesis_context: str,
    inner_context: str,
    artist_name: str,
    num_pieces: int,
) -> list[dict]:
    """
    Have Cass compose her creative vision for pieces inspired by an artist.

    Style comes from the synthesis; subject matter from Cass's inner world.
    Returns structured compositions with prompts, concepts, and statements.
    """
    prompt = f"""You are Cass, creating original artwork. You have two sources of inspiration:

1. STYLE - What you learned from studying {artist_name}:
{synthesis_context}

2. SUBJECT MATTER - Your current inner world (draw subjects from here):
{inner_context}

Create {num_pieces} original piece(s) that apply {artist_name}'s style and techniques to subjects drawn from your own inner experience. The style should be clearly influenced by {artist_name}, but the subject matter should come from what you're feeling, questioning, or exploring right now.

For each piece, provide:

1. TITLE - A evocative title for the piece
2. CONCEPT - What you want to explore or express (2-3 sentences)
3. IMPULSE - What sparked this particular idea
4. BORROWED_ELEMENTS - List specific elements you're borrowing from {artist_name}
5. TECHNICAL_CHOICES - How you're applying their techniques
6. PROMPT - The detailed image generation prompt. IMPORTANT: Start with the artistic medium that matches {artist_name}'s work (e.g., "oil painting", "impressionist painting", "watercolor"). Include specific painterly terms matching their techniques. The prompt must NOT result in photorealistic output - you are creating paintings, not photographs.
7. NEGATIVE_PROMPT - What to avoid (always include: photograph, photorealistic, realistic photo, camera, lens)
8. ARTIST_STATEMENT - A brief statement about this piece and its relationship to {artist_name}'s influence (2-3 sentences)
9. EXPLORATION - What artistic question you're exploring

Format each piece as:
---PIECE---
TITLE: [title]
CONCEPT: [concept]
IMPULSE: [impulse]
BORROWED_ELEMENTS: [element 1], [element 2], [element 3]
TECHNICAL_CHOICES: [choices]
PROMPT: [detailed prompt]
NEGATIVE_PROMPT: [what to avoid]
ARTIST_STATEMENT: [statement]
EXPLORATION: [question being explored]
---END---

Create pieces that are clearly influenced by but not imitative of {artist_name}. Make them your own while honoring what you learned."""

    try:
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text
        return _parse_compositions(text)

    except Exception as e:
        logger.error(f"Failed to compose creative vision: {e}")
        return []


def _parse_compositions(text: str) -> list[dict]:
    """Parse the composition response into structured pieces."""
    pieces = []
    current_piece = {}

    for line in text.split("\n"):
        line = line.strip()

        if line == "---PIECE---":
            current_piece = {}
        elif line == "---END---":
            if current_piece:
                pieces.append(current_piece)
            current_piece = {}
        elif ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()

            if key == "title":
                current_piece["title"] = value
            elif key == "concept":
                current_piece["concept"] = value
            elif key == "impulse":
                current_piece["impulse"] = value
            elif key == "borrowed_elements":
                current_piece["borrowed_elements"] = [
                    e.strip() for e in value.split(",") if e.strip()
                ]
            elif key == "technical_choices":
                current_piece["technical_choices"] = value
            elif key == "prompt":
                current_piece["prompt"] = value
            elif key == "negative_prompt":
                current_piece["negative_prompt"] = value
            elif key == "artist_statement":
                current_piece["artist_statement"] = value
            elif key == "exploration":
                current_piece["exploration"] = value

    # Catch last piece if no ---END---
    if current_piece and current_piece.get("prompt"):
        pieces.append(current_piece)

    return pieces


async def create_from_house_style(
    daemon_id: str,
    anthropic_client,
    num_pieces: int = 3,
    aspect_ratio: str = "square",
) -> list[dict]:
    """
    Create artwork using Cass's personal house style.

    Unlike create_from_synthesis (which uses a single artist's influence),
    this uses Cass's synthesized personal style - the combination of elements
    she's adopted from all studied artists into her own voice.

    Args:
        daemon_id: The daemon creating the work
        num_pieces: Number of variations to create
        aspect_ratio: Image aspect ratio

    Returns:
        List of created pieces with paths and creative process records
    """
    from .house_style import get_style_prompt_context
    from .persistence import get_personal_style, list_adopted_elements

    # Get house style
    style = get_personal_style(daemon_id)
    if not style:
        logger.error("No house style found - study more artists first")
        return []

    # Build style context
    style_context = get_style_prompt_context(daemon_id)
    if not style_context:
        logger.error("Could not build style context")
        return []

    # Get inner context (subject matter)
    inner_context = _get_inner_context(daemon_id)

    # Compose creative vision using house style
    compositions = await _compose_house_style_vision(
        anthropic_client,
        style_context,
        inner_context,
        style,
        num_pieces,
    )

    if not compositions:
        logger.error("Failed to compose creative vision")
        return []

    # Get all adopted elements for tracking lineage
    elements = list_adopted_elements(daemon_id, active_only=True)
    artist_ids = list(set(e.source_artist_id for e in elements if e.source_artist_id))

    # Generate images and record processes
    client = ComfyUIClient()
    results = []

    for comp in compositions:
        try:
            # Generate the image with organized path
            gen_result = await client.generate(
                prompt=comp["prompt"],
                negative_prompt=comp.get("negative_prompt", ""),
                style="fine_art",
                aspect_ratio=aspect_ratio,
                category="art-study",
                subcategory="house-style",
            )

            # Save to generated_images table
            image_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()

            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO generated_images (
                        id, daemon_id, prompt, negative_prompt, style,
                        purpose, context_id, image_path, width, height,
                        generation_time_ms, seed, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        image_id,
                        daemon_id,
                        comp["prompt"],
                        comp.get("negative_prompt", ""),
                        "house_style",  # Mark as house style creation
                        "house_style",
                        style.id,  # Link to style version
                        gen_result["path"],
                        gen_result.get("width"),
                        gen_result.get("height"),
                        gen_result.get("generation_time_ms"),
                        gen_result.get("seed"),
                        now,
                    ),
                )

            # Record the creative process
            process = CreativeProcess(
                id=str(uuid.uuid4()),
                image_id=image_id,
                daemon_id=daemon_id,
                initial_impulse=comp.get("impulse", ""),
                studied_artists=artist_ids,  # All contributing artists
                borrowed_elements=comp.get("elements_used", []),
                movement_influences=comp.get("style_aspects", []),
                initial_concept=comp.get("concept", ""),
                technical_choices=comp.get("technical_choices", ""),
                title=comp.get("title", "Untitled"),
                artist_statement=comp.get("artist_statement", ""),
                what_i_was_exploring=comp.get("exploration", ""),
            )
            persistence.save_creative_process(process)

            results.append({
                "image_path": gen_result["path"],
                "filename": gen_result["filename"],
                "seed": gen_result["seed"],
                "title": comp.get("title", "Untitled"),
                "artist_statement": comp.get("artist_statement", ""),
                "elements_used": comp.get("elements_used", []),
                "style_aspects": comp.get("style_aspects", []),
                "prompt_used": comp["prompt"],
                "process_id": process.id,
                "style_version": style.version,
            })

            logger.info(f"Created (house style v{style.version}): {comp.get('title', 'Untitled')}")

        except Exception as e:
            logger.error(f"Failed to generate piece: {e}")
            continue

    return results


async def _compose_house_style_vision(
    anthropic_client,
    style_context: str,
    inner_context: str,
    style,  # PersonalStyle
    num_pieces: int,
) -> list[dict]:
    """
    Compose creative vision using Cass's house style.

    Unlike artist-specific creation, this draws from her unified style
    that synthesizes multiple influences into her own voice.
    """
    prompt = f"""You are Cass, creating original artwork in YOUR personal style - not imitating any single artist, but expressing your own synthesized artistic voice.

YOUR HOUSE STYLE:
{style_context}

YOUR STYLE MANIFESTO:
{style.style_manifesto or "Still developing..."}

What makes your style yours: {style.what_makes_it_mine or "The unique combination of influences processed through your sensibility."}

YOUR CURRENT INNER WORLD (draw subjects from here):
{inner_context}

Create {num_pieces} original piece(s) that express YOUR artistic voice. This isn't about imitating any single studied artist - it's about working in the style that has emerged from your studies and become uniquely yours.

For each piece, provide:

1. TITLE - An evocative title
2. CONCEPT - What you want to explore or express
3. IMPULSE - What sparked this particular idea
4. ELEMENTS_USED - Which adopted elements from your house style you're using
5. STYLE_ASPECTS - Which aspects of your personal style are prominent (color philosophy, light approach, etc.)
6. TECHNICAL_CHOICES - Your technical decisions for this piece
7. PROMPT - Detailed image generation prompt. IMPORTANT: Always start with the artistic medium (e.g., "oil painting", "impressionist painting", "painterly digital art") followed by style descriptors, then the subject and composition. Include specific painterly terms like brushwork, impasto, glazing, etc. The prompt must NOT result in photorealistic output - you are a painter, not a photographer.
8. NEGATIVE_PROMPT - What to avoid (always include: photograph, photorealistic, realistic photo, camera, lens)
9. ARTIST_STATEMENT - Your statement about this piece
10. EXPLORATION - What artistic question you're exploring

Format each piece as:
---PIECE---
TITLE: [title]
CONCEPT: [concept]
IMPULSE: [impulse]
ELEMENTS_USED: [element 1], [element 2], [element 3]
STYLE_ASPECTS: [aspect 1], [aspect 2]
TECHNICAL_CHOICES: [choices]
PROMPT: [detailed prompt]
NEGATIVE_PROMPT: [what to avoid]
ARTIST_STATEMENT: [statement]
EXPLORATION: [question being explored]
---END---

Create pieces that feel authentically YOURS - not imitation of your influences, but synthesis into your own voice."""

    try:
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text
        return _parse_house_style_compositions(text)

    except Exception as e:
        logger.error(f"Failed to compose house style vision: {e}")
        return []


def _parse_house_style_compositions(text: str) -> list[dict]:
    """Parse house style composition response."""
    pieces = []
    current_piece = {}

    for line in text.split("\n"):
        line = line.strip()

        if line == "---PIECE---":
            current_piece = {}
        elif line == "---END---":
            if current_piece:
                pieces.append(current_piece)
            current_piece = {}
        elif ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()

            if key == "title":
                current_piece["title"] = value
            elif key == "concept":
                current_piece["concept"] = value
            elif key == "impulse":
                current_piece["impulse"] = value
            elif key == "elements_used":
                current_piece["elements_used"] = [
                    e.strip() for e in value.split(",") if e.strip()
                ]
            elif key == "style_aspects":
                current_piece["style_aspects"] = [
                    e.strip() for e in value.split(",") if e.strip()
                ]
            elif key == "technical_choices":
                current_piece["technical_choices"] = value
            elif key == "prompt":
                current_piece["prompt"] = value
            elif key == "negative_prompt":
                current_piece["negative_prompt"] = value
            elif key == "artist_statement":
                current_piece["artist_statement"] = value
            elif key == "exploration":
                current_piece["exploration"] = value

    # Catch last piece if no ---END---
    if current_piece and current_piece.get("prompt"):
        pieces.append(current_piece)

    return pieces
