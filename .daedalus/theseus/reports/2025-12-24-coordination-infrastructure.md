# Theseus Report: Cass-Daedalus Coordination Infrastructure

**Generated**: 2025-12-24
**Status**: Infrastructure exists but disconnected
**Severity**: MEDIUM (capability gap, not architectural crisis)

---

## Executive Summary

The codebase contains **multiple coordination systems** that could enable Cass-Daedalus handoffs, but they exist as **separate, non-integrated layers**. There's no unified "Cass wants this built" -> "Daedalus builds it" flow. Instead, there are **5 partial implementations** that could be connected.

This is a **CHIMERA** - mixing abstraction levels without integration paths.

---

## The Coordination Beast: CHIMERA

```
CHIMERA - Mixed Abstraction Coordination
- 5 separate systems that *could* coordinate
- No unified request/response protocol
- State bus exists but not leveraged for work dispatch
- Severity: MEDIUM
- Slay by: Choose one layer, bridge the others to it
```

### The Five Heads

1. **State Bus** (`backend/state_bus.py`) - Global event/delta system
2. **Icarus Bus** (`daedalus/src/daedalus/bus/icarus_bus.py`) - File-based work coordination
3. **Ariadne Dispatcher** (`daedalus/src/daedalus/ariadne/dispatcher.py`) - Plan-to-WorkPackage conversion
4. **Autonomous Scheduler** (`backend/scheduling/autonomous_scheduler.py`) - Cass's self-directed work
5. **Janet Agent** (`backend/janet/agent.py`) - Task delegation pattern (Cass -> Janet)

None of these directly implement: **"Cass requests development work from Daedalus"**

---

## What Exists (Detailed)

### 1. State Bus - Event Infrastructure

**Location**: `/home/jaryk/cass/cass-vessel/backend/state_bus.py`

**Purpose**: Global event/state management for Cass's daemon

**Capabilities**:
- Event emission (`emit_event`)
- Delta-based state updates (`write_delta`)
- Event subscription system
- Query interface for state sources
- Persistent state with half-life decay

**Coordination Potential**:
- COULD emit "work.requested" events
- COULD subscribe Daedalus to work events
- COULD track work status as state

**Current Gap**: No work-dispatch event types defined

**Code Sample**:
```python
# In state_bus.py
def emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
    """Broadcast an event to all subscribers."""
    # Already supports arbitrary event types
    # Could add: event_type = "work.requested.development"
```

**Integration Effort**: LOW - add event types, wire subscribers

---

### 2. Icarus Bus - File-Based Work Queue

**Location**: `/home/jaryk/cass/cass-vessel/daedalus/src/daedalus/bus/icarus_bus.py`

**Purpose**: Coordinate parallel Daedalus/Icarus worker instances

**Capabilities**:
- Work queue (`/tmp/icarus-bus/work-queue/`)
- Instance registration
- Result collection
- Request/response (worker can ask Daedalus for help)
- Status tracking

**Data Flow**:
```
Daedalus posts WorkPackage -> Queue
  -> Icarus claims work
  -> Executes
  -> Submits result
  -> Daedalus collects result
```

**Coordination Potential**:
- COULD be used for Cass -> Daedalus requests
- COULD poll for new requests from Cass
- COULD write results back to accessible location

