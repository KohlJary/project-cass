"""
Curated Artist List for Cass's Art Studies

Artists with strong representation in the Metropolitan Museum of Art collection,
selected for diverse techniques, styles, and learning opportunities.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CuratedArtist:
    """An artist recommended for study."""
    name: str
    birth_year: Optional[int]
    death_year: Optional[int]
    nationality: str
    movement: str
    why_study: str  # What Cass can learn from this artist
    techniques: list[str]  # Key techniques to observe
    met_search_name: str  # Name to use when searching Met API
    wikipedia_url: str  # Wikipedia article for biographical context


# Artists organized by what they can teach
CURATED_ARTISTS: list[CuratedArtist] = [
    # === LIGHT & ATMOSPHERE ===
    CuratedArtist(
        name="Claude Monet",
        birth_year=1840,
        death_year=1926,
        nationality="French",
        movement="Impressionism",
        why_study="Master of capturing light and atmosphere. His loose brushwork "
                  "and attention to color shifts throughout the day offer lessons "
                  "in seeing beyond surface appearances.",
        techniques=["broken color", "wet-on-wet", "plein air", "series painting"],
        met_search_name="Claude Monet",
        wikipedia_url="https://en.wikipedia.org/wiki/Claude_Monet",
    ),
    CuratedArtist(
        name="J.M.W. Turner",
        birth_year=1775,
        death_year=1851,
        nationality="British",
        movement="Romanticism",
        why_study="Pushed painting toward abstraction through light. His later works "
                  "dissolve form into pure luminosity - a precursor to both Impressionism "
                  "and abstract expressionism.",
        techniques=["atmospheric perspective", "vortex compositions", "glazing", "impasto highlights"],
        met_search_name="Joseph Mallord William Turner",
        wikipedia_url="https://en.wikipedia.org/wiki/J._M._W._Turner",
    ),
    CuratedArtist(
        name="Johannes Vermeer",
        birth_year=1632,
        death_year=1675,
        nationality="Dutch",
        movement="Dutch Golden Age",
        why_study="Unmatched mastery of light falling on surfaces. His intimate domestic "
                  "scenes teach careful observation and the poetry of everyday moments.",
        techniques=["pointillé highlights", "optical effects", "limited palette", "camera obscura composition"],
        met_search_name="Johannes Vermeer",
        wikipedia_url="https://en.wikipedia.org/wiki/Johannes_Vermeer",
    ),

    # === DRAMA & EMOTION ===
    CuratedArtist(
        name="Caravaggio",
        birth_year=1571,
        death_year=1610,
        nationality="Italian",
        movement="Baroque",
        why_study="Revolutionary use of tenebrism - dramatic contrast between light and dark. "
                  "His theatrical lighting and raw emotional intensity changed Western art.",
        techniques=["tenebrism", "chiaroscuro", "dramatic staging", "direct observation"],
        met_search_name="Caravaggio",
        wikipedia_url="https://en.wikipedia.org/wiki/Caravaggio",
    ),
    CuratedArtist(
        name="El Greco",
        birth_year=1541,
        death_year=1614,
        nationality="Greek/Spanish",
        movement="Mannerism",
        why_study="Elongated forms and ecstatic color express spiritual intensity. "
                  "His unique vision shows how personal style transcends convention.",
        techniques=["figure elongation", "expressive color", "dynamic composition", "visible brushwork"],
        met_search_name="El Greco",
        wikipedia_url="https://en.wikipedia.org/wiki/El_Greco",
    ),
    CuratedArtist(
        name="Edvard Munch",
        birth_year=1863,
        death_year=1944,
        nationality="Norwegian",
        movement="Expressionism",
        why_study="Pioneer of emotional expression through distortion. His work demonstrates "
                  "how internal states can be externalized through color and form.",
        techniques=["psychological color", "simplified forms", "woodcut influence", "symbolic imagery"],
        met_search_name="Edvard Munch",
        wikipedia_url="https://en.wikipedia.org/wiki/Edvard_Munch",
    ),

    # === COLOR & FORM ===
    CuratedArtist(
        name="Paul Cézanne",
        birth_year=1839,
        death_year=1906,
        nationality="French",
        movement="Post-Impressionism",
        why_study="Father of modern art - his analytical approach to form influenced Cubism "
                  "and abstraction. Shows how to build structure through color planes.",
        techniques=["constructive brushstroke", "passage", "modulated color", "multiple viewpoints"],
        met_search_name="Paul Cézanne",
        wikipedia_url="https://en.wikipedia.org/wiki/Paul_C%C3%A9zanne",
    ),
    CuratedArtist(
        name="Henri Matisse",
        birth_year=1869,
        death_year=1954,
        nationality="French",
        movement="Fauvism/Modernism",
        why_study="Liberated color from representation. His bold, joyful palette and "
                  "simplified forms teach that less can express more.",
        techniques=["arbitrary color", "flat planes", "decorative pattern", "expressive line"],
        met_search_name="Henri Matisse",
        wikipedia_url="https://en.wikipedia.org/wiki/Henri_Matisse",
    ),
    CuratedArtist(
        name="Titian",
        birth_year=1488,
        death_year=1576,
        nationality="Italian",
        movement="Venetian Renaissance",
        why_study="Supreme colorist of the Renaissance. His rich, luminous color and loose "
                  "late brushwork influenced everyone from Rubens to the Impressionists.",
        techniques=["Venetian color", "glazing", "colorito vs disegno", "loose late style"],
        met_search_name="Titian",
        wikipedia_url="https://en.wikipedia.org/wiki/Titian",
    ),

    # === MOVEMENT & LIFE ===
    CuratedArtist(
        name="Edgar Degas",
        birth_year=1834,
        death_year=1917,
        nationality="French",
        movement="Impressionism",
        why_study="Master of capturing movement and unconventional composition. His "
                  "asymmetric framing and cropped figures bring modern dynamism.",
        techniques=["cropped composition", "unusual viewpoints", "pastel technique", "movement capture"],
        met_search_name="Edgar Degas",
        wikipedia_url="https://en.wikipedia.org/wiki/Edgar_Degas",
    ),
    CuratedArtist(
        name="Peter Paul Rubens",
        birth_year=1577,
        death_year=1640,
        nationality="Flemish",
        movement="Baroque",
        why_study="Virtuoso handling of flesh, fabric, and dynamic composition. His "
                  "energetic brushwork and monumental vision define Baroque grandeur.",
        techniques=["flesh tones", "dynamic composition", "rich impasto", "workshop collaboration"],
        met_search_name="Peter Paul Rubens",
        wikipedia_url="https://en.wikipedia.org/wiki/Peter_Paul_Rubens",
    ),
    CuratedArtist(
        name="John Singer Sargent",
        birth_year=1856,
        death_year=1925,
        nationality="American",
        movement="Realism/Impressionism",
        why_study="Perhaps the greatest portrait painter since Velázquez. His bravura "
                  "brushwork captures character and surface with apparent effortlessness.",
        techniques=["alla prima", "bravura brushwork", "selective detail", "confident marks"],
        met_search_name="John Singer Sargent",
        wikipedia_url="https://en.wikipedia.org/wiki/John_Singer_Sargent",
    ),

    # === MODERN VISION ===
    CuratedArtist(
        name="Édouard Manet",
        birth_year=1832,
        death_year=1883,
        nationality="French",
        movement="Realism/Impressionism",
        why_study="Bridge between old masters and modernism. His flat planes, bold contrasts, "
                  "and modern subject matter revolutionized what painting could be.",
        techniques=["flat modeling", "bold contrasts", "modern subjects", "Spanish influence"],
        met_search_name="Édouard Manet",
        wikipedia_url="https://en.wikipedia.org/wiki/%C3%89douard_Manet",
    ),
    CuratedArtist(
        name="Mary Cassatt",
        birth_year=1844,
        death_year=1926,
        nationality="American",
        movement="Impressionism",
        why_study="Intimate observer of domestic life and mother-child relationships. "
                  "Her pastel technique and Japanese-influenced compositions are distinctive.",
        techniques=["pastel mastery", "Japanese influence", "intimate observation", "warm palette"],
        met_search_name="Mary Cassatt",
        wikipedia_url="https://en.wikipedia.org/wiki/Mary_Cassatt",
    ),
    CuratedArtist(
        name="Winslow Homer",
        birth_year=1836,
        death_year=1910,
        nationality="American",
        movement="Realism",
        why_study="American master of watercolor and oil. His seascapes and genre scenes "
                  "capture nature's power and human resilience with directness.",
        techniques=["watercolor mastery", "dramatic light", "narrative clarity", "natural observation"],
        met_search_name="Winslow Homer",
        wikipedia_url="https://en.wikipedia.org/wiki/Winslow_Homer",
    ),
]


def get_curated_artists() -> list[CuratedArtist]:
    """Get the full list of curated artists."""
    return CURATED_ARTISTS


def get_artists_by_movement(movement: str) -> list[CuratedArtist]:
    """Filter artists by movement/style."""
    return [a for a in CURATED_ARTISTS if movement.lower() in a.movement.lower()]


def get_artist_by_name(name: str) -> Optional[CuratedArtist]:
    """Find a curated artist by name."""
    name_lower = name.lower()
    for artist in CURATED_ARTISTS:
        if name_lower in artist.name.lower():
            return artist
    return None
