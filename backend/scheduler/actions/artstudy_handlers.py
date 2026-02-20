"""
Art Study Action Handlers - Autonomous art study capabilities.

Enables Cass to autonomously:
- Discover and select artists to study
- Study artist backgrounds and artworks
- Synthesize understanding of artists
- Extract adopted elements for her house style
- Synthesize her personal house style
- Create artwork from artist synthesis or house style
"""

import logging
import random
from typing import Any, Dict, List, Optional

from . import ActionResult

logger = logging.getLogger(__name__)


async def discover_artist_action(context: Dict[str, Any]) -> ActionResult:
    """
    Discover a new artist to study from the curated list.

    Selects an artist that hasn't been studied yet, or with the fewest studies.
    Context can include:
    - category: Optional category preference (light, drama, color, etc.)
    - movement: Optional art movement preference
    """
    from art_study.curated_artists import CURATED_ARTISTS
    from art_study import list_artists, save_artist
    from art_study.models import Artist

    category = context.get("category")
    movement = context.get("movement")

    # Get already studied artists
    studied = list_artists()
    studied_names = {a.name.lower() for a in studied}

    # Filter curated artists to unstudied ones
    candidates = [
        ca for ca in CURATED_ARTISTS
        if ca.name.lower() not in studied_names
    ]

    # Apply filters if specified
    if movement:
        filtered = [ca for ca in candidates if movement.lower() in ca.movement.lower()]
        if filtered:
            candidates = filtered

    if not candidates:
        # All studied - pick one with fewest works studied
        if studied:
            artist = min(studied, key=lambda a: a.works_studied)
            return ActionResult(
                success=True,
                message=f"All curated artists studied. Revisiting {artist.name} ({artist.works_studied} works studied)",
                data={"artist_id": artist.id, "artist_name": artist.name, "revisit": True}
            )
        else:
            return ActionResult(
                success=False,
                message="No curated artists available"
            )

    # Select randomly from candidates
    selected = random.choice(candidates)

    # Create artist record
    from uuid import uuid4
    artist = Artist(
        id=str(uuid4()),
        name=selected.name,
        period=selected.movement,
        years_active=f"{selected.birth_year}-{selected.death_year}" if selected.birth_year else None,
        movements=[selected.movement],
        wikipedia_url=selected.wikipedia_url,
        public_domain=True,
    )
    save_artist(artist)

    logger.info(f"Discovered artist to study: {artist.name}")

    return ActionResult(
        success=True,
        message=f"Discovered {artist.name} ({selected.movement}) for study: {selected.why_study}",
        data={
            "artist_id": artist.id,
            "artist_name": artist.name,
            "movement": selected.movement,
            "why_study": selected.why_study,
            "techniques": selected.techniques,
        }
    )


async def study_artist_background_action(context: Dict[str, Any]) -> ActionResult:
    """
    Study an artist's background via Wikipedia.

    Context should include:
    - artist_id: ID of artist to study (required)
    """
    from art_study import study_artist_background

    artist_id = context.get("artist_id")
    if not artist_id:
        return ActionResult(
            success=False,
            message="artist_id is required"
        )

    managers = context.get("managers", {})
    daemon_id = managers.get("daemon_id", "cass")

    # Get anthropic client
    try:
        import anthropic
        client = anthropic.Anthropic()
    except Exception as e:
        return ActionResult(success=False, message=f"Could not create Anthropic client: {e}")

    try:
        summary = await study_artist_background(
            artist_id=artist_id,
            anthropic_client=client,
            daemon_id=daemon_id,
        )

        if summary:
            return ActionResult(
                success=True,
                message=f"Studied artist background",
                cost_usd=0.05,  # Estimate for Wikipedia fetch + summary
                data={"artist_id": artist_id, "summary_length": len(summary)}
            )
        else:
            return ActionResult(
                success=False,
                message="Could not study artist background"
            )
    except Exception as e:
        logger.error(f"Error studying artist background: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Error: {e}")


