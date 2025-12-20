# Cliff Notes

Quick observations about things that need attention. Not urgent, but shouldn't be forgotten.

---

## 2025-12-20

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
