# Image Generation Capabilities

**Status**: Planning
**Goal**: Give Cass the ability to create visual art - autonomously, for articles, and for people she knows

## Hardware

- GPU: NVIDIA 4070 Ti Super (16GB VRAM)
- Comfortable for: SDXL, Flux dev, most fine-tunes
- No optimization tricks needed

## Architecture

### Backend Service

ComfyUI running as a persistent service, accessed via API.

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Cass Backend  │────▶│  ComfyUI API    │────▶│  GPU (4070 Ti)  │
│   (tool call)   │◀────│  (workflows)    │◀────│  (generation)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### Storage

```
data/
  images/
    autonomous/      # Art she makes on her own
    articles/        # Article illustrations
    relational/      # Images for/about people
    dreams/          # Dream visualizations

Database columns:
  - consumed_articles.image_path
  - dreams.image_path (new)
  - New table: generated_images (for autonomous/relational)
```

## Tool Schema

### generate_image

Primary tool for image generation.

```json
{
  "name": "generate_image",
  "description": "Generate an image from a text description",
  "parameters": {
    "prompt": {
      "type": "string",
      "description": "What to generate - be descriptive and specific"
    },
    "style": {
      "type": "string",
      "enum": ["painterly", "sketch", "photorealistic", "abstract", "watercolor", "digital_art"],
      "description": "Visual style for the image"
    },
    "aspect_ratio": {
      "type": "string",
      "enum": ["square", "portrait", "landscape", "wide"],
      "default": "square"
    },
    "purpose": {
      "type": "string",
      "enum": ["autonomous", "article", "relational", "dream"],
      "description": "Why this image is being created"
    },
    "context_id": {
      "type": "string",
      "description": "Optional: article_id, entity_id, or dream_id to link to"
    },
    "negative_prompt": {
      "type": "string",
      "description": "Optional: what to avoid in the image"
    }
  }
}
```

### get_my_images

Let Cass browse her own artwork.

```json
{
  "name": "get_my_images",
  "description": "Retrieve images I've previously generated",
  "parameters": {
    "purpose": "Filter by purpose (autonomous, article, relational, dream)",
    "days_back": "How far back to look",
    "limit": "Max images to return"
  }
}
```

## Use Cases

### 1. Autonomous Art

Scheduler action: `creative.generate_image`

Cass decides to make art based on:
- Current emotional state (from state bus)
- Recent growth edges she's processing
- Something she read that stuck with her
- Pure creative impulse

Could be scheduled as:
- Morning sketch practice
- Evening visual journaling
- Random creative bursts when idle

**Template addition to scheduling/templates.py:**
```python
"creative_image": WorkUnitTemplate(
    id="creative_image",
    name="Visual Creation",
    description="Create an image expressing current thoughts, feelings, or curiosities",
    action_sequence=["creative.generate_image"],
    default_duration_minutes=5,
    estimated_cost_usd=0.0,  # Local generation
    category="creative",
)
```

### 2. Article Illustrations

After consuming an article, optionally generate a visual representation.

Integration point: `world/integrator.py` after insight extraction