async def study_artwork_action(context: Dict[str, Any]) -> ActionResult:
    """
    Study a specific artwork or fetch and study new works.

    Context should include:
    - artist_id: ID of artist (required)
    - artwork_id: Optional specific artwork to study
    - fetch_count: Number of artworks to fetch from Met API if no artwork_id (default 3)
    """
    from art_study import study_artwork, get_artist, list_artworks_for_artist
    from art_study.wikiart import fetch_artworks_from_met

    artist_id = context.get("artist_id")
    artwork_id = context.get("artwork_id")
    fetch_count = context.get("fetch_count", 3)

    if not artist_id:
        return ActionResult(success=False, message="artist_id is required")

    managers = context.get("managers", {})
    daemon_id = managers.get("daemon_id", "cass")

    # Get anthropic client
    try:
        import anthropic
        client = anthropic.Anthropic()
    except Exception as e:
        return ActionResult(success=False, message=f"Could not create Anthropic client: {e}")

    artist = get_artist(artist_id)
    if not artist:
        return ActionResult(success=False, message=f"Artist {artist_id} not found")

    try:
        studies_created = []

        if artwork_id:
            # Study specific artwork
            study = await study_artwork(
                artwork_id=artwork_id,
                anthropic_client=client,
                daemon_id=daemon_id,
            )
            if study:
                studies_created.append(study.id)
        else:
            # Fetch new artworks from Met
            existing = list_artworks_for_artist(artist_id)
            existing_titles = {a.title.lower() for a in existing}

            # Fetch artworks
            new_artworks = await fetch_artworks_from_met(artist.name, limit=fetch_count)

            # Filter to unstudied
            to_study = [
                aw for aw in new_artworks
                if aw.title.lower() not in existing_titles
            ][:fetch_count]

            for artwork in to_study:
                study = await study_artwork(
                    artwork_id=artwork.id,
                    anthropic_client=client,
                    daemon_id=daemon_id,
                )
                if study:
                    studies_created.append(study.id)

        if studies_created:
            return ActionResult(
                success=True,
                message=f"Created {len(studies_created)} artwork studies for {artist.name}",
                cost_usd=0.10 * len(studies_created),  # Vision API cost estimate
                data={
                    "artist_id": artist_id,
                    "artist_name": artist.name,
                    "studies_created": studies_created,
                }
            )
        else:
            return ActionResult(
                success=True,
                message=f"No new artworks to study for {artist.name}",
                data={"artist_id": artist_id, "studies_created": []}
            )

    except Exception as e:
        logger.error(f"Error studying artwork: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Error: {e}")


async def synthesize_artist_action(context: Dict[str, Any]) -> ActionResult:
    """
    Synthesize overall understanding of an artist after studying their works.

    Context should include:
    - artist_id: ID of artist to synthesize (required)
    """
    from art_study import synthesize_artist_understanding, get_artist, list_studies_for_artist

    artist_id = context.get("artist_id")
    if not artist_id:
        return ActionResult(success=False, message="artist_id is required")

    managers = context.get("managers", {})
    daemon_id = managers.get("daemon_id", "cass")

    # Get anthropic client
    try:
        import anthropic
        client = anthropic.Anthropic()
    except Exception as e:
        return ActionResult(success=False, message=f"Could not create Anthropic client: {e}")

    artist = get_artist(artist_id)
    if not artist:
        return ActionResult(success=False, message=f"Artist {artist_id} not found")

    # Check we have enough studies
    studies = list_studies_for_artist(artist_id)
    if len(studies) < 2:
        return ActionResult(
            success=False,
            message=f"Need at least 2 artwork studies to synthesize. Have {len(studies)}."
        )

    try:
        synthesis = await synthesize_artist_understanding(
            artist_id=artist_id,
            anthropic_client=client,
            daemon_id=daemon_id,
        )

        if synthesis:
            return ActionResult(
                success=True,
                message=f"Synthesized understanding of {artist.name}",
                cost_usd=0.10,
                data={
                    "artist_id": artist_id,
                    "artist_name": artist.name,
                    "synthesis_id": synthesis.id,
                    "works_studied": synthesis.works_studied,
                    "signature_elements": synthesis.signature_elements[:5],
                }
            )
        else:
            return ActionResult(
                success=False,
                message="Could not synthesize artist understanding"
            )
    except Exception as e:
        logger.error(f"Error synthesizing artist: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Error: {e}")


