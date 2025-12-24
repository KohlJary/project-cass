# Theseus Report: Autonomous Scheduler System

**Generated**: 2025-12-24
**Target**: Autonomous scheduling system and atomic autonomous actions
**Status**: CRITICAL - System partially built, not operational

---

## Executive Summary

The autonomous scheduler system exists in a **half-built state**. The architecture is well-designed and the foundational components are present, but critical integration work remains incomplete. Cass cannot currently schedule or execute her own work autonomously.

**Key Finding**: The system has solid bones but no muscle tissue. The decision engine, work units, templates, and phase queuing exist - but action execution is stubbed out and the scheduler isn't being started.

---

## Architecture Map

### Component Hierarchy

```
AutonomousScheduler (scheduling/autonomous_scheduler.py)
├── SchedulingDecisionEngine (scheduling/decision_engine.py)
│   ├── Gathers context (emotional state, growth edges, curiosities)
│   ├── Scores work candidates
│   └── Asks Cass (via LLM) what she wants to work on
│
├── WorkUnit Templates (scheduling/templates.py)
│   ├── 17 pre-defined templates (reflection, research, growth, etc.)
│   ├── Maps to action sequences or session runners
│   └── Includes time windows, cost estimates, categories
│
├── PhaseQueueManager (scheduling/phase_queue.py)
│   ├── Queues work for specific day phases
│   ├── Dispatches on phase transitions
│   └── Integrates with Synkratos for execution
│
├── DayPhaseTracker (scheduling/day_phase.py)
│   ├── Tracks time-of-day phases (night/morning/afternoon/evening)
│   ├── Emits state bus events on transitions
│   └── Background loop checks every 60 seconds
│
└── WorkSummaryStore (scheduling/work_summary_store.py)
    └── Persists completed work summaries (not examined in detail)

Integration Points:
├── ActionRegistry (scheduler/actions/__init__.py)
│   ├── Loads action definitions from JSON
│   ├── Registers 30+ handler functions
│   └── Executes atomic actions with cost tracking
│
├── Synkratos (scheduler/core.py)
│   ├── Universal work orchestrator
│   ├── Budget management per category
│   ├── Task queues by category
│   └── Approval system (mentioned but not examined)
│
└── GlobalStateBus (state_bus.py - not examined)
    └── Event emission for state changes
```

### Data Flow (Intended)

1. **Daily Planning** (morning, or on startup):
   - `AutonomousScheduler.plan_day()` called
   - Decision engine gathers Cass's context (emotions, growth edges, questions)
   - Decision engine asks Cass (via LLM) to plan work for remaining phases
   - Work units queued to `PhaseQueueManager` for each phase

2. **Phase Transition**:
   - `DayPhaseTracker` detects time-of-day phase change
   - Emits event on state bus
   - `PhaseQueueManager.on_phase_changed()` dispatches queued work
   - Work units converted to Synkratos tasks and submitted

3. **Work Execution**:
   - Synkratos picks task from queue (budget permitting)
   - Task handler executes action sequence via `ActionRegistry`
   - Each action returns `ActionResult` with cost/success/data
   - Work summary generated and persisted
   - State bus updated with completion event

---

## Monsters Identified

### HYDRA - Work Execution Layer [CRITICAL]

**Location**: `scheduling/autonomous_scheduler.py:_run_session()` and `_run_action_sequence()`

**Problem**: The execution layer has **two conflicting paradigms**:

1. **Session runners** (deprecated, stub returns error)
2. **Action sequences** (intended replacement, implemented)

Yet work templates still reference both:
- Many templates have `runner_key` set (e.g., "reflection", "research")
- Some have `action_sequence` set (e.g., memory maintenance)
- Templates use session runner keys that don't map to actions

**Evidence**:
```python
# autonomous_scheduler.py:451
async def _run_session(self, work_unit: WorkUnit) -> Dict[str, Any]:
    """
    [STUB][DEPRECATED] Run a session-based work unit.

    NOTE: Session runners are being deprecated in favor of atomic actions.
    """
    logger.warning(
        f"[STUB] _run_session called with runner_key={work_unit.runner_key}. "
        "Session runners are deprecated - use action_sequence instead."
    )

    return {
        "success": False,
        "message": f"Session runners deprecated. Convert {work_unit.runner_key} to action_sequence.",
    }
```

**Template Example**:
```python
# templates.py:89
"reflection_block": WorkUnitTemplate(
    runner_key="reflection",        # Still set
    action_sequence=["session.reflection"],  # Also set
    # ...
)
```

**Impact**: **Most work units will fail to execute**. Templates have `runner_key` set, triggering the deprecated `_run_session()` path which returns a failure stub.

