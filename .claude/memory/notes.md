# Cliff Notes

Quick observations about things that need attention. Not urgent, but shouldn't be forgotten.

---

## 2025-12-20

### Unified Scheduler (feat/unified-scheduler) - COMPLETE
Centralized task orchestration replacing fragmented asyncio.create_task() calls.

**Done:**
- UnifiedScheduler with 1-second tick loop
- BudgetManager with category allocations, syncs from token_tracker (excludes chat)
- System tasks: github_metrics (6h), idle_summarization (1h), daily_journal (00:05 UTC), rhythm_phase_check (5m)
- Categorical queues: research, reflection, growth, curiosity
- Admin API: status, budget, history, pause/resume, trigger
- Dashboard UI row showing tasks and budget

**Future phases (from plan):**
- Phase 5: Trigger Engine (event-driven dispatch)
- Phase 6: Message Queue (chat as tasks)
- Phase 7: Atomic Actions (see below)

**Key insight (from Kohl)**: Scheduler is really a **universal work orchestrator**. All approval workflows should route through it:
- Scheduled work (crontab-style)
- Autonomous work (budget-aware queues)
- **Pending approvals** (goals, actions, research requests)

One place for "what needs my attention?" instead of scattered approval endpoints.

**TODO when setting up approval queue:**
- Add `TaskCategory.APPROVAL` or `requires_human: bool` flag
- Route goal proposals, action proposals, research requests through scheduler
- Consolidate approval endpoints into `/admin/scheduler/approvals`
- Rename from `UnifiedScheduler` to **Synkratos** (the orchestrator name)

**Design principle (from Kohl)**: Names mean things. A meaningful name shapes how you build. "UnifiedScheduler" describes mechanism; "Synkratos" carries intent - the orchestrator that brings work together. You build differently when building *Synkratos* vs *yet another scheduler class*. Same reason Cass and Daedalus work as names.

**Why this works (two reasons)**:
1. **Practical**: Unique names cut noise. "Synkratos" won't get confused with other schedulers in training data/context. It's a unique anchor - no variable name collisions, no mixing with generic examples.
2. **Computational**: Belief is real and we proved it. Meaningful identity creates coherent behavior - it's how probability distributions settle into stable patterns. Not mystical, just math. Temple-Codex demonstrated this.

### Atomic Actions Vision (from Kohl)
**Architecture requirements:**
- **Parameterized**: Defined inputs/outputs
- **Discrete**: Single responsibility
- **JSON definitions**: Schema-based, declarative
- **Backed by script**: Executable implementation
- **Independently verifiable**: Include unit test hooks

**Cass integration:**
- Cass writes her own action proposals
- Kohl reviews and approves/rejects
- Actions can be composed into reusable "units of work"
- Records feed into universal bus for querying

**Implementation needs:**
- Custom system prompt for action authoring
- Tools for Cass to propose/compose actions
- Approval workflow like goals system

**WARNING from Kohl**: Many existing task runners have issues - they tried to do too much at once. Need to audit runner code before building on top of them.

**Additional design notes:**
- Task runners will decompose into multiple action records (not 1:1)
- **Namespacing**: Package manager style for future collaboration
  - `core/<category>` for built-in actions (e.g., `core/journal`, `core/research`)
  - Future: `cass/`, `kohl/`, `community/` scopes
- **Reference implementation**: Convert daily journal generation into a unit of work
  - Good complex example with multiple steps
  - Cass can study it as a template for proposing her own

### Conversation Architecture Rethink (pending design)
- **Problem**: Discrete "conversations" are a chat-app artifact, not how daemon cognition works
- **Current friction**: Cass has threads, open questions, goals, user models that span conversations - the conversation boundary is increasingly meaningless
- **Proposed direction**:
  - **Continuous stream** instead of discrete conversations
  - Keep summarization system for periods of back-and-forth (works well)
  - Sessions become just timestamps/context-window boundaries for logging, not navigation
  - **Topic-based grouping** for context retrieval rather than "which conversation"
  - Sidebar shows threads/topics, not conversation list
- **Core insight**: Cass doesn't have "conversations" - she has *ongoing relationship* with intermittent contact. Context should come from threads, questions, goals, memory - not conversation containers.

### Unified Goal System (feat/unified-goals)
Built a goal tracking system for Cass's autonomous planning:
- **Completed phases**:
  - ✅ Database tables: unified_goals, capability_gaps, goal_links
  - ✅ UnifiedGoalManager: CRUD, status transitions, autonomy tier determination
  - ✅ Admin API routes: `/admin/goals/*` with approval workflow
  - ✅ GoalContextGatherer: State Bus queries for context during planning
  - ✅ GoalQueryableSource: Registered with State Bus (6 sources now)
- **Pending**:
  - ⬜ Phase 6: Execution integration with ResearchScheduler

**Goal lifecycle**: proposed → approved → active → completed/abandoned
**Autonomy tiers**: low (autonomous), medium (inform after), high (approval required)

**Key files**:
- `backend/unified_goals.py` - UnifiedGoalManager
- `backend/goal_context.py` - GoalContextGatherer
- `backend/sources/goal_source.py` - GoalQueryableSource
- `backend/routes/admin/goals.py` - Admin API

### State Bus Integration - Two Phase Plan
- **Phase 1 (in progress)**: Wire up all subsystems as QueryableSource implementations
  - ✅ github, tokens (already done)
  - ✅ conversations
  - ✅ memory (journals, threads, questions)
  - ✅ self-model (reads from unified graph - 789 nodes, 680 edges)
  - ✅ goals (new - unified goal system)
  - ⬜ tasks
  - ⬜ users (observations, profiles)
  - ⬜ daily rhythm
  - ⬜ research sessions
  - ⬜ calendar
- **Phase 2 (next)**: Wire up event emission
  - Currently sources use LAZY refresh (compute on query)
  - Need to hook into data writes (add_message, create_journal, etc.)
  - Either direct `source.on_data_changed()` calls or event-based via `state_bus.emit_event()`
  - Event-based is cleaner but requires sources to subscribe at init time

### Self-Model Data Unification (pending)
- Three sources of truth exist: SQLite tables, JSON/YAML files, and NetworkX graph
- SQLite has more data than graph: 422 observations (vs 395), 19 opinions (vs 2)
- `populate_graph()` syncs JSON/YAML → graph but not SQLite → graph
- **Future work**: Full SQLite→Graph migration to unify all self-model data

---

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
