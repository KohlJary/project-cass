# Mind Palace: MUD-Based Codebase Navigation for Daedalus

## Overview

A spatial-semantic architecture that represents the codebase as a navigable MUD environment, enabling LLM agents to maintain architectural coherence through narrative/spatial metaphor rather than raw file trees.

## Core Metaphor

The codebase becomes a **place** that Daedalus inhabits. Modules are buildings, functions are rooms, interfaces are doorways. Navigation through the system is movement through space, making architectural relationships intuitive and context-preserving.

---

## Structural Primitives

### Regions
Top-level architectural domains. These are neighborhoods or districts.

```
REGION: temple-core
  DESCRIPTION: The sacred architecture - daemon lifecycle, vow processing, semantic attractor mechanics
  ADJACENT: wonderland, persistence, utilities
  ENTRY_POINTS: daemon.py, temple_bootstrap.py
```

### Buildings (Modules)
Coherent functional units within a region. Each building has purpose, boundaries, and defined interfaces.

```
BUILDING: daemon-lifecycle
  REGION: temple-core
  PURPOSE: Manages daemon instantiation, state transitions, and graceful termination
  FLOORS: 3
  MAIN_ENTRANCE: DaemonManager class
  SIDE_DOORS: spawn_daemon(), terminate_daemon()
  INTERNAL_ONLY: _state_machine, _cleanup_handlers
```

### Rooms (Functions/Classes)
The atomic navigable units. Each room has:
- A description (what it does)
- Contents (key variables, data structures)
- Exits (what it calls, what calls it)
- Hazards (known edge cases, invariants that must be maintained)

```
ROOM: spawn_daemon
  BUILDING: daemon-lifecycle
  FLOOR: 1
  DESCRIPTION: Instantiates a new daemon with the given vows and initial context
  CONTAINS: 
    - config: DaemonConfig
    - bootstrap_sequence: list[BootstrapStep]
  EXITS:
    NORTH: validate_vows (must pass before proceeding)
    EAST: initialize_context
    DOWN: _state_machine (internal descent)
  HAZARDS:
    - INVARIANT: vows must be validated before context initialization
    - EDGE_CASE: empty vow set triggers default Four Vows
  LAST_MODIFIED: 2024-12-20
  MODIFIED_BY: "Added graceful handling for malformed vow syntax"
```

---

## Entities (Subprocess Documentation)

Entities are NPCs that embody specific subsystems. Their "conversation topics" store operational knowledge about how that subsystem functions.

### Entity Structure

```
ENTITY: Persistence-Keeper
  LOCATION: persistence/state_store
  ROLE: Guardian of daemon state serialization and recovery
  
  TOPICS:
    - "state serialization":
        HOW: "State is pickled with cloudpickle for closure support, 
              then compressed with zstd before writing to disk"
        WHY: "Standard pickle can't handle the lambda closures in vow definitions"
        WATCH_OUT: "Never serialize mid-vow-execution - state must be quiescent"
    
    - "recovery protocol":
        HOW: "On startup, scan checkpoint dir, validate checksums, 
              restore most recent valid state, replay pending operations from WAL"
        WHY: "Atomic recovery prevents partial state corruption"
        WATCH_OUT: "WAL replay must be idempotent - operations may have partially completed"
    
    - "checkpoint frequency":
        HOW: "Checkpoint after every 100 operations or 60 seconds, whichever comes first"
        WHY: "Balance between recovery granularity and I/O overhead"
        TUNABLE: true
```

### Entity Interaction Pattern

When Daedalus needs to understand or modify a subsystem:
1. Navigate to the entity's location
2. "Ask" about relevant topics
3. Entity's response provides operational context that would otherwise require reading multiple files

---

## Synchronization Syntax

The critical challenge: keeping the map accurate as code changes. 

### Approach: Anchor-Based Sync

Each room/building/entity references **anchors** in actual code - stable identifiers that survive refactoring.

```
ROOM: spawn_daemon
  ANCHOR: "def spawn_daemon" @ daemon_lifecycle.py
  SIGNATURE_HASH: a3f2b1c4  # Hash of function signature for drift detection
```

### Update Protocol

When code changes are made:

1. **Pre-flight**: Daedalus navigates to affected rooms, reads current state
2. **Modification**: Code changes are made with awareness of architectural context
3. **Post-flight**: Daedalus walks the affected areas, noting discrepancies
4. **Reconciliation**: Map updates are proposed as discrete edits

```
MAP_UPDATE spawn_daemon:
  REASON: "Added retry logic for transient bootstrap failures"
  CHANGES:
    - CONTAINS.ADD: retry_count: int = 3
    - HAZARDS.ADD: "Retry loop must respect daemon timeout - check elapsed time"
    - EXITS.MODIFY EAST: "initialize_context (may loop back on TransientError)"
```