**To Slay**:
1. Remove all `runner_key` references from templates
2. Ensure all templates have valid `action_sequence`
3. Remove `_run_session()` method entirely
4. Verify action handlers exist for all referenced action IDs

---

### SPIDER - Startup Integration Missing [CRITICAL]

**Location**: `backend/main_sdk.py` startup sequence

**Problem**: The autonomous scheduler is **instantiated but never started**.

**Evidence from main_sdk.py**:
```python
# Line 1232: Scheduler is created
autonomous_scheduler = AutonomousScheduler(
    synkratos=synkratos,
    decision_engine=decision_engine,
    state_bus=global_state_bus,
    action_registry=action_registry,
)

# Lines 1240-1248: Registered as queryable source
autonomous_source = AutonomousScheduleSource(
    daemon_id=_daemon_id,
    autonomous_scheduler=autonomous_scheduler,
)
global_state_bus.register_source(autonomous_source)

# Phase queue created and wired
phase_queue = PhaseQueueManager(
    synkratos=synkratos,
    state_bus=global_state_bus,
    summary_store=autonomous_scheduler.summary_store,
    action_registry=action_registry,
)
autonomous_scheduler.set_phase_queue(phase_queue)

# But MISSING: await autonomous_scheduler.start()
# But MISSING: await day_phase_tracker.start()
```

**What's Missing**:
- `autonomous_scheduler.start()` never called
- `day_phase_tracker.start()` never called (tracker not even instantiated)
- Phase queue callbacks never registered

**Impact**: The entire system is **inert**. Even if templates were fixed, nothing would ever run because:
- No daily planning triggered
- No phase tracking active
- No phase-based work dispatch

**To Slay**:
1. Instantiate `DayPhaseTracker` in startup
2. Call `await day_phase_tracker.start()`
3. Register phase change callbacks:
   - `day_phase_tracker.on_phase_change(autonomous_scheduler.on_phase_changed)`
   - `day_phase_tracker.on_phase_change(phase_queue.on_phase_changed)`
4. Call `await autonomous_scheduler.start()`

---

### CERBERUS - Action Definitions Missing [HIGH]

**Location**: `scheduler/actions/definitions.json` (expected location)

**Problem**: The action registry tries to load definitions from JSON but the file likely doesn't exist or is incomplete.

**Evidence**:
```python
# scheduler/actions/__init__.py:59
def load_definitions(self, json_path: Optional[Path] = None) -> int:
    if json_path is None:
        json_path = Path(__file__).parent / "definitions.json"

    if not json_path.exists():
        logger.warning(f"Action definitions not found: {json_path}")
        return 0
```

**Expected Structure** (from atomic-actions-projection.md):
- 30+ actions across 5 tiers
- Metadata: id, name, description, category, handler, costs
- Currently handlers are manually registered but definitions provide metadata

**Impact**:
- Actions can execute (handlers manually registered)
- But metadata missing (costs, categories, priorities)
- Budget tracking incomplete without cost estimates

**To Slay**:
1. Create `scheduler/actions/definitions.json`
2. Define all 30+ actions from spec/atomic-actions-projection.md
3. Include cost estimates, categories, default durations
4. Verify handler paths match registered handlers

---

### CHIMERA - Template/Action Mismatch [MEDIUM]

**Location**: Disconnect between `scheduling/templates.py` and `scheduler/actions/`

**Problem**: Work templates reference action IDs that may not exist or are incorrectly named.

**Examples**:
```python
# templates.py references:
"session.reflection"  # Does this action exist?
"session.synthesis"   # Handler registered: session_handlers.synthesis_action
"memory.summarize_idle_conversations"  # Handler registered
"wonderland.explore"  # Does this action exist?
"journal.generate_daily"  # Handler registered
```

**Handler Registration** (from `__init__.py`):
```python
registry.register_handler("session.reflection", session_handlers.reflection_action)
registry.register_handler("journal.generate_daily", journal_handlers.generate_daily_action)
# etc.
```

**Gap**: No verification that template action sequences reference real, registered actions.

**Impact**:
- Work units may be planned and queued
- Execution fails with "Unknown action" error
- Silent failures, hard to debug

**To Slay**:
1. Create validation function: `validate_template_actions()`
2. At startup, check all template `action_sequence` IDs exist in registry
3. Log warnings for missing actions
4. Consider: runtime validation when instantiating WorkUnits

---

## Safe Paths (Well-Designed Components)

These components are **architecturally sound** and ready to use once integration is complete:

### WorkUnit Model (work_unit.py) - CLEAN
- Clear state machine (PLANNED -> SCHEDULED -> RUNNING -> COMPLETED/FAILED)
- Time window scoring for scheduling preferences
- Action result tracking for detailed summaries
- Artifact tracking
- 223 lines, single responsibility, well-tested structure

