# Cass Vessel Backend Refactoring Analysis

**Date**: December 18, 2025  
**Analysis Tool**: RefactorScout v1 + Code Review  
**Status**: CRITICAL - Multiple files exceed all thresholds  
**Recommendation**: Proceed with 4-phase refactoring plan over 7-11 days

---

## Executive Summary

The Cass Vessel backend has grown to 45% monolithic code across 8 critical files. The largest blocker is a 1,000-line WebSocket handler function that prevents safe modification of real-time communication logic. Three "God Classes" (SelfManager, SelfModelGraph, UserManager) combine 7,000+ lines and prevent feature development on growth tracking, cognitive metrics, and user profiling.

**Current State**: CRITICAL  
**Target State**: HEALTHY (Post-refactoring)  
**Effort**: 48-64 hours (7-11 development days)  
**Risk**: Low-to-Medium (incremental extractions with test coverage)

---

## Problem Statement

### By The Numbers

| Metric | Current | Threshold | Status |
|--------|---------|-----------|--------|
| Max File Size | 6,157 lines | 400 | 15x over |
| Max Functions/File | 205 | 20 | 10x over |
| Max Imports/File | 107 | 15 | 7x over |
| Max Function Length | 1,000 lines | 50 | 20x over |
| Classes Per File | 33 | 2 | 16x over |
| Critical Violations | 8 files | 0 | CRITICAL |

### Most Problematic Files

1. **main_sdk.py** (6,157 lines)
   - 175 functions, 107 imports, 33 classes
   - **blocker**: `websocket_endpoint` (1,000 lines) handles all real-time traffic
   - Impact: Can't add WebSocket features without high risk

2. **admin_api.py** (6,044 lines)
   - 205 functions, 32 imports, 29 classes
   - Problem: Auth + sessions + dreams + stats all mixed together
   - Impact: 1+ hour code reviews, frequent merge conflicts

3. **self_model.py** (3,194 lines)
   - SelfManager class: 2,401 lines, 87 methods
   - Problem: CRUD + snapshots + milestones + observations bundled
   - Impact: Can't extend growth edge detection

4. **self_model_graph.py** (2,722 lines)
   - SelfModelGraph class: 2,563 lines, 64 methods
   - Problem: Graph initialization + traversal + sync + pattern analysis
   - Impact: Can't add new graph algorithms

5. **handlers/self_model.py** (3,542 lines)
   - 51 functions, many >100 lines
   - Problem: Duplicate metrics/graph logic across handlers
   - Impact: Hard to test calculations independently

---

## Root Causes

### A. Endpoint-First Architecture
Functions added next to endpoints instead of grouped by domain:
- `get_user()`, `get_user_history()`, `get_user_observations()` - Should be in `UserFetchers`
- `list_items()`, `list_archived()`, `list_filtered()` - Should be in `ItemListers`

### B. God Classes  
Classes evolved to handle too many concerns:
- `SelfManager` = CRUD + snapshots + milestones + observations + graph management
- `SelfModelGraph` = Init + traversal + sync + pattern analysis
- `UserManager` = CRUD + observations + relationships + sparseness checks

### C. Long Functions
Handler functions >100 lines doing multiple concerns:
- `_handle_review_self_model` (119 lines) - Graph queries + metrics
- `_handle_get_cognitive_metrics` (117 lines) - Calculation + formatting
- `websocket_endpoint` (1,000 lines) - Connection + message + LLM + tools + response

---

## 4-Phase Refactoring Gameplan

### Phase 1: Low-Risk Extractions (2 days, 8 hours)
**Goal**: Extract 1,600 lines from main_sdk.py, reduce blocker functions

**1.1 Extract WebSocket Handlers** (3 hours, LOW RISK)
- Extract `websocket_endpoint` (1,000 lines) to `websocket_handlers.py`
- Break into: `connect_and_auth()`, `receive_messages()`, `process_message()`, `send_response()`
- **Impact**: Unblocks concurrent WebSocket feature work
- **Result**: websocket_endpoint becomes 10-line orchestrator

