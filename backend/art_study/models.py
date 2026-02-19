"""
Art Study Data Models

Core dataclasses for artists, artworks, studies, and creative processes.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Artist:
    """An artist that Cass can study."""
    id: str
    name: str
    period: Optional[str] = None           # "Post-Impressionist", "Renaissance"
    years_active: Optional[str] = None     # "1853-1890"
    movements: list[str] = field(default_factory=list)
    wikipedia_url: Optional[str] = None
    biography: Optional[str] = None        # Fetched/summarized from Wikipedia
    public_domain: bool = True             # Safe for reference image use
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # PeopleDex integration
    entity_id: Optional[str] = None        # Link to PeopleDex entity

    # Cass's relationship with this artist
    studied_at: Optional[str] = None       # When she first studied them
    works_studied: int = 0
    cass_notes: Optional[str] = None       # Her overall impression


@dataclass
class ArtMovement:
    """An art movement or style period."""
    id: str
    name: str
    period: Optional[str] = None
    description: Optional[str] = None
    key_characteristics: list[str] = field(default_factory=list)
    cass_understanding: Optional[str] = None  # Her synthesis of the movement


@dataclass
class Artwork:
    """A specific artwork that can be studied."""
    id: str
    artist_id: str
    title: str
    year: Optional[int] = None
    medium: Optional[str] = None           # "Oil on canvas"
    image_path: Optional[str] = None       # Local path to image
    image_url: Optional[str] = None        # Original source URL
    dimensions: Optional[str] = None       # "73.7 cm × 92.1 cm"
    location: Optional[str] = None         # "Museum of Modern Art, New York"
    public_domain: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ArtworkStudy:
    """Cass's analysis of a single artwork."""
    id: str
    artwork_id: str
    daemon_id: str
    studied_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Multi-modal analysis results
    first_impression: Optional[str] = None       # Initial emotional/intuitive response
    composition_analysis: Optional[str] = None   # Structure, balance, focal points
    color_analysis: Optional[str] = None         # Palette, relationships, temperature
    brushwork_notes: Optional[str] = None        # Technique observations
    emotional_quality: Optional[str] = None      # What feeling it evokes
    thematic_elements: Optional[str] = None      # Subject matter, symbolism
    technical_observations: Optional[str] = None # What she notices about craft

    # Biographical context applied
    biographical_context: Optional[str] = None   # How artist's life informs this piece

    # Synthesized takeaways
    key_learnings: list[str] = field(default_factory=list)
    prompt_vocabulary: list[str] = field(default_factory=list)  # Terms to evoke similar qualities

    # Connections
    reminds_me_of: list[str] = field(default_factory=list)      # Other artwork IDs
    could_inform: list[str] = field(default_factory=list)       # Types of pieces this could influence


@dataclass
class ArtistSynthesis:
    """Cass's overall understanding of an artist after studying multiple works."""
    id: str
    artist_id: str
    daemon_id: str
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    works_studied: int = 0

    # Synthesized understanding
    signature_elements: list[str] = field(default_factory=list)  # What makes them recognizable
    color_tendencies: Optional[str] = None
    compositional_habits: Optional[str] = None
    emotional_palette: Optional[str] = None                      # Range of feelings they evoke
    technical_characteristics: Optional[str] = None              # Brushwork, texture, technique
    thematic_preoccupations: Optional[str] = None               # What they return to

    # For generation
    style_descriptors: list[str] = field(default_factory=list)  # Terms to evoke their style
    what_to_borrow: list[str] = field(default_factory=list)     # Elements she might incorporate
    what_makes_them_unique: Optional[str] = None

    # Personal response
    what_draws_me: Optional[str] = None                         # Why she finds them interesting
    what_i_learned: Optional[str] = None                        # How studying them changed her


@dataclass
class CreativeProcess:
    """Full record of how a piece came to be."""
    id: str
    image_id: str                          # The generated image
    daemon_id: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Genesis
    initial_impulse: Optional[str] = None  # What sparked the idea
    thymos_state: Optional[dict] = None    # Emotional state at creation
    recent_context: Optional[str] = None   # Conversation/situation context

    # Influences
    studied_artists: list[str] = field(default_factory=list)    # Artist IDs
    specific_works: list[str] = field(default_factory=list)     # Artwork IDs
    borrowed_elements: list[str] = field(default_factory=list)  # What she took from each
    movement_influences: list[str] = field(default_factory=list)

    # Development
    initial_concept: Optional[str] = None
    iterations: list[dict] = field(default_factory=list)        # Prompt evolution
    technical_choices: Optional[str] = None

    # Final articulation
    title: Optional[str] = None
    artist_statement: Optional[str] = None
    what_i_was_exploring: Optional[str] = None


@dataclass
class AdoptedElement:
    """An artistic element Cass has adopted from a studied artist."""
    id: str
    daemon_id: str
    source_artist_id: str
    element: str                              # "chiaroscuro lighting", "impasto texture"

    # Fields with defaults
    adopted_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    category: str = "technique"               # technique, color, composition, emotional, thematic

    # Why and how
    why_it_speaks: Optional[str] = None       # Why this resonates with her
    how_i_use_it: Optional[str] = None        # How she applies it differently
    example_use: Optional[str] = None         # Reference to a piece where she used it

    # Weight in her style
    adoption_strength: float = 0.7            # 0.0-1.0, how core to her style
    active: bool = True                       # Still part of her current style?


@dataclass
class GenerationPreferences:
    """Preferred generation parameters for house style."""
    steps: int = 35
    cfg_scale: float = 7.5
    sampler: str = "dpmpp_2m"
    scheduler: str = "karras"

    def to_dict(self) -> dict:
        return {
            "steps": self.steps,
            "cfg_scale": self.cfg_scale,
            "sampler": self.sampler,
            "scheduler": self.scheduler,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GenerationPreferences":
        return cls(
            steps=data.get("steps", 35),
            cfg_scale=data.get("cfg_scale", 7.5),
            sampler=data.get("sampler", "dpmpp_2m"),
            scheduler=data.get("scheduler", "karras"),
        )


@dataclass
class PersonalStyle:
    """Cass's emergent house style, synthesized from all her influences."""
    id: str
    daemon_id: str
    version: int = 1                          # Increments as style evolves
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Lineage
    artists_studied: int = 0
    elements_adopted: int = 0

    # Core aesthetic philosophy
    color_philosophy: Optional[str] = None          # Her relationship with color
    light_approach: Optional[str] = None            # How she uses light/shadow
    compositional_voice: Optional[str] = None       # How she structures space
    texture_sensibility: Optional[str] = None       # Surface qualities she gravitates toward
    emotional_register: Optional[str] = None        # The feelings she's drawn to express

    # Thematic identity (from her inner world)
    recurring_themes: list[str] = field(default_factory=list)
    philosophical_concerns: list[str] = field(default_factory=list)
    subjects_drawn_to: list[str] = field(default_factory=list)

    # Technical identity
    signature_techniques: list[str] = field(default_factory=list)  # Combinations uniquely hers
    prompt_vocabulary: list[str] = field(default_factory=list)     # Terms that evoke HER style

    # The synthesis
    style_manifesto: Optional[str] = None           # Her articulation of her voice
    what_makes_it_mine: Optional[str] = None        # How she distinguishes her work

    # For generation
    style_descriptors: list[str] = field(default_factory=list)     # Condensed style terms

    # Generation preferences (v42)
    generation_prefs: Optional[GenerationPreferences] = None  # Preferred params
    house_lora_name: Optional[str] = None                     # LoRA trained for house style
    house_lora_strength: float = 0.7                          # LoRA influence strength