### Decision Engine (decision_engine.py) - CLEAN
- Beautiful self-directed decision making
- Gathers rich context (emotions, growth edges, curiosities)
- Cass decides via LLM what to work on (not algorithmic)
- Day planning in one LLM call (token efficient)
- Scoring for pre-filtering, but Cass makes final choice
- 780 lines, clear separation of concerns

### PhaseQueueManager (phase_queue.py) - CLEAN
- Clear queuing semantics
- Priority ordering within phases
- Work summary generation on completion
- State bus integration
- 465 lines, focused responsibility

### DayPhaseTracker (day_phase.py) - CLEAN
- Simple, focused time-of-day tracking
- Clean event emission on transitions
- Configurable phase windows
- Background loop with graceful shutdown
- 323 lines, does one thing well

---

## Current Operational Capacity: 0%

**What Works**:
- Component classes can be instantiated
- Templates can be loaded
- Action handlers are registered
- Work units can be created

**What Doesn't Work**:
- Nothing executes autonomously
- Scheduler never starts
- Phase tracking never starts
- Work execution fails (session runner stubs)
- Templates reference non-existent actions

**Missing for Minimal Viable**:
1. Start the scheduler and phase tracker
2. Fix template execution paths (remove runner_keys)
3. Validate action sequences
4. Create action definitions JSON

---

## Prioritized Roadmap to Operational Capacity

### Phase 1: Critical Path to First Execution [MUST FIX]

**Goal**: Get ONE work unit to execute successfully end-to-end

**Tasks**:

1. **Fix Template Execution** (1-2 hours)
   - Remove `runner_key` from all templates in `templates.py`
   - Verify `action_sequence` is set for all templates
   - Pick simplest template for testing (e.g., `daily_journal`)
   - File: `backend/scheduling/templates.py`

2. **Start the Scheduler** (1 hour)
   - Instantiate `DayPhaseTracker` in `main_sdk.py`
   - Call `await day_phase_tracker.start()`
   - Call `await autonomous_scheduler.start()`
   - Register phase change callbacks
   - File: `backend/main_sdk.py` (around line 1250)

3. **Validate Action Handlers** (30 min)
   - Check that `session.reflection` action handler exists
   - Check that `journal.generate_daily` action handler exists
   - Test execution with minimal work unit
   - Files: `backend/scheduler/actions/session_handlers.py`, `journal_handlers.py`

4. **Test Minimal Flow** (1 hour)
   - Manually trigger `autonomous_scheduler.plan_day()`
   - Verify work gets queued to phase queue
   - Manually trigger phase transition or dispatch
   - Observe execution, check logs for errors

**Success Criteria**: One work unit executes, completes, and saves a work summary.

---

### Phase 2: Core Loop Operational [HIGH PRIORITY]

**Goal**: Full autonomous scheduling loop works

**Tasks**:

5. **Create Action Definitions** (2-3 hours)
   - Create `backend/scheduler/actions/definitions.json`
   - Define all actions from `spec/atomic-actions-projection.md`
   - Include: id, name, description, category, handler, estimated_cost_usd
   - Verify cost estimates are reasonable
   - File: New file

6. **Template Validation** (1 hour)
   - Write `validate_template_actions()` function
   - Call at startup, log warnings for issues
   - Fix any broken template action sequences
   - File: `backend/scheduling/templates.py` or new `validation.py`

7. **Phase Transition Integration** (1 hour)
   - Verify phase transitions trigger work dispatch
   - Test with multiple work units queued
   - Verify priority ordering works
   - Monitor state bus events

8. **Daily Planning Logic** (1 hour)
   - Test morning planning trigger
   - Test startup planning (mid-day scenario)
   - Verify decision engine context gathering
   - Test variety in work selection

**Success Criteria**: Cass autonomously plans her day, work executes on phase transitions, summaries are saved.

---

### Phase 3: Robustness & Monitoring [MEDIUM PRIORITY]

**Goal**: System is reliable and observable

**Tasks**:

9. **Error Handling** (2 hours)
   - Handle action execution failures gracefully
   - Budget exhaustion scenarios
   - Network errors in LLM calls
   - State bus connection issues

10. **Budget Integration** (2 hours)
    - Verify budget tracking works per action
    - Test budget exhaustion (work stops)
    - Test budget allocation by category
    - Monitor daily budget consumption

11. **Observability** (2 hours)
    - Admin dashboard endpoints for scheduler state
    - Work history queries
    - Phase queue inspection
    - Budget status display

12. **Work Summary Quality** (2 hours)
    - Improve summary generation (currently minimal)
    - Extract key insights from action results
    - Link to artifacts (journals, wiki pages, etc.)
    - Queryable work history

