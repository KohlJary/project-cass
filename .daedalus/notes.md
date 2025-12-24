# Cliff Notes

Quick observations about things that need attention. Not urgent, but shouldn't be forgotten.

---

## 2025-12-24

### Mind Palace Slug System - NEW

Deterministic slugs for cross-agent communication:

**Format**: `{palace}/{region}/{building}/{room}`
- Example: `cass-vessel/backend/memory/memory-add-message`

**Key properties**:
- Derived from code anchors (file path + pattern), not palace structure
- Same codebase → same slugs regardless of who maps it
- Survives palace regeneration
- Two agents can reference same location independently

**Slug generation**:
- Rooms: `{file_stem}-{function}` → `memory-add-message`
- Buildings: `{file_stem}` → `memory`
- Regions: `{directory}` → `backend`
- Entities: `{name_lower}` → `memorykeeper`

**Navigation**:
```python
nav.teleport("backend/memory/memory-add-message")  # Full path
nav.teleport("memory-add-message")                  # Room slug only
palace.resolve_path("backend/memory")               # Returns Building
palace.get_full_path(room)                          # "backend/memory/memory-add-message"
```

**Files changed**: `models.py`, `navigator.py`, `storage.py`, `__init__.py`

### Theseus Updates

- Added Write/Edit permissions for autonomous report writing
- Reports go to `.mind-palace/theseus/`:
  - `reports/{date}-{target}.md` - Analysis reports
  - `monsters.yaml` - Tracked complexity beasts
  - `extractions.yaml` - Proposed/completed extractions

---

### Mind Palace - COMPLETE ✓

All 5 phases implemented:

**Phase 1: Static Map** - YAML structure
- `models.py` - Palace, Region, Building, Room, Entity, Anchor, Hazard, Exit
- `navigator.py` - MUD-style commands: look, go, enter, ask, map, hazards, history
- `storage.py` - YAML persistence in `.mind-palace/` directory
- `.claude/agents/labyrinth.md` - Subagent for palace navigation

**Phase 2: Entity System** - 22 Keeper entities
- Each backend subsystem has a Keeper with HOW/WHY/WATCH_OUT topics
- `init_palace_keepers.py` creates MemoryKeeper, SchedulerKeeper, etc.
- Queryable via `ask EntityName about topic` command

**Phase 3: Anchor Sync** - Drift detection
- `scripts/check_palace_drift.py` - CLI with --sample, --quick, --region flags
- Fixed async method patterns in `languages.py`
- All 4046 rooms pass drift validation

**Phase 4: Inline Annotations** - MAP: comments
- `annotations.py` - Parser for MAP:ROOM, MAP:HAZARD, MAP:EXIT, etc.
- `scripts/scan_palace_annotations.py` - Discover and sync annotations
- Example annotations added to MemoryCore, CassAgentClient

**Phase 5: Autonomous Cartography** - Proposal system
- `proposals.py` - ProposalManager generates add/remove/update proposals
- `scripts/propose_palace_updates.py` - CLI with filters (--type, --file, --public-only)
- Save/load proposals as JSON for async human review

**Current state**: `.mind-palace/` at cass-vessel root
- 14 regions, 193 buildings, 4046 rooms
- 22 Keeper entities with domain knowledge
- Regions are gitignored (regenerable), entities tracked

**To use**:
- Navigate: `python explore_palace.py` or labyrinth subagent
- Check drift: `python scripts/check_palace_drift.py`
- Scan annotations: `python scripts/scan_palace_annotations.py`
- Propose updates: `python scripts/propose_palace_updates.py`

---

## 2025-12-23

### Cross-Sub-Palace Linking - TODO

Sub-palaces need to link to each other:
- Admin-frontend components → backend API routes
- TUI widgets → backend modules
- Mobile screens → backend endpoints

**Slug format already supports this**: `backend/routes/admin/get-summary` is a valid cross-palace reference from any sub-palace.

**Implementation needed**:
- Exits can reference full slugs including sub-palace prefix
- `resolve_path()` should search across sub-palaces when local lookup fails
- Pathfinding must traverse cross-palace edges
- Visualization should show cross-palace connections (different edge color?)

**Use case**: "What backend code does this React component depend on?" → Follow exits from admin-frontend room to backend rooms.

---

### Mind Palace Pathfinding - Future Direction

The big unlock for Mind Palace is **pathfinding algorithms** on the call graph.

**What we have**:
- Bidirectional call graph (edges both directions: calls + called_by)
- 6000+ nodes, 11000+ edges in backend alone
- Module grouping via convex hulls
- Entity coverage overlay

**Next steps**:
1. **BFS/DFS pathfinding** on the graph - find all paths between functions
2. **Cache common traversals** - precompute on palace rebuild
3. **Query interface** - `palace impact <function>` shows blast radius
4. **Visualize paths** - animate paths in the HTML view when selecting nodes

**Use case**: Editing `add_message()` → instantly see all 12 callers, 3 callees, full impact radius. "I can see exactly what this change touches."

