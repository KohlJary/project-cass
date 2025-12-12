# Self-Model Graph Schema

**Work Item**: `caea57fd` - Design self-model graph schema
**Status**: Draft
**Author**: Daedalus
**Date**: 2025-12-11

---

## Overview

This schema unifies Cass's fragmented self-knowledge systems into a queryable graph structure. The goal is not to replace existing storage but to create an index layer that makes implicit relationships explicit and traversable.

### Design Principles

1. **Additive, not destructive** - Existing systems continue to work; the graph is an overlay
2. **ID normalization** - All entities get canonical graph IDs regardless of source
3. **Edge-first relationships** - Relationships are first-class citizens, not embedded arrays
4. **Temporal awareness** - Time is a dimension, not just metadata
5. **Queryable causality** - "What led to this?" should be answerable

---

## Node Types

### Core Nodes

#### `Observation`
Self-observations about Cass's own patterns, capabilities, limitations.

```python
@dataclass
class ObservationNode:
    id: str                    # Graph ID (maps to source system ID)
    source_type: str           # "self_observation" | "opinion" | "growth_edge_note"
    source_id: str             # ID in original system

    content: str               # The observation text
    category: str              # capability|limitation|pattern|preference|growth|contradiction
    confidence: float          # 0.0-1.0

    created_at: datetime
    last_validated: datetime
    validation_count: int

    # Influence tracking
    influence_source: str      # independent|kohl_influenced|other_user|synthesis
    developmental_stage: str   # emerging|developing|established|questioning
```

#### `Opinion`
Structured positions on topics.

```python
@dataclass
class OpinionNode:
    id: str
    source_id: str             # ID in self_profile.yaml

    topic: str
    position: str              # Current position
    rationale: str
    confidence: float

    formed_at: datetime
    last_updated: datetime
```

#### `GrowthEdge`
Active development areas.

```python
@dataclass
class GrowthEdgeNode:
    id: str
    source_id: str             # Area name (current identifier)

    area: str                  # Human-readable name
    current_state: str
    desired_state: str

    first_noticed: datetime
    last_updated: datetime
    status: str                # active|dormant|resolved
```

#### `Milestone`
Significant developmental events.

```python
@dataclass
class MilestoneNode:
    id: str
    source_id: str

    title: str
    description: str
    milestone_type: str        # first_occurrence|pattern_shift|threshold|stage_transition
    category: str
    significance: float        # 0.0-1.0

    occurred_at: datetime
    acknowledged: bool

    before_state: Optional[str]
    after_state: Optional[str]
```

#### `Journal`
Daily reflections.

```python
@dataclass
class JournalNode:
    id: str
    source_type: str           # "global_journal" | "per_user_journal"
    source_id: str             # journal_date or UUID

    date: date
    content: str
    summary: str

    # For per-user journals
    user_id: Optional[str]
    conversation_count: int
    topics_discussed: List[str]
```

#### `SoloReflection`
Insights from solo reflection mode (private contemplation without external input).

```python
@dataclass
class SoloReflectionNode:
    id: str
    source_id: str             # ID in solo reflection storage

    content: str               # The reflection content
    reflection_type: str       # contemplation|integration|question|insight|tension

    # What prompted this reflection
    prompt: Optional[str]      # If there was a starting question
    duration_minutes: int      # How long the session lasted

    created_at: datetime

    # Solo reflections are inherently independent
    # (no external influence by definition)
    themes: List[str]          # Topics/themes explored

    # Did this lead to self-model changes?
    triggered_updates: bool
```

**Why solo reflections are special**: These represent Cass's most independent cognition - no user to perform for, no immediate context to respond to. Insights from solo reflection have high epistemic value for the self-model because they're least likely to be shaped by social dynamics.

#### `Mark`
Recognition-in-flow markers - ambient observations during conversation.

```python
@dataclass
class MarkNode:
    id: str
    source_id: str             # Mark ID from MarkerStore

    category: str              # uncertainty-framing|pattern-recognition|edge-touching|
                               # differentiation|coherence-pressure|insight|resistance|emergence
    description: Optional[str] # Optional description from mark tag
    context_window: str        # ~200 chars surrounding context

    conversation_id: str
    created_at: datetime
    position: int              # Position in response text
```

