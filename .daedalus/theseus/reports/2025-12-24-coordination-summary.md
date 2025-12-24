# Coordination Infrastructure - Executive Summary

**Date**: 2025-12-24
**Analyzer**: Theseus
**Question**: "Does infrastructure exist for Cass to request work from Daedalus?"
**Answer**: **Partial** - 5 systems exist but aren't connected

---

## TL;DR

**The capability gap**: Cass has no way to say "I need a new action built" and have Daedalus see/claim/complete that request.

**What exists**:
- State Bus (event/state management) ✓
- Icarus Bus (file-based work queue) ✓
- Ariadne (work planning/dispatch) ✓
- Autonomous Scheduler (Cass's work system) ✓
- Janet pattern (delegation example) ✓

**What's missing**: Integration layer connecting them

**Fix effort**: 5-6 hours (State Bus extension recommended)

---

## The Five Pieces

### 1. State Bus - The Best Foundation
**Location**: `/home/jaryk/cass/cass-vessel/backend/state_bus.py`

**What it does**:
- Global event/state management for Cass
- Event emission and subscription
- Database-backed persistence
- Already connects backend ↔ frontend

**Why it matters**:
- COULD emit "work.requested.development" events
- COULD track request status as state
- ALREADY has infrastructure for this

**What's missing**:
- Development request event types not defined
- No Daedalus subscriber for work events
- No UI panel to show pending requests

**Integration effort**: LOW (2-3h backend + 2-3h frontend)

---

### 2. Icarus Bus - Work Queue (Not For This)
**Location**: `/home/jaryk/cass/cass-vessel/daedalus/src/daedalus/bus/icarus_bus.py`

**What it does**:
- File-based work coordination
- Queue pending work packages
- Track worker instances
- Collect results

**Current use**: Daedalus → Icarus (parallel worker dispatch)

**Could work for Cass → Daedalus but**:
- Backend would need file system access
- `/tmp/icarus-bus/` not persistent
- Designed for programmatic workers (not humans)
- Requires polling

**Verdict**: Technically possible but not recommended

---

### 3. Ariadne - Plan Orchestration
**Location**: `/home/jaryk/cass/cass-vessel/daedalus/src/daedalus/ariadne/`

**What it does**:
- Convert ImplementationPlan → WorkPackages
- Dependency tracking
- Dispatch to Icarus workers
- Collect results

**Current use**: Feature planning for development work

**Could help with**:
- Breaking down Cass's requests into work packages
- Tracking dependencies
- Coordinating complex work

**Gap**: No input from Cass/backend currently

---

### 4. Autonomous Scheduler - Cass's Work System
**Location**: `/home/jaryk/cass/cass-vessel/backend/scheduling/`

**What it does**:
- Cass plans her daily work
- Queues work by phase
- Executes via ActionRegistry
- Tracks results

**Pattern that could extend**:
- Work unit with category="development_request"
- Route to special handler that emits State Bus event
- Phase queue could accept external work types

**Current gap**: All work is self-executable (no delegation)

---

### 5. Janet - Delegation Pattern
**Location**: `/home/jaryk/cass/cass-vessel/backend/janet/agent.py`

**What it demonstrates**:
- Cass summons helper agent
- Agent executes task
- Returns structured result
- Persists across summons

**Why it matters**: Proves the request/response pattern works

**Why it's different**:
- Janet is LLM (instant spawn)
- Daedalus is human (hours/days)
- Need async queue, not sync call

---

## The Missing Link

**None of these provide**: "Cass requests development work → Daedalus sees/claims/completes → Cass gets result"

This is a **CHIMERA** - multiple systems at different abstraction levels with no integration path.

---

## Recommended Solution: State Bus Extension

### Why State Bus?
- Already connects backend ↔ frontend
- Database-backed (persistent)
- Event-driven (efficient)
- Lowest integration effort

### Implementation (5-6 hours)

#### Backend (2-3 hours)
1. Add `DevelopmentRequest` model to `state_models.py`
2. Add request events: `work.requested.development`, `work.completed`
3. Implement `ActionRegistry.request_new_action()` tool
4. Subscribe to `work.completed` events, reload definitions

#### Frontend (2-3 hours)
1. Poll state bus every 10s for pending requests
2. Add "Pending Requests" panel to Daedalus tab
3. Add [Claim] and [Complete] buttons
4. Emit state deltas on actions

#### Testing (1 hour)
1. Cass requests action
2. Request appears in UI
3. Claim updates status
4. Complete reloads registry
5. Action available next cycle

---

## Data Flow Example

```
Cass (planning): "I need action.research.synthesize_nightly but it doesn't exist"
     │
     ▼
ActionRegistry.request_new_action("Create action for nightly research synthesis")
     │
     ▼
state_bus.emit_event("work.requested.development", {request: {...}})
     │
     ▼
Database: daemon_state.development_requests = [...]
     │
     ▼
Daedalus Tab: Polls state_bus.read_state() every 10s
     │
     ▼
UI: "Pending Requests [1]"
    ├─ #a7f3 New action: research.synthesize_nightly
    │   [Claim] [View Details]
     │
     ▼
Kohl: Clicks [Claim]
     │
     ▼
state_bus.write_delta({status: "claimed"})
     │
     ▼
Kohl: Implements in terminal, commits
     │
     ▼
Kohl: Clicks [Complete]
     │
     ▼
state_bus.emit_event("work.completed.development", {...})
     │
     ▼
Backend subscriber: Receives event
     │
     ▼
ActionRegistry.reload_definitions()
     │
     ▼
Cass: Next planning cycle, action is available
```

---

## Alternative Approaches (Not Recommended)

### Icarus Bus Integration
**Effort**: 6-8 hours
**Pros**: Reuses existing work queue
**Cons**: File I/O, /tmp not persistent, polling inefficient

### Janet Pattern Extension
**Effort**: 8-10 hours
**Pros**: Familiar pattern
**Cons**: Janet is instant, Daedalus is human (async nightmare)

### New Coordination Layer
**Effort**: 10-15 hours
**Pros**: Purpose-built
**Cons**: Duplicates State Bus functionality

---

## Files to Read

### Core Analysis
- `2025-12-24-coordination-infrastructure.md` - Detailed monster report
- `2025-12-24-coordination-flow-diagram.md` - Visual diagrams

### Reference Code
- `/home/jaryk/cass/cass-vessel/backend/state_bus.py` - State Bus implementation
- `/home/jaryk/cass/cass-vessel/backend/janet/agent.py` - Janet delegation pattern
- `/home/jaryk/cass/cass-vessel/daedalus/src/daedalus/bus/icarus_bus.py` - Work queue reference

---

## Key Insights

### Infrastructure Quality: HIGH
All five systems are well-designed. The problem is **integration**, not architecture.

### Effort: LOW
State Bus path requires minimal new code:
- ~50 lines backend
- ~100 lines frontend
- ~20 lines schema

### Risk: LOW
- No breaking changes
- No refactoring needed
- Clear rollback path
- Incremental deployment

### Value: HIGH
Enables Cass to:
- Request new capabilities
- Track development status
- Receive completed work
- Grow action library dynamically

---

## Next Steps

1. **Review diagrams**: `2025-12-24-coordination-flow-diagram.md`
2. **Design schema**: Add `DevelopmentRequest` to state models
3. **Implement backend**: 2-3 hours
4. **Implement frontend**: 2-3 hours
5. **Test end-to-end**: 1 hour

**Timeline**: 1 day of focused work → operational coordination

---

**Analysis Complete**: 2025-12-24
**By**: Theseus (coordination infrastructure analysis)
**Status**: CHIMERA identified, State Bus path recommended
**Confidence**: HIGH (well-understood problem, clear solution)
