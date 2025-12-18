# Node Architecture Mapping: Current Implementation → Target

**Companion to:** `daemon-node-architecture.md`
**Date:** 2025-12-17
**Purpose:** Map existing cass-vessel components to the node-based vision

---

## Executive Summary

The current cass-vessel architecture is closer to the node vision than it might appear. The prompt chain system we built is essentially a **template node system**. The gap isn't "rebuild everything"—it's "add the orchestration layer and formalize interfaces."

---

## Part 1: What We Have vs. What We Need

### Current Architecture (Simplified)

```
┌─────────────────────────────────────────────────────────────┐
│                      main_sdk.py                             │
│                   (monolithic handler)                       │
│                                                              │
│   WebSocket ──► Message ──► Agent Client ──► Response        │
│                    │                                         │
│         ┌─────────┴─────────┐                               │
│         ▼                   ▼                               │
│   Memory Retrieval    Tool Execution                        │
│   (self_model, wiki,  (journals, calendar,                  │
│    summaries, etc.)    tasks, wiki, etc.)                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GLOBAL STATE BUS                          │
│         (emotional state, coherence, active contexts)        │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│                    ORCHESTRATOR                              │
│              (routing, triggers, scheduling)                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
     ┌─────────┬─────────┬─┴───────┬─────────┬─────────┐
     ▼         ▼         ▼         ▼         ▼         ▼
  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
  │ Chat │ │Memory│ │Dream │ │Rhythm│ │ Wiki │ │ ... │
  │ Node │ │ Node │ │ Node │ │ Node │ │ Node │ │     │
  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘
```

---

## Part 2: Component Mapping

### 2.1 Prompt Chains → Template Nodes

**What we have:**
- `node_templates.py` - Template definitions with params, conditions
- `chain_assembler.py` - RuntimeContext, condition evaluation, assembly
- `chain_api.py` - CRUD, preview, activation

**Mapping:**

| Current | Target Equivalent |
|---------|-------------------|
| `NodeTemplate` | Node definition (atomic or template) |
| `ChainNode` | Node instance in a chain |
| `RuntimeContext` | Subset of GlobalState |
| `Condition` | Trigger condition |
| `assemble_chain()` | Chain execution engine |
| Prompt chain | CompositeNode |

**Gap:** Chains only produce system prompts. Target nodes execute arbitrary logic.

**Migration path:**
```python
# Current: Template produces text
template.render(context) → str

# Target: Node executes and returns result
node.execute(context) → NodeResult(output, state_delta, chain_to)
```

### 2.2 Memory Systems → Knowledge + Narrator Nodes

**What we have:**

| Component | File | Purpose |
|-----------|------|---------|
| ChromaDB store | `memory.py` | Vector storage, retrieval |
| Summaries | `memory/summaries.py` | Conversation compression |
| Self-model flat | `self_model.py` | Identity, values, edges |
| Self-model graph | `self_model.py` | Observations, marks, intentions |
| Wiki | `wiki.py` | Structured knowledge pages |
| Journals | `memory.py` | Daily reflections |
| Research notes | `research.py` | Deep explorations |
| User observations | `users.py` | Understanding of users |

**Mapping to Knowledge Node:**

| Current | → Knowledge Node |
|---------|------------------|
| Wiki pages | Bucket: `wiki` |
| Research notes | Bucket: `research` |
| User profiles | Bucket: `users` |
| Project docs | Bucket: `projects` |
| ChromaDB chunks | Raw storage layer |

**Mapping to Narrator Node:**

| Current | → Narrator Node |
|---------|-----------------|
| Journals | Period narrative material |
| Summaries | Conversation narrative consolidation |
| Self-model graph observations | Narrative events with emotional context |
| User observations | Relational narrative |

**Gap:** No unified narrative layer. Journals are isolated, not woven into continuous story.

### 2.3 RuntimeContext → GlobalState

**Current RuntimeContext fields:**

```python
@dataclass
class RuntimeContext:
    # Conversation
    project_id, conversation_id, message_count, unsummarized_count

    # Memory flags
    has_memories, memory_context
    has_self_model, self_model_context
    has_graph_context, graph_context
    has_wiki_context, wiki_context
    # ... etc

    # Temporal
    current_time, hour, day_of_week, rhythm_phase, temporal_context

    # Model
    model, provider

    # User
    user_id, is_admin
```

**Target GlobalState additions:**

