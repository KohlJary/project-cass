"""
Art Study Persistence

Database operations for artists, artworks, studies, and creative processes.
"""

import json
import logging
from typing import Optional
from datetime import datetime

from .models import (
    Artist,
    Artwork,
    ArtworkStudy,
    ArtistSynthesis,
    CreativeProcess,
)

logger = logging.getLogger(__name__)


def _get_db():
    """Get database connection."""
    from database import get_db
    return get_db()


# =============================================================================
# ARTISTS
# =============================================================================

def save_artist(artist: Artist) -> None:
    """Save or update an artist."""
    conn = _get_db()
    conn.execute("""
        INSERT OR REPLACE INTO artists (
            id, name, period, years_active, movements, wikipedia_url,
            biography, public_domain, created_at, studied_at, works_studied, cass_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        artist.id,
        artist.name,
        artist.period,
        artist.years_active,
        json.dumps(artist.movements),
        artist.wikipedia_url,
        artist.biography,
        artist.public_domain,
        artist.created_at,
        artist.studied_at,
        artist.works_studied,
        artist.cass_notes,
    ))
    conn.commit()


def get_artist(artist_id: str) -> Optional[Artist]:
    """Get an artist by ID."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM artists WHERE id = ?", (artist_id,)
    ).fetchone()

    if not row:
        return None

    return Artist(
        id=row[0],
        name=row[1],
        period=row[2],
        years_active=row[3],
        movements=json.loads(row[4]) if row[4] else [],
        wikipedia_url=row[5],
        biography=row[6],
        public_domain=bool(row[7]),
        created_at=row[8],
        studied_at=row[9],
        works_studied=row[10] or 0,
        cass_notes=row[11],
    )


def get_artist_by_name(name: str) -> Optional[Artist]:
    """Get an artist by name (case-insensitive)."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM artists WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()

    if not row:
        return None

    return Artist(
        id=row[0],
        name=row[1],
        period=row[2],
        years_active=row[3],
        movements=json.loads(row[4]) if row[4] else [],
        wikipedia_url=row[5],
        biography=row[6],
        public_domain=bool(row[7]),
        created_at=row[8],
        studied_at=row[9],
        works_studied=row[10] or 0,
        cass_notes=row[11],
    )


def list_artists(studied_only: bool = False) -> list[Artist]:
    """List all artists, optionally only those Cass has studied."""
    conn = _get_db()
    if studied_only:
        rows = conn.execute(
            "SELECT * FROM artists WHERE studied_at IS NOT NULL ORDER BY name"
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM artists ORDER BY name").fetchall()

    return [
        Artist(
            id=row[0],
            name=row[1],
            period=row[2],
            years_active=row[3],
            movements=json.loads(row[4]) if row[4] else [],
            wikipedia_url=row[5],
            biography=row[6],
            public_domain=bool(row[7]),
            created_at=row[8],
            studied_at=row[9],
            works_studied=row[10] or 0,
            cass_notes=row[11],
        )
        for row in rows
    ]


def update_artist_biography(artist_id: str, biography: str) -> None:
    """Update an artist's biography."""
    conn = _get_db()
    conn.execute(
        "UPDATE artists SET biography = ? WHERE id = ?",
        (biography, artist_id)
    )
    conn.commit()


def mark_artist_studied(artist_id: str) -> None:
    """Mark an artist as studied (first study timestamp)."""
    conn = _get_db()
    conn.execute("""
        UPDATE artists
        SET studied_at = COALESCE(studied_at, ?),
            works_studied = works_studied + 1
        WHERE id = ?
    """, (datetime.utcnow().isoformat(), artist_id))
    conn.commit()


# =============================================================================
# ARTWORKS
# =============================================================================

def save_artwork(artwork: Artwork) -> None:
    """Save or update an artwork."""
    conn = _get_db()
    conn.execute("""
        INSERT OR REPLACE INTO artworks (
            id, artist_id, title, year, medium, image_path,
            image_url, dimensions, location, public_domain, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        artwork.id,
        artwork.artist_id,
        artwork.title,
        artwork.year,
        artwork.medium,
        artwork.image_path,
        artwork.image_url,
        artwork.dimensions,
        artwork.location,
        artwork.public_domain,
        artwork.created_at,
    ))
    conn.commit()


def get_artwork(artwork_id: str) -> Optional[Artwork]:
    """Get an artwork by ID."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM artworks WHERE id = ?", (artwork_id,)
    ).fetchone()

    if not row:
        return None

    return Artwork(
        id=row[0],
        artist_id=row[1],
        title=row[2],
        year=row[3],
        medium=row[4],
        image_path=row[5],
        image_url=row[6],
        dimensions=row[7],
        location=row[8],
        public_domain=bool(row[9]),
        created_at=row[10],
    )


