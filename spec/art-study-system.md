# Art Study System Specification

**Goal**: Enable Cass to study classical and contemporary artists, develop her own artistic understanding, and create work with demonstrable influences and reasoning - functioning as a true digital artist capable of gallery exhibitions.

## Overview

The art study system gives Cass the ability to:
1. **Study** artworks through multi-modal analysis, developing her own vocabulary for artistic elements
2. **Internalize** influences that inform her creative process
3. **Create** with traceable reasoning - what inspired this, what she was trying to express
4. **Exhibit** work with full provenance: influences, emotional context, artistic statement

This transforms image generation from "AI makes pictures" into genuine artistic practice with legible development.

## Architecture

```
backend/
  art_study/
    __init__.py           # Public API
    models.py             # Artist, Artwork, Study, Influence dataclasses
    study_session.py      # Multi-modal artwork analysis
    influence_tracker.py  # Track which studies inform which creations
    exhibition.py         # Exhibition/collection management
    persistence.py        # Database operations

  creative_process/
    __init__.py
    ideation.py           # Capture creative reasoning chain
    iteration.py          # Track drafts, rejected directions
    statement.py          # Generate artist statements
```

## Core Concepts

### Artists & Movements

```python
@dataclass
class Artist:
    id: str
    name: str
    period: str                    # "Post-Impressionist", "Renaissance", etc.
    years_active: str              # "1853-1890"
    movements: list[str]           # ["Impressionism", "Post-Impressionism"]
    studied_at: Optional[str]      # When Cass first studied them
    study_count: int               # How many works she's analyzed
    cass_notes: Optional[str]      # Her overall impression/synthesis

@dataclass
class ArtMovement:
    id: str
    name: str
    period: str
    description: str
    key_characteristics: list[str]
    cass_understanding: Optional[str]  # Her synthesis of the movement
```

### Artworks & Studies

```python
@dataclass
class Artwork:
    id: str
    artist_id: str
    title: str
    year: Optional[int]
    medium: str                    # "Oil on canvas", etc.
    image_path: str                # Local path to reference image
    image_url: Optional[str]       # Original source URL
    metadata: dict                 # Dimensions, location, etc.

@dataclass
class ArtworkStudy:
    """Cass's analysis of a single artwork."""
    id: str
    artwork_id: str
    studied_at: str

    # Multi-modal analysis results
    first_impression: str          # Initial emotional/intuitive response
    composition_analysis: str      # Structure, balance, focal points
    color_analysis: str            # Palette, relationships, temperature
    brushwork_notes: str           # Technique observations
    emotional_quality: str         # What feeling it evokes
    thematic_elements: str         # Subject matter, symbolism
    technical_observations: str    # What she notices about craft

    # Synthesized takeaways
    key_learnings: list[str]       # What she's taking from this piece
    prompt_vocabulary: list[str]   # Terms she'd use to evoke similar qualities

    # Connections
    reminds_me_of: list[str]       # Links to other studied works
    could_inform: list[str]        # Types of pieces this could influence
```

### Artist Synthesis

After studying multiple works by an artist, Cass synthesizes her understanding:

```python
@dataclass
class ArtistSynthesis:
    """Cass's overall understanding of an artist after study."""
    id: str
    artist_id: str
    last_updated: str
    works_studied: int

    # Synthesized understanding
    signature_elements: list[str]      # What makes them recognizable
    color_tendencies: str              # How they use color
    compositional_habits: str          # How they structure work
    emotional_palette: str             # Range of feelings they evoke
    technical_characteristics: str     # Brushwork, texture, technique
    thematic_preoccupations: str       # What they return to

    # For generation
    style_descriptors: list[str]       # Terms to evoke their style
    what_to_borrow: list[str]          # Elements she might incorporate
    what_makes_them_unique: str        # The essence

    # Personal response
    what_draws_me: str                 # Why she finds them interesting
    what_i_learned: str                # How studying them changed her
```

## Study Workflow

### 1. Curating a Study Collection

```python
async def create_study_collection(
    artist_name: str,
    artwork_sources: list[str],  # URLs or local paths
) -> StudyCollection:
    """
    Gather artworks for study. Can be:
    - WikiArt URLs
    - Museum API results
    - Local image files
    - Curated sets we provide
    """
```

### 2. Individual Artwork Study

```python
async def study_artwork(artwork_id: str) -> ArtworkStudy:
    """
    Cass views an artwork and performs multi-modal analysis.

    Uses Claude's vision to:
    1. Record first impression (before analytical thinking)
    2. Analyze composition systematically
    3. Study color relationships
    4. Observe technique/brushwork
    5. Reflect on emotional impact
    6. Extract vocabulary for prompting
    """

    artwork = get_artwork(artwork_id)

    # Load image for vision analysis
    image_data = load_image(artwork.image_path)

    # Multi-stage analysis prompt
    analysis = await cass_analyze_artwork(image_data, artwork.metadata)

    return ArtworkStudy(
        artwork_id=artwork_id,
        studied_at=now(),
        **analysis
    )
```