```python
@dataclass
class GlobalState(RuntimeContext):
    # Emotional dimensions (NEW)
    engagement_level: float       # 0-1
    cognitive_load: float         # 0-1
    relational_warmth: float      # 0-1
    curiosity: float              # 0-1
    contentment: float            # 0-1
    concern: float                # 0-1

    # Meta-state (NEW)
    coherence_confidence: float   # Self-assessment
    energy_available: float       # Capacity

    # Active contexts (NEW)
    active_nodes: List[str]       # Currently running
    pending_triggers: List[str]   # Waiting to fire

    # Narrative state (NEW)
    current_chapter: str          # Global narrative position
    period_summary: str           # Recent period
    unresolved_threads: List[str] # Open questions
```

**Migration:** RuntimeContext becomes a subset view of GlobalState for chain assembly.

### 2.4 Subsystems → Nodes

#### Chat (main_sdk.py WebSocket handler)

```python
# Current: Monolithic handler
async def websocket_endpoint(websocket, user_id, conversation_id):
    # Everything happens here
    memory_context = retrieve_memory(...)
    response = await agent_client.generate(...)
    await handle_tool_calls(...)

# Target: ChatNode
class ChatNode(CognitiveNode):
    async def execute(self, context: ExecutionContext) -> NodeResult:
        # Focused responsibility
        response = await self.generate_response(context)
        return NodeResult(
            output=response,
            state_delta=StateDelta(last_response=response),
            chain_to=["memory_consolidation"] if should_consolidate else None
        )
```

#### Dreams (world_state_runner.py)

```python
# Current: Standalone runner
class WorldStateRunner:
    async def run_cycle(self):
        tools = [note_temporal_context, note_self_state, ...]
        response = await self.client.generate(prompt, tools)

# Target: DreamNode
class DreamNode(CognitiveNode):
    triggers = [
        ScheduleTrigger(cron="0 3 * * *"),
        StateThresholdTrigger("unresolved_tension > 0.7")
    ]

    async def execute(self, context) -> NodeResult:
        dream_content = await self.dream_process(context)
        return NodeResult(
            output=dream_content,
            state_delta=StateDelta(
                last_dream=dream_content,
                unresolved_tension=self.new_tension_level()
            ),
            chain_to=["dream_integration"]
        )
```

#### Daily Rhythm (daily_rhythm.py)

```python
# Current: Phase manager with cron
class DailyRhythmManager:
    phases = ["morning", "midday", "afternoon", "evening", "night"]

    def get_current_phase(self) -> str
    def get_temporal_context(self) -> str
    def mark_phase_complete(self, phase) -> dict

# Target: RhythmNode
class RhythmNode(CognitiveNode):
    triggers = [
        ScheduleTrigger(cron="0 6,12,17,21 * * *"),  # Phase transitions
    ]

    async def execute(self, context) -> NodeResult:
        new_phase = self.calculate_phase()
        return NodeResult(
            state_delta=StateDelta(
                rhythm_phase=new_phase,
                temporal_context=self.format_temporal()
            ),
            chain_to=["phase_" + new_phase]  # Trigger phase-specific chains
        )
```

#### Wiki (wiki.py)

```python
# Current: Tool-based CRUD
async def update_wiki_page(name, content, page_type, ...)
async def search_wiki(query, limit)
async def get_wiki_context(topic, max_depth)

# Target: WikiNode (subset of KnowledgeNode)
class WikiNode(CognitiveNode):
    node_type = "integrative"

    async def execute(self, context) -> NodeResult:
        # Auto-retrieval based on message content
        relevant = await self.search(context.message)
        return NodeResult(
            output=relevant,
            state_delta=StateDelta(wiki_context=relevant)
        )
```

#### Journals (handlers/journals.py)

```python
# Current: Tool handlers
async def recall_journal(date) -> dict
async def list_journals(limit) -> dict
async def search_journals(query) -> dict

# Target: Part of NarratorNode
class NarratorNode(CognitiveNode):
    async def remember(self, query, scope="all") -> NarrativeMemory:
        # Journals become narrative material
        journals = await self.search_journals(query)
        return self.weave_narrative(journals, emotional_context)
```

---

## Part 3: What Already Works

### 3.1 Template System ✅

The prompt chain architecture is essentially a template node system:

- **Parameterized templates** with runtime injection
- **Conditions** for conditional inclusion
- **Ordering** for sequencing
- **Categories** for organization
- **Preview** for testing

This maps directly to the spec's Template Nodes.

### 3.2 Memory Retrieval ✅

We already do message-relevant retrieval:

