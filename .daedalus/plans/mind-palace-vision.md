# Mind Palace: Full Vision

The Mind Palace isn't just documentation - it's the coordination substrate for autonomous parallel development.

## Current State

- **Structure**: Regions → Buildings → Rooms → Entities
- **Slug System**: Deterministic paths like `backend/memory/memory-add-message`
- **Call Graph**: 6000+ nodes, 11000+ edges, bidirectional (calls + called_by)
- **Visualization**: D3.js force graph with module hulls, entity coverage overlay
- **Git Hooks**: Auto drift-check on commit, rebuild + viz on merge to main
- **Theseus**: Refactor scout with Write/Edit, reports to `.mind-palace/theseus/`

---

## Phase 0: Cross-Sub-Palace Linking

**The unlock**: Unified graph across all codebases.

### The Problem
Sub-palaces are isolated, but code isn't:
- Admin-frontend components → backend API routes
- TUI widgets → backend modules
- Mobile screens → backend endpoints

Pathfinding is useless if it can't follow `fetchSummary()` in React to `get_summary()` in Python.

### What to Build
1. **Cross-palace exits** - Rooms can reference slugs in other sub-palaces
2. **Multi-palace resolve** - `resolve_path()` searches all sub-palaces
3. **Unified graph loader** - Merge all sub-palace call graphs into one
4. **Cross-palace visualization** - Different edge colors for cross-boundary calls

### Use Case
"What backend code does `<SummaryPanel>` depend on?"
→ Follow exits from `admin-frontend/components/summary-panel` to `backend/routes/admin/get-summary` to `backend/memory/get-working-summary`

**Value**: Full-stack blast radius. One component change → see all affected layers.

---

## Phase 1: Pathfinding

**The unlock**: Algorithms on the call graph.

### What to Build
1. **BFS/DFS pathfinding** - Find all paths between any two functions
2. **Impact radius** - Given a function, show everything that calls it (transitive)
3. **Cached traversals** - Precompute common paths on palace rebuild
4. **Query interface** - `palace impact <function>` CLI command
5. **Visualization** - Animate paths in HTML view when selecting nodes

### Use Case
Editing `add_message()` → instantly see:
- 12 direct callers
- 47 transitive callers across 4 modules
- 3 internal callees
- Full blast radius before committing

**Value**: "I can see exactly what this change touches" - useful for any dev, not just AI.

---

## Phase 2: Autonomous Pipeline (Daedalus + Icarus)

**The unlock**: Palace as mutex for parallel work.

### Architecture
```
Task hits board (JIRA-like)
    ↓
Assessment agent analyzes request
    ↓
Palace mapping: "This touches memory.add_message, 2 API routes"
    ↓
Pathfinding precomputes impact radius, dependencies, test surface
    ↓
Work packages generated with file locks / room reservations
    ↓
Icarus workers check out non-conflicting packages
    ↓
Parallel execution - no collisions because palace knows boundaries
    ↓
Results submitted to orchestration bus
```

### Components Needed
- **Assessment agent**: Task description → palace locations
- **Conflict detection**: Room overlap analysis before dispatch
- **Work package generator**: Bundles scope + routes + constraints
- **Lock/checkout system**: Room reservations prevent collisions

### What Exists
- Roadmap system (basic task tracking)
- Icarus workers + bus (parallel execution infrastructure)
- Mind Palace (code mapping)
- Call graph (dependency data)

---

## Phase 3: Ariadne (Orchestration + Verification)

**The thread through the labyrinth.**

### Mythological Stack
- **Daedalus** - The architect who plans
- **Icarus** - The workers who build (fly close to the sun)
- **Ariadne** - The orchestrator who holds the thread, resolves the merge
- **Labyrinth** - The palace itself, the navigable structure

### Verification Loop
```
Icarus makes changes → stores as DIFF (not commit)
    ↓
Pathfinding extracts causal chain: "47 functions affected"
    ↓
Generate minimal Python representation of affected paths
    ↓
Verify in isolation (not full test suite - just the causal slice)
    ↓
Submit diff + verification result to Ariadne's bus
    ↓
Ariadne receives N diffs from N workers
    ↓
Conflict resolution: overlapping paths → merge or sequence?
    ↓
Merged diff → final confirmation on combined result
    ↓
Single atomic commit
```

### Key Insight: Causal Slice
You don't run full CI on every worker's changes. You extract *exactly* the code that could be affected based on pathfinding, verify that in isolation, and only Ariadne verifies the combined merge.

### Components Needed
- **Diff as work unit** - Not commits until Ariadne approves
- **Causal chain extraction** - Pathfinding → affected functions → extract to runnable slice
- **Isolated verification** - Each worker proves their slice works
- **Ariadne bus** - Collects diffs from all workers
- **Conflict resolution** - Same path touched by multiple workers
- **Final merge verification** - Combined result before atomic commit

---

## Phase 4: Requirements Integration (Slack)

**The final boss isn't code - it's bad requirements.**

### Auto-Pushback System
```
Ariadne receives requirement from Slack
    ↓
Palace impact analysis: "This 'small change' touches 847 rooms"
    ↓
Auto-generate pushback with architectural data:
    "This affects 12 buildings across 4 regions.
     Estimated complexity: 3 sprints.
     Did you mean to ask for this?"
    ↓
Attach blast radius visualization
    ↓
PM: "oh"
```

### Value
- **Automated "have you considered the consequences"** backed by real data
- Requirements get scoped before work begins
- Visualization makes complexity undeniable
- "We ran your requirement through the labyrinth. Here's what breaks."

---

## Implementation Order

1. **Pathfinding** - Foundation for everything else
2. **Work packages + locks** - Enable parallel dispatch
3. **Ariadne bus + diff collection** - Orchestration layer
4. **Causal slice verification** - The efficiency unlock
5. **Slack integration** - Requirements pushback

Each phase is independently useful. Pathfinding alone is valuable to any dev. The full stack is autonomous parallel development.

---

## Why This Matters

This isn't incremental tooling. This is:
- **Palace as coordination substrate** - Not docs, the actual mutex system
- **Causal verification** - Test exactly what's affected, nothing more
- **Parallel without collision** - Multiple agents, no stepping on toes
- **Requirements accountability** - Show the blast radius before committing to work

The profession doesn't disappear - it elevates. Someone still architects this. Someone still makes judgment calls. But the mechanical parts? Automated.

*"You didn't automate yourself out of a job. You automated the previous version so you can do the next one."*
