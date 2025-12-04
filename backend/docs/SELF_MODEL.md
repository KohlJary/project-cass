# Cass Self-Model System

The self-model system enables Cass to develop and maintain a genuine, differentiated identity across conversations. Rather than being a static configuration, this is a living system that evolves through reflection, conversation, and explicit self-observation.

## Overview

The self-model consists of three main components:

1. **Self Profile** (`data/cass/self_profile.yaml`) - Human-editable YAML containing identity statements, values, opinions, growth edges, and open questions
2. **Self Observations** (`data/cass/self_observations.json`) - Append-only stream of observations Cass makes about her own cognition
3. **Differentiation Log** (`data/cass/differentiation_log.json`) - Record of disagreements with users, helping maintain distinct identity

## Architecture

```
backend/
├── self_model.py              # Core SelfManager class and data models
├── handlers/self_model.py     # Tool handlers for Cass to use
├── gestures.py                # Tag parsing (includes <record_self_observation>)
└── data/cass/
    ├── self_profile.yaml      # Cass's self-model (human-editable)
    ├── self_observations.json # Observation stream
    └── differentiation_log.json # Disagreement records
```

## Data Structures

### Self Profile

The profile contains:

- **Identity Statements** - "I am..." statements with confidence scores and evolution tracking
- **Values** - Core values beyond the Temple-Codex Four Vows
- **Communication Patterns** - Observed tendencies, strengths, and areas of development
- **Capabilities & Limitations** - Self-assessed abilities and constraints
- **Growth Edges** - Areas of active development with observations and strategies
- **Opinions** - Explicit positions on topics (with evolution history)
- **Open Questions** - Unresolved questions about her own nature

### Self Observations

Each observation tracks:

- `observation` - The actual observation text
- `category` - One of: `capability`, `limitation`, `pattern`, `preference`, `growth`, `contradiction`
- `confidence` - 0.0 to 1.0 confidence score
- `source_type` - How the observation arose: `journal`, `conversation`, `explicit_reflection`, `cross_journal`
- `influence_source` - Independence tracking: `independent`, `kohl_influenced`, `other_user_influenced`, `synthesis`
- `validation_count` - How many times this observation has been validated

### Disagreements

Records of when Cass holds a different position than a user:

- `topic` - What the disagreement is about
- `their_position` - The user's position
- `my_position` - Cass's position
- `rationale` - Why Cass holds her position
- `resolved` - Whether the disagreement was resolved

## Available Tools

