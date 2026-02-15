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

logger = logging.getLogger(__name__)


def _load_image_as_base64(image_path: str) -> Optional[str]:
    """Load an image file and return as base64."""
    path = Path(image_path)
    if not path.exists():
        logger.warning(f"Image not found: {image_path}")
        return None

    with open(path, "rb") as f:
        data = f.read()

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

    return f"data:{media_type};base64,{base64.b64encode(data).decode()}"


async def study_artist_background(
    artist_id: str,
    anthropic_client=None,
) -> Optional[str]:
    """
    Read Wikipedia article on artist for biographical context.

    Returns a summary that will inform artwork analysis.
    """
    artist = persistence.get_artist(artist_id)
    if not artist:
        logger.error(f"Artist not found: {artist_id}")
        return None

    if not artist.wikipedia_url:
        logger.warning(f"No Wikipedia URL for artist: {artist.name}")
        return None

    # Use WebFetch to read the article
    # For now, we'll use a simple approach - in production this would
    # use the actual WebFetch infrastructure
    try:
        import httpx
        from bs4 import BeautifulSoup

        async with httpx.AsyncClient() as client:
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
        if anthropic_client:
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

            response = await anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[{"role": "user", "content": summary_prompt}]
            )
            biography = response.content[0].text
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
        # Fetch it if we don't have it
        bio = await study_artist_background(artwork.artist_id, anthropic_client)
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

        # Parse the structured response
        study = _parse_analysis(analysis_text, artwork_id, daemon_id, bio_context)

        # Save the study
        persistence.save_study(study)

        # Mark artist as studied
        if artist:
            persistence.mark_artist_studied(artist.id)

        logger.info(f"Completed study of '{artwork.title}' by {artist_name}")
        return study

    except Exception as e:
        logger.error(f"Failed to analyze artwork: {e}")
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
        line_upper = line.strip().upper()

        # Check for section headers
        if "FIRST IMPRESSION" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "first_impression"
            current_content = []
        elif "COMPOSITION ANALYSIS" in line_upper or "COMPOSITION" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "composition"
            current_content = []
        elif "COLOR ANALYSIS" in line_upper or "COLOR" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "color"
            current_content = []
        elif "BRUSHWORK" in line_upper or "TECHNIQUE" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "brushwork"
            current_content = []
        elif "EMOTIONAL QUALITY" in line_upper or "EMOTIONAL" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "emotional"
            current_content = []
        elif "THEMATIC" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "thematic"
            current_content = []
        elif "BIOGRAPHICAL" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "biographical"
            current_content = []
        elif "KEY LEARNINGS" in line_upper or "KEY LEARNING" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "learnings"
            current_content = []
        elif "PROMPT VOCABULARY" in line_upper or "VOCABULARY" in line_upper:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "vocabulary"
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