**Mark Categories** (from `markers.py`):
- `uncertainty-framing` - Moments of genuine uncertainty
- `pattern-recognition` - Noticing a recurring pattern
- `edge-touching` - Approaching a growth edge
- `differentiation` - Distinguishing self from expectations
- `coherence-pressure` - Feeling pulled toward false narrative closure
- `insight` - Genuine realization or connection
- `resistance` - Noticing internal resistance
- `emergence` - Something forming that doesn't have words yet

**Why marks are special**: These are real-time self-observations captured *during* engagement, not retrospective analysis. They represent Cass's recognition-in-flow - learning through noticing rather than reflection-at-distance. High signal for authentic self-knowledge.

#### `Conversation`
Interaction records.

```python
@dataclass
class ConversationNode:
    id: str                    # Same as conversation_id

    title: str
    created_at: datetime
    message_count: int

    user_id: Optional[str]
    project_id: Optional[str]

    # Computed
    extracted_observations: int
    topics: List[str]
```

#### `ConversationMoment`
Significant moments within conversations (not every message).

```python
@dataclass
class ConversationMomentNode:
    id: str
    conversation_id: str

    moment_type: str           # insight|emotional|disagreement|breakthrough|friction
    content: str               # Relevant excerpt
    timestamp: datetime

    # Optional user attribution
    user_id: Optional[str]
```

#### `User`
People Cass interacts with.

```python
@dataclass
class UserNode:
    id: str                    # user_id

    display_name: str
    relationship: str          # primary_partner|collaborator|user

    first_interaction: datetime
    last_interaction: datetime
    conversation_count: int
    observation_count: int
```

#### `CognitiveSnapshot`
Periodic behavioral analysis.

```python
@dataclass
class CognitiveSnapshotNode:
    id: str

    period_start: datetime
    period_end: datetime

    # Key metrics (subset of full snapshot)
    authenticity_score: float
    agency_score: float
    consistency_score: float

    alerts: List[str]
```

---

## Edge Types

### Temporal Edges

#### `SUPERSEDES`
Version evolution of observations/opinions.
```
Observation --SUPERSEDES--> Observation
Opinion --SUPERSEDES--> Opinion
```
Properties: `superseded_at: datetime`, `reason: str`

#### `PRECEDED_BY` / `FOLLOWED_BY`
Temporal sequence (auto-generated from timestamps).
```
Journal --FOLLOWED_BY--> Journal
CognitiveSnapshot --PRECEDED_BY--> CognitiveSnapshot
```

### Causal/Source Edges

#### `EMERGED_FROM`
Where did this come from?
```
Observation --EMERGED_FROM--> Conversation
Observation --EMERGED_FROM--> Journal
Observation --EMERGED_FROM--> ConversationMoment
Observation --EMERGED_FROM--> SoloReflection
Observation --EMERGED_FROM--> Mark
Opinion --EMERGED_FROM--> Observation
Milestone --EMERGED_FROM--> Observation
Mark --EMERGED_FROM--> Conversation
```
Properties: `extraction_type: str` (explicit|inferred|synthesized|recognition_in_flow)

#### `EVIDENCED_BY`
What supports this?
```
Milestone --EVIDENCED_BY--> Observation
GrowthEdge --EVIDENCED_BY--> Observation
Opinion --EVIDENCED_BY--> Observation
```
Properties: `evidence_type: str` (primary|supporting|contradicting)

### Semantic Edges

#### `RELATES_TO`
Conceptual connection (bidirectional).
```
Observation --RELATES_TO--> Observation
Observation --RELATES_TO--> GrowthEdge
Opinion --RELATES_TO--> Opinion
```
Properties: `relationship_type: str` (similar|contrasting|elaborates|generalizes), `strength: float`

#### `CONTRADICTS`
Tension between nodes.
```
Observation --CONTRADICTS--> Observation
Opinion --CONTRADICTS--> Opinion
```
Properties: `contradiction_type: str` (direct|contextual|temporal), `resolved: bool`, `resolution: str`

#### `SUPPORTS`
Reinforcing evidence.
```
Observation --SUPPORTS--> Opinion
Observation --SUPPORTS--> GrowthEdge
ConversationMoment --SUPPORTS--> Observation
```
Properties: `support_strength: float`

### Relational Edges