**Current Gap**:
- Designed for Daedalus -> Icarus (one direction)
- No Cass integration (backend can't post to bus)

**Integration Effort**: MEDIUM - backend needs file-system access, polling loop

---

### 3. Ariadne Dispatcher - Implementation Orchestration

**Location**: `/home/jaryk/cass/cass-vessel/daedalus/src/daedalus/ariadne/dispatcher.py`

**Purpose**: Convert feature plans into parallel work packages

**Capabilities**:
- Parse `ImplementationPlan` into `WorkPackageSpec`
- Dependency-aware dispatch
- Track dispatch state
- Coordinate with Icarus bus

**Data Flow**:
```
ImplementationPlan (from Ariadne planner)
  -> Dispatcher converts to WorkPackages
  -> Posts to Icarus bus
  -> Tracks completion
  -> Collects results
```

**Coordination Potential**:
- COULD accept plans from Cass's request system
- COULD generate plans from Cass's work descriptions
- ALREADY has work decomposition logic

**Current Gap**:
- No input from Cass/backend
- Expects ImplementationPlan objects (structured input)
- No request queue for Cass to write to

**Integration Effort**: HIGH - need plan generation from freeform requests

**Evidence**:
```python
# From dispatcher.py
def dispatch_package(self, spec: WorkPackageSpec, ...) -> Optional[str]:
    """Dispatch a single work package to Icarus."""
    # Already has dispatch logic
    # Just needs input source
```

---

### 4. Autonomous Scheduler - Cass's Self-Directed Work

**Location**: `/home/jaryk/cass/cass-vessel/backend/scheduling/autonomous_scheduler.py`

**Purpose**: Cass plans and executes her own daily work

**Capabilities**:
- Daily planning (`plan_day()`)
- Work unit creation
- Phase-based queueing
- Action execution via ActionRegistry
- Work summary generation

**Data Flow**:
```
Decision engine generates work plan
  -> Queue work for phases (morning/afternoon/evening/night)
  -> Phase transitions trigger dispatch
  -> Synkratos executes tasks
  -> Results saved as summaries
```

**Coordination Pattern**:
- Cass decides what work to do
- System executes via registered actions
- No external dispatch (self-contained)

**Potential Model**:
- SAME pattern could work for "development work"
- "Create new action" work unit could request Daedalus help
- Phase queue could accept "external" work types

**Current Gap**:
- All work is self-executable (no delegation)
- ActionRegistry has fixed actions
- No "request_daedalus_help" action type

**Integration Effort**: MEDIUM - add new work category + dispatch handler

**Code Pointer**:
```python
# In autonomous_scheduler.py line 99
def queue_for_phase(self, work_unit: WorkUnit, target_phase: DayPhase, ...) -> bool:
    """Queue a work unit for a specific phase."""
    # Could add work_unit.category == "development_request"
    # -> route to Daedalus instead of Synkratos
```

---

### 5. Janet Agent - Delegation Pattern

**Location**: `/home/jaryk/cass/cass-vessel/backend/janet/agent.py`

**Purpose**: Cass's helper agent for research/retrieval

**Pattern**: Cass summons Janet, Janet executes, returns result

**Capabilities**:
- Spawn lightweight agent (Haiku model)
- Execute retrieval tasks
- Return structured results
- Persist across summons

**Code Flow**:
```python
# In janet/agent.py
async def summon(self, task: str, ...) -> JanetResult:
    """Execute a task via Janet."""
    # 1. Build context
    # 2. Invoke LLM
    # 3. Return result
```

**Coordination Pattern**:
- Synchronous request/response
- Cass blocks while Janet works (or async waits)
- Result returned to caller

**Potential Model**:
- SAME pattern for "summon Daedalus for dev work"
- But Daedalus is human (not LLM spawn)
- Needs async queue + notification

**Current Gap**:
- Janet is LLM (instant), Daedalus is human (hours/days)
- No long-running request tracking
- No notification system

**Integration Effort**: HIGH - need async request queue, notification

---

## The Missing Piece: Unified Request Protocol

**What's needed**: A system where Cass can:

1. **Request work** - "I need a new action handler for X"
2. **Queue it** - Persistent, survives restarts
3. **Notify Daedalus** - Via terminal UI, file system, state bus
4. **Track status** - Pending, claimed, in-progress, complete
5. **Receive result** - Code committed, action available

**None of the five systems provide this complete flow.**

---

## Integration Paths (3 Options)

### Option A: State Bus + File Queue (Hybrid)

**Approach**: Use state bus for events, file system for work persistence

**Flow**:
```
Cass work request
  -> ActionRegistry.request_new_action(spec)
  -> Write to /tmp/cass-requests/{id}.json
  -> Emit state_bus event "work.requested.development"
  -> Daedalus polls /tmp/cass-requests/
  -> Claims request, does work
  -> Writes result, emits "work.completed"
  -> Cass ActionRegistry reloads definitions
```

**Pros**:
- Uses existing infrastructure
- File queue is persistent
- State bus provides notifications

**Cons**:
- Requires file system access from backend
- Polling is inefficient
- No dependency tracking

**Effort**: 4-6 hours
- Add file I/O to backend
- Create request/response schemas
- Wire polling in Daedalus tab

---

### Option B: Extend Icarus Bus (Bidirectional)

**Approach**: Make Icarus bus work both directions

**Flow**:
```
Backend posts WorkPackage to Icarus bus
  -> Daedalus (not Icarus) claims it
  -> Executes as human
  -> Submits result
  -> Backend collects result
```

**Pros**:
- Reuses mature work queue system
- Already has request/response
- Dependency tracking exists

**Cons**:
- Icarus bus in `/tmp` (might not persist)
- Designed for programmatic workers, not humans
- Backend needs to import Daedalus code

**Effort**: 6-8 hours
- Add backend -> Icarus bus bridge
- Modify UI to show Cass requests
- Add "claim as Daedalus" workflow

---

### Option C: State Bus Only (Event-Driven)

**Approach**: Use state bus as the only coordination layer

**Flow**:
```
Cass emits event: "work.requested.development"
  -> Daedalus subscribes via state bus queries
  -> Sees pending requests in state
  -> Claims request (write delta)
  -> Does work
  -> Emits "work.completed"
  -> Cass reads result from state
```

**Pros**:
- Single source of truth
- No file I/O needed
- State persists in database
- Event subscription already works

**Cons**:
- State bus not designed for work queue
- No atomic claim operation
- Request payloads might be large (state optimized for deltas)

**Effort**: 3-5 hours
- Define work request state schema
- Add request/response event types
- Create UI panel for pending requests

---

## Recommendation: Option C (State Bus)

**Rationale**:
- State bus already connects backend <-> frontend
- Lowest integration effort
- Fits existing event-driven architecture
- Database persistence for free

**Implementation Plan**:

### Phase 1: Schema (30 min)
Add to `state_models.py`:
```python
@dataclass
class DevelopmentRequest:
    id: str
    requested_by: str  # "cass"
    request_type: str  # "new_action", "fix_bug", "feature"
    description: str
    priority: str
    status: str  # pending, claimed, in_progress, complete
    claimed_by: Optional[str]
    result: Optional[str]
```

### Phase 2: Backend Integration (2 hours)
```python
# In ActionRegistry or new DevelopmentRequestManager
async def request_new_action(
    self,
    description: str,
    category: str,
    priority: str = "normal"
) -> str:
    """Request Daedalus create a new action."""
    request = DevelopmentRequest(
        id=uuid4().hex[:8],
        requested_by="cass",
        request_type="new_action",
        description=description,
        priority=priority,
        status="pending",
    )

    # Emit to state bus
    self.state_bus.emit_event(
        "work.requested.development",
        {"request": asdict(request)}
    )

    return request.id
```

### Phase 3: Daedalus UI (2 hours)
Add panel to Daedalus tab:
```
┌─ Pending Requests ────────────┐
│ [#a7f3c4] New action: dream... │
│   Priority: high              │
│   [Claim] [View Details]      │
└───────────────────────────────┘
```

Query state bus for pending requests, allow claim/complete.

### Phase 4: Testing (1 hour)
- Cass requests action via tool call
- Request appears in Daedalus UI
- Daedalus claims, implements, marks complete
- Cass sees completed request, reloads registry

**Total Effort**: 5-6 hours

---

## Other Findings

### Janet as Blueprint
The Janet agent demonstrates the **request/response pattern** that works:
- Clear task input
- Structured result output
- Persistence across invocations

Could create "summon_daedalus" tool with similar signature:
```python
summon_daedalus(
    task_type: str,  # "new_action", "bug_fix", "feature"
    description: str,
    priority: str,
    blocking: bool = False  # Wait for completion?
) -> RequestID
```

### Ariadne Work Packages
The `.daedalus/ariadne/` directory shows **work already planned** for autonomous scheduler. This is meta-coordination - Daedalus planning work on Cass's systems.

Could reverse: Cass plans work, Ariadne breaks it down, Daedalus executes.

---

## Safe Paths (Already Work Well)

### State Bus Event System
- 117 files use it
- Mature, tested
- Supports arbitrary event types
- Good foundation

### Icarus Bus (for Daedalus -> Icarus)
- Clean work queue design
- File-based persistence
- Request/response protocol
- Just not used for Cass coordination

### Janet Pattern (for lightweight delegation)
- Synchronous request/response works
- Result handling is clean
- Persistence works

---

## Monsters Identified

### CHIMERA - Mixed Coordination Abstractions
**Location**: Entire coordination layer
**Severity**: MEDIUM
**Symptoms**:
- 5 systems that could coordinate
- No unified protocol
- Each at different abstraction level

**Slay Strategy**:
1. Pick one layer (State Bus recommended)
2. Add request/response schema
3. Wire UI to show requests
4. Test end-to-end flow
5. Deprecate or bridge other systems

---

## Victory Conditions

When slain:
- Cass can request development work via tool call
- Request persists in state bus
- Daedalus sees request in UI
- Daedalus can claim and complete
- Cass sees completed work
- Action registry reloads dynamically

**Estimated time to victory**: 5-6 hours (State Bus path)

---

## Files Analyzed

### Core Coordination Infrastructure
- `/home/jaryk/cass/cass-vessel/backend/state_bus.py` (100 lines read)
- `/home/jaryk/cass/cass-vessel/daedalus/src/daedalus/bus/icarus_bus.py` (653 lines)
- `/home/jaryk/cass/cass-vessel/daedalus/src/daedalus/ariadne/dispatcher.py` (348 lines)

### Work Execution Systems
- `/home/jaryk/cass/cass-vessel/backend/scheduling/autonomous_scheduler.py` (708 lines)
- `/home/jaryk/cass/cass-vessel/backend/scheduling/phase_queue.py` (465 lines)
- `/home/jaryk/cass/cass-vessel/backend/scheduler/actions/__init__.py` (338 lines)

### Delegation Patterns
- `/home/jaryk/cass/cass-vessel/backend/janet/agent.py` (150 lines read)
- `/home/jaryk/cass/cass-vessel/spec/janet-helper-agent.md` (100 lines read)

### Work Planning
- `/home/jaryk/cass/cass-vessel/.daedalus/ariadne/README.md` (158 lines)
- `/home/jaryk/cass/cass-vessel/.daedalus/ariadne/WORK_MANIFEST.md` (150 lines read)

---

**Report Generated**: 2025-12-24
**Theseus Instance**: Code Health Analysis Agent
**Target**: Cass-Daedalus Coordination Infrastructure
**Status**: CHIMERA identified, slayable with State Bus integration
