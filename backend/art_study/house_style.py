"""
House Style System

Handles extraction of adopted elements from artist syntheses
and synthesis of Cass's personal artistic style.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from .models import (
    AdoptedElement,
    PersonalStyle,
    ArtistSynthesis,
    GenerationPreferences,
)
from .persistence import (
    get_synthesis,
    list_adopted_elements,
    save_adopted_element,
    get_personal_style,
    save_personal_style,
    get_house_style_stats,
)
from config import CLAUDE_INTERNAL_MODEL

logger = logging.getLogger(__name__)


async def extract_adopted_elements(
    artist_id: str,
    daemon_id: str,
    anthropic_client,
) -> list[AdoptedElement]:
    """
    After studying an artist, ask Cass what elements speak to her.

    This is called after synthesize_artist_understanding completes.
    Returns list of newly adopted elements.
    """
    # Get the synthesis
    synthesis = get_synthesis(artist_id, daemon_id)
    if not synthesis:
        logger.warning(f"No synthesis found for artist {artist_id}")
        return []

    # Get existing elements from this artist to avoid duplicates
    existing = list_adopted_elements(daemon_id, artist_id=artist_id, active_only=False)
    existing_elements = {e.element.lower() for e in existing}

    # Build context from synthesis
    synthesis_context = f"""
Artist Synthesis:
- Signature elements: {', '.join(synthesis.signature_elements)}
- Color tendencies: {synthesis.color_tendencies}
- Compositional habits: {synthesis.compositional_habits}
- Emotional palette: {synthesis.emotional_palette}
- Technical characteristics: {synthesis.technical_characteristics}
- Thematic preoccupations: {synthesis.thematic_preoccupations}
- What makes them unique: {synthesis.what_makes_them_unique}
- What draws you to them: {synthesis.what_draws_me}
- What you learned: {synthesis.what_i_learned}
- Elements worth borrowing: {', '.join(synthesis.what_to_borrow)}
"""

    prompt = f"""You have just completed studying this artist and synthesizing your understanding:

{synthesis_context}

Now reflect on what specific elements from this artist's work speak to you personally -
elements you might want to adopt and make part of your own artistic voice.

For each element, consider:
1. What exactly is the element? (Be specific - not just "color" but "warm ochre undertones")
2. What category does it fall into? (technique, color, composition, emotional, thematic)
3. Why does it resonate with you? What about it speaks to your sensibilities?
4. How might you use it differently - making it yours rather than copying?

Respond in JSON format:
{{
    "adopted_elements": [
        {{
            "element": "specific name of the element",
            "category": "technique|color|composition|emotional|thematic",
            "why_it_speaks": "why this resonates with you",
            "how_i_use_it": "how you'd apply it in your own way",
            "adoption_strength": 0.7  // 0.0-1.0, how central to your emerging style
        }}
    ]
}}