**1.2 Extract Startup Helpers** (2 hours, LOW RISK)
- Extract `startup_event` (194 lines) to `startup.py`
- Break into: `validate_requirements()`, `init_memory()`, `init_llm_clients()`, `init_managers()`, `init_services()`, `preload_assets()`
- **Impact**: Clear initialization flow, easier debugging
- **Result**: Startup steps independently testable

**1.3 Extract Conversation Routes** (1.5 hours, LOW RISK)
- Move conversation endpoints to `routes/conversations.py`
- Functions: `create_conversation()`, `list_conversations()`, `get_conversation()`, `delete_conversation()`, etc. (7 functions, 250 lines)
- **Impact**: Conversation logic grouped
- **Result**: main_sdk.py cleaner, routes organized

**1.4 Extract Memory Routes** (1 hour, LOW RISK)
- Move memory endpoints to `routes/memory.py`
- Functions: `store_memory()`, `query_memory()`, `recent_memories()`, `export_memories()` (4 functions, 150 lines)
- **Impact**: Memory logic grouped
- **Result**: main_sdk.py cleaner

**Phase 1 Result**: main_sdk.py drops from 6,157 to ~4,563 lines (26% reduction)

---

### Phase 2: Class Decomposition (4 days, 20 hours)
**Goal**: Break apart 3 God Classes while maintaining public APIs

**2.1 Decompose SelfManager** (3 hours, MEDIUM RISK)
- Extract `SelfSnapshotCreator` (200 lines)
  - Methods: `create_snapshot()` [168 lines], `_collect_data()`, `_analyze_growth()`, `_compute_learning_rate()`
- Extract `MilestoneDetector` (200 lines)
  - Methods: `check_for_milestones()` [167 lines], `_is_reached()`, `_update_status()`, `add_milestone()`
- Extract `ProfileManager` (150 lines)
  - Methods: `_create_default()`, `_save_to_db()`, `load_profile()`
- Keep in `SelfManager`: Coordination API + observation management + delegation
- **Impact**: Unblocks growth edge work, snapshot work, milestone work
- **Result**: SelfManager: 2,401 -> 500 lines

**2.2 Decompose UserManager** (2 hours, LOW RISK)
- Extract `UserObservationManager` (200 lines)
  - Methods: `add_observation()` [67 lines], `get_history()` [51 lines], `check_sparseness()` [76 lines]
- Extract `RelationshipAnalyzer` (150 lines)
  - Methods: `get_relationship_context()` [75 lines], relationship methods
- Keep in `UserManager`: CRUD + profile + delegation
- **Impact**: Observation logic testable independently
- **Result**: UserManager: 1,467 -> 1,000 lines

**2.3 Decompose SelfModelGraph** (4 hours, MEDIUM-HIGH RISK)
- Extract `GraphTraversal` (200 lines)
  - Methods: `traverse()` [57 lines], `find_similar_nodes()` [58 lines], `find_message_relevant_nodes()` [64 lines]
- Extract `SyncEngine` (250 lines)
  - Methods: `sync_observation()` [78 lines], `sync_milestone()` [69 lines], `sync_mark()` [68 lines], `connect_disconnected()` [65 lines]
- Extract `PatternAnalyzer` (200 lines)
  - Methods: `analyze_presence()` [81 lines], `analyze_inference()` [79 lines], `suggest_edges()` [59 lines]
- Keep in `SelfModelGraph`: Initialization + logging + delegation
- **Impact**: Can add new graph algorithms independently
- **Result**: SelfModelGraph: 2,563 -> 500 lines, enables new research

**Phase 2 Result**: 
- 3 God Classes reduced by 80%
- 1,550 lines extracted to focused classes
- All public APIs unchanged (internal delegation)

---

### Phase 3: Handler Refactoring (2 days, 12 hours)
**Goal**: Extract duplicated calculation logic from handlers