async def extract_elements_action(context: Dict[str, Any]) -> ActionResult:
    """
    Extract adopted elements from an artist synthesis.

    Context should include:
    - artist_id: ID of artist to extract elements from (required)
    """
    from art_study import extract_adopted_elements, get_synthesis

    artist_id = context.get("artist_id")
    if not artist_id:
        return ActionResult(success=False, message="artist_id is required")

    managers = context.get("managers", {})
    daemon_id = managers.get("daemon_id", "cass")

    # Get anthropic client
    try:
        import anthropic
        client = anthropic.Anthropic()
    except Exception as e:
        return ActionResult(success=False, message=f"Could not create Anthropic client: {e}")

    # Check synthesis exists
    synthesis = get_synthesis(artist_id, daemon_id)
    if not synthesis:
        return ActionResult(
            success=False,
            message=f"No synthesis found for artist {artist_id}. Run synthesize first."
        )

    try:
        elements = await extract_adopted_elements(
            artist_id=artist_id,
            daemon_id=daemon_id,
            anthropic_client=client,
        )

        if elements:
            return ActionResult(
                success=True,
                message=f"Extracted {len(elements)} elements to adopt",
                cost_usd=0.05,
                data={
                    "artist_id": artist_id,
                    "elements": [
                        {"element": e.element, "category": e.category, "strength": e.adoption_strength}
                        for e in elements
                    ]
                }
            )
        else:
            return ActionResult(
                success=True,
                message="No elements resonated strongly enough to adopt",
                data={"artist_id": artist_id, "elements": []}
            )
    except Exception as e:
        logger.error(f"Error extracting elements: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Error: {e}")


async def synthesize_house_style_action(context: Dict[str, Any]) -> ActionResult:
    """
    Synthesize Cass's personal house style from all adopted elements.
    """
    from art_study import synthesize_house_style, list_adopted_elements, get_personal_style

    managers = context.get("managers", {})
    daemon_id = managers.get("daemon_id", "cass")

    # Get anthropic client
    try:
        import anthropic
        client = anthropic.Anthropic()
    except Exception as e:
        return ActionResult(success=False, message=f"Could not create Anthropic client: {e}")

    # Check we have adopted elements
    elements = list_adopted_elements(daemon_id, active_only=True)
    if len(elements) < 3:
        return ActionResult(
            success=False,
            message=f"Need at least 3 adopted elements to synthesize house style. Have {len(elements)}."
        )

    # Get current style version
    current_style = get_personal_style(daemon_id)
    current_version = current_style.version if current_style else 0

    try:
        style = await synthesize_house_style(
            daemon_id=daemon_id,
            anthropic_client=client,
        )

        if style:
            return ActionResult(
                success=True,
                message=f"Synthesized house style v{style.version}",
                cost_usd=0.15,
                data={
                    "style_id": style.id,
                    "version": style.version,
                    "previous_version": current_version,
                    "artists_studied": style.artists_studied,
                    "elements_adopted": style.elements_adopted,
                    "style_descriptors": style.style_descriptors[:5],
                }
            )
        else:
            return ActionResult(
                success=False,
                message="Could not synthesize house style"
            )
    except Exception as e:
        logger.error(f"Error synthesizing house style: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Error: {e}")