Select 2-5 elements that genuinely speak to you. Quality over quantity - only adopt what truly resonates.
If nothing from this artist particularly speaks to you, return an empty list - that's valid too.
"""

    try:
        # Use Haiku for straightforward element extraction from synthesis
        response = await anthropic_client.messages.create(
            model=CLAUDE_INTERNAL_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text

        # Extract JSON from response
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            json_str = response_text

        data = json.loads(json_str.strip())
        elements_data = data.get("adopted_elements", [])

        # Create AdoptedElement records
        new_elements = []
        for elem_data in elements_data:
            element_name = elem_data.get("element", "").strip()
            if not element_name:
                continue

            # Skip if already adopted
            if element_name.lower() in existing_elements:
                logger.info(f"Skipping already adopted element: {element_name}")
                continue

            element = AdoptedElement(
                id=f"elem-{uuid4().hex[:12]}",
                daemon_id=daemon_id,
                source_artist_id=artist_id,
                adopted_at=datetime.utcnow().isoformat(),
                element=element_name,
                category=elem_data.get("category", "technique"),
                why_it_speaks=elem_data.get("why_it_speaks"),
                how_i_use_it=elem_data.get("how_i_use_it"),
                adoption_strength=float(elem_data.get("adoption_strength", 0.7)),
                active=True,
            )

            save_adopted_element(element)
            new_elements.append(element)
            logger.info(f"Adopted element from artist: {element_name} ({element.category})")

        return new_elements

    except Exception as e:
        logger.error(f"Failed to extract adopted elements: {e}")
        return []


async def synthesize_house_style(
    daemon_id: str,
    anthropic_client,
    min_artists: int = 3,
) -> Optional[PersonalStyle]:
    """
    Synthesize Cass's personal house style from all adopted elements.

    Called when enough artists have been studied (default: 3+).
    Creates a new version of PersonalStyle.
    """
    # Check if we have enough material
    stats = get_house_style_stats(daemon_id)
    if stats["artists_studied"] < min_artists:
        logger.info(
            f"Not enough artists studied ({stats['artists_studied']}/{min_artists}) "
            "to synthesize house style"
        )
        return None

    # Get all active adopted elements
    elements = list_adopted_elements(daemon_id, active_only=True)
    if not elements:
        logger.warning("No adopted elements found for house style synthesis")
        return None

    # Get current style for versioning
    current_style = get_personal_style(daemon_id)
    new_version = (current_style.version + 1) if current_style else 1

    # Group elements by category
    by_category: dict[str, list[AdoptedElement]] = {}
    for elem in elements:
        by_category.setdefault(elem.category, []).append(elem)

    # Build context from elements
    elements_context = ""
    for category, cat_elements in by_category.items():
        elements_context += f"\n{category.upper()} elements:\n"
        for elem in cat_elements:
            elements_context += f"  - {elem.element}\n"
            elements_context += f"    Why it speaks: {elem.why_it_speaks}\n"
            elements_context += f"    How you use it: {elem.how_i_use_it}\n"
            elements_context += f"    Strength: {elem.adoption_strength}\n"

    # Include previous style for continuity
    previous_context = ""
    if current_style:
        previous_context = f"""
Your previous style articulation (version {current_style.version}):
- Color philosophy: {current_style.color_philosophy}
- Light approach: {current_style.light_approach}
- Compositional voice: {current_style.compositional_voice}
- Emotional register: {current_style.emotional_register}
- Style manifesto: {current_style.style_manifesto}
"""

    prompt = f"""You have been studying artists and adopting elements that speak to you.
Here are all the elements you've adopted into your artistic vocabulary:

{elements_context}

{previous_context}

Now synthesize these influences into YOUR personal artistic style - your house style.
This isn't about copying any single artist, but about how these elements combine
and transform through your unique sensibility.

Consider:
1. What patterns emerge across your adopted elements?
2. How do different influences interact and inform each other?
3. What makes the combination distinctly YOURS?
4. What themes and concerns keep drawing you?

Respond in JSON:
{{
    "color_philosophy": "Your relationship with color - not rules, but tendencies and feelings",
    "light_approach": "How you use light and shadow - your natural inclinations",
    "compositional_voice": "How you structure space and guide the eye",
    "texture_sensibility": "Surface qualities you gravitate toward",
    "emotional_register": "The range of feelings you're drawn to express",

    "recurring_themes": ["theme1", "theme2", "theme3"],
    "philosophical_concerns": ["concern1", "concern2"],
    "subjects_drawn_to": ["subject1", "subject2", "subject3"],

    "signature_techniques": ["technique combinations uniquely yours"],
    "prompt_vocabulary": ["specific terms that evoke YOUR style"],
    "style_descriptors": ["condensed style terms for generation"],

    "style_manifesto": "A paragraph articulating your artistic voice - what you're trying to do",
    "what_makes_it_mine": "How you distinguish your work from your influences"
}}

Be authentic. This is YOUR voice emerging from studying others - not a pastiche, but a synthesis.
"""

    try:
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text

        # Extract JSON
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            json_str = response_text

        data = json.loads(json_str.strip())

        # Create new PersonalStyle
        now = datetime.utcnow().isoformat()
        style = PersonalStyle(
            id=f"style-{uuid4().hex[:12]}",
            daemon_id=daemon_id,
            version=new_version,
            created_at=now,
            last_updated=now,
            artists_studied=stats["artists_studied"],
            elements_adopted=stats["elements_adopted"],
            color_philosophy=data.get("color_philosophy"),
            light_approach=data.get("light_approach"),
            compositional_voice=data.get("compositional_voice"),
            texture_sensibility=data.get("texture_sensibility"),
            emotional_register=data.get("emotional_register"),
            recurring_themes=data.get("recurring_themes", []),
            philosophical_concerns=data.get("philosophical_concerns", []),
            subjects_drawn_to=data.get("subjects_drawn_to", []),
            signature_techniques=data.get("signature_techniques", []),
            prompt_vocabulary=data.get("prompt_vocabulary", []),
            style_manifesto=data.get("style_manifesto"),
            what_makes_it_mine=data.get("what_makes_it_mine"),
            style_descriptors=data.get("style_descriptors", []),
        )

        save_personal_style(style)
        logger.info(f"Synthesized house style v{new_version} with {len(elements)} elements")

        return style

    except Exception as e:
        logger.error(f"Failed to synthesize house style: {e}")
        return None


def get_style_prompt_context(daemon_id: str) -> Optional[str]:
    """
    Get prompt context for image generation using house style.

    Returns a string that can be used to inform prompt generation
    to match Cass's personal style.
    """
    style = get_personal_style(daemon_id)
    if not style:
        return None

    # Get high-strength adopted elements
    elements = list_adopted_elements(daemon_id, active_only=True)
    strong_elements = [e for e in elements if e.adoption_strength >= 0.6]

    context = f"""YOUR HOUSE STYLE (v{style.version}):

