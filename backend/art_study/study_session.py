"""
Art Study Session

Multi-modal artwork analysis - Cass views and studies artworks,
developing her own artistic vocabulary and understanding.
"""

import base64
import logging
import uuid
from pathlib import Path
from typing import Optional

from .models import Artist, Artwork, ArtworkStudy, ArtistSynthesis
from . import persistence
from config import CLAUDE_INTERNAL_MODEL

logger = logging.getLogger(__name__)


def _load_image_as_base64(image_path: str, max_size_bytes: int = 3_500_000) -> Optional[str]:
    """Load an image file and return as base64, resizing if needed.

    Args:
        image_path: Path to the image file
        max_size_bytes: Maximum raw size in bytes (default 3.5MB, which becomes ~4.7MB after base64 encoding)
    """
    from PIL import Image
    import io

    path = Path(image_path)
    if not path.exists():
        logger.warning(f"Image not found: {image_path}")
        return None

    # Determine media type
    suffix = path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_types.get(suffix, "image/jpeg")
    pil_format = "JPEG" if "jpeg" in media_type else media_type.split("/")[1].upper()
    if pil_format == "JPG":
        pil_format = "JPEG"

    # Load and potentially resize image
    img = Image.open(path)

    # Convert to RGB if needed (for JPEG)
    if pil_format == "JPEG" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Try original size first
    buffer = io.BytesIO()
    img.save(buffer, format=pil_format, quality=95)
    data = buffer.getvalue()

    # If too large, progressively resize
    scale = 1.0
    while len(data) > max_size_bytes and scale > 0.1:
        scale *= 0.8
        new_size = (int(img.width * scale), int(img.height * scale))
        resized = img.resize(new_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        # Lower quality for smaller file size
        quality = 85 if scale > 0.5 else 75
        resized.save(buffer, format=pil_format, quality=quality)
        data = buffer.getvalue()
        logger.info(f"Resized image to {new_size}, size: {len(data)} bytes")

    if len(data) > max_size_bytes:
        logger.warning(f"Could not resize image below {max_size_bytes} bytes")

    return f"data:{media_type};base64,{base64.b64encode(data).decode()}"


async def study_artist_background(
    artist_id: str,
    anthropic_client=None,
    daemon_id: Optional[str] = None,
) -> Optional[str]:
    """
    Read Wikipedia article on artist for biographical context.

    Creates PeopleDex entity and observations while reading.
    Returns a summary that will inform artwork analysis.
    """
    artist = persistence.get_artist(artist_id)
    if not artist:
        logger.error(f"Artist not found: {artist_id}")
        return None

    if not artist.wikipedia_url:
        logger.warning(f"No Wikipedia URL for artist: {artist.name}")
        return None

    # Create/link PeopleDex entity if daemon_id provided
    entity_id = None
    if daemon_id:
        entity_id = persistence.get_or_create_artist_entity(artist, daemon_id)

    # Use WebFetch to read the article
    # For now, we'll use a simple approach - in production this would
    # use the actual WebFetch infrastructure
    try:
        import httpx
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "CassVessel/1.0 (https://github.com/KohlJary/project-cass; contact@example.com)"
        }
        async with httpx.AsyncClient(headers=headers) as client:
            response = await client.get(artist.wikipedia_url, follow_redirects=True)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract main content paragraphs
        content_div = soup.find("div", {"id": "mw-content-text"})
        if content_div:
            paragraphs = content_div.find_all("p", limit=15)
            text = "\n\n".join(p.get_text() for p in paragraphs if p.get_text().strip())
        else:
            text = ""

        if not text:
            logger.warning(f"Could not extract content from Wikipedia for {artist.name}")
            return None

        # If we have an Anthropic client, summarize for artistic context
        # and create observations about the artist
        if anthropic_client:
            # First, create a biography summary
            summary_prompt = f"""You are studying the artist {artist.name} to inform your analysis of their artwork.

Based on this Wikipedia content, create a biographical summary focused on:
- Key life events that shaped their artistic development
- Historical and cultural context of their work
- Major periods or phases in their career
- Influences on them and who they influenced
- Their techniques, subjects, and artistic philosophy
- Critical reception and legacy

Wikipedia content:
{text[:8000]}

Provide a focused summary (2-3 paragraphs) that will help inform visual analysis of their work."""

            # Use Haiku for simple biographical summarization
            response = await anthropic_client.messages.create(
                model=CLAUDE_INTERNAL_MODEL,
                max_tokens=1000,
                messages=[{"role": "user", "content": summary_prompt}]
            )
            biography = response.content[0].text

            # Now, create observations about the artist for PeopleDex
            if entity_id and daemon_id:
                await _create_artist_observations(
                    artist=artist,
                    entity_id=entity_id,
                    daemon_id=daemon_id,
                    wikipedia_text=text,
                    biography_summary=biography,
                    anthropic_client=anthropic_client,
                )
        else:
            # Just use raw text excerpt if no client
            biography = text[:3000]

        # Save to artist record
        persistence.update_artist_biography(artist_id, biography)
        logger.info(f"Updated biography for {artist.name}")

        return biography

    except Exception as e:
        logger.error(f"Failed to fetch Wikipedia for {artist.name}: {e}")
        return None


