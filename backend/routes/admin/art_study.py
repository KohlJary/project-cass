"""
Art Study Admin API

Endpoints for managing and viewing Cass's art studies.
"""

import os
import uuid
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional

from art_study import persistence
from art_study.models import Artist, Artwork
from art_study.study_session import study_artwork, study_artist_background, synthesize_artist_understanding

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
        studied_at=artist.studied_at,
        works_studied=artist.works_studied,
        cass_notes=artist.cass_notes,
    )


@router.post("/artists/{artist_id}/fetch-biography")
async def fetch_artist_biography(artist_id: str) -> dict:
    """Fetch and summarize the artist's Wikipedia biography."""
    if not _anthropic_client:
        raise HTTPException(status_code=503, detail="Anthropic client not initialized")

    artist = persistence.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    if not artist.wikipedia_url:
        raise HTTPException(status_code=400, detail="Artist has no Wikipedia URL")

    biography = await study_artist_background(artist_id, _anthropic_client)
    if not biography:
        raise HTTPException(status_code=500, detail="Failed to fetch biography")

    return {"status": "success", "biography": biography}


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

    return {"status": "success", "image_path": filepath}


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