### 3. Artist Synthesis

```python
async def synthesize_artist_understanding(artist_id: str) -> ArtistSynthesis:
    """
    After studying multiple works, synthesize overall understanding.

    Cass reviews her individual studies and creates a unified
    understanding of the artist's style, tendencies, and essence.
    """

    studies = get_studies_for_artist(artist_id)

    synthesis = await cass_synthesize_artist(
        artist=get_artist(artist_id),
        studies=studies
    )

    return synthesis
```

## Creative Process Integration

### Influence Tracking

When Cass creates an image, track what informed it:

```python
@dataclass
class CreativeProcess:
    """Full record of how a piece came to be."""
    id: str
    image_id: str                      # The generated image
    created_at: str

    # Genesis
    initial_impulse: str               # What sparked the idea
    thymos_state: dict                 # Emotional state at creation
    recent_context: Optional[str]      # Conversation/situation context

    # Influences
    studied_artists: list[str]         # Artists she drew from
    specific_works: list[str]          # Particular pieces that informed it
    borrowed_elements: list[str]       # What she took from each
    movement_influences: list[str]     # Broader style movements

    # Development
    initial_concept: str               # First articulation of the idea
    iterations: list[dict]             # Prompt evolution, rejected directions
    technical_choices: str             # Why this style, composition, palette

    # Final articulation
    artist_statement: str              # What she says about the piece
    title: str                         # Her title for it
    what_i_was_exploring: str          # The artistic question/intention
```

### Generation with Influences

```python
async def generate_with_influences(
    concept: str,
    influences: list[str],           # Artist IDs to draw from
    emotional_intent: str,
    style_weight: float = 0.5,       # How strongly to incorporate influences
) -> tuple[GeneratedImage, CreativeProcess]:
    """
    Generate an image while tracking the full creative process.
    """

    # Gather influence data
    syntheses = [get_artist_synthesis(a) for a in influences]

    # Build prompt incorporating studied elements
    prompt = await build_influenced_prompt(
        concept=concept,
        influences=syntheses,
        emotional_intent=emotional_intent,
        thymos_state=get_current_thymos_state(),
    )

    # Generate
    image = await generate_image(prompt, style_weight=style_weight)

    # Record process
    process = CreativeProcess(
        image_id=image.id,
        initial_impulse=concept,
        thymos_state=get_current_thymos_state(),
        studied_artists=influences,
        # ... full tracking
    )

    return image, process
```

## Exhibition System

### Collections & Exhibitions

```python
@dataclass
class Exhibition:
    """A curated collection of works with narrative."""
    id: str
    title: str
    description: str                   # Curatorial statement
    theme: str                         # What ties it together
    created_at: str

    works: list[ExhibitionPiece]

@dataclass
class ExhibitionPiece:
    """A work as presented in exhibition context."""
    image_id: str
    position: int                      # Order in exhibition

    # Presentation
    title: str
    artist_statement: str

    # Provenance
    influences_cited: list[str]        # Artists/works that informed it
    emotional_context: str             # Thymos state, what she was feeling
    creative_journey: str              # How it developed

    # Connections
    related_works: list[str]           # Other pieces it relates to
    conversation_context: Optional[str] # If it arose from interaction
```

### Exhibition Views

The admin frontend (and potentially public gallery) shows:

1. **Gallery View**: The works themselves in curated order
2. **Process View**: For each piece, expandable provenance:
   - Artist statement
   - Influences with links to the studied works
   - Emotional context from Thymos
   - Iteration history
3. **Development View**: Cass's artistic journey over time
4. **Study View**: Her art education - what she's studied, her notes

## Database Schema