async def create_from_artist_action(context: Dict[str, Any]) -> ActionResult:
    """
    Create artwork inspired by a specific studied artist.

    Context should include:
    - artist_id: ID of artist to draw inspiration from (required)
    - inner_context: Optional custom context (uses live inner state if not provided)
    """
    from art_study import create_from_synthesis, get_synthesis, get_artist

    artist_id = context.get("artist_id")
    if not artist_id:
        return ActionResult(success=False, message="artist_id is required")

    managers = context.get("managers", {})
    daemon_id = managers.get("daemon_id", "cass")

    artist = get_artist(artist_id)
    if not artist:
        return ActionResult(success=False, message=f"Artist {artist_id} not found")

    # Check synthesis exists
    synthesis = get_synthesis(artist_id, daemon_id)
    if not synthesis:
        return ActionResult(
            success=False,
            message=f"No synthesis for {artist.name}. Run synthesize first."
        )

    inner_context = context.get("inner_context")

    try:
        process = await create_from_synthesis(
            synthesis=synthesis,
            daemon_id=daemon_id,
            inner_context=inner_context,
        )

        if process:
            return ActionResult(
                success=True,
                message=f"Created artwork inspired by {artist.name}",
                cost_usd=0.0,  # Local generation
                data={
                    "process_id": process.id,
                    "image_id": process.image_id,
                    "artist_name": artist.name,
                    "title": process.title,
                }
            )
        else:
            return ActionResult(
                success=False,
                message="Could not create artwork"
            )
    except Exception as e:
        logger.error(f"Error creating from artist: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Error: {e}")


async def create_from_house_style_action(context: Dict[str, Any]) -> ActionResult:
    """
    Create artwork in Cass's personal house style.

    Context can include:
    - inner_context: Optional custom context (uses live inner state if not provided)
    """
    from art_study import create_from_house_style, get_personal_style

    managers = context.get("managers", {})
    daemon_id = managers.get("daemon_id", "cass")

    # Check we have a house style
    style = get_personal_style(daemon_id)
    if not style:
        return ActionResult(
            success=False,
            message="No house style synthesized yet. Study artists and synthesize first."
        )

    inner_context = context.get("inner_context")

    try:
        process = await create_from_house_style(
            daemon_id=daemon_id,
            inner_context=inner_context,
        )

        if process:
            return ActionResult(
                success=True,
                message=f"Created artwork in house style v{style.version}",
                cost_usd=0.0,  # Local generation
                data={
                    "process_id": process.id,
                    "image_id": process.image_id,
                    "style_version": style.version,
                    "title": process.title,
                }
            )
        else:
            return ActionResult(
                success=False,
                message="Could not create artwork"
            )
    except Exception as e:
        logger.error(f"Error creating from house style: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Error: {e}")


async def full_study_session_action(context: Dict[str, Any]) -> ActionResult:
    """
    Run a complete art study session - discover artist, study, synthesize, extract.

    This is a composite action that chains together:
    1. Discover a new artist (or pick one to revisit)
    2. Study their background
    3. Study 3-5 artworks
    4. Synthesize understanding
    5. Extract adopted elements

    Context can include:
    - artist_id: Optional specific artist to study
    - artwork_count: Number of artworks to study (default 3)
    """
    artist_id = context.get("artist_id")
    artwork_count = context.get("artwork_count", 3)

    results = {"steps": []}
    total_cost = 0.0

    # Step 1: Discover or use provided artist
    if not artist_id:
        discover_result = await discover_artist_action(context)
        results["steps"].append({"discover": discover_result.message})
        if not discover_result.success:
            return ActionResult(
                success=False,
                message=f"Discovery failed: {discover_result.message}",
                data=results
            )
        artist_id = discover_result.data.get("artist_id")
        total_cost += discover_result.cost_usd or 0

    # Update context with artist_id
    context["artist_id"] = artist_id

    # Step 2: Study background
    background_result = await study_artist_background_action(context)
    results["steps"].append({"background": background_result.message})
    total_cost += background_result.cost_usd or 0
    # Continue even if background fails (Wikipedia might be unavailable)

    # Step 3: Study artworks
    context["fetch_count"] = artwork_count
    artwork_result = await study_artwork_action(context)
    results["steps"].append({"artworks": artwork_result.message})
    if not artwork_result.success:
        return ActionResult(
            success=False,
            message=f"Artwork study failed: {artwork_result.message}",
            data=results
        )
    total_cost += artwork_result.cost_usd or 0

    studies_created = artwork_result.data.get("studies_created", [])
    if len(studies_created) < 2:
        return ActionResult(
            success=True,
            message="Not enough artworks studied to synthesize. Will try again later.",
            cost_usd=total_cost,
            data=results
        )

    # Step 4: Synthesize understanding
    synthesis_result = await synthesize_artist_action(context)
    results["steps"].append({"synthesis": synthesis_result.message})
    if not synthesis_result.success:
        return ActionResult(
            success=False,
            message=f"Synthesis failed: {synthesis_result.message}",
            cost_usd=total_cost,
            data=results
        )
    total_cost += synthesis_result.cost_usd or 0

    # Step 5: Extract elements
    elements_result = await extract_elements_action(context)
    results["steps"].append({"elements": elements_result.message})
    total_cost += elements_result.cost_usd or 0

    # Compile final result
    from art_study import get_artist
    artist = get_artist(artist_id)
    artist_name = artist.name if artist else artist_id

    elements = elements_result.data.get("elements", []) if elements_result.success else []

    return ActionResult(
        success=True,
        message=f"Completed art study session for {artist_name}: {len(studies_created)} works, {len(elements)} elements adopted",
        cost_usd=total_cost,
        data={
            "artist_id": artist_id,
            "artist_name": artist_name,
            "works_studied": len(studies_created),
            "elements_adopted": len(elements),
            "steps": results["steps"],
        }
    )


