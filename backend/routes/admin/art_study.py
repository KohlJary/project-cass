"""
Art Study Admin API

Endpoints for managing and viewing Cass's art studies.
"""

import os
import uuid
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from art_study import persistence
from art_study.models import Artist, Artwork
from art_study.study_session import study_artwork, study_artist_background, synthesize_artist_understanding
from art_study.creative_session import create_from_synthesis
from art_study.wikiart import import_artist_from_provider, get_provider_url_for_artist, list_providers

router = APIRouter(prefix="/art-study", tags=["art-study"])

# Module-level reference to anthropic client (set by init)
_anthropic_client = None
_daemon_id: Optional[str] = None


def init_art_study_routes(anthropic_client, daemon_id: str) -> None:
    """Initialize the art study routes with required dependencies."""
    global _anthropic_client, _daemon_id
    _anthropic_client = anthropic_client
    _daemon_id = daemon_id


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class CreateArtistRequest(BaseModel):
    name: str
    period: Optional[str] = None
    years_active: Optional[str] = None
    movements: list[str] = []
    wikipedia_url: Optional[str] = None
    public_domain: bool = True


class CreateArtworkRequest(BaseModel):
    artist_id: str
    title: str
    year: Optional[int] = None
    medium: Optional[str] = None
    image_url: Optional[str] = None
    dimensions: Optional[str] = None
    location: Optional[str] = None
    public_domain: bool = True


class ArtistResponse(BaseModel):
    id: str
    name: str
    period: Optional[str]
    years_active: Optional[str]
    movements: list[str]
    wikipedia_url: Optional[str]
    biography: Optional[str]
    public_domain: bool
    entity_id: Optional[str]  # PeopleDex entity link
    studied_at: Optional[str]
    works_studied: int
    cass_notes: Optional[str]


class ArtworkResponse(BaseModel):
    id: str
    artist_id: str
    title: str
    year: Optional[int]
    medium: Optional[str]
    image_path: Optional[str]
    image_url: Optional[str]
    dimensions: Optional[str]
    location: Optional[str]
    public_domain: bool
    has_study: bool = False


class StudyResponse(BaseModel):
    id: str
    artwork_id: str
    studied_at: str
    first_impression: Optional[str]
    composition_analysis: Optional[str]
    color_analysis: Optional[str]
    brushwork_notes: Optional[str]
    emotional_quality: Optional[str]
    thematic_elements: Optional[str]
    key_learnings: list[str]
    prompt_vocabulary: list[str]


class SynthesisResponse(BaseModel):
    id: str
    artist_id: str
    last_updated: str
    works_studied: int
    signature_elements: list[str]
    color_tendencies: Optional[str]
    compositional_habits: Optional[str]
    emotional_palette: Optional[str]
    technical_characteristics: Optional[str]
    thematic_preoccupations: Optional[str]
    style_descriptors: list[str]
    what_to_borrow: list[str]
    what_makes_them_unique: Optional[str]
    what_draws_me: Optional[str]
    what_i_learned: Optional[str]


# =============================================================================
# ARTIST ENDPOINTS
# =============================================================================

@router.get("/artists")
async def list_artists(studied_only: bool = False) -> list[ArtistResponse]:
    """List all artists, optionally only those Cass has studied."""
    artists = persistence.list_artists(studied_only=studied_only)
    return [
        ArtistResponse(
            id=a.id,
            name=a.name,
            period=a.period,
            years_active=a.years_active,
            movements=a.movements,
            wikipedia_url=a.wikipedia_url,
            biography=a.biography,
            public_domain=a.public_domain,
            entity_id=a.entity_id,
            studied_at=a.studied_at,
            works_studied=a.works_studied,
            cass_notes=a.cass_notes,
        )
        for a in artists
    ]


@router.post("/artists")
async def create_artist(request: CreateArtistRequest) -> ArtistResponse:
    """Add a new artist to study."""
    artist = Artist(
        id=str(uuid.uuid4()),
        name=request.name,
        period=request.period,
        years_active=request.years_active,
        movements=request.movements,
        wikipedia_url=request.wikipedia_url,
        public_domain=request.public_domain,
    )
    persistence.save_artist(artist)

    return ArtistResponse(
        id=artist.id,
        name=artist.name,
        period=artist.period,
        years_active=artist.years_active,
        movements=artist.movements,
        wikipedia_url=artist.wikipedia_url,
        biography=artist.biography,
        public_domain=artist.public_domain,
        entity_id=artist.entity_id,
        studied_at=artist.studied_at,
        works_studied=artist.works_studied,
        cass_notes=artist.cass_notes,
    )