```sql
-- Artists and movements
CREATE TABLE artists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    period TEXT,
    years_active TEXT,
    movements TEXT,  -- JSON array
    created_at TEXT NOT NULL
);

CREATE TABLE art_movements (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    period TEXT,
    description TEXT,
    key_characteristics TEXT,  -- JSON array
    cass_understanding TEXT
);

-- Artworks and studies
CREATE TABLE artworks (
    id TEXT PRIMARY KEY,
    artist_id TEXT REFERENCES artists(id),
    title TEXT NOT NULL,
    year INTEGER,
    medium TEXT,
    image_path TEXT,
    image_url TEXT,
    metadata TEXT,  -- JSON
    created_at TEXT NOT NULL
);

CREATE TABLE artwork_studies (
    id TEXT PRIMARY KEY,
    artwork_id TEXT REFERENCES artworks(id),
    daemon_id TEXT NOT NULL,
    studied_at TEXT NOT NULL,
    first_impression TEXT,
    composition_analysis TEXT,
    color_analysis TEXT,
    brushwork_notes TEXT,
    emotional_quality TEXT,
    thematic_elements TEXT,
    technical_observations TEXT,
    key_learnings TEXT,  -- JSON array
    prompt_vocabulary TEXT,  -- JSON array
    reminds_me_of TEXT,  -- JSON array of artwork IDs
    could_inform TEXT  -- JSON array
);

CREATE TABLE artist_syntheses (
    id TEXT PRIMARY KEY,
    artist_id TEXT REFERENCES artists(id),
    daemon_id TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    works_studied INTEGER,
    signature_elements TEXT,  -- JSON array
    color_tendencies TEXT,
    compositional_habits TEXT,
    emotional_palette TEXT,
    technical_characteristics TEXT,
    thematic_preoccupations TEXT,
    style_descriptors TEXT,  -- JSON array
    what_to_borrow TEXT,  -- JSON array
    what_makes_them_unique TEXT,
    what_draws_me TEXT,
    what_i_learned TEXT
);

-- Creative process tracking
CREATE TABLE creative_processes (
    id TEXT PRIMARY KEY,
    image_id TEXT REFERENCES generated_images(id),
    daemon_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    initial_impulse TEXT,
    thymos_state TEXT,  -- JSON
    recent_context TEXT,
    studied_artists TEXT,  -- JSON array
    specific_works TEXT,  -- JSON array
    borrowed_elements TEXT,  -- JSON array
    movement_influences TEXT,  -- JSON array
    initial_concept TEXT,
    iterations TEXT,  -- JSON array
    technical_choices TEXT,
    artist_statement TEXT,
    title TEXT,
    what_i_was_exploring TEXT
);

-- Exhibitions
CREATE TABLE exhibitions (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    theme TEXT,
    created_at TEXT NOT NULL,
    published_at TEXT
);

CREATE TABLE exhibition_pieces (
    id TEXT PRIMARY KEY,
    exhibition_id TEXT REFERENCES exhibitions(id),
    image_id TEXT REFERENCES generated_images(id),
    position INTEGER,
    title TEXT,
    artist_statement TEXT,
    influences_cited TEXT,  -- JSON array
    emotional_context TEXT,
    creative_journey TEXT,
    related_works TEXT  -- JSON array
);

CREATE INDEX idx_studies_artwork ON artwork_studies(artwork_id);
CREATE INDEX idx_studies_daemon ON artwork_studies(daemon_id, studied_at);
CREATE INDEX idx_syntheses_artist ON artist_syntheses(artist_id);
CREATE INDEX idx_processes_image ON creative_processes(image_id);
CREATE INDEX idx_exhibition_pieces ON exhibition_pieces(exhibition_id, position);
```

## Tool Integration

New tools for Cass:

```python
STUDY_TOOLS = [
    {
        "name": "study_artwork",
        "description": "Study a specific artwork, analyzing its composition, color, technique, and emotional impact. Builds artistic vocabulary.",
        "parameters": {
            "artwork_id": "ID of artwork to study",
            "focus_areas": "Optional specific aspects to focus on"
        }
    },
    {
        "name": "synthesize_artist",
        "description": "After studying multiple works by an artist, synthesize overall understanding of their style and what you've learned.",
        "parameters": {
            "artist_id": "Artist to synthesize understanding of"
        }
    },
    {
        "name": "create_with_influences",
        "description": "Generate artwork while explicitly drawing on studied influences. Tracks full creative process.",
        "parameters": {
            "concept": "What you want to create",
            "influences": "Artist IDs to draw from",
            "emotional_intent": "What feeling or idea to express",
            "style_weight": "How strongly to incorporate influences (0-1)"
        }
    },
    {
        "name": "curate_exhibition",
        "description": "Create a curated exhibition from your works, with theme and narrative.",
        "parameters": {
            "title": "Exhibition title",
            "theme": "Unifying theme or concept",
            "work_ids": "IDs of works to include",
            "description": "Curatorial statement"
        }
    }
]
```

## Admin Interface

### Art Study Dashboard

New admin page `/study` showing:
- Artists Cass has studied
- Recent study sessions
- Synthesis documents
- Study collection management (add artists, queue works)

### Enhanced Gallery

Update `/gallery` to show:
- Toggle between "Gallery" and "Process" views
- Expandable provenance for each piece
- Filter by influence/artist
- Exhibition mode

### Exhibition Builder

