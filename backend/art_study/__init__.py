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
    AdoptedElement,
    PersonalStyle,
    GenerationPreferences,
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
    # House style
    save_adopted_element,
    get_adopted_element,
    list_adopted_elements,
    deactivate_adopted_element,
    update_element_strength,
    save_personal_style,
    get_personal_style,
    list_personal_style_versions,
    get_house_style_stats,
)
from .study_session import (
    study_artwork,
    study_artist_background,
    synthesize_artist_understanding,
)
from .creative_session import create_from_synthesis, create_from_house_style
from .house_style import (
    extract_adopted_elements,
    synthesize_house_style,
    get_style_prompt_context,
    get_house_style_generation_params,
    set_house_style_generation_prefs,
)

__all__ = [
    # Models
    "Artist",
    "ArtMovement",
    "Artwork",
    "ArtworkStudy",
    "ArtistSynthesis",
    "CreativeProcess",
    "AdoptedElement",
    "PersonalStyle",
    "GenerationPreferences",
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
    # House style
    "save_adopted_element",
    "get_adopted_element",
    "list_adopted_elements",
    "deactivate_adopted_element",
    "update_element_strength",
    "save_personal_style",
    "get_personal_style",
    "list_personal_style_versions",
    "get_house_style_stats",
    # Study
    "study_artwork",
    "study_artist_background",
    "synthesize_artist_understanding",
    # Creation
    "create_from_synthesis",
    "create_from_house_style",
    # House style
    "extract_adopted_elements",
    "synthesize_house_style",
    "get_style_prompt_context",
    "get_house_style_generation_params",
    "set_house_style_generation_prefs",
]