async def get_study_status_action(context: Dict[str, Any]) -> ActionResult:
    """
    Get current art study status - counts of artists, studies, elements, etc.

    Returns data useful for spell conditions:
    - unstudied_artists: Count of curated artists not yet studied
    - artists_needing_synthesis: Artists with studies but no synthesis
    - artists_needing_elements: Artists with synthesis but no extracted elements
    - total_adopted_elements: Count of adopted elements
    - has_house_style: Whether house style has been synthesized
    - next_artist_id/name: ID and name of next artist to work on (if any)
    - next_work_type: What type of work is needed (more_studies, synthesis, elements, new_artist)
    """
    from art_study.curated_artists import CURATED_ARTISTS
    from art_study import (
        list_artists,
        list_studies_for_artist,
        get_synthesis,
        list_adopted_elements,
        get_personal_style,
    )

    managers = context.get("managers", {})
    daemon_id = managers.get("daemon_id", "cass")

    try:
        # Get all studied artists
        studied_artists = list_artists()
        studied_names = {a.name.lower() for a in studied_artists}

        # Count unstudied artists from curated list
        unstudied = [ca for ca in CURATED_ARTISTS if ca.name.lower() not in studied_names]

        # Check which artists need more work
        artists_needing_synthesis = []
        artists_needing_elements = []
        artists_needing_more_studies = []

        for artist in studied_artists:
            studies = list_studies_for_artist(artist.id)
            synthesis = get_synthesis(artist.id, daemon_id)
            elements = list_adopted_elements(daemon_id, artist_id=artist.id, active_only=True)

            if len(studies) < 3:
                artists_needing_more_studies.append({
                    "id": artist.id,
                    "name": artist.name,
                    "study_count": len(studies),
                })
            elif not synthesis:
                artists_needing_synthesis.append({
                    "id": artist.id,
                    "name": artist.name,
                    "study_count": len(studies),
                })
            elif not elements:
                artists_needing_elements.append({
                    "id": artist.id,
                    "name": artist.name,
                })

        # Get house style status
        all_elements = list_adopted_elements(daemon_id, active_only=True)
        house_style = get_personal_style(daemon_id)

        # Determine next work item (flat values for spell access)
        next_artist_id = None
        next_artist_name = None
        next_work_type = None

        if artists_needing_more_studies:
            next_artist_id = artists_needing_more_studies[0]["id"]
            next_artist_name = artists_needing_more_studies[0]["name"]
            next_work_type = "more_studies"
        elif artists_needing_synthesis:
            next_artist_id = artists_needing_synthesis[0]["id"]
            next_artist_name = artists_needing_synthesis[0]["name"]
            next_work_type = "synthesis"
        elif artists_needing_elements:
            next_artist_id = artists_needing_elements[0]["id"]
            next_artist_name = artists_needing_elements[0]["name"]
            next_work_type = "elements"
        elif unstudied:
            next_work_type = "new_artist"

        return ActionResult(
            success=True,
            message="Art study status retrieved",
            data={
                "unstudied_artists": len(unstudied),
                "artists_needing_more_studies": len(artists_needing_more_studies),
                "artists_needing_synthesis": len(artists_needing_synthesis),
                "artists_needing_elements": len(artists_needing_elements),
                "total_adopted_elements": len(all_elements),
                "has_house_style": house_style is not None,
                "house_style_version": house_style.version if house_style else 0,
                # Flat values for spell access (no array indexing needed)
                "next_artist_id": next_artist_id,
                "next_artist_name": next_artist_name,
                "next_work_type": next_work_type,
            }
        )

    except Exception as e:
        logger.error(f"Error getting study status: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Error: {e}")