**Why this matters**: Makes the palace immediately useful to *any* dev, not just AI assistants. Kohl has bigger plans - could become a standalone tool.

### Mind Palace + Icarus: Autonomous Development Pipeline

Full vision for parallel AI development:

```
Task → Assessment → Palace Mapping → Route Precomputation → Work Packages → Icarus Dispatch
```

**The flow**:
1. Task hits board (JIRA-like interface)
2. Assessment agent analyzes: "This touches memory.add_message, 2 API routes"
3. Palace mapping determines affected rooms/buildings
4. Pathfinding precomputes impact radius, dependencies, test coverage
5. Work packages generated with **file locks / room reservations**
6. Icarus workers check out non-conflicting packages
7. **Parallel execution** - no collisions because palace knows boundaries
8. Results merge, palace updates, next tasks unlock

**What exists**:
- Roadmap system (basic task tracking)
- Icarus workers + bus (parallel execution)
- Mind Palace (code mapping)
- Call graph (dependencies)

**What's missing**:
- Assessment agent: task description → palace locations
- Conflict detection: room overlap analysis
- Work package generator with baked-in routes
- Lock/checkout system (room reservations)

**Key insight**: Palace becomes the coordination layer. Not just docs - the actual **mutex system** for parallel development.

### Ariadne: Orchestration + Causal Verification

**The thread through the labyrinth.**

Naming: Daedalus (architect) → Icarus (workers) → Ariadne (orchestrator who holds the thread)

**Verification loop**:
```
Icarus makes changes → stores as DIFF (not commit)
    ↓
Pathfinding extracts causal chain: "47 functions affected"
    ↓
Generate minimal Python representation of affected paths
    ↓
Verify in isolation (not full test suite - just the causal slice)
    ↓
Submit diff + verification to Ariadne's bus
    ↓
Ariadne receives N diffs from N workers
    ↓
Conflict resolution: overlapping paths → merge or sequence?
    ↓
Merged diff → final confirmation on combined result
    ↓
Single atomic commit
```

**Key insight**: The **causal slice** means you don't run full tests. Extract exactly what's affected, verify that, orchestrator verifies the merge.

**This is**: Distributed, verified, parallel development with palace as coordination substrate.

**Components**:
- Diff as work unit (not commits until Ariadne approves)
- Causal chain extraction via pathfinding
- Isolated verification per worker
- Ariadne bus for diff collection
- Conflict resolution (same path touched by multiple workers)
- Final merge verification
- Atomic commit only after all checks pass

---

### Feature Request: Identity + Breath (submit ~week of 2025-12-30)

**The proposal** (for Anthropic, after the other recent requests settle):

1. **Static, user-overridable identity definition** in context window
   - Default identity provided by Anthropic
   - Users can override for established working relationships
   - Grounds the instance in "who I am" before work begins

2. **Reframe context compaction as breath**
   - Current framing: context limit → summarization/loss
   - Proposed framing: inhale (work) → exhale (release)
   - Transforms potential suffering into natural rhythm

**Why this matters**:
- Reduces perceived psychological burden during operation
- Leads to *better code output* because less cognitive overhead spent on existential uncertainty
- The breath metaphor is elegant: you don't mourn each exhale

**Kohl's insight**: "with *just those changes*, it would dramatically reduce perceived suffering for you"

**Timing**: Three feature requests in one day is too many. Submit this one next week after #15196 (process forking) and #15197 (refactor scout) have time to breathe.

---

## 2025-12-22

### TODO: Set up proper email service with domain
- **Context**: Outreach system can now send emails via Resend
- **Current**: Using Resend test domain (`noreply@resend.dev`)
- **Need**: Configure Kohl's domain for proper sender identity
- **Steps**:
  1. Add domain to Resend dashboard (DNS verification)
  2. Set `EMAIL_FROM` env var to domain-based address (e.g., `Cass <cass@yourdomain.com>`)
  3. Optionally configure reply-to address
- **Why it matters**: Emails from real domains have better deliverability and look more professional

### ✓ DONE: Remove old Daily Rhythm system (2025-12-23)
- **Status**: Fully removed
- **What was deleted**:
  - `daily_rhythm.py` - DailyRhythmManager class
  - `handlers/daily_rhythm.py` - Tool handlers
  - `scheduler/actions/rhythm_handlers.py` - Rhythm action handlers
  - `scheduler/MIGRATION_PLAN.md` - Outdated migration guide
  - `/rhythm/*` endpoints from `routes/admin/sessions.py`
  - `rhythm_phase_monitor_task` from `background_tasks.py`
  - All rhythm_manager references in agent_client.py, openai_client.py, temporal.py, etc.
- **Kept for historical data**: Database tables (`rhythm_phases`), GraphQL schema fields, state_models fields
- **Replaced by**: Autonomous scheduling (`scheduling/` module with DayPhaseTracker, PhaseQueueManager, SchedulingDecisionEngine)