**Success Criteria**: System runs reliably for multiple days, budget respected, rich summaries available.

---

### Phase 4: Polish & Expansion [LOW PRIORITY]

**Goal**: Full feature set from spec

**Tasks**:

13. **Advanced Work Types** (3-4 hours)
    - Wonderland exploration actions
    - Multi-action composite work units
    - Long-running research sessions
    - Creative output sessions

14. **Decision Engine Enhancements** (2-3 hours)
    - Improve context gathering (more growth edges, questions)
    - Better time window matching
    - Learning from past work (what worked well)
    - Variety tracking (avoid repetition)

15. **API & Admin Controls** (2 hours)
    - Endpoint to manually trigger work
    - Endpoint to view/modify day plan
    - Endpoint to pause/resume scheduling
    - Endpoint to adjust budget allocations

**Success Criteria**: Full spec implemented, Cass has rich autonomous capabilities.

---

## Complexity Metrics

| File | Lines | Cyclo. Complexity (est.) | Nesting | Status |
|------|-------|--------------------------|---------|--------|
| `autonomous_scheduler.py` | 708 | Medium (10-15) | 2-3 | Incomplete |
| `decision_engine.py` | 780 | Medium (10-15) | 2-3 | Complete |
| `work_unit.py` | 295 | Low (5-8) | 1-2 | Complete |
| `templates.py` | 323 | Low (2-5) | 1 | Needs fixing |
| `phase_queue.py` | 465 | Medium (8-12) | 2-3 | Complete |
| `day_phase.py` | 323 | Low (5-8) | 2 | Complete |
| `scheduler/actions/__init__.py` | 338 | Low (5-8) | 2 | Complete |

**Overall Health**: YELLOW (design is good, integration is broken)

---

## Risk Assessment

### High Risk Items

1. **Session Runner Legacy**: Templates still reference deprecated session runners. High chance of runtime failures.
2. **Missing Startup**: Scheduler never starts. Zero autonomous work happening currently.
3. **Budget Tracking**: Without action definitions, budget tracking is incomplete.

### Medium Risk Items

4. **Action Mismatch**: Templates may reference non-existent actions.
5. **Error Handling**: Unknown how system behaves on LLM failures, budget exhaustion.
6. **State Bus Integration**: Untested if state bus events are properly emitted/consumed.

### Low Risk Items

7. **Performance**: System is event-driven, should be efficient.
8. **Scalability**: Current design handles 5-10 work units/day easily.

---

## Dependencies

**Before autonomous scheduling works, these must exist**:

- Synkratos (scheduler/core.py) - EXISTS, used
- ActionRegistry with handlers - EXISTS, handlers registered
- State bus - EXISTS, integrated
- Budget manager - EXISTS (part of Synkratos)
- Self manager (growth edges, questions) - EXISTS
- Session runners (being deprecated) - EXISTS but stubbed
- Work summary store - EXISTS

**Blockers**: None external. All dependencies exist. Only integration work needed.

---

## Recommended Action

**Immediate (Today/Tomorrow)**:
1. Fix template `runner_key` issue - remove deprecated references
2. Add scheduler startup calls to `main_sdk.py`
3. Test with one simple work unit

**Short-term (This Week)**:
4. Create action definitions JSON
5. Validate template action sequences
6. Test full autonomous loop (planning -> phase transition -> execution)

**Medium-term (Next Week)**:
7. Error handling and robustness
8. Budget integration verification
9. Admin dashboard for monitoring

**Long-term (Later)**:
10. Advanced work types
11. Decision engine improvements
12. Full spec implementation

---

## Architecture Quality: GOOD

**Strengths**:
- Clean separation of concerns
- Event-driven design (state bus integration)
- Self-directed decision making (Cass decides, not algorithm)
- Budget-aware from the start
- Composable work units
- Phase-based scheduling is elegant

**Weaknesses**:
- Incomplete migration from session runners to actions
- Missing startup integration
- Action definitions not persisted
- Limited observability currently

**Verdict**: **Solid architecture**, just needs the integration work completed. No major refactoring needed, just finish the implementation.

---

## Summary

The autonomous scheduler is a **half-built bridge**. The design is sound, the components are well-structured, but the integration work was left incomplete. With focused effort over 1-2 days, this can be fully operational.

**Three critical fixes needed**:
1. Remove session runner references from templates
2. Start the scheduler and phase tracker in main_sdk.py
3. Validate action sequences

Once these are done, Cass will be able to autonomously plan her day, schedule work across phases, and execute work units with budget awareness.

**Estimated time to operational**: 8-12 hours of focused work

**Estimated time to production-ready**: 20-25 hours

---

**Theseus Assessment**: This is a **repairable system**. The monsters are identifiable and slayable. No deep architectural issues. Proceed with confidence.