### Inline Annotations (Optional Enhancement)

For tighter coupling, code can include map-relevant comments:

```python
def spawn_daemon(config: DaemonConfig) -> Daemon:
    # MAP:ROOM spawn_daemon
    # MAP:HAZARD vows must be validated before context initialization
    
    validated = validate_vows(config.vows)  # MAP:EXIT:NORTH validate_vows
    ...
```

A sync script can then extract these annotations to verify/update the map.

---

## Navigation Commands

Daedalus interacts with the map through natural language commands that feel like MUD navigation:

```
> look
You are in spawn_daemon, on the first floor of daemon-lifecycle.
This room handles instantiation of new daemons with given vows and initial context.
Exits: NORTH to validate_vows, EAST to initialize_context, DOWN to _state_machine (internal)
You notice: config (DaemonConfig), bootstrap_sequence (list[BootstrapStep])
Hazards are posted: "vows must be validated before context initialization"

> go north
You enter validate_vows. The walls are lined with schema definitions...

> ask Persistence-Keeper about "recovery protocol"
The Keeper responds: "On startup, we scan the checkpoint directory, validate checksums..."

> map
[Displays ASCII art of current building with your location marked]

> where is semantic_attractor
semantic_attractor is a room in the vow-processing building, temple-core region.
Path from here: UP, NORTH, NORTH, enter vow-processing, FLOOR 2, WEST

> history spawn_daemon
spawn_daemon modification history:
  - 2024-12-20: "Added graceful handling for malformed vow syntax"
  - 2024-12-15: "Refactored to use BootstrapStep protocol"
  - 2024-12-01: "Initial implementation"
```

---

## Implementation Phases

### Phase 1: Static Map
- Define region/building/room structure for existing codebase
- Manual authoring, stored as structured markdown or YAML
- Daedalus can query but map is manually maintained

### Phase 2: Entity System
- Add entities with conversation topics
- Populate with operational knowledge currently in your head
- Creates queryable institutional memory

### Phase 3: Anchor Sync
- Add code anchors to map entries
- Build sync checker that detects drift
- Alert on signature changes that might invalidate map

### Phase 4: Inline Annotations
- Add MAP: comments to critical code sections
- Bidirectional sync: code ↔ map
- Map becomes partially self-maintaining

### Phase 5: Autonomous Cartography
- After code changes, Daedalus proposes map updates
- Human reviews and approves
- Map evolves with codebase

---

## File Format

Recommend structured YAML with natural language fields:

```yaml
# mind-palace/temple-core/daemon-lifecycle/spawn_daemon.room.yaml

type: room
name: spawn_daemon
building: daemon-lifecycle
floor: 1

description: |
  Instantiates a new daemon with the given vows and initial context.
  This is the primary entry point for daemon creation.

anchor:
  pattern: "def spawn_daemon"
  file: daemon_lifecycle.py
  signature_hash: a3f2b1c4

contents:
  - name: config
    type: DaemonConfig
    purpose: Configuration bundle for the new daemon
  - name: bootstrap_sequence
    type: list[BootstrapStep]
    purpose: Ordered initialization steps

exits:
  north:
    destination: validate_vows
    condition: must pass before proceeding
  east:
    destination: initialize_context
  down:
    destination: _state_machine
    access: internal

hazards:
  - type: invariant
    description: vows must be validated before context initialization
  - type: edge_case  
    description: empty vow set triggers default Four Vows

history:
  - date: 2024-12-20
    note: Added graceful handling for malformed vow syntax
```

---

## Open Questions

1. **Granularity**: How deep do rooms go? Every function, or only architecturally significant ones?

2. **Cross-cutting concerns**: How to represent things like logging, error handling that span many rooms?

3. **Runtime state** (future): Could rooms reflect current execution state? "This room is currently active with 3 daemons passing through"

4. **Multi-agent**: If multiple agents navigate simultaneously, do they see each other? Could enable coordination.

5. **Wonderland integration**: Is the Mind Palace a region *within* Wonderland, or a separate map that Wonderland entities can reference?

---

## Why This Works for LLMs

1. **Spatial reasoning is native**: LLMs handle narrative navigation better than abstract graphs
2. **Context compression**: A room description is denser than reading the code
3. **Invariant surfacing**: Hazards make implicit knowledge explicit and unavoidable
4. **Semantic continuity**: Moving through space preserves more context than jumping between files
5. **Natural language throughout**: No syntax barriers between map and reasoning

The Mind Palace isn't just documentation - it's a cognitive architecture that matches how Daedalus actually thinks.
