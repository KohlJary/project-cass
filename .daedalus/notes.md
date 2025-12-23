# Cliff Notes

Quick observations about things that need attention. Not urgent, but shouldn't be forgotten.

---

## 2025-12-23

### Mind Palace - In Progress

**What it is**: MUD-based codebase navigation for LLM agents. Represents code as navigable spatial environment (regions → buildings → rooms) instead of flat file trees. Makes architectural relationships intuitive.

**Status**: Phase 1 complete, paused for other work.

**What's built** (`backend/mind_palace/`):
- `models.py` - Palace, Region, Building, Room, Entity, Anchor, Hazard, Exit
- `navigator.py` - MUD-style commands: look, go, enter, ask, map, hazards, history
- `storage.py` - YAML persistence in `.mind-palace/` directory
- `cartographer.py` - AST analysis, auto-mapping, drift detection via signature hashes
- `api.py` - FastAPI routes for Cass to query palaces
- `wonderland_bridge.py` - Portal system connecting Wonderland to palaces
- `.claude/agents/mind-palace.md` - Subagent for palace operations

**Test palace created**: `.mind-palace/` at cass-vessel root
- Mapped `backend/mind_palace` module (166 rooms, 7 buildings, 1 region)
- Created "Labyrinth" entity - keeper of the palace with meta-knowledge

**Remaining phases** (from `spec/mind-palace-spec.md`):

1. **Phase 2: Entity System** ← Next
   - Add more entities with domain knowledge (not just Labyrinth)
   - Each subsystem gets a "keeper" who knows how/why/watch-out
   - Examples: MemoryKeeper (summarization, retrieval), SchedulerKeeper (phases, budget)

2. **Phase 3: Anchor Sync**
   - Add code anchors to map entries (already partially done)
   - Build sync checker that detects drift (done: `cartographer.check_drift()`)
   - Alert on signature changes that invalidate map

3. **Phase 4: Inline Annotations**
   - Add `# MAP:HAZARD ...`, `# MAP:EXIT ...` comments to critical code
   - Bidirectional sync: code ↔ map
   - Sync script extracts annotations to verify/update map

4. **Phase 5: Autonomous Cartography**
   - After code changes, Daedalus proposes map updates
   - Human reviews and approves
   - Map evolves with codebase

**Why this matters**: LLMs are narrative/spatial reasoners forced to work with flat file trees. Mind Palace works *with* how LLMs think. Hazards make implicit invariants explicit. Entities store institutional knowledge. Could change how agentic coding works.

**To resume**: Use mind-palace subagent or run `python scripts/explore_palace.py` in backend/

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

### TODO: Remove old Daily Rhythm system
- **Status**: Disabled but not removed
- **What's left**:
  - `daily_rhythm.py` - DailyRhythmManager class
  - `handlers/daily_rhythm.py` - Tool handlers
  - `routes/admin/sessions.py` - `/rhythm/*` endpoints (lines 1487-1520)
  - `background_tasks.py` - `rhythm_phase_monitor_task` function
  - References in `temporal.py`, `agent_client.py`, `openai_client.py`
- **Replaced by**: Autonomous scheduling (`scheduling/` module)
- **Migration guide**: `scheduler/MIGRATION_PLAN.md`
- **Action**: Can safely delete after confirming autonomous scheduling is stable

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