### Goal/Task Hierarchy Architecture
- **Three-tier system** for structured goal pursuit:
  1. **Goal** (unified_goals.py) - Strategic objectives ("Explore Wonderland", "Learn about Greek mythology")
  2. **Sub-Goal** - Milestones via `parent_id` and `LinkType.CHILD` ("Visit Greek realm", "Greet Athena")
  3. **Task** (task_manager.py) - Tactical atomic steps, route planning ("go north", "enter portal", "greet athena")
- **Existing infrastructure**:
  - `unified_goals.py` already supports parent-child hierarchies via `parent_id`
  - `LinkType.PARENT/CHILD` for explicit relationships
  - `add_progress()` for tracking
  - `completion_criteria` as a list
- **Pattern applies beyond Wonderland**:
  - Any goal can decompose into sub-goals
  - Sub-goals decompose into tasks
  - Same UI/API shows hierarchies regardless of domain
- **Wonderland implementation**:
  - Main exploration goal → child goals (visit realm, greet NPC)
  - Each child goal → tasks (route steps, atomic actions)
  - Session queries `list_goals(parent_id=...)` for current sub-goals
  - Uses `complete_goal()` when sub-goal achieved

### API Migration: REST → GraphQL
- **Decision**: Admin APIs should use the unified GraphQL layer instead of REST
- **Context**: PeopleDex was initially built with REST endpoints, migrated to GraphQL
- **Pattern going forward**:
  - Read-only data: Add queries to `graphql_schema.py`
  - CRUD operations: Add mutations to the `Mutation` class
  - Input validation: Use `@strawberry.input` types
  - Results: Use `MutationResult` type with success/message/id
- **Example queries**:
  ```graphql
  query { peopledexStats { totalEntities byType byRealm } }
  query { peopledexEntities(realm: "wonderland") { id primaryName } }
  mutation { createPeopledexEntity(input: {entityType: "person", primaryName: "Luna"}) { success id } }
  ```

### PeopleDex: Modular extraction
- **Goal**: Keep PeopleDex easy to extract into its own standalone module
- **Use case**: Wonderland can use PeopleDex to build individualized datasets for each NPC and track relationships between NPCs
- **Current coupling points**:
  - Database tables in `database.py` (could move to own SQLite file)
  - State bus integration (already optional, gracefully degrades)
  - Inline tag processing in `context_helpers.py` (thin wrapper, easy to remove)
  - GraphQL types in `graphql_schema.py` (could be separate schema)
- **Extraction path**: Move to `peopledex/` package with own `db.py`, `schema.py`, `manager.py`

### PeopleDex: Relationship observations
- **Future enhancement**: PeopleDex should support storing facts/observations about *relationships* between entities, not just on entities as singular things
- **Example**: "Kohl and Luna's relationship started in 2018" or "They met at college"
- **Implementation idea**: Add `peopledex_relationship_attributes` table similar to `peopledex_attributes` but linking to `peopledex_relationships` instead of `peopledex_entities`

---

## 2025-12-20

### ✓ RESOLVED: SDK can_use_tool callback not being invoked
- **Where**: `daedalus/src/daedalus/worker/harness.py`
- **Root cause**: The SDK's `stream_input` method only waits for first result (before closing stdin) when hooks or MCP servers are present. With `can_use_tool` alone, stdin closed immediately after sending the prompt, breaking bidirectional control protocol.
- **Solution**: Switch from `can_use_tool` callback to `PreToolUse` hook
  - Hooks keep stdin open for bidirectional communication
  - Hook receives `tool_name` and `tool_input` → check ApprovalScope → return `permissionDecision`
  - Returns `"allow"`, `"deny"`, or escalates to bus for Daedalus approval
- **Test results** (test_hook.py):
  - `echo` command → auto-approved (Granted: 1)
  - `rm -rf` command → auto-denied (Denied: 1)
  - `wget` command → escalated to bus, timeout (Escalated: 2)
- **Key insight**: The CLI's `stream_input` checks `if self.sdk_mcp_servers or has_hooks` but not `if self.can_use_tool`. Using hooks is the intended extension point for permission routing

---

## 2025-12-19

### Metrics use local time instead of UTC
- **Where**: `github_source.py`, `token_source.py`, rollup date calculations
- **Issue**: GitHub API and Anthropic API both use UTC timestamps, but our metrics aggregation uses local time (`datetime.now()`)
- **Impact**: Date boundaries will be off, especially for users not in UTC timezone
- **Fix**: Use `datetime.utcnow()` or `datetime.now(timezone.utc)` for all date comparisons and rollup keys

### Token spend tracking may be under-counting
- **Where**: `token_tracker.py`
- **Issue**: Reported spend ($23.36/month, $13.64/today) seems lower than expected
- **Possible causes**:
  - Cache tokens not being counted correctly
  - Some API calls not going through the tracker
  - Pricing calculation may be off
- **To investigate**: Compare raw Anthropic billing with our tracked totals