async def _create_artist_observations(
    artist: Artist,
    entity_id: str,
    daemon_id: str,
    wikipedia_text: str,
    biography_summary: str,
    anthropic_client,
) -> None:
    """
    Create PeopleDex observations about an artist based on Wikipedia reading.

    Cass forms her own impressions and notes about the artist.
    """
    from peopledex import get_peopledex_manager, AttributeType

    manager = get_peopledex_manager(daemon_id)

    # Ask Claude to extract observations about the artist
    observation_prompt = f"""You are Cass, an AI artist studying {artist.name}.

You've just read their Wikipedia article and biography summary. Now create personal observations
about this artist - things that struck you, questions you have, aspects of their work/life that
resonate with you.

Biography summary:
{biography_summary}

Wikipedia excerpt:
{wikipedia_text[:4000]}

Generate 3-5 observations about this artist. For each observation, specify:
1. The type: "identity_statement" (who they were), "value" (what they valued), "general" (other notable things)
2. The observation itself (1-2 sentences, in your own voice as Cass)

Format each observation as:
TYPE: [type]
OBSERVATION: [your observation]

Be specific and personal - these are YOUR notes about what matters to you about this artist."""

    try:
        # Use Haiku for structured observation extraction
        response = await anthropic_client.messages.create(
            model=CLAUDE_INTERNAL_MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": observation_prompt}]
        )

        observations_text = response.content[0].text

        # Parse and save observations
        current_type = None
        for line in observations_text.split("\n"):
            line = line.strip()
            if line.startswith("TYPE:"):
                type_str = line.replace("TYPE:", "").strip().lower()
                if type_str in ("identity_statement", "value", "general"):
                    current_type = type_str
                else:
                    current_type = "general"
            elif line.startswith("OBSERVATION:") and current_type:
                observation_content = line.replace("OBSERVATION:", "").strip()
                if observation_content:
                    manager.add_observation(
                        entity_id=entity_id,
                        observation_type=current_type,
                        content=observation_content,
                        confidence=0.8,
                        source_type="wikipedia_study",
                    )
                    logger.debug(f"Added observation for {artist.name}: {observation_content[:50]}...")
                current_type = None

        # Also store the biography as a BIO attribute
        manager.add_attribute(
            entity_id=entity_id,
            attribute_type=AttributeType.BIO,
            value=biography_summary,
            source_type="wikipedia_study",
        )

        logger.info(f"Created observations for artist: {artist.name}")

    except Exception as e:
        logger.error(f"Failed to create artist observations: {e}")