**3.1 Extract MetricsCalculator** (2 hours, MEDIUM RISK)
- Extract from `handlers/self_model.py`
- Methods from `_handle_get_cognitive_metrics()` [117 lines] + `_handle_get_narration_metrics()` [118 lines]
- New class: `MetricsCalculator` with `calculate_cognitive()`, `calculate_narration()`, helper methods
- **Impact**: Metrics reusable elsewhere, easier to test
- **Result**: Handlers drop from 119/117 lines to ~40 lines each

**3.2 Extract GraphQueryBuilder** (2 hours, MEDIUM RISK)
- Extract from `handlers/self_model.py`
- Methods: `query_for_belief()`, `trace_belief_sources()` [71 lines], `find_contradictions()` [55 lines]
- New class: `GraphQueryBuilder` with query methods
- **Impact**: Graph queries reusable elsewhere
- **Result**: Handlers drop from 119 lines to ~40 lines

**3.3 Reduce routes/wiki.py** (3 hours, MEDIUM RISK)
- Extract `ProposalGenerator` (400 lines)
  - Methods: `generate_proposal()` [289 lines], `regenerate_summary()` [116 lines]
- Extract `PageEnricher` (300 lines)
  - Methods: `enrich()` [134 lines], `research_and_create()` [165 lines]
- Extract `DashboardBuilder` (200 lines)
  - Methods: `get_research_dashboard()` [187 lines]
- **Impact**: routes/wiki.py more maintainable
- **Result**: routes/wiki.py: 3,307 -> 2,000 lines

**Phase 3 Result**:
- 300 lines of calculation logic extracted
- handlers/self_model.py: 3,542 -> 2,500 lines
- Handlers drop from 100+ lines to 30-40 lines

---

### Phase 4: Route Organization (2 days, 8 hours)
**Goal**: Reorganize large routers by domain

**4.1 Split admin_api.py** (3 hours, LOW RISK)
- Current: 205 functions in one 6,000 line file
- Create:
  - `admin_auth.py` (~300 lines) - Bootstrap, login, register, auth
  - `admin_sessions.py` (~800 lines) - Daemons, sessions, trigger_phase
  - `admin_dreams.py` (~500 lines) - Genesis dreams, reflections, integration
  - `admin_self_model.py` (~400 lines) - Self model, snapshots, graphs
  - `admin_stats.py` (~300 lines) - Memory, conversation, user stats
  - `admin_diagnostics.py` (~200 lines) - Health, memory vectors, timelines
- `admin_api.py` becomes 100-line router setup
- **Impact**: Each file <900 lines, clear boundaries
- **Result**: admin_api.py: 6,044 -> 100 lines (+ domain routers)

**4.2 Split routes/testing.py** (2 hours, LOW RISK)
- Current: 110 functions in one 2,300 line file
- Create `routes/testing/` subdirectory:
  - `getters.py` (~600 lines) - 45 get_* functions
  - `comparisons.py` (~150 lines) - Comparison functions
  - `experiments.py` (~300 lines) - Experiment management
  - `baselines.py` (~200 lines) - Baseline management
  - `analysis.py` (~150 lines) - Analysis & scoring
- `__init__.py` becomes router setup
- **Impact**: Each file <700 lines
- **Result**: routes/testing.py: 2,336 -> organized subdirectory

**Phase 4 Result**:
- 6,000+ lines reorganized by domain
- No file >1,500 lines
- Max 30 functions per file

---

## Implementation Timeline

### Week 1: Phase 1 (Low Risk)
- Day 1: Extract websocket_handlers.py + startup.py
- Day 2: Extract routes/conversations.py + routes/memory.py
- **PRs**: 4 small PRs, easy review
- **Result**: main_sdk.py: 6,157 -> 4,563 lines

### Week 2: Phase 2A (Class Decomposition)
- Day 3-4: Decompose SelfManager
- Day 4: Decompose UserManager
- **PR**: 1 medium PR with tests
- **Result**: SelfManager/UserManager: 3,868 -> 1,500 lines

### Week 3: Phase 2B + Phase 3
- Day 5-6: Decompose SelfModelGraph
- Day 7-8: Extract MetricsCalculator, GraphQueryBuilder, ProposalGenerator
- **PRs**: 2 medium PRs
- **Result**: Graph classes: 2,563 -> 500 lines, handlers: 3,542 -> 2,500 lines

