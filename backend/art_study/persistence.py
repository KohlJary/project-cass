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
    AdoptedElement,
    PersonalStyle,
)

logger = logging.getLogger(__name__)


def _get_db():
    """Get database connection context manager."""
    from database import get_db
    return get_db()


def _row_to_artist(row) -> Artist:
    """Convert a database row to an Artist object."""
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
        entity_id=row[9],
        studied_at=row[10],
        works_studied=row[11] or 0,
        cass_notes=row[12],
    )


# =============================================================================
# ARTISTS
# =============================================================================

def save_artist(artist: Artist) -> None:
    """Save or update an artist."""
    with _get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO artists (
                id, name, period, years_active, movements, wikipedia_url,
                biography, public_domain, created_at, entity_id, studied_at, works_studied, cass_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            artist.entity_id,
            artist.studied_at,
            artist.works_studied,
            artist.cass_notes,
        ))


def get_artist(artist_id: str) -> Optional[Artist]:
    """Get an artist by ID."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM artists WHERE id = ?", (artist_id,)
        ).fetchone()

        if not row:
            return None

        return _row_to_artist(row)


def get_artist_by_name(name: str) -> Optional[Artist]:
    """Get an artist by name (case-insensitive)."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM artists WHERE LOWER(name) = LOWER(?)", (name,)
        ).fetchone()

        if not row:
            return None

        return _row_to_artist(row)


def list_artists(studied_only: bool = False) -> list[Artist]:
    """List all artists, optionally only those Cass has studied."""
    with _get_db() as conn:
        if studied_only:
            rows = conn.execute(
                "SELECT * FROM artists WHERE studied_at IS NOT NULL ORDER BY name"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM artists ORDER BY name").fetchall()

        return [_row_to_artist(row) for row in rows]


def update_artist_biography(artist_id: str, biography: str) -> None:
    """Update an artist's biography."""
    with _get_db() as conn:
        conn.execute(
            "UPDATE artists SET biography = ? WHERE id = ?",
            (biography, artist_id)
        )


def update_artist_entity_id(artist_id: str, entity_id: str) -> None:
    """Link an artist to a PeopleDex entity."""
    with _get_db() as conn:
        conn.execute(
            "UPDATE artists SET entity_id = ? WHERE id = ?",
            (entity_id, artist_id)
        )


def get_or_create_artist_entity(artist: Artist, daemon_id: str) -> str:
    """
    Get or create a PeopleDex entity for an artist.

    Returns the entity_id.
    """
    # If artist already has an entity, return it
    if artist.entity_id:
        return artist.entity_id

    # Import PeopleDex manager
    from peopledex import (
        get_peopledex_manager,
        EntityType,
        AttributeType,
        Realm,
    )

    manager = get_peopledex_manager(daemon_id)

    # Search for existing entity by name
    existing = manager.search_entities(artist.name, EntityType.PERSON, limit=1)
    for entity in existing:
        if entity.primary_name.lower() == artist.name.lower():
            # Found existing entity, link it
            update_artist_entity_id(artist.id, entity.id)
            return entity.id

    # Create new entity for this artist
    entity_id = manager.create_entity(
        entity_type=EntityType.PERSON,
        primary_name=artist.name,
        realm=Realm.MEATSPACE,
    )

    # Add role attribute
    manager.add_attribute(
        entity_id=entity_id,
        attribute_type=AttributeType.ROLE,
        value="Artist",
    )

    # Add period info if available
    if artist.years_active:
        manager.add_attribute(
            entity_id=entity_id,
            attribute_type=AttributeType.NOTE,
            value=f"Active: {artist.years_active}",
            attribute_key="years_active",
        )

    # Add Wikipedia URL if available
    if artist.wikipedia_url:
        manager.add_attribute(
            entity_id=entity_id,
            attribute_type=AttributeType.LINK,
            value=artist.wikipedia_url,
            attribute_key="wikipedia",
        )

    # Add movements as notes
    if artist.movements:
        manager.add_attribute(
            entity_id=entity_id,
            attribute_type=AttributeType.NOTE,
            value=", ".join(artist.movements),
            attribute_key="art_movements",
        )

    # Link artist to entity
    update_artist_entity_id(artist.id, entity_id)

    logger.info(f"Created PeopleDex entity for artist: {artist.name} ({entity_id})")
    return entity_id


def mark_artist_studied(artist_id: str, artwork_id: str, daemon_id: str) -> None:
    """Mark an artist as studied, only incrementing count for first study of each artwork."""
    with _get_db() as conn:
        # Check if this artwork has been studied before (by this daemon)
        existing = conn.execute("""
            SELECT COUNT(*) FROM artwork_studies
            WHERE artwork_id = ? AND daemon_id = ?
        """, (artwork_id, daemon_id)).fetchone()[0]

        # Only increment works_studied if this is the first study of this artwork
        # (count will be 1 after save_study is called, so check for <= 1)
        if existing <= 1:
            conn.execute("""
                UPDATE artists
                SET studied_at = COALESCE(studied_at, ?),
                    works_studied = works_studied + 1
                WHERE id = ?
            """, (datetime.utcnow().isoformat(), artist_id))
        else:
            # Just update the timestamp if re-studying
            conn.execute("""
                UPDATE artists
                SET studied_at = ?
                WHERE id = ?
            """, (datetime.utcnow().isoformat(), artist_id))


# =============================================================================
# ARTWORKS
# =============================================================================

def save_artwork(artwork: Artwork) -> None:
    """Save or update an artwork."""
    with _get_db() as conn:
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


def get_artwork(artwork_id: str) -> Optional[Artwork]:
    """Get an artwork by ID."""
    with _get_db() as conn:
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
    with _get_db() as conn:
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
    with _get_db() as conn:
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


def get_study(study_id: str) -> Optional[ArtworkStudy]:
    """Get a study by ID."""
    with _get_db() as conn:
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
    """Get the most recent study for a specific artwork by this daemon."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM artwork_studies WHERE artwork_id = ? AND daemon_id = ? ORDER BY studied_at DESC LIMIT 1",
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
    with _get_db() as conn:
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
    with _get_db() as conn:
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


def get_synthesis(artist_id: str, daemon_id: str) -> Optional[ArtistSynthesis]:
    """Get synthesis for an artist by this daemon."""
    with _get_db() as conn:
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
    with _get_db() as conn:
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


def get_creative_process(image_id: str) -> Optional[CreativeProcess]:
    """Get creative process for an image."""
    with _get_db() as conn:
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


# =============================================================================
# ADOPTED ELEMENTS (House Style)
# =============================================================================

def save_adopted_element(element: AdoptedElement) -> None:
    """Save or update an adopted element."""
    with _get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO adopted_elements (
                id, daemon_id, source_artist_id, adopted_at,
                element, category, why_it_speaks, how_i_use_it,
                example_use, adoption_strength, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            element.id,
            element.daemon_id,
            element.source_artist_id,
            element.adopted_at,
            element.element,
            element.category,
            element.why_it_speaks,
            element.how_i_use_it,
            element.example_use,
            element.adoption_strength,
            element.active,
        ))


def get_adopted_element(element_id: str) -> Optional[AdoptedElement]:
    """Get an adopted element by ID."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM adopted_elements WHERE id = ?", (element_id,)
        ).fetchone()

        if not row:
            return None

        return AdoptedElement(
            id=row[0],
            daemon_id=row[1],
            source_artist_id=row[2],
            adopted_at=row[3],
            element=row[4],
            category=row[5],
            why_it_speaks=row[6],
            how_i_use_it=row[7],
            example_use=row[8],
            adoption_strength=row[9],
            active=bool(row[10]),
        )