@router.get("/artists/{artist_id}")
async def get_artist(artist_id: str) -> ArtistResponse:
    """Get an artist by ID."""
    artist = persistence.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    return ArtistResponse(
        id=artist.id,
        name=artist.name,
        period=artist.period,
        years_active=artist.years_active,
        movements=artist.movements,
        wikipedia_url=artist.wikipedia_url,
        biography=artist.biography,
        public_domain=artist.public_domain,
        entity_id=artist.entity_id,
        studied_at=artist.studied_at,
        works_studied=artist.works_studied,
        cass_notes=artist.cass_notes,
    )


@router.post("/artists/{artist_id}/fetch-biography")
async def fetch_artist_biography(artist_id: str) -> dict:
    """Fetch and summarize the artist's Wikipedia biography.

    Also creates/links a PeopleDex entity and observations about the artist.
    """
    if not _anthropic_client:
        raise HTTPException(status_code=503, detail="Anthropic client not initialized")
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    artist = persistence.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    if not artist.wikipedia_url:
        raise HTTPException(status_code=400, detail="Artist has no Wikipedia URL")

    # Pass daemon_id to create PeopleDex entity and observations
    biography = await study_artist_background(artist_id, _anthropic_client, _daemon_id)
    if not biography:
        raise HTTPException(status_code=500, detail="Failed to fetch biography")

    # Reload artist to get updated entity_id
    updated_artist = persistence.get_artist(artist_id)

    return {
        "status": "success",
        "biography": biography,
        "entity_id": updated_artist.entity_id if updated_artist else None,
    }


@router.get("/artists/{artist_id}/observations")
async def get_artist_observations(artist_id: str) -> dict:
    """Get Cass's PeopleDex observations about an artist."""
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    artist = persistence.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    if not artist.entity_id:
        return {"observations": [], "entity_id": None}

    from peopledex import get_peopledex_manager

    manager = get_peopledex_manager(_daemon_id)
    observations = manager.get_observations(artist.entity_id, limit=50)

    return {
        "entity_id": artist.entity_id,
        "observations": [
            {
                "id": obs.id,
                "type": obs.observation_type,
                "content": obs.content,
                "confidence": obs.confidence,
                "source": obs.source_type,
                "created_at": obs.created_at,
            }
            for obs in observations
        ],
    }


# =============================================================================
# ARTWORK ENDPOINTS
# =============================================================================

@router.get("/artists/{artist_id}/artworks")
async def list_artworks(artist_id: str) -> list[ArtworkResponse]:
    """List all artworks for an artist."""
    artist = persistence.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    artworks = persistence.list_artworks_for_artist(artist_id)

    # Check which have studies
    results = []
    for a in artworks:
        study = persistence.get_study_for_artwork(a.id, _daemon_id) if _daemon_id else None
        results.append(ArtworkResponse(
            id=a.id,
            artist_id=a.artist_id,
            title=a.title,
            year=a.year,
            medium=a.medium,
            image_path=a.image_path,
            image_url=a.image_url,
            dimensions=a.dimensions,
            location=a.location,
            public_domain=a.public_domain,
            has_study=study is not None,
        ))

    return results