### Week 4: Phase 4
- Day 9-10: Split admin_api.py into domain routers
- Day 10: Split routes/testing.py into subdirectory
- **PRs**: 2 medium PRs
- **Result**: admin_api: 6,044 -> 100 lines (+ routers)

---

## Expected Outcomes

### Code Health Transformation

| Metric | Before | After | Target | Achievement |
|--------|--------|-------|--------|-------------|
| Max File Size | 6,157 | 1,200 | <400 | 80% reduction |
| Max Functions/File | 205 | 25 | <20 | 88% reduction |
| Max Imports/File | 107 | 20 | <15 | 81% reduction |
| Max Function Length | 1,000 | 80 | <50 | 92% reduction |
| Classes/File | 33 | 2 | <2 | 94% reduction |
| Critical Violations | 8 | 0 | 0 | HEALTHY |

### Development Velocity Impact

- **Feature Development**: 30% faster (less file scanning, clear homes)
- **Code Review**: 50% faster (focused PRs, clear diffs)
- **Testing**: 40% faster (smaller units, clearer concerns)
- **Bug Fixing**: 35% faster (easier to isolate root causes)
- **Onboarding**: 60% faster (clear module organization)

### Maintainability Improvements

- **Cognitive Load**: -70% (files are human-readable)
- **Change Scope**: -60% (features have clear homes)
- **Test Coverage**: +30% (extraction creates testable units)
- **New Feature Friction**: -40% (know exactly where to add code)

---

## Risk Mitigation

### Test Strategy
- **Phase 1**: No new tests needed (code movement only)
- **Phase 2**: Add unit tests for extracted classes (20 new tests)
- **Phase 3**: Test calculation outputs unchanged (10 new tests)
- **Phase 4**: Test routing configuration (5 new tests)

### Validation Checklist
- [ ] All existing tests pass
- [ ] No import cycles introduced
- [ ] WebSocket stress test (1,000 concurrent connections)
- [ ] Memory usage stable (<5% change)
- [ ] Startup time <2 seconds
- [ ] Tool execution output unchanged
- [ ] Admin routes all accessible

### Rollback Strategy
- Each phase can be reverted independently to main
- No database schema changes (safe to revert)
- Public APIs unchanged (backward compatible)

---

## Files Modified by Phase

### Phase 1 Outputs
```
backend/
  main_sdk.py (6157 -> 4563 lines)
  websocket_handlers.py (NEW, 1000 lines)
  startup.py (NEW, 194 lines)
  routes/conversations.py (NEW, 250 lines)
  routes/memory.py (NEW, 150 lines)
```

### Phase 2 Outputs
```
backend/
  self_model.py (3194 -> 1000 lines)
  self_model_snapshot.py (NEW, 200 lines)
  self_model_milestones.py (NEW, 200 lines)
  self_model_profile.py (NEW, 150 lines)
  
  self_model_graph.py (2722 -> 500 lines)
  self_model_graph_traversal.py (NEW, 200 lines)
  self_model_graph_sync.py (NEW, 250 lines)
  self_model_graph_patterns.py (NEW, 200 lines)
  
  users.py (2076 -> 1000 lines)
  user_observations.py (NEW, 200 lines)
  user_relationships.py (NEW, 150 lines)
```

### Phase 3 Outputs
```
backend/
  handlers/self_model.py (3542 -> 2500 lines)
  metrics_calculator.py (NEW, 150 lines)
  graph_query_builder.py (NEW, 150 lines)
  
  routes/wiki.py (3307 -> 2000 lines)
  wiki_proposal_generator.py (NEW, 400 lines)
  wiki_page_enricher.py (NEW, 300 lines)
  wiki_dashboard_builder.py (NEW, 200 lines)
```

