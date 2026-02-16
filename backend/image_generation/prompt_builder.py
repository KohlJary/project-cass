"""
Prompt Builder for Image Generation

Builds effective prompts for SDXL based on style and content.
Incorporates Cass's house style when available.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Style presets with prompt prefixes and generation parameters
STYLE_PRESETS = {
    "painterly": {
        "prefix": "oil painting, masterful brushwork, rich colors, artistic",
        "negative": "photograph, photorealistic, 3d render",
        "steps": 30,
        "cfg": 7.0,
    },
    "sketch": {
        "prefix": "pencil sketch, detailed linework, artistic drawing, monochrome",
        "negative": "color, painting, photograph",
        "steps": 20,
        "cfg": 8.0,
    },
    "photorealistic": {
        "prefix": "photograph, 8k, highly detailed, professional photography, cinematic lighting",
        "negative": "painting, drawing, illustration, cartoon, anime",
        "steps": 35,
        "cfg": 6.0,
    },
    "abstract": {
        "prefix": "abstract art, geometric shapes, bold colors, modern art, expressionist",
        "negative": "realistic, photograph, detailed face",
        "steps": 25,
        "cfg": 9.0,
    },
    "watercolor": {
        "prefix": "watercolor painting, soft edges, flowing colors, artistic, delicate",
        "negative": "oil painting, photograph, sharp edges",
        "steps": 25,
        "cfg": 7.0,
    },
    "digital_art": {
        "prefix": "digital art, vibrant colors, detailed, trending on artstation, concept art",
        "negative": "photograph, blurry, low quality",
        "steps": 30,
        "cfg": 7.0,
    },
    "dreamlike": {
        "prefix": "surreal, dreamlike, ethereal, mystical atmosphere, soft glow, otherworldly",
        "negative": "realistic, harsh lighting, mundane",
        "steps": 35,
        "cfg": 8.0,
    },
}

# Mood modifiers
MOOD_MODIFIERS = {
    "contemplative": "serene atmosphere, thoughtful, soft lighting, introspective",
    "curious": "sense of wonder, discovery, warm light, inviting",
    "concerned": "somber tones, dramatic lighting, tension",
    "hopeful": "warm colors, dawn light, uplifting atmosphere",
    "melancholic": "muted colors, rain, twilight, bittersweet",
    "joyful": "bright colors, sunshine, vibrant, celebratory",
    "mysterious": "shadows, fog, enigmatic, hidden depths",
    "peaceful": "calm, tranquil, soft colors, gentle light",
}

# Default negative prompt
DEFAULT_NEGATIVE = (
    "ugly, blurry, low quality, distorted, deformed, disfigured, bad anatomy, "
    "watermark, signature, text, logo, cropped, out of frame, worst quality, "
    "low resolution, jpeg artifacts"
)


def get_house_style_modifiers(daemon_id: str = "cass") -> Optional[dict]:
    """
    Get house style modifiers for prompt building if available.

    Returns:
        Dict with 'prefix', 'techniques', 'negative' or None if no house style
    """
    try:
        from art_study.persistence import get_personal_style, list_adopted_elements

        style = get_personal_style(daemon_id)
        if not style or not style.style_descriptors:
            return None

        # Build prefix from style descriptors and signature techniques
        prefix_parts = []

        # Add style descriptors (e.g., "empathetically observational", "atmospherically unified")
        if style.style_descriptors:
            prefix_parts.extend(style.style_descriptors[:4])  # Top 4

        # Add signature techniques
        if style.signature_techniques:
            prefix_parts.extend(style.signature_techniques[:3])  # Top 3

        # Get adopted elements for technique vocabulary
        elements = list_adopted_elements(daemon_id, active_only=True)
        technique_elements = [e.element for e in elements if e.category == "technique" and e.adoption_strength >= 0.7][:3]

        # Build the house style negative (always painterly, not photographic)
        house_negative = "photograph, photorealistic, realistic photo, camera, lens, 3d render"

        return {
            "prefix": "oil painting, painterly, " + ", ".join(prefix_parts) if prefix_parts else None,
            "techniques": technique_elements,
            "negative": house_negative,
            "color_philosophy": style.color_philosophy,
            "light_approach": style.light_approach,
        }
    except Exception as e:
        logger.debug(f"Could not get house style: {e}")
        return None


def build_image_prompt(
    subject: str,
    style: str = "digital_art",
    mood: Optional[str] = None,
    additional_context: Optional[str] = None,
    daemon_id: Optional[str] = None,
    use_house_style: bool = True,
) -> tuple[str, str]:
    """
    Build an effective SDXL prompt from components.

    Args:
        subject: What to generate (the main content)
        style: Visual style from STYLE_PRESETS
        mood: Optional mood modifier from MOOD_MODIFIERS
        additional_context: Optional extra context to include
        daemon_id: Optional daemon ID to look up house style
        use_house_style: Whether to incorporate house style if available (default True)

    Returns:
        Tuple of (positive_prompt, negative_prompt)
    """
    parts = []

    # Check for house style
    house_style = None
    if use_house_style and daemon_id:
        house_style = get_house_style_modifiers(daemon_id)

    if house_style and house_style.get("prefix"):
        # Use house style as base
        parts.append(house_style["prefix"])

        # Add techniques
        if house_style.get("techniques"):
            parts.extend(house_style["techniques"])

        # Add color/light context if available
        if house_style.get("color_philosophy"):
            # Extract key terms from philosophy
            color_terms = house_style["color_philosophy"][:100]  # Keep it brief
            parts.append(color_terms)
    else:
        # Fall back to style preset
        preset = STYLE_PRESETS.get(style, STYLE_PRESETS["digital_art"])
        parts.append(preset["prefix"])

    # Main subject
    parts.append(subject)

    # Mood modifier
    if mood and mood in MOOD_MODIFIERS:
        parts.append(MOOD_MODIFIERS[mood])

    # Additional context
    if additional_context:
        parts.append(additional_context)

    # Build positive prompt
    positive = ", ".join(filter(None, parts))

    # Build negative prompt
    negative_parts = [DEFAULT_NEGATIVE]

    if house_style and house_style.get("negative"):
        # Use house style negative (anti-photographic)
        negative_parts.append(house_style["negative"])
    else:
        # Use style preset negative
        preset = STYLE_PRESETS.get(style, STYLE_PRESETS["digital_art"])
        if preset.get("negative"):
            negative_parts.append(preset["negative"])

    negative = ", ".join(negative_parts)

    return positive, negative


def get_generation_params(style: str = "digital_art") -> dict:
    """
    Get generation parameters for a style.

    Args:
        style: Visual style from STYLE_PRESETS

    Returns:
        Dict with steps, cfg, and other params
    """
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["digital_art"])
    return {
        "steps": preset.get("steps", 25),
        "cfg": preset.get("cfg", 7.0),
    }


def extract_dream_imagery(dream_content: str) -> str:
    """
    Extract visual imagery from dream text for image generation.

    This is a simple extraction - could be enhanced with LLM summarization.

    Args:
        dream_content: The text content of a dream

    Returns:
        A condensed prompt focusing on visual elements
    """
    # For now, take the first paragraph and clean it up
    # In the future, could use LLM to extract key visual elements
    paragraphs = dream_content.strip().split("\n\n")
    if paragraphs:
        first_para = paragraphs[0][:500]  # Limit length
        # Clean up for prompt use
        first_para = first_para.replace('"', '')
        first_para = first_para.replace('\n', ' ')
        return first_para
    return dream_content[:300]