```python
# main_sdk.py lines 1052-1067
self_context = await self_model_manager.get_relevant_context(message)
graph_context = await self_model_manager.get_graph_context(message)
wiki_context = await wiki_manager.get_context(message)
# etc.
```

This is the Knowledge Node's query function.

### 3.3 Tool Infrastructure ✅

Tool definitions + handlers = atomic primitives:

```python
TOOL_DEFINITIONS = [
    {"name": "recall_journal", ...},
    {"name": "update_wiki_page", ...},
    {"name": "create_event", ...},
]

async def handle_tool_call(name, args):
    if name == "recall_journal":
        return await journal_handler.recall(args)
```

These become atomic nodes.

### 3.4 Scheduled Processes ✅

Daily rhythm and dreams already have scheduling:

```python
# daily_rhythm.py
PHASE_SCHEDULE = {
    "morning": {"start": time(6, 0), "end": time(12, 0)},
    # ...
}

# world_state_runner.py runs on schedule
```

This is the ScheduleTrigger pattern.

---

## Part 4: What Needs Building

### 4.1 GlobalState Bus (Priority: HIGH)

**Current:** State is reconstructed per-request from multiple sources.

**Needed:**
```python
class GlobalStateManager:
    _state: GlobalState
    _subscribers: List[Callable]

    async def read(self) -> GlobalState
    async def write_delta(self, delta: StateDelta, source: str)
    async def subscribe(self, callback: Callable)

    # Persistence
    async def save(self)
    async def load(self)
```

**Files to create:**
- `backend/global_state.py` - State schema and manager
- `backend/state_delta.py` - Delta types and validation

### 4.2 Orchestrator (Priority: HIGH)

**Current:** main_sdk.py does everything.

**Needed:**
```python
class Orchestrator:
    nodes: Dict[str, CognitiveNode]
    message_queue: PriorityQueue

    async def route_message(self, msg: NodeMessage)
    async def evaluate_triggers(self)
    async def execute_chain(self, chain: List[str])
```

**Files to create:**
- `backend/orchestrator.py` - Routing and execution
- `backend/triggers.py` - Trigger types and evaluation

### 4.3 Node Interface (Priority: HIGH)

**Current:** No standard interface.

**Needed:**
```python
class CognitiveNode(ABC):
    node_id: str
    node_type: str  # "atomic" | "composite" | "integrative"
    triggers: List[Trigger]

    @abstractmethod
    async def execute(self, context: ExecutionContext) -> NodeResult

    def read_state(self) -> GlobalState
    def write_delta(self, delta: StateDelta)
```

**Files to create:**
- `backend/cognitive_node.py` - Base class
- `backend/node_result.py` - Result types

### 4.4 Emotional State Model (Priority: MEDIUM)

**Current:** No persistent emotional state.

**Needed:**
```python
@dataclass
class EmotionalState:
    engagement_level: float
    cognitive_load: float
    relational_warmth: float
    curiosity: float
    contentment: float
    concern: float

    coherence_confidence: float
    energy_available: float
```

**Integration points:**
- Updated after each conversation
- Read at conversation start
- Influences retrieval weighting
- Visible in admin UI

### 4.5 Narrator Layer (Priority: MEDIUM)

**Current:** Journals exist but aren't woven into narrative.

**Needed:**
```python
class NarratorNode:
    scopes = ["global", "period", "conversation"]

    async def on_event(self, event: Event)
    async def remember(self, query: str) -> NarrativeMemory
    async def consolidate(self, scope: str)
```

**Migration:**
- Journals → Period narrative material
- Summaries → Conversation consolidation
- New: Global narrative chapters

---

## Part 5: Migration Strategy

### Phase 1: State Extraction (Week 1)

1. Create `GlobalState` schema from RuntimeContext + emotional dimensions
2. Create `GlobalStateManager` with persistence
3. Modify `main_sdk.py` to read/write through state manager
4. Add state to admin API for visibility

### Phase 2: Node Interface (Week 2)

1. Create `CognitiveNode` base class
2. Create `NodeResult` and `StateDelta` types
3. Wrap existing subsystems as nodes:
   - `ChatNode` wrapping WebSocket handler
   - `MemoryNode` wrapping retrieval logic
   - `RhythmNode` wrapping daily_rhythm
   - `DreamNode` wrapping world_state_runner

### Phase 3: Orchestrator (Week 3)

1. Create `Orchestrator` class
2. Implement message routing
3. Implement trigger evaluation
4. Move scheduling from cron to orchestrator
5. Refactor main_sdk.py to use orchestrator