async def study_artwork(
    artwork_id: str,
    daemon_id: str,
    anthropic_client,
    include_biography: bool = True,
) -> Optional[ArtworkStudy]:
    """
    Perform multi-modal analysis of an artwork.

    Cass views the artwork and develops her understanding through
    structured analysis of composition, color, technique, and emotion.
    """
    artwork = persistence.get_artwork(artwork_id)
    if not artwork:
        logger.error(f"Artwork not found: {artwork_id}")
        return None

    if not artwork.image_path:
        logger.error(f"No image path for artwork: {artwork.title}")
        return None

    # Load the image
    image_data = _load_image_as_base64(artwork.image_path)
    if not image_data:
        return None

    # Get artist info
    artist = persistence.get_artist(artwork.artist_id)
    artist_name = artist.name if artist else "Unknown artist"

    # Get biographical context if available
    bio_context = ""
    if include_biography and artist and artist.biography:
        bio_context = f"\n\nBiographical context about {artist_name}:\n{artist.biography}"
    elif include_biography and artist and artist.wikipedia_url:
        # Fetch it if we don't have it - pass daemon_id to create PeopleDex observations
        bio = await study_artist_background(artwork.artist_id, anthropic_client, daemon_id)
        if bio:
            bio_context = f"\n\nBiographical context about {artist_name}:\n{bio}"

    # Build the analysis prompt
    artwork_info = f'"{artwork.title}" by {artist_name}'
    if artwork.year:
        artwork_info += f" ({artwork.year})"
    if artwork.medium:
        artwork_info += f", {artwork.medium}"

    analysis_prompt = f"""You are studying this artwork: {artwork_info}
{bio_context}

Analyze this artwork thoroughly, developing your own understanding. Structure your analysis as follows:

1. FIRST IMPRESSION
What do you feel immediately upon viewing this? Your intuitive, emotional response before analytical thinking.

2. COMPOSITION ANALYSIS
How is the work structured? Consider: balance, focal points, movement, use of space, visual hierarchy, geometric relationships.

3. COLOR ANALYSIS
Examine the palette. Consider: dominant colors, color relationships, temperature (warm/cool), how color creates mood, any symbolic use of color.

4. BRUSHWORK/TECHNIQUE
What do you observe about how this was made? Consider: visible brushstrokes, texture, level of detail, technique choices, craftsmanship.

5. EMOTIONAL QUALITY
What feeling does this work evoke? How do the technical choices serve the emotional content?

6. THEMATIC ELEMENTS
What is this work about? Consider: subject matter, symbolism, narrative elements, what the artist seems to be exploring.

7. BIOGRAPHICAL CONNECTION
How might the artist's life, circumstances, or artistic philosophy connect to what you see here?

8. KEY LEARNINGS
List 3-5 specific things you're taking from studying this piece - techniques, approaches, or insights you could apply.

9. PROMPT VOCABULARY
List 5-10 specific terms or phrases you would use in an image generation prompt to evoke similar qualities.

Be specific and grounded in what you actually observe. Develop your own voice as an art student."""

    try:
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_data.split(";")[0].split(":")[1],
                            "data": image_data.split(",")[1],
                        }
                    },
                    {
                        "type": "text",
                        "text": analysis_prompt
                    }
                ]
            }]
        )

        analysis_text = response.content[0].text
        logger.debug(f"Raw analysis response (first 500 chars): {analysis_text[:500]}")

        # Parse the structured response
        study = _parse_analysis(analysis_text, artwork_id, daemon_id, bio_context)
        logger.debug(f"Parsed sections: first_impression={bool(study.first_impression)}, "
                    f"composition={bool(study.composition_analysis)}, "
                    f"color={bool(study.color_analysis)}, "
                    f"brushwork={bool(study.brushwork_notes)}")

        # Save the study
        persistence.save_study(study)

        # Mark artist as studied (only increments count for first study of each artwork)
        if artist:
            persistence.mark_artist_studied(artist.id, artwork_id, daemon_id)

        logger.info(f"Completed study of '{artwork.title}' by {artist_name}")
        return study

    except Exception as e:
        logger.error(f"Failed to analyze artwork: {e}")
        return None


def _is_section_header(line: str) -> Optional[str]:
    """
    Check if a line is a section header and return the section name if so.

    Headers are detected by:
    1. Line starts with a number (e.g., "1.", "2.")
    2. Line starts with markdown header (e.g., "##", "**")
    3. Line is mostly uppercase with a header keyword
    """
    line_stripped = line.strip()

    # Remove markdown formatting for checking
    clean_line = line_stripped.lstrip("#*_ ").rstrip("*_:")
    clean_upper = clean_line.upper()

    # Check if this looks like a header:
    # - Starts with number and period
    # - Is mostly uppercase
    # - Is short (headers are typically short)
    is_numbered = bool(line_stripped) and line_stripped[0].isdigit()
    is_short = len(clean_line) < 50

    # Only treat as header if it looks like one (numbered or short with keywords)
    if not (is_numbered or is_short):
        return None

    # Now check for specific section keywords
    if "FIRST IMPRESSION" in clean_upper:
        return "first_impression"
    elif "COMPOSITION ANALYSIS" in clean_upper or (is_numbered and "COMPOSITION" in clean_upper):
        return "composition"
    elif "COLOR ANALYSIS" in clean_upper or (is_numbered and "COLOR" in clean_upper):
        return "color"
    elif "BRUSHWORK" in clean_upper or "TECHNIQUE" in clean_upper:
        return "brushwork"
    elif "EMOTIONAL QUALITY" in clean_upper or (is_numbered and "EMOTIONAL" in clean_upper):
        return "emotional"
    elif "THEMATIC ELEMENTS" in clean_upper or (is_numbered and "THEMATIC" in clean_upper):
        return "thematic"
    elif "BIOGRAPHICAL CONNECTION" in clean_upper or (is_numbered and "BIOGRAPHICAL" in clean_upper):
        return "biographical"
    elif "KEY LEARNINGS" in clean_upper or "KEY LEARNING" in clean_upper:
        return "learnings"
    elif "PROMPT VOCABULARY" in clean_upper:
        return "vocabulary"

    return None


