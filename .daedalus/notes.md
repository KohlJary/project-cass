# Cliff Notes

Quick observations about things that need attention. Not urgent, but shouldn't be forgotten.

---

## 2025-12-22

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