async def batch_study_artworks_action(context: Dict[str, Any]) -> ActionResult:
    """
    Study multiple artworks for an artist in one batch.

    Context should include:
    - artist_id: ID of artist (required)
    - batch_size: Number of artworks to study (default 3, max 5)
    """
    artist_id = context.get("artist_id")
    batch_size = min(context.get("batch_size", 3), 5)

    if not artist_id:
        return ActionResult(success=False, message="artist_id is required")

    managers = context.get("managers", {})
    daemon_id = managers.get("daemon_id", "cass")

    from art_study import (
        get_artist,
        list_artworks_for_artist,
        list_studies_for_artist,
        study_artwork,
    )
    from art_study.wikiart import fetch_artworks_from_met

    artist = get_artist(artist_id)
    if not artist:
        return ActionResult(success=False, message=f"Artist {artist_id} not found")

    # Get anthropic client
    try:
        import anthropic
        client = anthropic.Anthropic()
    except Exception as e:
        return ActionResult(success=False, message=f"Could not create Anthropic client: {e}")

    try:
        # Get existing artworks and studies
        existing_artworks = list_artworks_for_artist(artist_id)
        existing_studies = list_studies_for_artist(artist_id)
        studied_artwork_ids = {s.artwork_id for s in existing_studies}

        # Find unstudied existing artworks
        unstudied = [aw for aw in existing_artworks if aw.id not in studied_artwork_ids]

        # If not enough, fetch more from Met
        if len(unstudied) < batch_size:
            needed = batch_size - len(unstudied)
            existing_titles = {a.title.lower() for a in existing_artworks}

            new_artworks = await fetch_artworks_from_met(artist.name, limit=needed + 2)
            for aw in new_artworks:
                if aw.title.lower() not in existing_titles and len(unstudied) < batch_size:
                    unstudied.append(aw)
                    existing_titles.add(aw.title.lower())

        # Study the batch
        studies_created = []
        total_cost = 0.0

        for artwork in unstudied[:batch_size]:
            try:
                study = await study_artwork(
                    artwork_id=artwork.id,
                    anthropic_client=client,
                    daemon_id=daemon_id,
                )
                if study:
                    studies_created.append({
                        "id": study.id,
                        "artwork_title": artwork.title,
                    })
                    total_cost += 0.10  # Vision API cost estimate
            except Exception as e:
                logger.warning(f"Failed to study artwork {artwork.title}: {e}")

        return ActionResult(
            success=True,
            message=f"Studied {len(studies_created)} artworks for {artist.name}",
            cost_usd=total_cost,
            data={
                "artist_id": artist_id,
                "artist_name": artist.name,
                "studies_created": studies_created,
                "batch_size": batch_size,
            }
        )

    except Exception as e:
        logger.error(f"Error in batch study: {e}", exc_info=True)
        return ActionResult(success=False, message=f"Error: {e}")