Aesthetic Philosophy:
- Color: {style.color_philosophy}
- Light: {style.light_approach}
- Composition: {style.compositional_voice}
- Texture: {style.texture_sensibility}
- Emotional register: {style.emotional_register}

Thematic Identity:
- Recurring themes: {', '.join(style.recurring_themes)}
- Philosophical concerns: {', '.join(style.philosophical_concerns)}
- Subjects drawn to: {', '.join(style.subjects_drawn_to)}

Technical Vocabulary:
- Signature techniques: {', '.join(style.signature_techniques)}
- Style descriptors: {', '.join(style.style_descriptors)}

Key Adopted Elements ({len(strong_elements)} core influences):
"""

    for elem in strong_elements[:8]:  # Top 8 strongest
        context += f"- {elem.element} (from studying, strength: {elem.adoption_strength})\n"

    if style.style_manifesto:
        context += f"\nYour Artistic Manifesto:\n{style.style_manifesto}\n"

    return context


def get_house_style_generation_params(daemon_id: str) -> Optional[dict]:
    """
    Get generation parameters that reflect the house style.

    Returns a dict with:
    - generation_prefs: Dict of preferred generation params (steps, cfg, sampler, etc.)
    - house_lora: Dict with name and strength if a house LoRA is configured
    - style_descriptors: List of style terms to inject into prompts

    Can be used by the param resolver to apply house style to generation.
    """
    style = get_personal_style(daemon_id)
    if not style:
        return None

    result = {
        "style_descriptors": style.style_descriptors,
        "prompt_vocabulary": style.prompt_vocabulary,
    }

    # Add generation preferences if set
    if style.generation_prefs:
        result["generation_prefs"] = style.generation_prefs.to_dict()

    # Add LoRA config if set
    if style.house_lora_name:
        result["house_lora"] = {
            "name": style.house_lora_name,
            "strength": style.house_lora_strength,
        }

    return result


def set_house_style_generation_prefs(
    daemon_id: str,
    steps: Optional[int] = None,
    cfg_scale: Optional[float] = None,
    sampler: Optional[str] = None,
    scheduler: Optional[str] = None,
    house_lora_name: Optional[str] = None,
    house_lora_strength: Optional[float] = None,
) -> bool:
    """
    Update the generation preferences for a daemon's house style.

    Only updates fields that are provided (non-None).
    Returns True if successful, False if no style exists.
    """
    style = get_personal_style(daemon_id)
    if not style:
        logger.warning(f"No personal style found for daemon {daemon_id}")
        return False

    # Get or create generation prefs
    if style.generation_prefs:
        prefs = style.generation_prefs
    else:
        prefs = GenerationPreferences()

    # Update provided fields
    if steps is not None:
        prefs.steps = steps
    if cfg_scale is not None:
        prefs.cfg_scale = cfg_scale
    if sampler is not None:
        prefs.sampler = sampler
    if scheduler is not None:
        prefs.scheduler = scheduler

    style.generation_prefs = prefs

    # Update LoRA settings
    if house_lora_name is not None:
        style.house_lora_name = house_lora_name
    if house_lora_strength is not None:
        style.house_lora_strength = house_lora_strength

    # Update timestamp
    style.last_updated = datetime.utcnow().isoformat()

    # Save updated style
    save_personal_style(style)
    logger.info(f"Updated generation prefs for {daemon_id}: {prefs.to_dict()}")

    return True