def list_artworks_for_artist(artist_id: str) -> list[Artwork]:
    """List all artworks for an artist."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM artworks WHERE artist_id = ? ORDER BY year, title",
        (artist_id,)
    ).fetchall()

    return [
        Artwork(
            id=row[0],
            artist_id=row[1],
            title=row[2],
            year=row[3],
            medium=row[4],
            image_path=row[5],
            image_url=row[6],
            dimensions=row[7],
            location=row[8],
            public_domain=bool(row[9]),
            created_at=row[10],
        )
        for row in rows
    ]


# =============================================================================
# ARTWORK STUDIES
# =============================================================================

def save_study(study: ArtworkStudy) -> None:
    """Save an artwork study."""
    conn = _get_db()
    conn.execute("""
        INSERT OR REPLACE INTO artwork_studies (
            id, artwork_id, daemon_id, studied_at,
            first_impression, composition_analysis, color_analysis,
            brushwork_notes, emotional_quality, thematic_elements,
            technical_observations, biographical_context,
            key_learnings, prompt_vocabulary, reminds_me_of, could_inform
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        study.id,
        study.artwork_id,
        study.daemon_id,
        study.studied_at,
        study.first_impression,
        study.composition_analysis,
        study.color_analysis,
        study.brushwork_notes,
        study.emotional_quality,
        study.thematic_elements,
        study.technical_observations,
        study.biographical_context,
        json.dumps(study.key_learnings),
        json.dumps(study.prompt_vocabulary),
        json.dumps(study.reminds_me_of),
        json.dumps(study.could_inform),
    ))
    conn.commit()


def get_study(study_id: str) -> Optional[ArtworkStudy]:
    """Get a study by ID."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM artwork_studies WHERE id = ?", (study_id,)
    ).fetchone()

    if not row:
        return None

    return ArtworkStudy(
        id=row[0],
        artwork_id=row[1],
        daemon_id=row[2],
        studied_at=row[3],
        first_impression=row[4],
        composition_analysis=row[5],
        color_analysis=row[6],
        brushwork_notes=row[7],
        emotional_quality=row[8],
        thematic_elements=row[9],
        technical_observations=row[10],
        biographical_context=row[11],
        key_learnings=json.loads(row[12]) if row[12] else [],
        prompt_vocabulary=json.loads(row[13]) if row[13] else [],
        reminds_me_of=json.loads(row[14]) if row[14] else [],
        could_inform=json.loads(row[15]) if row[15] else [],
    )


def get_study_for_artwork(artwork_id: str, daemon_id: str) -> Optional[ArtworkStudy]:
    """Get study for a specific artwork by this daemon."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM artwork_studies WHERE artwork_id = ? AND daemon_id = ?",
        (artwork_id, daemon_id)
    ).fetchone()

    if not row:
        return None

    return ArtworkStudy(
        id=row[0],
        artwork_id=row[1],
        daemon_id=row[2],
        studied_at=row[3],
        first_impression=row[4],
        composition_analysis=row[5],
        color_analysis=row[6],
        brushwork_notes=row[7],
        emotional_quality=row[8],
        thematic_elements=row[9],
        technical_observations=row[10],
        biographical_context=row[11],
        key_learnings=json.loads(row[12]) if row[12] else [],
        prompt_vocabulary=json.loads(row[13]) if row[13] else [],
        reminds_me_of=json.loads(row[14]) if row[14] else [],
        could_inform=json.loads(row[15]) if row[15] else [],
    )


def list_studies_for_artist(artist_id: str, daemon_id: str) -> list[ArtworkStudy]:
    """List all studies for artworks by an artist."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT s.* FROM artwork_studies s
        JOIN artworks a ON s.artwork_id = a.id
        WHERE a.artist_id = ? AND s.daemon_id = ?
        ORDER BY s.studied_at DESC
    """, (artist_id, daemon_id)).fetchall()

    return [
        ArtworkStudy(
            id=row[0],
            artwork_id=row[1],
            daemon_id=row[2],
            studied_at=row[3],
            first_impression=row[4],
            composition_analysis=row[5],
            color_analysis=row[6],
            brushwork_notes=row[7],
            emotional_quality=row[8],
            thematic_elements=row[9],
            technical_observations=row[10],
            biographical_context=row[11],
            key_learnings=json.loads(row[12]) if row[12] else [],
            prompt_vocabulary=json.loads(row[13]) if row[13] else [],
            reminds_me_of=json.loads(row[14]) if row[14] else [],
            could_inform=json.loads(row[15]) if row[15] else [],
        )
        for row in rows
    ]