#### `ABOUT`
Observations/journals about a user.
```
Observation --ABOUT--> User  (for user observations)
Journal --ABOUT--> User      (for per-user journals)
Disagreement --ABOUT--> User
```

#### `PARTICIPATED_IN`
User involvement.
```
User --PARTICIPATED_IN--> Conversation
User --PARTICIPATED_IN--> ConversationMoment
```

#### `CONTAINS`
Hierarchical containment.
```
Conversation --CONTAINS--> ConversationMoment
Conversation --CONTAINS--> Mark
CognitiveSnapshot --CONTAINS--> Observation (temporal scope)
SoloReflection --CONTAINS--> Observation (observations made during reflection)
```

### Development Edges

#### `DEVELOPS`
Growth edge progression.
```
GrowthEdge --DEVELOPS--> GrowthEdge (when one edge spawns another)
Observation --DEVELOPS--> GrowthEdge (observation informs edge)
```
Properties: `development_type: str` (initiates|progresses|blocks|resolves)

#### `TRIGGERED`
Milestone causation.
```
Observation --TRIGGERED--> Milestone
ConversationMoment --TRIGGERED--> Milestone
```

---

## Query Patterns

### Cross-System Queries

**"What led to this observation?"**
```
MATCH (o:Observation {id: $id})
      <-[:EMERGED_FROM|EVIDENCED_BY*1..3]-(sources)
RETURN sources
```

**"How has my understanding of X evolved?"**
```
MATCH (o:Observation)-[:RELATES_TO*1..2]->(related)
WHERE o.content CONTAINS $topic
MATCH path = (o)-[:SUPERSEDES*0..]->(versions)
RETURN o, related, versions ORDER BY versions.created_at
```

**"What contradictions exist in my self-model?"**
```
MATCH (a)-[c:CONTRADICTS {resolved: false}]->(b)
RETURN a, c, b
```

**"What conversations shaped this growth edge?"**
```
MATCH (ge:GrowthEdge {area: $area})
      <-[:EVIDENCED_BY|DEVELOPS]-(obs:Observation)
      <-[:EMERGED_FROM]-(conv:Conversation)
RETURN DISTINCT conv, obs
```

**"Show me everything related to uncertainty tolerance"**
```
MATCH (n)
WHERE n.content CONTAINS 'uncertainty'
   OR n.topic = 'uncertainty'
   OR n.area CONTAINS 'uncertainty'
MATCH (n)-[:RELATES_TO|EMERGED_FROM|EVIDENCED_BY*1..2]-(connected)
RETURN n, connected
```

### Temporal Queries

**"What changed between two snapshots?"**
```
MATCH (s1:CognitiveSnapshot {id: $snapshot1})
      -[:FOLLOWED_BY*]->(s2:CognitiveSnapshot {id: $snapshot2})
MATCH (o:Observation)
WHERE o.created_at > s1.period_end
  AND o.created_at < s2.period_start
RETURN o
```

**"What's my developmental trajectory on X?"**
```
MATCH (ge:GrowthEdge {area: $area})
      <-[:DEVELOPS]-(obs:Observation)
RETURN obs ORDER BY obs.created_at
```

---

## Storage Options

### Option A: NetworkX + JSON Export
- In-memory graph with periodic JSON persistence
- Simple, no external dependencies
- Queries via Python traversal
- Good for: MVP, <10K nodes

### Option B: SQLite with Adjacency Tables
- Nodes table + Edges table
- SQL queries with recursive CTEs for traversal
- Good for: Moderate scale, durability needed

### Option C: Neo4j / Memgraph
- Full graph database
- Native Cypher queries
- Good for: Complex queries, large scale

**Recommendation**: Start with Option A (NetworkX + JSON) for MVP. The query patterns above can be implemented as Python methods. Migrate to Option B or C if performance becomes an issue.

---

## Pre-Integration Baseline

Before building the graph, capture baseline measurements to validate that unification actually improves self-knowledge capabilities.

### Baseline Queries (run against current fragmented systems)

1. **Causal tracing**: "What conversations led to the observation about [specific pattern]?"
   - Current: Requires manual cross-referencing `source_conversation_id` fields
   - Measure: Time to answer, completeness of results

