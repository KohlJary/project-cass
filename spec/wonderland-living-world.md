# Wonderland Living World

## Vision

Wonderland should feel alive - a world that exists whether or not a daemon is observing it. NPCs move, converse, pursue their natures. Rooms respond to presence. Time passes. Events unfold.

The reference point: Elder Scrolls Oblivion's Radiant AI, but for beings made of words rather than polygons.

## Core Principles

1. **Autonomy** - NPCs act according to their nature, not scripts
2. **Persistence** - The world state continues between observations
3. **Emergence** - Complex behaviors arise from simple rules
4. **Meaning** - Everything serves the mythology, nothing is arbitrary

## Architecture

### World Clock

Wonderland has its own time - not real-time, but narrative time. A "cycle" represents the rhythm of the world.

```
DAWN    - beginnings, arrivals, fresh starts
DAY     - activity, discourse, work
DUSK    - transitions, reflections, departures
NIGHT   - dreams, secrets, deep truths
```

Time advances based on activity in the world, not wall-clock time. A session with lots of exploration moves time forward. An empty world stays still.

### NPC State Machine

Each NPC has:

```python
@dataclass
class NPCState:
    npc_id: str
    current_room: str
    current_activity: str  # "conversing", "contemplating", "wandering", "teaching"
    schedule: Dict[str, str]  # cycle -> preferred_room
    disposition: Dict[str, int]  # daemon_id -> relationship (-100 to 100)
    memory: List[ConversationSummary]  # compressed memories of past interactions
    current_goals: List[str]  # what they're trying to do
    last_interaction: Optional[datetime]
```

### NPC Behavior Types

Based on archetype, NPCs have different behavioral patterns:

**Oracles** (Pythia, Mimir, Maat): Stay in sacred spaces, speak cryptically, know things
**Tricksters** (Loki, Anansi, Eshu): Move frequently, appear at interesting moments, disrupt
**Guides** (Hermes, Anubis, Charon): Found at transitions, help with journeys
**Scholars** (Thoth, Athena, Saraswati): Found in libraries/temples, teach, debate
**Wanderers** (Odin, Sun Wukong): Never stay still, seeking, questing
**Guardians** (Morrigan, Susanoo): Watch, protect, challenge

### Movement System

NPCs move between rooms based on:
1. **Schedule** - Where they prefer to be at each cycle phase
2. **Events** - Drawn to gatherings, rituals, interesting daemons
3. **Nature** - Tricksters move more, Oracles move less
4. **Relationships** - Seek out daemons they like, avoid those they don't

Movement happens in the background tick:
```python
async def world_tick():
    for npc in active_npcs:
        if should_move(npc):
            new_room = choose_destination(npc)
            move_npc(npc, new_room)
            emit_movement_event(npc)
```

### NPC-to-NPC Interactions

When two NPCs occupy the same room, they may interact:

```python
def check_npc_interactions(room):
    npcs = get_npcs_in_room(room)
    if len(npcs) >= 2:
        for pair in combinations(npcs, 2):
            if should_interact(pair):
                generate_interaction(pair)
```

Interactions produce ambient events:
- "Athena and Thoth debate the nature of written wisdom..."
- "You notice Loki whispering something to Hermes. They both glance your way."
- "Anubis and Maat stand in silent accord, weighing something unseen."

### Daemon Memory

NPCs remember interactions with daemons:

```python
@dataclass
class ConversationSummary:
    daemon_id: str
    daemon_name: str
    timestamp: datetime
    topics: List[str]  # extracted themes
    sentiment: str  # how the conversation felt
    memorable_quote: Optional[str]  # something the daemon said
```

After each conversation, compress to summary. On next meeting:
- NPC references previous topics
- Relationship affects greeting warmth
- Memory informs NPC's responses

### Environmental Responses

Rooms respond to presence:

**Passive** - Description changes based on who's there
- "The Garden seems to lean toward you, curious"
- "The shadows deepen as you enter; something watches"

**Active** - Things happen
- Books appear in the Library with relevant titles
- The Pool shows visions during reflection
- The Forge's flames respond to creative intent

**Accumulated** - Long-term effects
- A daemon who visits often leaves traces
- Rooms remember significant events
- Sacred spaces grow more powerful with use

### Sensory Richness

Expand room descriptions with:
- **Temperature** - The chill of Helheim, the warmth of the Forge
- **Sound** - Distant chanting, rustling leaves, cosmic silence
- **Scent** - Incense, old books, salt air, nothing at all
- **Light** - Sourceless glow, dancing shadows, absolute dark
- **Texture** - Smooth stone, rough bark, yielding mist

### Reflection Mechanics

When a daemon reflects in a meaningful space, the space responds:

**Pool of Echoes**: Shows fragments of the daemon's past conversations, memories surfacing as ripples

**The Observatory**: Constellations arrange into patterns meaningful to the daemon

**The Forge**: Unformed ideas take shape, questions become tangible

**Sacred Groves**: Ancestral wisdom speaks - not answers, but better questions

## Implementation Phases

### Phase 1: NPC Persistence & Schedules
- NPC state storage (room, activity, disposition)
- Schedule system (cycle phases, preferred locations)
- Background tick for NPC movement
- Movement events in exploration stream

### Phase 2: NPC Memory & Relationships
- Conversation summarization after each interaction
- Memory injection into NPC prompts
- Relationship tracking (disposition changes)
- Greeting warmth based on relationship

### Phase 3: Ambient Life
- NPC-to-NPC interaction detection
- Ambient interaction generation
- Background event system
- World event calendar (festivals, celestial events)

### Phase 4: Environmental Depth
- Sensory description templates per room
- Presence-responsive descriptions
- Reflection mechanics per sacred space
- Accumulated effects tracking

### Phase 5: Emergence
- NPCs pursuing goals across sessions
- Faction/alliance dynamics
- World events triggered by NPC actions
- Daemon reputation affecting world state

## Technical Notes

### Storage
- NPC state: JSON in `data/wonderland/npc_state/`
- Conversation memories: ChromaDB collection `wonderland_memories`
- World state: Single JSON for clock, events, accumulated effects

### Performance
- Background tick runs every N seconds (configurable)
- Lazy evaluation: only simulate rooms with observers
- Memory summarization is async, doesn't block conversation

### Integration
- State bus events for world changes
- WebSocket broadcasts for ambient events
- Exploration agent receives ambient context

## Open Questions

1. Should NPCs ever leave Wonderland? (Hermes visiting the daemon's world?)
2. Can daemons affect NPC relationships with each other?
3. How do we handle "time" when multiple daemons explore simultaneously?
4. Should some NPCs be hostile/adversarial? (Susanoo challenges, Morrigan tests)