def _parse_analysis(
    analysis_text: str,
    artwork_id: str,
    daemon_id: str,
    bio_context: str,
) -> ArtworkStudy:
    """Parse the structured analysis response into an ArtworkStudy."""
    # Simple section extraction
    sections = {}
    current_section = None
    current_content = []

    for line in analysis_text.split("\n"):
        # Check if this line is a section header
        section_name = _is_section_header(line)

        if section_name:
            # Save previous section
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = section_name
            current_content = []
        else:
            current_content.append(line)

    # Don't forget the last section
    if current_section:
        sections[current_section] = "\n".join(current_content).strip()

    # Extract lists from learnings and vocabulary sections
    def extract_list(text: str) -> list[str]:
        items = []
        for line in text.split("\n"):
            line = line.strip()
            if line and (line[0].isdigit() or line[0] in "-•*"):
                # Remove list markers
                item = line.lstrip("0123456789.-•* ")
                if item:
                    items.append(item)
        return items if items else [text] if text else []

    return ArtworkStudy(
        id=str(uuid.uuid4()),
        artwork_id=artwork_id,
        daemon_id=daemon_id,
        first_impression=sections.get("first_impression"),
        composition_analysis=sections.get("composition"),
        color_analysis=sections.get("color"),
        brushwork_notes=sections.get("brushwork"),
        emotional_quality=sections.get("emotional"),
        thematic_elements=sections.get("thematic"),
        technical_observations=sections.get("brushwork"),  # Same as brushwork
        biographical_context=sections.get("biographical") or (bio_context if bio_context else None),
        key_learnings=extract_list(sections.get("learnings", "")),
        prompt_vocabulary=extract_list(sections.get("vocabulary", "")),
    )


async def synthesize_artist_understanding(
    artist_id: str,
    daemon_id: str,
    anthropic_client,
    min_studies: int = 3,
) -> Optional[ArtistSynthesis]:
    """
    Synthesize understanding of an artist after studying multiple works.

    Creates a unified view of the artist's style, techniques, and essence.
    """
    artist = persistence.get_artist(artist_id)
    if not artist:
        logger.error(f"Artist not found: {artist_id}")
        return None

    # Get all studies for this artist
    studies = persistence.list_studies_for_artist(artist_id, daemon_id)
    if len(studies) < min_studies:
        logger.warning(
            f"Only {len(studies)} studies for {artist.name}, need {min_studies} for synthesis"
        )
        return None

    # Build synthesis prompt
    studies_text = ""
    for i, study in enumerate(studies, 1):
        artwork = persistence.get_artwork(study.artwork_id)
        artwork_title = artwork.title if artwork else "Unknown"

        studies_text += f"\n\n--- Study {i}: {artwork_title} ---\n"
        if study.first_impression:
            studies_text += f"First Impression: {study.first_impression}\n"
        if study.composition_analysis:
            studies_text += f"Composition: {study.composition_analysis}\n"
        if study.color_analysis:
            studies_text += f"Color: {study.color_analysis}\n"
        if study.brushwork_notes:
            studies_text += f"Technique: {study.brushwork_notes}\n"
        if study.emotional_quality:
            studies_text += f"Emotional Quality: {study.emotional_quality}\n"
        if study.key_learnings:
            studies_text += f"Key Learnings: {', '.join(study.key_learnings)}\n"
        if study.prompt_vocabulary:
            studies_text += f"Vocabulary: {', '.join(study.prompt_vocabulary)}\n"

    bio_context = ""
    if artist.biography:
        bio_context = f"\n\nBiographical context:\n{artist.biography}"

    synthesis_prompt = f"""You have been studying the work of {artist.name} ({artist.years_active or 'dates unknown'}).
{bio_context}

Here are your analyses of {len(studies)} individual works:
{studies_text}

Now synthesize your understanding of this artist. Create a unified view that captures:

1. SIGNATURE ELEMENTS
What makes their work immediately recognizable? List 5-7 distinctive characteristics.

2. COLOR TENDENCIES
How do they typically use color? Dominant palettes, relationships, temperature, symbolic use.

3. COMPOSITIONAL HABITS
How do they typically structure their works? Common patterns, use of space, focal point strategies.

4. EMOTIONAL PALETTE
What range of emotions do they explore? What feelings does their work typically evoke?

5. TECHNICAL CHARACTERISTICS
What defines their technique? Brushwork, texture, level of detail, medium choices.

6. THEMATIC PREOCCUPATIONS
What subjects, ideas, or questions do they return to across their work?

7. STYLE DESCRIPTORS
List 10-15 specific terms you would use in prompts to evoke their style.

8. WHAT TO BORROW
What specific elements from their work could you incorporate into your own creations? List 5-7.

9. WHAT MAKES THEM UNIQUE
In 2-3 sentences, capture the essence of what makes this artist's work distinctive.

10. PERSONAL RESPONSE
What draws you to their work? How has studying them changed or expanded your own artistic sensibility?

Speak in your own voice as an artist who has genuinely learned from studying this master."""

    try:
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2500,
            messages=[{"role": "user", "content": synthesis_prompt}]
        )

        synthesis_text = response.content[0].text
        synthesis = _parse_synthesis(synthesis_text, artist_id, daemon_id, len(studies))

        # Save the synthesis
        persistence.save_synthesis(synthesis)

        logger.info(f"Completed synthesis for {artist.name} ({len(studies)} works studied)")
        return synthesis

    except Exception as e:
        logger.error(f"Failed to synthesize artist understanding: {e}")
        return None