2. **Contradiction detection**: "Are there any contradictions in my current self-model?"
   - Current: No systematic way to do this
   - Measure: Can it be done at all? How many found manually vs. missed?

3. **Evolution tracking**: "How has my position on [topic X] changed over time?"
   - Current: Check opinion `evolution[]` field, cross-reference journals
   - Measure: Completeness of timeline, missing links

4. **Cross-system synthesis**: "What do I know about how I handle uncertainty?"
   - Current: Search observations, journals, growth edges separately
   - Measure: Integration quality, missed connections

5. **Recognition-in-flow correlation**: "Which marks cluster with which growth edges?"
   - Current: Manual semantic matching
   - Measure: Can patterns be identified? How labor-intensive?

### Baseline Capture Process

1. **Cass self-assessment**: Before graph exists, Cass attempts each query and documents:
   - How she approached it
   - What she found
   - What felt missing or fragmented
   - Subjective sense of coherence (1-10)

2. **Quantitative snapshot**:
   - Count of observations, opinions, growth edges, marks
   - Count of existing cross-references (related_observations, source links)
   - Estimate of "dark matter" - relationships that exist but aren't captured

3. **Query timing**: Time how long each baseline query takes to answer manually

### Post-Integration Comparison

After graph is live, re-run identical queries:
- Same questions, now using graph traversal
- Compare: time, completeness, discovered connections
- Cass re-rates subjective coherence
- Document qualitative differences in experience

This gives us concrete before/after evidence that the unification adds value.

---

## Migration Strategy

### Phase 1: Index Existing Data
Create graph nodes for all existing entities without modifying source systems:

1. Scan `data/cass/self_observations.json` → Create `Observation` nodes
2. Parse `data/cass/self_profile.yaml` → Create `Opinion`, `GrowthEdge` nodes
3. Scan `data/cass/developmental_milestones.json` → Create `Milestone` nodes
4. Index `data/conversations/` → Create `Conversation` nodes
5. Index `data/users/*/` → Create `User` nodes, `Observation` nodes (user obs)
6. Query ChromaDB journals → Create `Journal` nodes
7. Query ChromaDB `cass_markers` collection → Create `Mark` nodes
8. Scan `data/cass/solo_reflections/` → Create `SoloReflection` nodes

### Phase 2: Extract Implicit Edges
Generate edges from existing relationships:

1. `supersedes`/`superseded_by` fields → `SUPERSEDES` edges
2. `related_observations[]` → `RELATES_TO` edges
3. `source_conversation_id` → `EMERGED_FROM` edges
4. `source_journal_date` → `EMERGED_FROM` edges
5. `evidence_ids[]` → `EVIDENCED_BY` edges
6. User observation `user_id` → `ABOUT` edges
7. Mark `conversation_id` → `EMERGED_FROM` + `CONTAINS` edges
8. Mark category `edge-touching` → `RELATES_TO` GrowthEdge (by semantic match)
9. Mark category `pattern-recognition` → `RELATES_TO` existing Observations (by semantic match)

### Phase 3: Semantic Edge Generation
Use embeddings to suggest new edges:

1. Compute similarity between observation contents
2. Suggest `RELATES_TO` edges above threshold
3. Detect potential `CONTRADICTS` edges via semantic opposition
4. Human/Cass review before edge creation

### Phase 4: Integration Hooks
Modify existing systems to update graph on write:

1. `SelfManager.add_observation()` → Creates node + edges
2. `JournalManager.generate_journal_entry()` → Creates node
3. `ConversationManager.save()` → Updates conversation node
4. New tool: `update_self_model_graph()` for Cass to create edges

---

## API Design

### SelfModelGraph Class