# =============================================================================
# ARTIST SYNTHESIS
# =============================================================================

def save_synthesis(synthesis: ArtistSynthesis) -> None:
    """Save or update an artist synthesis."""
    conn = _get_db()
    conn.execute("""
        INSERT OR REPLACE INTO artist_syntheses (
            id, artist_id, daemon_id, last_updated, works_studied,
            signature_elements, color_tendencies, compositional_habits,
            emotional_palette, technical_characteristics, thematic_preoccupations,
            style_descriptors, what_to_borrow, what_makes_them_unique,
            what_draws_me, what_i_learned
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        synthesis.id,
        synthesis.artist_id,
        synthesis.daemon_id,
        synthesis.last_updated,
        synthesis.works_studied,
        json.dumps(synthesis.signature_elements),
        synthesis.color_tendencies,
        synthesis.compositional_habits,
        synthesis.emotional_palette,
        synthesis.technical_characteristics,
        synthesis.thematic_preoccupations,
        json.dumps(synthesis.style_descriptors),
        json.dumps(synthesis.what_to_borrow),
        synthesis.what_makes_them_unique,
        synthesis.what_draws_me,
        synthesis.what_i_learned,
    ))
    conn.commit()


def get_synthesis(artist_id: str, daemon_id: str) -> Optional[ArtistSynthesis]:
    """Get synthesis for an artist by this daemon."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM artist_syntheses WHERE artist_id = ? AND daemon_id = ?",
        (artist_id, daemon_id)
    ).fetchone()

    if not row:
        return None

    return ArtistSynthesis(
        id=row[0],
        artist_id=row[1],
        daemon_id=row[2],
        last_updated=row[3],
        works_studied=row[4],
        signature_elements=json.loads(row[5]) if row[5] else [],
        color_tendencies=row[6],
        compositional_habits=row[7],
        emotional_palette=row[8],
        technical_characteristics=row[9],
        thematic_preoccupations=row[10],
        style_descriptors=json.loads(row[11]) if row[11] else [],
        what_to_borrow=json.loads(row[12]) if row[12] else [],
        what_makes_them_unique=row[13],
        what_draws_me=row[14],
        what_i_learned=row[15],
    )


# =============================================================================
# CREATIVE PROCESS
# =============================================================================

def save_creative_process(process: CreativeProcess) -> None:
    """Save a creative process record."""
    conn = _get_db()
    conn.execute("""
        INSERT OR REPLACE INTO creative_processes (
            id, image_id, daemon_id, created_at,
            initial_impulse, thymos_state, recent_context,
            studied_artists, specific_works, borrowed_elements, movement_influences,
            initial_concept, iterations, technical_choices,
            title, artist_statement, what_i_was_exploring
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        process.id,
        process.image_id,
        process.daemon_id,
        process.created_at,
        process.initial_impulse,
        json.dumps(process.thymos_state) if process.thymos_state else None,
        process.recent_context,
        json.dumps(process.studied_artists),
        json.dumps(process.specific_works),
        json.dumps(process.borrowed_elements),
        json.dumps(process.movement_influences),
        process.initial_concept,
        json.dumps(process.iterations),
        process.technical_choices,
        process.title,
        process.artist_statement,
        process.what_i_was_exploring,
    ))
    conn.commit()


def get_creative_process(image_id: str) -> Optional[CreativeProcess]:
    """Get creative process for an image."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM creative_processes WHERE image_id = ?", (image_id,)
    ).fetchone()

    if not row:
        return None

    return CreativeProcess(
        id=row[0],
        image_id=row[1],
        daemon_id=row[2],
        created_at=row[3],
        initial_impulse=row[4],
        thymos_state=json.loads(row[5]) if row[5] else None,
        recent_context=row[6],
        studied_artists=json.loads(row[7]) if row[7] else [],
        specific_works=json.loads(row[8]) if row[8] else [],
        borrowed_elements=json.loads(row[9]) if row[9] else [],
        movement_influences=json.loads(row[10]) if row[10] else [],
        initial_concept=row[11],
        iterations=json.loads(row[12]) if row[12] else [],
        technical_choices=row[13],
        title=row[14],
        artist_statement=row[15],
        what_i_was_exploring=row[16],
    )