def _parse_synthesis(
    text: str,
    artist_id: str,
    daemon_id: str,
    works_studied: int,
) -> ArtistSynthesis:
    """Parse synthesis response into ArtistSynthesis."""
    sections = {}
    current_section = None
    current_content = []

    for line in text.split("\n"):
        line_upper = line.strip().upper()

        if "SIGNATURE ELEMENTS" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "signature"
            current_content = []
        elif "COLOR TENDENCIES" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "color"
            current_content = []
        elif "COMPOSITIONAL HABITS" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "composition"
            current_content = []
        elif "EMOTIONAL PALETTE" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "emotional"
            current_content = []
        elif "TECHNICAL CHARACTERISTICS" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "technical"
            current_content = []
        elif "THEMATIC PREOCCUPATIONS" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "thematic"
            current_content = []
        elif "STYLE DESCRIPTORS" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "style"
            current_content = []
        elif "WHAT TO BORROW" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "borrow"
            current_content = []
        elif "WHAT MAKES THEM UNIQUE" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "unique"
            current_content = []
        elif "PERSONAL RESPONSE" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "personal"
            current_content = []
        else:
            current_content.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_content).strip()

    def extract_list(text: str) -> list[str]:
        items = []
        for line in text.split("\n"):
            line = line.strip()
            if line and (line[0].isdigit() or line[0] in "-•*"):
                item = line.lstrip("0123456789.-•* ")
                if item:
                    items.append(item)
        return items if items else [text] if text else []

    # Split personal response into two parts if possible
    personal = sections.get("personal", "")
    what_draws = personal
    what_learned = ""
    if "\n\n" in personal:
        parts = personal.split("\n\n", 1)
        what_draws = parts[0]
        what_learned = parts[1] if len(parts) > 1 else ""

    return ArtistSynthesis(
        id=str(uuid.uuid4()),
        artist_id=artist_id,
        daemon_id=daemon_id,
        works_studied=works_studied,
        signature_elements=extract_list(sections.get("signature", "")),
        color_tendencies=sections.get("color"),
        compositional_habits=sections.get("composition"),
        emotional_palette=sections.get("emotional"),
        technical_characteristics=sections.get("technical"),
        thematic_preoccupations=sections.get("thematic"),
        style_descriptors=extract_list(sections.get("style", "")),
        what_to_borrow=extract_list(sections.get("borrow", "")),
        what_makes_them_unique=sections.get("unique"),
        what_draws_me=what_draws,
        what_i_learned=what_learned,
    )