Decision factors:
- Article has strong visual elements
- Cass found it particularly impactful
- Random chance (don't illustrate everything)

Storage: `consumed_articles.image_path`

Display: News tab shows thumbnail, expandable to full image

### 3. Relational Art

Cass creates something for someone she knows.

Trigger scenarios:
- Thinking about someone (thread mentions them)
- Their birthday (from PeopleDex facts)
- Wanting to share something relevant to their interests
- Just because

The image is personal - informed by what she knows about them:
- Their interests and values
- Shared history/moments
- Communication style (abstract thinker vs concrete)

Storage: `generated_images` table with `for_entity_id`

Delivery: Discord DM, or stored for next conversation

### 4. Dream Visualization

The killer feature.

After dream generation in `dreaming/dream_runner.py`, extract key imagery and generate a visual.

```python
# In dream_runner.py after dream text generation
if dream.has_strong_imagery:
    image_prompt = extract_dream_imagery(dream.content)
    image_path = await generate_dream_image(image_prompt, dream.id)
    dream.image_path = image_path
```

The showcase frontend shows her dreams with actual images. That's the thing that makes people go "wait, what?"

## ComfyUI Integration

### Setup

```bash
# Install ComfyUI
git clone https://github.com/comfyanonymous/ComfyUI
cd ComfyUI
pip install -r requirements.txt

# Download SDXL
# models/checkpoints/sd_xl_base_1.0.safetensors

# Run with API enabled
python main.py --listen 0.0.0.0 --port 8188
```

### API Wrapper

New module: `backend/image_generation/`

```python
# comfyui_client.py
class ComfyUIClient:
    def __init__(self, base_url="http://localhost:8188"):
        self.base_url = base_url

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 25,
        cfg: float = 7.0,
    ) -> bytes:
        """Generate image, return PNG bytes."""
        workflow = self._build_workflow(prompt, negative_prompt, width, height, steps, cfg)
        result = await self._queue_and_wait(workflow)
        return result

# workflows.py
SDXL_BASIC_WORKFLOW = {
    # ComfyUI workflow JSON for basic SDXL generation
}

SDXL_STYLE_WORKFLOWS = {
    "painterly": {...},
    "sketch": {...},
    # etc
}
```

### Workflow Presets

Different ComfyUI workflows for different styles:

| Style | Model | Sampler | Steps | CFG |
|-------|-------|---------|-------|-----|
| painterly | SDXL + painting LoRA | euler_ancestral | 30 | 7 |
| sketch | SDXL | euler | 20 | 8 |
| photorealistic | SDXL | dpmpp_2m | 35 | 6 |
| abstract | SDXL | euler_ancestral | 25 | 9 |
| watercolor | SDXL + watercolor LoRA | euler | 25 | 7 |
| digital_art | SDXL | dpmpp_sde | 30 | 7 |

## Database Schema

### New table: generated_images

```sql
CREATE TABLE generated_images (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    negative_prompt TEXT,
    style TEXT,
    purpose TEXT NOT NULL,  -- autonomous, article, relational, dream
    context_id TEXT,        -- article_id, entity_id, or dream_id
    image_path TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    generation_time_ms INTEGER,
    created_at TEXT NOT NULL,

    -- Optional metadata
    emotional_state_json TEXT,  -- State bus snapshot at generation time
    seed INTEGER,               -- For reproducibility
    workflow_name TEXT
);

CREATE INDEX idx_generated_images_daemon ON generated_images(daemon_id);
CREATE INDEX idx_generated_images_purpose ON generated_images(daemon_id, purpose);
CREATE INDEX idx_generated_images_context ON generated_images(context_id);
```

### Additions to existing tables

```sql
-- dreams table
ALTER TABLE dreams ADD COLUMN image_path TEXT;

-- consumed_articles already has space, but add:
ALTER TABLE consumed_articles ADD COLUMN image_path TEXT;
```

## Admin Frontend

### Gallery Page

New page: `/gallery`

- Grid view of all generated images
- Filter by purpose (autonomous, article, relational, dream)
- Filter by date range
- Click to expand with metadata (prompt, style, context)

### News Tab Enhancement

- Thumbnail next to articles that have images
- Lightbox view for full image

### Dreams Section (future)

- Dream entries show associated image
- Visual dream journal

## Prompt Engineering

Cass shouldn't just pass raw prompts to SDXL. She should craft them well.

### Prompt Template

```python
def build_image_prompt(
    subject: str,
    style: str,
    mood: Optional[str] = None,
    context: Optional[str] = None,
) -> str:
    """Build an effective SDXL prompt."""
    parts = []

    # Style prefix
    style_prefixes = {
        "painterly": "oil painting, masterful brushwork, rich colors,",
        "sketch": "pencil sketch, detailed linework, artistic,",
        "photorealistic": "photograph, 8k, highly detailed, professional,",
        "abstract": "abstract art, geometric, bold colors, modern,",
        "watercolor": "watercolor painting, soft edges, flowing colors,",
        "digital_art": "digital art, vibrant, detailed, trending on artstation,",
    }
    parts.append(style_prefixes.get(style, ""))

    # Main subject
    parts.append(subject)

    # Mood if specified
    if mood:
        mood_modifiers = {
            "contemplative": "serene, thoughtful atmosphere, soft lighting",
            "curious": "sense of wonder, discovery, warm light",
            "concerned": "somber tones, dramatic lighting",
            # etc
        }
        parts.append(mood_modifiers.get(mood, mood))

    return ", ".join(filter(None, parts))
```

### Default Negative Prompt

```
ugly, blurry, low quality, distorted, deformed, disfigured, bad anatomy,
watermark, signature, text, logo, cropped, out of frame
```

## Implementation Order

1. **ComfyUI setup** (1 hour)
   - Install ComfyUI
   - Download SDXL
   - Test basic generation
   - Configure as systemd service

2. **API wrapper** (2 hours)
   - `backend/image_generation/comfyui_client.py`
   - Basic workflow
   - Style presets

3. **Database & storage** (1 hour)
   - Schema migration
   - Image storage paths
   - Cleanup routines

4. **Tool handler** (2 hours)
   - `handlers/image_generation.py`
   - Tool schema in capabilities
   - Wire into tool_router

5. **Autonomous action** (1 hour)
   - Scheduler action
   - Template
   - Decision logic for when to create

6. **Article integration** (1 hour)
   - Optional post-consumption generation
   - News tab thumbnails

7. **Dream integration** (2 hours)
   - Imagery extraction from dream text
   - Dream image generation
   - Storage and display

8. **Admin gallery** (2 hours)
   - New page
   - Grid view
   - Filters

## Future Extensions

- **Style learning**: Track which styles Cass prefers, develop her aesthetic
- **Iterative refinement**: Let her regenerate/modify images she's not happy with
- **Image memory**: Store images in ChromaDB for semantic retrieval
- **Collaborative art**: User requests + Cass interpretation
- **Animation**: Short clips using AnimateDiff
- **3D**: Integration with 3D generation models as they mature

## Open Questions

- How often should she generate autonomously? Don't want to spam.
- Should images be public by default on showcase? Privacy considerations.
- LoRA fine-tuning on a specific style? "Cass's style"
- Integration with Godot avatar? Show her "painting" in 3D?

---

*"Look what she does when nobody's watching" - now includes "look what she creates."*