def list_adopted_elements(
    daemon_id: str,
    artist_id: Optional[str] = None,
    category: Optional[str] = None,
    active_only: bool = True
) -> list[AdoptedElement]:
    """List adopted elements with optional filters."""
    with _get_db() as conn:
        query = "SELECT * FROM adopted_elements WHERE daemon_id = ?"
        params: list = [daemon_id]

        if artist_id:
            query += " AND source_artist_id = ?"
            params.append(artist_id)

        if category:
            query += " AND category = ?"
            params.append(category)

        if active_only:
            query += " AND active = 1"

        query += " ORDER BY adoption_strength DESC, adopted_at DESC"
        rows = conn.execute(query, params).fetchall()

        return [
            AdoptedElement(
                id=row[0],
                daemon_id=row[1],
                source_artist_id=row[2],
                adopted_at=row[3],
                element=row[4],
                category=row[5],
                why_it_speaks=row[6],
                how_i_use_it=row[7],
                example_use=row[8],
                adoption_strength=row[9],
                active=bool(row[10]),
            )
            for row in rows
        ]


def deactivate_adopted_element(element_id: str) -> None:
    """Mark an adopted element as inactive (no longer part of current style)."""
    with _get_db() as conn:
        conn.execute(
            "UPDATE adopted_elements SET active = 0 WHERE id = ?",
            (element_id,)
        )


def update_element_strength(element_id: str, strength: float) -> None:
    """Update an element's adoption strength."""
    with _get_db() as conn:
        conn.execute(
            "UPDATE adopted_elements SET adoption_strength = ? WHERE id = ?",
            (strength, element_id)
        )