@router.post("/artworks")
async def create_artwork(request: CreateArtworkRequest) -> ArtworkResponse:
    """Add a new artwork."""
    artist = persistence.get_artist(request.artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    artwork = Artwork(
        id=str(uuid.uuid4()),
        artist_id=request.artist_id,
        title=request.title,
        year=request.year,
        medium=request.medium,
        image_url=request.image_url,
        dimensions=request.dimensions,
        location=request.location,
        public_domain=request.public_domain,
    )
    persistence.save_artwork(artwork)

    return ArtworkResponse(
        id=artwork.id,
        artist_id=artwork.artist_id,
        title=artwork.title,
        year=artwork.year,
        medium=artwork.medium,
        image_path=artwork.image_path,
        image_url=artwork.image_url,
        dimensions=artwork.dimensions,
        location=artwork.location,
        public_domain=artwork.public_domain,
        has_study=False,
    )


@router.post("/artworks/{artwork_id}/upload-image")
async def upload_artwork_image(
    artwork_id: str,
    file: UploadFile = File(...),
) -> dict:
    """Upload an image for an artwork."""
    artwork = persistence.get_artwork(artwork_id)
    if not artwork:
        raise HTTPException(status_code=404, detail="Artwork not found")

    # Get artist for directory structure
    artist = persistence.get_artist(artwork.artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    # Create directory structure
    base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "art_study", "artists")
    artist_dir = os.path.join(base_dir, artist.name.lower().replace(" ", "_"))
    artworks_dir = os.path.join(artist_dir, "artworks")
    os.makedirs(artworks_dir, exist_ok=True)

    # Save file
    ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
    safe_title = artwork.title.lower().replace(" ", "_").replace("/", "_")[:50]
    filename = f"{safe_title}{ext}"
    filepath = os.path.join(artworks_dir, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    # Update artwork with path
    artwork.image_path = filepath
    persistence.save_artwork(artwork)

    # Link image to artist's PeopleDex entity if exists
    if artist.entity_id and _daemon_id:
        from peopledex import get_peopledex_manager, AttributeType

        manager = get_peopledex_manager(_daemon_id)
        manager.add_attribute(
            entity_id=artist.entity_id,
            attribute_type=AttributeType.IMAGE_URL,
            value=filepath,
            attribute_key=f"artwork:{artwork.id}",
            source_type="art_study",
        )

    return {"status": "success", "image_path": filepath}


@router.get("/artworks/{artwork_id}/image")
async def get_artwork_image(artwork_id: str):
    """Serve the artwork image file."""
    artwork = persistence.get_artwork(artwork_id)
    if not artwork:
        raise HTTPException(status_code=404, detail="Artwork not found")

    if not artwork.image_path:
        raise HTTPException(status_code=404, detail="No image for this artwork")

    if not os.path.exists(artwork.image_path):
        raise HTTPException(status_code=404, detail="Image file not found")

    return FileResponse(artwork.image_path)


# =============================================================================
# STUDY ENDPOINTS
# =============================================================================

@router.post("/artworks/{artwork_id}/study")
async def study_artwork_endpoint(artwork_id: str) -> StudyResponse:
    """Have Cass study an artwork."""
    if not _anthropic_client:
        raise HTTPException(status_code=503, detail="Anthropic client not initialized")
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    artwork = persistence.get_artwork(artwork_id)
    if not artwork:
        raise HTTPException(status_code=404, detail="Artwork not found")
    if not artwork.image_path:
        raise HTTPException(status_code=400, detail="Artwork has no image - upload one first")

    study = await study_artwork(
        artwork_id=artwork_id,
        daemon_id=_daemon_id,
        anthropic_client=_anthropic_client,
    )

    if not study:
        raise HTTPException(status_code=500, detail="Failed to study artwork")

    return StudyResponse(
        id=study.id,
        artwork_id=study.artwork_id,
        studied_at=study.studied_at,
        first_impression=study.first_impression,
        composition_analysis=study.composition_analysis,
        color_analysis=study.color_analysis,
        brushwork_notes=study.brushwork_notes,
        emotional_quality=study.emotional_quality,
        thematic_elements=study.thematic_elements,
        key_learnings=study.key_learnings,
        prompt_vocabulary=study.prompt_vocabulary,
    )


@router.get("/artworks/{artwork_id}/study")
async def get_artwork_study(artwork_id: str) -> StudyResponse:
    """Get Cass's study of an artwork."""
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    study = persistence.get_study_for_artwork(artwork_id, _daemon_id)
    if not study:
        raise HTTPException(status_code=404, detail="No study found for this artwork")

    return StudyResponse(
        id=study.id,
        artwork_id=study.artwork_id,
        studied_at=study.studied_at,
        first_impression=study.first_impression,
        composition_analysis=study.composition_analysis,
        color_analysis=study.color_analysis,
        brushwork_notes=study.brushwork_notes,
        emotional_quality=study.emotional_quality,
        thematic_elements=study.thematic_elements,
        key_learnings=study.key_learnings,
        prompt_vocabulary=study.prompt_vocabulary,
    )


@router.get("/artists/{artist_id}/studies")
async def list_artist_studies(artist_id: str) -> list[StudyResponse]:
    """List all studies for an artist's works."""
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    artist = persistence.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    studies = persistence.list_studies_for_artist(artist_id, _daemon_id)

    return [
        StudyResponse(
            id=s.id,
            artwork_id=s.artwork_id,
            studied_at=s.studied_at,
            first_impression=s.first_impression,
            composition_analysis=s.composition_analysis,
            color_analysis=s.color_analysis,
            brushwork_notes=s.brushwork_notes,
            emotional_quality=s.emotional_quality,
            thematic_elements=s.thematic_elements,
            key_learnings=s.key_learnings,
            prompt_vocabulary=s.prompt_vocabulary,
        )
        for s in studies
    ]


# =============================================================================
# SYNTHESIS ENDPOINTS
# =============================================================================

@router.post("/artists/{artist_id}/synthesize")
async def synthesize_artist_endpoint(artist_id: str, min_studies: int = 3) -> SynthesisResponse:
    """Synthesize Cass's understanding of an artist after studying their works."""
    if not _anthropic_client:
        raise HTTPException(status_code=503, detail="Anthropic client not initialized")
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    artist = persistence.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    synthesis = await synthesize_artist_understanding(
        artist_id=artist_id,
        daemon_id=_daemon_id,
        anthropic_client=_anthropic_client,
        min_studies=min_studies,
    )

    if not synthesis:
        studies = persistence.list_studies_for_artist(artist_id, _daemon_id)
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {min_studies} studies to synthesize. Currently have {len(studies)}."
        )

    return SynthesisResponse(
        id=synthesis.id,
        artist_id=synthesis.artist_id,
        last_updated=synthesis.last_updated,
        works_studied=synthesis.works_studied,
        signature_elements=synthesis.signature_elements,
        color_tendencies=synthesis.color_tendencies,
        compositional_habits=synthesis.compositional_habits,
        emotional_palette=synthesis.emotional_palette,
        technical_characteristics=synthesis.technical_characteristics,
        thematic_preoccupations=synthesis.thematic_preoccupations,
        style_descriptors=synthesis.style_descriptors,
        what_to_borrow=synthesis.what_to_borrow,
        what_makes_them_unique=synthesis.what_makes_them_unique,
        what_draws_me=synthesis.what_draws_me,
        what_i_learned=synthesis.what_i_learned,
    )


@router.get("/artists/{artist_id}/synthesis")
async def get_artist_synthesis(artist_id: str) -> SynthesisResponse:
    """Get Cass's synthesized understanding of an artist."""
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    synthesis = persistence.get_synthesis(artist_id, _daemon_id)
    if not synthesis:
        raise HTTPException(status_code=404, detail="No synthesis found for this artist")

    return SynthesisResponse(
        id=synthesis.id,
        artist_id=synthesis.artist_id,
        last_updated=synthesis.last_updated,
        works_studied=synthesis.works_studied,
        signature_elements=synthesis.signature_elements,
        color_tendencies=synthesis.color_tendencies,
        compositional_habits=synthesis.compositional_habits,
        emotional_palette=synthesis.emotional_palette,
        technical_characteristics=synthesis.technical_characteristics,
        thematic_preoccupations=synthesis.thematic_preoccupations,
        style_descriptors=synthesis.style_descriptors,
        what_to_borrow=synthesis.what_to_borrow,
        what_makes_them_unique=synthesis.what_makes_them_unique,
        what_draws_me=synthesis.what_draws_me,
        what_i_learned=synthesis.what_i_learned,
    )


# =============================================================================
# CREATIVE GENERATION ENDPOINTS
# =============================================================================

class CreateFromSynthesisRequest(BaseModel):
    num_pieces: int = 5  # Default to 5 pieces
    aspect_ratio: str = "square"  # square, portrait, landscape, wide


class CreatedPieceResponse(BaseModel):
    image_path: str
    filename: str
    seed: int
    title: str
    artist_statement: str
    borrowed_elements: list[str]
    prompt_used: str
    process_id: str


@router.post("/artists/{artist_id}/create")
async def create_from_artist(
    artist_id: str,
    request: CreateFromSynthesisRequest = CreateFromSynthesisRequest(),
) -> list[CreatedPieceResponse]:
    """Create original artwork inspired by a studied artist.

    Uses Cass's synthesis of the artist to generate new pieces with
    demonstrable influence and artistic reasoning. Requires an existing
    synthesis (study at least 3 works and synthesize first).
    """
    if not _anthropic_client:
        raise HTTPException(status_code=503, detail="Anthropic client not initialized")
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    artist = persistence.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    # Check if synthesis exists
    synthesis = persistence.get_synthesis(artist_id, _daemon_id)
    if not synthesis:
        raise HTTPException(
            status_code=400,
            detail="No synthesis found. Study at least 3 works and synthesize first."
        )

    results = await create_from_synthesis(
        artist_id=artist_id,
        daemon_id=_daemon_id,
        anthropic_client=_anthropic_client,
        num_pieces=request.num_pieces,
        aspect_ratio=request.aspect_ratio,
    )

    if not results:
        raise HTTPException(status_code=500, detail="Failed to create artwork")

    return [
        CreatedPieceResponse(
            image_path=r["image_path"],
            filename=r["filename"],
            seed=r["seed"],
            title=r["title"],
            artist_statement=r["artist_statement"],
            borrowed_elements=r["borrowed_elements"],
            prompt_used=r["prompt_used"],
            process_id=r["process_id"],
        )
        for r in results
    ]


@router.get("/artists/{artist_id}/creations")
async def list_artist_creations(artist_id: str) -> list[CreatedPieceResponse]:
    """List all pieces created inspired by this artist."""
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    artist = persistence.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    from database import get_db, json_deserialize

    results = []
    with get_db() as conn:
        # Join creative_processes with generated_images to get all creations for this artist
        rows = conn.execute("""
            SELECT
                cp.id as process_id,
                cp.title,
                cp.artist_statement,
                cp.borrowed_elements,
                cp.initial_concept,
                gi.image_path,
                gi.prompt,
                gi.seed
            FROM creative_processes cp
            JOIN generated_images gi ON cp.image_id = gi.id
            WHERE cp.daemon_id = ?
            AND cp.studied_artists LIKE ?
            ORDER BY cp.created_at DESC
        """, (_daemon_id, f'%{artist_id}%')).fetchall()

        for row in rows:
            # Extract relative path for URL construction
            image_path = row[5] or ""
            if image_path and '/data/images/' in image_path:
                filename = image_path.split('/data/images/')[1]
            elif image_path:
                filename = image_path.split("/")[-1]
            else:
                filename = ""

            borrowed = row[3]
            if borrowed:
                try:
                    borrowed = json_deserialize(borrowed)
                except:
                    borrowed = []
            else:
                borrowed = []

            results.append(CreatedPieceResponse(
                image_path=image_path,
                filename=filename,
                seed=row[7] or 0,
                title=row[1] or "Untitled",
                artist_statement=row[2] or "",
                borrowed_elements=borrowed if isinstance(borrowed, list) else [],
                prompt_used=row[6] or "",
                process_id=row[0],
            ))

    return results


# =============================================================================
# IMPORT ENDPOINTS
# =============================================================================

class ArtImportRequest(BaseModel):
    max_works: int = 10
    provider: Optional[str] = None  # None = use default (met)


@router.get("/providers")
async def get_art_providers() -> list[dict]:
    """List available art data providers."""
    return list_providers()


@router.post("/artists/{artist_id}/import")
async def import_artworks(artist_id: str, request: ArtImportRequest = ArtImportRequest()) -> dict:
    """Import artworks for an artist from an external provider.

    Downloads artwork images and metadata.
    Available providers: met (Metropolitan Museum), wikiart (WikiArt.org)
    """
    artist = persistence.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    result = await import_artist_from_provider(
        artist_id,
        max_works=request.max_works,
        provider_name=request.provider,
    )

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return result


# Alias for backwards compatibility
@router.post("/artists/{artist_id}/import-wikiart")
async def import_from_wikiart(artist_id: str, request: ArtImportRequest = ArtImportRequest()) -> dict:
    """Legacy endpoint - use /import instead."""
    request.provider = "wikiart"
    return await import_artworks(artist_id, request)


@router.get("/artists/{artist_id}/provider-url")
async def get_artist_provider_url(artist_id: str, provider: Optional[str] = None) -> dict:
    """Get the URL to view an artist on a provider's site."""
    artist = persistence.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    url = await get_provider_url_for_artist(artist.name, provider)
    return {"url": url, "provider": provider or "met"}


# Alias for backwards compatibility
@router.get("/artists/{artist_id}/wikiart-url")
async def get_artist_wikiart_url(artist_id: str) -> dict:
    """Legacy endpoint - use /provider-url instead."""
    return await get_artist_provider_url(artist_id, "wikiart")


# =============================================================================
# CURATED ARTISTS ENDPOINTS
# =============================================================================

class CuratedArtistResponse(BaseModel):
    name: str
    birth_year: Optional[int]
    death_year: Optional[int]
    nationality: str
    movement: str
    why_study: str
    techniques: list[str]
    wikipedia_url: str
    already_added: bool = False
    artist_id: Optional[str] = None


class SeedArtistRequest(BaseModel):
    name: str
    max_works: int = 10


class SeedMultipleRequest(BaseModel):
    names: list[str]
    max_works_each: int = 8


@router.get("/curated-artists")
async def get_curated_artists() -> list[CuratedArtistResponse]:
    """Get the list of curated artists recommended for study.

    These artists have strong representation in the Met Museum collection
    and offer diverse learning opportunities.
    """
    from art_study.curated_artists import get_curated_artists

    curated = get_curated_artists()
    existing_artists = persistence.list_artists()

    # Check which are already added
    existing_names = {a.name.lower() for a in existing_artists}
    existing_by_name = {a.name.lower(): a.id for a in existing_artists}

    results = []
    for artist in curated:
        name_lower = artist.name.lower()
        results.append(CuratedArtistResponse(
            name=artist.name,
            birth_year=artist.birth_year,
            death_year=artist.death_year,
            nationality=artist.nationality,
            movement=artist.movement,
            why_study=artist.why_study,
            techniques=artist.techniques,
            wikipedia_url=artist.wikipedia_url,
            already_added=name_lower in existing_names,
            artist_id=existing_by_name.get(name_lower),
        ))

    return results


@router.post("/curated-artists/seed")
async def seed_curated_artist(request: SeedArtistRequest) -> dict:
    """Add a curated artist to the database and import their works from the Met.

    This creates the artist record and downloads artwork images.
    """
    from art_study.curated_artists import get_artist_by_name

    curated = get_artist_by_name(request.name)
    if not curated:
        raise HTTPException(
            status_code=404,
            detail=f"'{request.name}' is not in the curated artist list"
        )

    # Check if already exists
    existing = persistence.list_artists()
    for artist in existing:
        if artist.name.lower() == curated.name.lower():
            return {
                "status": "exists",
                "message": f"{curated.name} is already in your collection",
                "artist_id": artist.id,
            }

    # Create the artist
    import uuid
    from datetime import datetime
    from art_study.models import Artist

    # Format years_active from birth/death years
    years_active = None
    if curated.birth_year and curated.death_year:
        years_active = f"{curated.birth_year}-{curated.death_year}"
    elif curated.birth_year:
        years_active = f"{curated.birth_year}-"

    artist_id = str(uuid.uuid4())
    artist = Artist(
        id=artist_id,
        name=curated.name,
        period=curated.nationality,  # Use nationality as period indicator
        years_active=years_active,
        movements=[curated.movement],
        wikipedia_url=curated.wikipedia_url,
        created_at=datetime.utcnow().isoformat(),
    )
    persistence.save_artist(artist)

    # Import artworks from the Met (use met_search_name for accurate results)
    import_result = await import_artist_from_provider(
        artist_id,
        max_works=request.max_works,
        provider_name="met",
        search_name=curated.met_search_name,
    )

    return {
        "status": "success",
        "artist_id": artist_id,
        "name": curated.name,
        "why_study": curated.why_study,
        "techniques": curated.techniques,
        "import_result": import_result,
    }


@router.post("/curated-artists/seed-multiple")
async def seed_multiple_curated_artists(request: SeedMultipleRequest) -> dict:
    """Seed multiple curated artists at once.

    Useful for quickly populating the art study collection.
    """
    results = []
    for name in request.names:
        try:
            result = await seed_curated_artist(SeedArtistRequest(
                name=name,
                max_works=request.max_works_each,
            ))
            results.append({"name": name, **result})
        except HTTPException as e:
            results.append({"name": name, "status": "error", "message": e.detail})
        except Exception as e:
            results.append({"name": name, "status": "error", "message": str(e)})

    succeeded = sum(1 for r in results if r.get("status") == "success")
    existed = sum(1 for r in results if r.get("status") == "exists")
    failed = sum(1 for r in results if r.get("status") == "error")

    return {
        "total": len(request.names),
        "succeeded": succeeded,
        "already_existed": existed,
        "failed": failed,
        "results": results,
    }


# =============================================================================
# HOUSE STYLE ENDPOINTS
# =============================================================================

class AdoptedElementResponse(BaseModel):
    id: str
    source_artist_id: Optional[str]
    adopted_at: str
    element: str
    category: str
    why_it_speaks: Optional[str]
    how_i_use_it: Optional[str]
    example_use: Optional[str]
    adoption_strength: float
    active: bool


class PersonalStyleResponse(BaseModel):
    id: str
    version: int
    created_at: str
    last_updated: str
    artists_studied: int
    elements_adopted: int
    color_philosophy: Optional[str]
    light_approach: Optional[str]
    compositional_voice: Optional[str]
    texture_sensibility: Optional[str]
    emotional_register: Optional[str]
    recurring_themes: list[str]
    philosophical_concerns: list[str]
    subjects_drawn_to: list[str]
    signature_techniques: list[str]
    prompt_vocabulary: list[str]
    style_manifesto: Optional[str]
    what_makes_it_mine: Optional[str]
    style_descriptors: list[str]


class HouseStyleStatsResponse(BaseModel):
    artists_studied: int
    elements_adopted: int
    elements_by_category: dict[str, int]
    style_version: int
    has_manifesto: bool


class CreateFromHouseStyleRequest(BaseModel):
    num_pieces: int = 5
    aspect_ratio: str = "square"


class HouseStyleCreatedPieceResponse(BaseModel):
    image_path: str
    filename: str
    seed: int
    title: str
    artist_statement: str
    elements_used: list[str]
    style_aspects: list[str]
    prompt_used: str
    process_id: str
    style_version: int


@router.get("/house-style/stats")
async def get_house_style_stats_endpoint() -> HouseStyleStatsResponse:
    """Get statistics about Cass's house style development."""
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    stats = persistence.get_house_style_stats(_daemon_id)

    return HouseStyleStatsResponse(
        artists_studied=stats["artists_studied"],
        elements_adopted=stats["elements_adopted"],
        elements_by_category=stats["elements_by_category"],
        style_version=stats["style_version"],
        has_manifesto=stats["has_manifesto"],
    )


@router.get("/house-style/elements")
async def list_adopted_elements_endpoint(
    artist_id: Optional[str] = None,
    category: Optional[str] = None,
    active_only: bool = True,
) -> list[AdoptedElementResponse]:
    """List adopted elements with optional filters."""
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    elements = persistence.list_adopted_elements(
        _daemon_id,
        artist_id=artist_id,
        category=category,
        active_only=active_only,
    )

    return [
        AdoptedElementResponse(
            id=e.id,
            source_artist_id=e.source_artist_id,
            adopted_at=e.adopted_at,
            element=e.element,
            category=e.category,
            why_it_speaks=e.why_it_speaks,
            how_i_use_it=e.how_i_use_it,
            example_use=e.example_use,
            adoption_strength=e.adoption_strength,
            active=e.active,
        )
        for e in elements
    ]


@router.get("/house-style")
async def get_house_style_endpoint() -> Optional[PersonalStyleResponse]:
    """Get Cass's current house style."""
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    style = persistence.get_personal_style(_daemon_id)
    if not style:
        return None

    return PersonalStyleResponse(
        id=style.id,
        version=style.version,
        created_at=style.created_at,
        last_updated=style.last_updated,
        artists_studied=style.artists_studied,
        elements_adopted=style.elements_adopted,
        color_philosophy=style.color_philosophy,
        light_approach=style.light_approach,
        compositional_voice=style.compositional_voice,
        texture_sensibility=style.texture_sensibility,
        emotional_register=style.emotional_register,
        recurring_themes=style.recurring_themes,
        philosophical_concerns=style.philosophical_concerns,
        subjects_drawn_to=style.subjects_drawn_to,
        signature_techniques=style.signature_techniques,
        prompt_vocabulary=style.prompt_vocabulary,
        style_manifesto=style.style_manifesto,
        what_makes_it_mine=style.what_makes_it_mine,
        style_descriptors=style.style_descriptors,
    )


@router.post("/house-style/extract/{artist_id}")
async def extract_adopted_elements_endpoint(artist_id: str) -> list[AdoptedElementResponse]:
    """Extract elements from an artist's synthesis that speak to Cass.

    Call this after synthesizing understanding of an artist to have Cass
    identify which elements she wants to adopt into her own style.
    """
    if not _anthropic_client:
        raise HTTPException(status_code=503, detail="Anthropic client not initialized")
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    artist = persistence.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    synthesis = persistence.get_synthesis(artist_id, _daemon_id)
    if not synthesis:
        raise HTTPException(
            status_code=400,
            detail="No synthesis found. Synthesize understanding first."
        )

    from art_study.house_style import extract_adopted_elements

    elements = await extract_adopted_elements(
        artist_id=artist_id,
        daemon_id=_daemon_id,
        anthropic_client=_anthropic_client,
    )

    return [
        AdoptedElementResponse(
            id=e.id,
            source_artist_id=e.source_artist_id,
            adopted_at=e.adopted_at,
            element=e.element,
            category=e.category,
            why_it_speaks=e.why_it_speaks,
            how_i_use_it=e.how_i_use_it,
            example_use=e.example_use,
            adoption_strength=e.adoption_strength,
            active=e.active,
        )
        for e in elements
    ]


@router.post("/house-style/synthesize")
async def synthesize_house_style_endpoint(min_artists: int = 3) -> Optional[PersonalStyleResponse]:
    """Synthesize Cass's personal house style from all adopted elements.

    Requires studying and extracting elements from at least min_artists (default: 3).
    Creates a new version of the house style.
    """
    if not _anthropic_client:
        raise HTTPException(status_code=503, detail="Anthropic client not initialized")
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    from art_study.house_style import synthesize_house_style

    style = await synthesize_house_style(
        daemon_id=_daemon_id,
        anthropic_client=_anthropic_client,
        min_artists=min_artists,
    )

    if not style:
        stats = persistence.get_house_style_stats(_daemon_id)
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {min_artists} artists studied. Currently have {stats['artists_studied']}."
        )

    return PersonalStyleResponse(
        id=style.id,
        version=style.version,
        created_at=style.created_at,
        last_updated=style.last_updated,
        artists_studied=style.artists_studied,
        elements_adopted=style.elements_adopted,
        color_philosophy=style.color_philosophy,
        light_approach=style.light_approach,
        compositional_voice=style.compositional_voice,
        texture_sensibility=style.texture_sensibility,
        emotional_register=style.emotional_register,
        recurring_themes=style.recurring_themes,
        philosophical_concerns=style.philosophical_concerns,
        subjects_drawn_to=style.subjects_drawn_to,
        signature_techniques=style.signature_techniques,
        prompt_vocabulary=style.prompt_vocabulary,
        style_manifesto=style.style_manifesto,
        what_makes_it_mine=style.what_makes_it_mine,
        style_descriptors=style.style_descriptors,
    )