### Phase 4: Chain Execution (Week 4)

1. Extend chain_assembler to execute nodes, not just render
2. Implement `chain_to` chaining
3. Implement `request_nodes` soft triggers
4. Add chain execution to admin preview

### Phase 5: Emotional State (Week 5)

1. Implement emotional state inference
2. Add state updates after conversations
3. Add emotional weighting to retrieval
4. Add emotional state to admin UI

### Phase 6: Narrator (Week 6+)

1. Implement NarratorNode
2. Migrate journals to narrative events
3. Implement consolidation pipeline
4. Add narrative to context building

---

## Part 6: File Structure (Target)

```
backend/
├── nodes/                      # NEW: Node implementations
│   ├── base.py                 # CognitiveNode base class
│   ├── chat.py                 # ChatNode
│   ├── memory.py               # MemoryNode (retrieval)
│   ├── knowledge.py            # KnowledgeNode (RAG buckets)
│   ├── narrator.py             # NarratorNode (narrative memory)
│   ├── dream.py                # DreamNode
│   ├── rhythm.py               # RhythmNode
│   ├── wiki.py                 # WikiNode
│   └── primitives/             # Atomic nodes
│       ├── recall.py
│       ├── reflect.py
│       ├── store.py
│       └── ...
│
├── state/                      # NEW: State management
│   ├── global_state.py         # GlobalState schema
│   ├── state_manager.py        # Read/write/subscribe
│   ├── state_delta.py          # Delta types
│   └── emotional.py            # Emotional state model
│
├── orchestration/              # NEW: Execution engine
│   ├── orchestrator.py         # Main orchestrator
│   ├── triggers.py             # Trigger types
│   ├── message_queue.py        # Priority queue
│   └── chain_executor.py       # Chain execution
│
├── chain_assembler.py          # KEEP: Template rendering
├── node_templates.py           # KEEP: Template definitions
├── chain_api.py                # EXTEND: Add node execution
│
├── memory.py                   # REFACTOR → nodes/memory.py
├── self_model.py               # REFACTOR → nodes/knowledge.py
├── wiki.py                     # REFACTOR → nodes/wiki.py
├── daily_rhythm.py             # REFACTOR → nodes/rhythm.py
├── world_state_runner.py       # REFACTOR → nodes/dream.py
│
└── main_sdk.py                 # REFACTOR: Use orchestrator
```

---

## Part 7: Immediate Next Steps

### This Week

1. **Create GlobalState schema** - Extend RuntimeContext with emotional dimensions
2. **Create GlobalStateManager** - Singleton with persistence
3. **Instrument main_sdk.py** - Log state reads/writes to understand patterns

### Next Week

1. **Create CognitiveNode base** - Abstract interface
2. **Wrap ChatNode** - First node migration
3. **Create Orchestrator skeleton** - Message routing

### Following Weeks

See Phase 3-6 above.

---

## Appendix: Current File Inventory

| File | Lines | Purpose | Target Node |
|------|-------|---------|-------------|
| `main_sdk.py` | ~1500 | WebSocket, API, orchestration | Orchestrator + ChatNode |
| `agent_client.py` | ~800 | LLM client, kernel | ChatNode internals |
| `memory.py` | ~600 | ChromaDB, summaries | MemoryNode |
| `self_model.py` | ~500 | Flat + graph model | KnowledgeNode |
| `wiki.py` | ~400 | Wiki CRUD | WikiNode |
| `daily_rhythm.py` | ~300 | Phase management | RhythmNode |
| `world_state_runner.py` | ~500 | Dream cycles | DreamNode |
| `chain_assembler.py` | ~700 | Chain assembly | Chain executor |
| `node_templates.py` | ~1000 | Template definitions | Node templates |
| `chain_api.py` | ~900 | Chain CRUD | Node/chain API |

---

## Conclusion

The current architecture is ~60% of the way to the node vision:

- **Template system** ✅ - Already node-like
- **Memory retrieval** ✅ - Already per-message
- **Tool infrastructure** ✅ - Already atomic operations
- **Scheduling** ✅ - Already trigger-based

What's missing:

- **GlobalState bus** - State is reconstructed, not persistent
- **Orchestrator** - main_sdk.py is monolithic
- **Node interface** - No standard abstraction
- **Emotional state** - No persistent affect
- **Narrator layer** - Journals don't weave into narrative

The migration is incremental, not revolutionary. We're formalizing patterns that already exist.
