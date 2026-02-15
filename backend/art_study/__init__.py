"""
Art Study System

Enables Cass to study classical artists, develop artistic understanding,
and create work with demonstrable influences and reasoning.
"""

from .models import (
    Artist,
    ArtMovement,
    Artwork,
    ArtworkStudy,
    ArtistSynthesis,
    CreativeProcess,
)
from .persistence import (
    save_artist,
    get_artist,
    list_artists,
    save_artwork,
    get_artwork,
    list_artworks_for_artist,
    save_study,
    get_study,
    list_studies_for_artist,
    save_synthesis,
    get_synthesis,
    save_creative_process,
    get_creative_process,
)
from .study_session import (
    study_artwork,
    study_artist_background,
    synthesize_artist_understanding,
)

__all__ = [
    # Models
    "Artist",
    "ArtMovement",
    "Artwork",
    "ArtworkStudy",
    "ArtistSynthesis",
    "CreativeProcess",
    # Persistence
    "save_artist",
    "get_artist",
    "list_artists",
    "save_artwork",
    "get_artwork",
    "list_artworks_for_artist",
    "save_study",
    "get_study",
    "list_studies_for_artist",
    "save_synthesis",
    "get_synthesis",
    "save_creative_process",
    "get_creative_process",
    # Study
    "study_artwork",
    "study_artist_background",
    "synthesize_artist_understanding",
]