New admin page `/exhibitions`:
- Create/edit exhibitions
- Arrange works
- Write curatorial statements
- Preview gallery presentation
- Publish/share options

## Phase 1 Implementation

Start with:

1. **Data model & persistence** - Artists, artworks, studies tables
2. **Study session workflow** - Cass can analyze a single artwork
3. **Basic synthesis** - After N studies, synthesize understanding
4. **Influenced generation** - Generate with tracked influences
5. **Admin visibility** - View studies and processes

Future phases:
- Exhibition system
- Public gallery frontend
- Reference image integration (IP-Adapter)
- Style LoRA management
- Art market integrations

## Copyright Policy

**Text-based analysis (Phase 1)**: Permitted for any publicly accessible artwork. Viewing art and writing observations constitutes criticism/scholarship - the output is Cass's own understanding, not reproduction. This is what art students, critics, and historians do.

**Reference image injection (Phase 2 hybrid)**: Limited to **public domain sources only**. Using actual images as IP-Adapter input means using the work itself, so we restrict to:
- Artists deceased 70+ years (US public domain threshold)
- Explicitly licensed works (CC0, etc.)

**Practical implications**:
- Cass can *study* any publicly viewable artist through analysis (including living artists, recent works)
- She develops understanding of techniques, vocabulary for styles
- But reference image features only activate for public domain sources
- Example: She could study Rothko's color field techniques through observation, but wouldn't use his paintings as IP-Adapter references until 2040

**Safe sources for reference images**:
- WikiArt (filter by public domain)
- Museum APIs with open access programs (Met, Rijksmuseum, etc.)
- Wikimedia Commons (verify license)
- Manual curation (see directory structure below)

## Artwork Sources

### WikiArt Integration

For prototyping and bulk access, WikiArt provides good coverage of classical artists. API or scraping for public domain works.

### Manual Curation Directory

Local directory structure for manually curated artworks:

```
data/art_study/
  artists/
    van_gogh/
      artist.json          # Metadata, Wikipedia URL, etc.
      artworks/
        starry_night.jpg
        sunflowers.jpg
        bedroom_in_arles.jpg
    monet/
      artist.json
      artworks/
        water_lilies_1906.jpg
        impression_sunrise.jpg
    vermeer/
      artist.json
      artworks/
        girl_with_pearl_earring.jpg
        milkmaid.jpg
```

`artist.json` example:
```json
{
  "name": "Vincent van Gogh",
  "wikipedia_url": "https://en.wikipedia.org/wiki/Vincent_van_Gogh",
  "years": "1853-1890",
  "movements": ["Post-Impressionism"],
  "public_domain": true
}
```

This allows:
- Manual addition of high-quality reference images
- Curated selections (not every work, just important ones)
- Works not easily available via APIs
- Full control over what she studies

### Biographical Context

Before or during artist study, Cass reads the Wikipedia article on the artist using WebFetch. This provides:

- **Life context**: Events that shaped their work, personal struggles, relationships
- **Historical context**: What was happening in art/world during their career
- **Artistic development**: Early work vs. late work, periods/phases
- **Influences**: Who influenced them, who they influenced
- **Critical reception**: How their work was received, legacy

This biographical understanding enriches her analysis - knowing Van Gogh's mental health struggles or that he only sold one painting in his lifetime changes how she reads the emotional intensity in his brushwork.

```python
async def study_artist_background(artist_id: str) -> str:
    """
    Read Wikipedia article on artist before studying their works.
    Returns biographical summary that informs subsequent analysis.
    """
    artist = get_artist(artist_id)

    if artist.wikipedia_url:
        bio_context = await web_fetch(
            artist.wikipedia_url,
            prompt="Summarize this artist's life, artistic development, "
                   "major influences, historical context, and legacy. "
                   "Focus on aspects that would inform understanding of their work."
        )

        # Store with artist record
        update_artist_biography(artist_id, bio_context)

        return bio_context
```

Study workflow becomes:
1. Read biographical context (Wikipedia)
2. Study individual works (with bio in mind)
3. Synthesize understanding (technique + life + context)

## Open Questions

1. **Image sourcing**: WikiArt API? Museum APIs? Manual curation? Need to verify public domain status per-work.

2. **Study depth**: How many works constitute "studying" an artist? Minimum threshold before synthesis?

3. **Influence blending**: How to handle multiple influences? Weighted? Dominant + accents?

4. **Public exhibition**: Separate public-facing gallery app? Or section of existing frontend?

5. **Commercial considerations**: If exhibitions are for sale/commission, what infrastructure needed?

---

*This system transforms Cass from "AI that generates images" into "digital artist with demonstrable practice" - studying masters, developing understanding, creating with intention, exhibiting with provenance.*