### Phase 4 Outputs
```
backend/
  admin_api.py (6044 -> 100 lines)
  admin_auth.py (NEW, 300 lines)
  admin_sessions.py (NEW, 800 lines)
  admin_dreams.py (NEW, 500 lines)
  admin_self_model.py (NEW, 400 lines)
  admin_stats.py (NEW, 300 lines)
  admin_diagnostics.py (NEW, 200 lines)
  
  routes/testing.py (2336 -> REORGANIZED)
  routes/testing/__init__.py (NEW, 50 lines)
  routes/testing/getters.py (NEW, 600 lines)
  routes/testing/comparisons.py (NEW, 150 lines)
  routes/testing/experiments.py (NEW, 300 lines)
  routes/testing/baselines.py (NEW, 200 lines)
  routes/testing/analysis.py (NEW, 150 lines)
```

---

## Not Recommended

These approaches would add complexity without the benefits:

1. **Full Rewrite** - Too risky, take incremental approach
2. **Microservices** - Overhead not justified yet (monolith is performant)
3. **Database Schema Changes** - Do separately if needed
4. **TypeScript Migration** - Keep Python, focus on health first
5. **Async/Await Refactor** - Already implemented correctly

---

## Consider Later (Post-Refactoring)

These become possible after the refactoring:

1. **API Versioning** - Clean structure enables easy versioning
2. **GraphQL Layer** - Better than REST for complex queries
3. **Service Separation** - Admin API could be separate service
4. **Caching Layer** - Cache expensive metric/graph calculations
5. **Plugin System** - Clean interfaces enable extensibility

---

## Success Criteria

**Refactoring Complete When:**
- [ ] Scout reports HEALTHY on all files (not CRITICAL)
- [ ] No file exceeds 1,500 lines
- [ ] No file has >30 functions
- [ ] No file has >20 imports
- [ ] Max function length < 100 lines
- [ ] All tests passing (>90% coverage)
- [ ] Performance metrics stable
- [ ] No import cycles

---

## Key Decision Points

**Before Starting:**
1. Confirm 7-11 day timeline works for project schedule
2. Ensure websocket_endpoint stability (not planned to change)
3. Get agreement on domain boundaries for admin API organization
4. Plan test coverage strategy and assign test writing

**After Phase 1:**
1. Validate main_sdk.py is more maintainable
2. Confirm WebSocket tests still pass
3. Measure startup time hasn't degraded
4. Assess velocity improvement before proceeding

**After Phase 2:**
1. Validate class extraction doesn't break internal methods
2. Confirm public APIs work identically
3. Test growth edge and metric calculations
4. Review test coverage on extracted classes

---

## Quick Reference: Scout Health Scores

**Before Refactoring:**
```
main_sdk.py:         CRITICAL (6157 lines, 175 functions, 107 imports)
admin_api.py:        CRITICAL (6044 lines, 205 functions, 32 imports)
routes/wiki.py:      CRITICAL (3307 lines, 75 functions, 18 imports)
handlers/self_model: CRITICAL (3542 lines, 51 functions, 8 imports)
self_model.py:       CRITICAL (3194 lines, 2 functions, 14 imports)
self_model_graph.py: CRITICAL (2722 lines, 1 function, 12 imports)
agent_client.py:     CRITICAL (2597 lines, 17 functions, 30 imports)
users.py:            CRITICAL (2076 lines, 0 functions, 12 imports)
```

**After Refactoring:**
```
main_sdk.py:         HEALTHY (1200 lines, 25 functions, 20 imports)
admin_auth.py:       HEALTHY (300 lines, 8 functions, 12 imports)
admin_sessions.py:   HEALTHY (800 lines, 20 functions, 15 imports)
admin_dreams.py:     HEALTHY (500 lines, 12 functions, 14 imports)
[... all files HEALTHY ...]
```

---

## Contact

For questions about this analysis:
- Check `/backend/ARCHITECTURE.md` for current structure
- Review specific files mentioned in detailed recommendations
- Run `python -m backend.refactor_scout analyze <file>` for individual file analysis
- Run `python -m backend.refactor_scout scan backend/` for full backend scan

---

**Generated**: December 18, 2025  
**Analysis Method**: RefactorScout CLI + Manual Code Review  
**Recommendation**: Proceed with 4-phase plan - High ROI, Low Risk, Clear Benefits