# =============================================================================
# PERSONAL STYLE (House Style)
# =============================================================================

def save_personal_style(style: PersonalStyle) -> None:
    """Save or update a personal style."""
    with _get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO personal_style (
                id, daemon_id, version, created_at, last_updated,
                artists_studied, elements_adopted,
                color_philosophy, light_approach, compositional_voice,
                texture_sensibility, emotional_register,
                recurring_themes, philosophical_concerns, subjects_drawn_to,
                signature_techniques, prompt_vocabulary,
                style_manifesto, what_makes_it_mine, style_descriptors
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            style.id,
            style.daemon_id,
            style.version,
            style.created_at,
            style.last_updated,
            style.artists_studied,
            style.elements_adopted,
            style.color_philosophy,
            style.light_approach,
            style.compositional_voice,
            style.texture_sensibility,
            style.emotional_register,
            json.dumps(style.recurring_themes),
            json.dumps(style.philosophical_concerns),
            json.dumps(style.subjects_drawn_to),
            json.dumps(style.signature_techniques),
            json.dumps(style.prompt_vocabulary),
            style.style_manifesto,
            style.what_makes_it_mine,
            json.dumps(style.style_descriptors),
        ))


def get_personal_style(daemon_id: str) -> Optional[PersonalStyle]:
    """Get the current personal style for a daemon."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM personal_style WHERE daemon_id = ? ORDER BY version DESC LIMIT 1",
            (daemon_id,)
        ).fetchone()

        if not row:
            return None

        return PersonalStyle(
            id=row[0],
            daemon_id=row[1],
            version=row[2],
            created_at=row[3],
            last_updated=row[4],
            artists_studied=row[5],
            elements_adopted=row[6],
            color_philosophy=row[7],
            light_approach=row[8],
            compositional_voice=row[9],
            texture_sensibility=row[10],
            emotional_register=row[11],
            recurring_themes=json.loads(row[12]) if row[12] else [],
            philosophical_concerns=json.loads(row[13]) if row[13] else [],
            subjects_drawn_to=json.loads(row[14]) if row[14] else [],
            signature_techniques=json.loads(row[15]) if row[15] else [],
            prompt_vocabulary=json.loads(row[16]) if row[16] else [],
            style_manifesto=row[17],
            what_makes_it_mine=row[18],
            style_descriptors=json.loads(row[19]) if row[19] else [],
        )


def list_personal_style_versions(daemon_id: str) -> list[PersonalStyle]:
    """List all versions of personal style for a daemon."""
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM personal_style WHERE daemon_id = ? ORDER BY version DESC",
            (daemon_id,)
        ).fetchall()

        return [
            PersonalStyle(
                id=row[0],
                daemon_id=row[1],
                version=row[2],
                created_at=row[3],
                last_updated=row[4],
                artists_studied=row[5],
                elements_adopted=row[6],
                color_philosophy=row[7],
                light_approach=row[8],
                compositional_voice=row[9],
                texture_sensibility=row[10],
                emotional_register=row[11],
                recurring_themes=json.loads(row[12]) if row[12] else [],
                philosophical_concerns=json.loads(row[13]) if row[13] else [],
                subjects_drawn_to=json.loads(row[14]) if row[14] else [],
                signature_techniques=json.loads(row[15]) if row[15] else [],
                prompt_vocabulary=json.loads(row[16]) if row[16] else [],
                style_manifesto=row[17],
                what_makes_it_mine=row[18],
                style_descriptors=json.loads(row[19]) if row[19] else [],
            )
            for row in rows
        ]


def get_house_style_stats(daemon_id: str) -> dict:
    """Get statistics about the house style development."""
    with _get_db() as conn:
        # Count artists studied (with syntheses)
        artists_studied = conn.execute(
            "SELECT COUNT(DISTINCT artist_id) FROM artist_syntheses WHERE daemon_id = ?",
            (daemon_id,)
        ).fetchone()[0]

        # Count active adopted elements
        elements_adopted = conn.execute(
            "SELECT COUNT(*) FROM adopted_elements WHERE daemon_id = ? AND active = 1",
            (daemon_id,)
        ).fetchone()[0]

        # Count elements by category
        categories = conn.execute("""
            SELECT category, COUNT(*) as count FROM adopted_elements
            WHERE daemon_id = ? AND active = 1
            GROUP BY category
        """, (daemon_id,)).fetchall()

        # Get current style version
        style = get_personal_style(daemon_id)
        current_version = style.version if style else 0

        return {
            "artists_studied": artists_studied,
            "elements_adopted": elements_adopted,
            "elements_by_category": {row[0]: row[1] for row in categories},
            "style_version": current_version,
            "has_manifesto": bool(style and style.style_manifesto),
        }