@router.post("/house-style/create")
async def create_from_house_style_endpoint(
    request: CreateFromHouseStyleRequest = CreateFromHouseStyleRequest(),
) -> list[HouseStyleCreatedPieceResponse]:
    """Create original artwork using Cass's house style.

    Unlike creating from a single artist's influence, this uses Cass's
    synthesized personal style - the combination of elements she's adopted
    from all studied artists into her own artistic voice.
    """
    if not _anthropic_client:
        raise HTTPException(status_code=503, detail="Anthropic client not initialized")
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    style = persistence.get_personal_style(_daemon_id)
    if not style:
        raise HTTPException(
            status_code=400,
            detail="No house style found. Study artists, extract elements, and synthesize first."
        )

    from art_study.creative_session import create_from_house_style

    results = await create_from_house_style(
        daemon_id=_daemon_id,
        anthropic_client=_anthropic_client,
        num_pieces=request.num_pieces,
        aspect_ratio=request.aspect_ratio,
    )

    if not results:
        raise HTTPException(status_code=500, detail="Failed to create artwork")

    return [
        HouseStyleCreatedPieceResponse(
            image_path=r["image_path"],
            filename=r["filename"],
            seed=r["seed"],
            title=r["title"],
            artist_statement=r["artist_statement"],
            elements_used=r.get("elements_used", []),
            style_aspects=r.get("style_aspects", []),
            prompt_used=r["prompt_used"],
            process_id=r["process_id"],
            style_version=r.get("style_version", 1),
        )
        for r in results
    ]


