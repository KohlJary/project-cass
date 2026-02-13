"""
Prompt Builder for Image Generation

Builds effective prompts for SDXL based on style and content.
"""

from typing import Optional

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


def build_image_prompt(
    subject: str,
    style: str = "digital_art",
    mood: Optional[str] = None,
    additional_context: Optional[str] = None,
) -> tuple[str, str]:
    """
    Build an effective SDXL prompt from components.

    Args:
        subject: What to generate (the main content)
        style: Visual style from STYLE_PRESETS
        mood: Optional mood modifier from MOOD_MODIFIERS
        additional_context: Optional extra context to include

    Returns:
        Tuple of (positive_prompt, negative_prompt)
    """
    parts = []

    # Get style preset
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["digital_art"])

    # Style prefix
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