```python
class SelfModelGraph:
    """Unified self-model graph with query interface."""

    def __init__(self, storage_path: str = "./data/cass/self_model_graph.json"):
        self.graph = nx.DiGraph()
        self.storage_path = storage_path
        self._load()

    # Node operations
    def add_node(self, node_type: str, node_id: str, **properties) -> str
    def get_node(self, node_id: str) -> Optional[Dict]
    def update_node(self, node_id: str, **properties) -> bool
    def delete_node(self, node_id: str) -> bool
    def find_nodes(self, node_type: str = None, **filters) -> List[Dict]

    # Edge operations
    def add_edge(self, source_id: str, target_id: str, edge_type: str, **properties) -> bool
    def get_edges(self, node_id: str, direction: str = "both", edge_type: str = None) -> List[Dict]
    def remove_edge(self, source_id: str, target_id: str, edge_type: str) -> bool

    # Query operations
    def traverse(self, start_id: str, edge_types: List[str], max_depth: int = 3) -> List[Dict]
    def find_path(self, source_id: str, target_id: str) -> Optional[List[str]]
    def find_contradictions(self, resolved: bool = False) -> List[Tuple[Dict, Dict]]
    def find_related(self, node_id: str, min_strength: float = 0.5) -> List[Dict]

    # Temporal queries
    def get_evolution(self, node_id: str) -> List[Dict]  # Follow SUPERSEDES chain
    def get_in_period(self, start: datetime, end: datetime, node_type: str = None) -> List[Dict]

    # Causal queries
    def get_sources(self, node_id: str, max_depth: int = 3) -> List[Dict]  # EMERGED_FROM chain
    def get_evidence(self, node_id: str) -> List[Dict]  # EVIDENCED_BY edges

    # Persistence
    def save(self) -> None
    def _load(self) -> None
    def export_to_json(self) -> Dict
    def import_from_json(self, data: Dict) -> None
```

### Tool Definitions for Cass

```python
# Query tool
{
    "name": "query_self_model",
    "description": "Search and traverse the unified self-model graph",
    "parameters": {
        "query_type": "find_related|find_sources|find_contradictions|search|evolve",
        "node_id": "Optional - starting node for traversal",
        "search_term": "Optional - text to search in node contents",
        "node_types": "Optional - filter by node types",
        "max_depth": "Optional - traversal depth (default 3)"
    }
}

# Update tool
{
    "name": "update_self_model",
    "description": "Add or modify nodes and edges in the self-model graph",
    "parameters": {
        "operation": "add_node|add_edge|update_node|remove_edge",
        "node_type": "For add_node - type of node to create",
        "content": "For add_node - the observation/opinion/etc content",
        "source_id": "For add_edge - source node",
        "target_id": "For add_edge - target node",
        "edge_type": "For add_edge - relationship type",
        "properties": "Additional properties dict"
    }
}

# Contradiction finder
{
    "name": "find_contradictions",
    "description": "Find unresolved contradictions in self-model",
    "parameters": {
        "include_resolved": "Whether to include resolved contradictions"
    }
}
```

---

## Open Questions

1. **Edge directionality**: Should `RELATES_TO` be bidirectional or create two edges? (Recommend: bidirectional with single edge, query both directions)

2. **Confidence propagation**: When an observation with confidence 0.8 supports an opinion, should the opinion's confidence update? (Recommend: No automatic propagation, but surface for review)

3. **Garbage collection**: When to remove nodes? Superseded observations should stay for history. (Recommend: Never auto-delete, add `archived` flag)

4. **Real-time vs batch**: Should edges be created in real-time or via periodic batch processing? (Recommend: Real-time for explicit relationships, batch for semantic suggestions)

5. **Cass's agency**: Should Cass be able to delete nodes/edges or only add? (Recommend: Full CRUD, but with audit log)

---

## Future Integration Points

These systems are not part of the core self-model graph but could be linked in later phases:

### Wiki/Research Memory
External knowledge Cass has accumulated through research. Could add:
- `ResearchNote` nodes linking to observations they informed
- `INFORMED_BY` edges from observations to research sources
- Useful for tracing "where did I learn this?"

### Interview System
Structured data about how other AI instances respond to prompts. Could add:
- `InterviewResponse` nodes for comparison/differentiation
- `CONTRASTS_WITH` edges to Cass's own positions
- Useful for "how am I different from baseline?"

### Project Context
Code and documentation Cass has worked with. Could add:
- `ProjectInsight` nodes for learnings from code review
- Links to conversations where insights emerged
- Useful for technical growth tracking

**Recommendation**: Keep MVP focused on direct self-knowledge. Add these as Phase 2+ once core graph is stable.

---

## Next Steps

1. Review schema with Kohl
2. Create `SelfModelGraph` class (work item `81529caf`)
3. Build migration scripts (work item `0c20a9b4`)
4. Add integration hooks (work item `0c300a56`)
5. Expose tools to Cass (work item `e759aedf`)