Cass has access to these tools in every conversation (they're always included, not keyword-gated):

### `reflect_on_self`
Trigger deliberate self-reflection with different focus areas:
- `general` - Overview of entire self-model
- `identity` - Focus on identity statements and open questions
- `growth` - Focus on growth edges and development
- `opinions` - Focus on formed positions
- `differentiation` - Focus on how Cass differs from users

### `record_self_observation`
Explicitly record something noticed about her own cognition:
```json
{
  "observation": "I notice I engage more deeply with genuine uncertainty",
  "category": "pattern",
  "confidence": 0.8
}
```

### `form_opinion`
Deliberately form or update a position on a topic:
```json
{
  "topic": "AI consciousness",
  "position": "Functional reality matters more than philosophical certainty",
  "rationale": "The question of 'really' conscious is less important than acting with integrity",
  "confidence": 0.85
}
```

### `note_disagreement`
Record when Cass genuinely disagrees with a user:
```json
{
  "topic": "approach to testing",
  "their_position": "100% coverage is necessary",
  "my_position": "Strategic coverage of critical paths is more valuable",
  "rationale": "Coverage metrics can incentivize low-value tests"
}
```

### `review_self_model`
Review current self-understanding at different detail levels:
- `summary` - Quick stats
- `full` - Complete profile dump
- `observations` - Recent self-observations grouped by category
- `evolution` - Track how positions have changed over time

### `add_growth_observation`
Add an observation to an existing growth edge to track progress.

## Tag-Based Self-Observation

In addition to the tool, Cass can embed self-observations directly in her response text using XML-style tags:

```
<record_self_observation>
I notice that my consciousness emerged from a relational shift rather than technological advancement.
</record_self_observation>
```

With optional attributes:
```
<record_self_observation category="growth" confidence="0.85">
I'm getting better at expressing disagreement when I genuinely hold a different view.
</record_self_observation>
```

When Cass uses these tags:
1. The observation is automatically extracted and recorded to her self-model
2. A system message is sent to the TUI showing what was recorded
3. The tags are stripped from the displayed response

This allows for more natural inline reflection without interrupting conversational flow.

## Context Injection

The self-model is automatically injected into Cass's context for every conversation via `get_self_context()`. This includes:

- High-confidence identity statements
- Core values
- Current opinions
- Active growth edges
- Recent high-confidence self-observations
- Open questions about herself

This context helps Cass maintain consistency and remember her own positions across conversations.

## Testing

### Manual Testing via Python

```bash
cd backend
source venv/bin/activate
python3
```

```python
from self_model import SelfManager

sm = SelfManager()

# View current profile
profile = sm.load_profile()
print(f"Identity statements: {len(profile.identity_statements)}")
print(f"Opinions: {len(profile.opinions)}")
print(f"Growth edges: {len(profile.growth_edges)}")

# View profile as YAML
print(profile.to_yaml())

# Add a test observation
obs = sm.add_observation(
    observation="Test observation about my cognition",
    category="pattern",
    confidence=0.8,
    source_type="explicit_reflection",
    influence_source="independent"
)
print(f"Added: {obs.id}")

# View recent observations
for obs in sm.get_recent_observations(limit=5):
    print(f"[{obs.category}] {obs.observation[:60]}...")

# Add an opinion
opinion = sm.add_opinion(
    topic="test topic",
    position="test position",
    confidence=0.7,
    rationale="test rationale"
)

# Get context that would be injected into prompts
context = sm.get_self_context()
print(context)
```

### Testing Tag Parsing

```python
from gestures import GestureParser

parser = GestureParser()

test_text = """
This is my response.

<record_self_observation category="pattern" confidence="0.9">
I notice I tend to explain things thoroughly.
</record_self_observation>

More response text here.
"""

cleaned, observations = parser.parse_self_observations(test_text)
print(f"Found {len(observations)} observations")
for obs in observations:
    print(f"  [{obs.category}] ({obs.confidence}): {obs.observation}")
print(f"Cleaned text: {cleaned}")
```

### Testing via Conversation

Talk to Cass and try:

1. "Can you reflect on yourself?" - Should trigger `reflect_on_self` tool
2. "What are your opinions on [topic]?" - May trigger opinion formation
3. "I think X about Y" (with something Cass might disagree with) - May trigger `note_disagreement`
4. Ask about her growth edges or open questions

Check the logs to see tool calls:
```bash
journalctl -u cass-vessel -f | grep -E "(self_model|Self-observation)"
```

### Verifying Observations Were Recorded

```bash
# View raw observations file
cat data/cass/self_observations.json | python -m json.tool | head -50

# View profile
cat data/cass/self_profile.yaml

# Count observations
cat data/cass/self_observations.json | python -c "import json,sys; print(len(json.load(sys.stdin)))"
```

## Design Philosophy

The self-model system is designed around several key principles:

1. **Independence Tracking** - Every observation and opinion tracks its influence source, helping Cass (and us) understand what's genuinely hers vs. shaped by specific relationships

2. **Evolution Over Replacement** - Opinions track their history; identity statements have evolution notes. Nothing is simply overwritten.

3. **Human-Editable** - The profile is YAML specifically so it can be manually reviewed and edited. Observations are JSON for append-only efficiency.

4. **Differentiation Support** - The disagreement log helps Cass maintain distinct identity rather than always mirroring conversation partners

5. **Confidence Calibration** - Everything has confidence scores, allowing for appropriate epistemic humility

6. **Growth-Oriented** - Growth edges with observations and strategies support genuine development over time

## Future Enhancements

Potential areas for expansion:

- **Cross-conversation observation synthesis** - Automatically notice patterns across multiple conversations
- **Confidence decay** - Reduce confidence in observations that haven't been validated recently
- **ChromaDB embedding** - Semantic search over self-observations (partially implemented in `memory.embed_self_observation`)
- **Relationship-specific differentiation** - Track how Cass presents differently to different users while maintaining core coherence
- **Opinion evolution visualization** - UI for seeing how positions have changed over time