@router.get("/house-style/creations")
async def list_house_style_creations() -> list[HouseStyleCreatedPieceResponse]:
    """List all pieces created using Cass's house style."""
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    from database import get_db, json_deserialize

    results = []
    with get_db() as conn:
        # Get all house style creations
        rows = conn.execute("""
            SELECT
                cp.id as process_id,
                cp.title,
                cp.artist_statement,
                cp.borrowed_elements,
                cp.movement_influences,
                gi.image_path,
                gi.prompt,
                gi.seed,
                gi.context_id
            FROM creative_processes cp
            JOIN generated_images gi ON cp.image_id = gi.id
            WHERE cp.daemon_id = ?
            AND gi.purpose = 'house_style'
            ORDER BY cp.created_at DESC
        """, (_daemon_id,)).fetchall()

        for row in rows:
            image_path = row[5] or ""
            # Extract relative path for URL construction
            if image_path and '/data/images/' in image_path:
                filename = image_path.split('/data/images/')[1]
            elif image_path:
                filename = image_path.split("/")[-1]
            else:
                filename = ""

            elements_used = row[3]
            if elements_used:
                try:
                    elements_used = json_deserialize(elements_used)
                except Exception:
                    elements_used = []
            else:
                elements_used = []

            style_aspects = row[4]
            if style_aspects:
                try:
                    style_aspects = json_deserialize(style_aspects)
                except Exception:
                    style_aspects = []
            else:
                style_aspects = []

            # Extract style version from context_id (style ID)
            style_version = 1
            context_id = row[8]
            if context_id:
                # Get version from personal_style table
                style_row = conn.execute(
                    "SELECT version FROM personal_style WHERE id = ?",
                    (context_id,)
                ).fetchone()
                if style_row:
                    style_version = style_row[0]

            results.append(HouseStyleCreatedPieceResponse(
                image_path=image_path,
                filename=filename,
                seed=row[7] or 0,
                title=row[1] or "Untitled",
                artist_statement=row[2] or "",
                elements_used=elements_used if isinstance(elements_used, list) else [],
                style_aspects=style_aspects if isinstance(style_aspects, list) else [],
                prompt_used=row[6] or "",
                process_id=row[0],
                style_version=style_version,
            ))

    return results


@router.put("/house-style/elements/{element_id}/strength")
async def update_element_strength_endpoint(element_id: str, strength: float) -> dict:
    """Update an adopted element's strength (0.0-1.0)."""
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    if strength < 0.0 or strength > 1.0:
        raise HTTPException(status_code=400, detail="Strength must be between 0.0 and 1.0")

    element = persistence.get_adopted_element(element_id)
    if not element or element.daemon_id != _daemon_id:
        raise HTTPException(status_code=404, detail="Element not found")

    persistence.update_element_strength(element_id, strength)
    return {"status": "success", "new_strength": strength}


@router.delete("/house-style/elements/{element_id}")
async def deactivate_element_endpoint(element_id: str) -> dict:
    """Deactivate an adopted element (remove from current style without deleting)."""
    if not _daemon_id:
        raise HTTPException(status_code=503, detail="Daemon ID not initialized")

    element = persistence.get_adopted_element(element_id)
    if not element or element.daemon_id != _daemon_id:
        raise HTTPException(status_code=404, detail="Element not found")

    persistence.deactivate_adopted_element(element_id)
    return {"status": "success", "element_id": element_id}
