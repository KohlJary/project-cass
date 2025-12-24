# Autonomous Scheduler - Work Package Manifest

**Status**: Ready for dispatch  
**Total Estimated Hours**: 8-10 hours  
**Critical Path**: WP1 -> WP2 -> (WP3 + WP4 in parallel) -> WP5  
**Target Completion**: 1-2 days of focused work  

---

## Work Package Summary

| ID | Title | Priority | Hours | Status | Phase | Depends On |
|---|---|---|---|---|---|---|
| WP1 | Fix Template Execution Paths | P0 | 1.5 | ready | 1 | - |
| WP2 | Start Scheduler (Startup Wiring) | P0 | 1.0 | ready | 1 | WP1 |
| WP3 | Validate Action Handlers | P1 | 1.5 | ready | 1 | WP1, WP2 |
| WP4 | Create Action Definitions JSON | P1 | 2.5 | ready | 1 | WP3 |
| WP5 | Test and Verify End-to-End | P1 | 1.5 | ready | 1 | WP1-4 |

---

## Execution Strategy

### Critical Path (Blocking)
1. **WP1** (1.5 hrs) - FIX: Remove runner_key from templates
   - Must complete before scheduling can work
   - Straightforward code deletion
   - Low risk, high value

2. **WP2** (1.0 hrs) - WIRE: Start scheduler and phase tracker
   - Depends on WP1 complete
   - Can code in parallel but execution depends
   - Activates the system

### Parallel Work (Can start after WP1)
3. **WP3** (1.5 hrs) - VALIDATE: Action handlers and sequences
   - Quality assurance
   - Prevents silent failures
   - Blocks WP5 testing

4. **WP4** (2.5 hrs) - CREATE: Action definitions JSON
   - Independent work
   - Metadata for budgeting
   - Blocks WP5 verification

### Integration Testing (Gate)
5. **WP5** (1.5 hrs) - TEST: End-to-end verification
   - Integration test
   - Validates all previous work
   - Discovers bugs

---

## Work Package Details

### WP1: Fix Template Execution Paths
**File**: `/home/jaryk/cass/cass-vessel/backend/scheduling/templates.py`

**What's Broken**:
- Templates have `runner_key` field set (e.g., "reflection", "research")
- Code routes to deprecated `_run_session()` stub
- Stub returns error: "Session runners deprecated"

**Fix**:
```python
# BEFORE:
"reflection_block": WorkUnitTemplate(
    id="reflection_block",
    runner_key="reflection",              # DELETE THIS
    action_sequence=["session.reflection"],
    ...
)

# AFTER:
"reflection_block": WorkUnitTemplate(
    id="reflection_block",
    # runner_key deleted
    action_sequence=["session.reflection"],
    ...
)
```

**Tasks**:
1. Remove `runner_key=` from all 15+ templates
2. Verify each template has `action_sequence` set
3. Delete or bypass `_run_session()` method in autonomous_scheduler.py

**Success**: All templates pass validation, no runner_key fields remain

---

### WP2: Start Scheduler
**File**: `/home/jaryk/cass/cass-vessel/backend/main_sdk.py` (lines ~1250)

**What's Missing**:
- `DayPhaseTracker` is created but never started
- No `await day_phase_tracker.start()`
- No `await autonomous_scheduler.start()`
- Phase change callbacks not registered

**Code to Add** (after line 1268):
```python
# Register phase change callbacks
day_phase_tracker.on_phase_change(autonomous_scheduler.on_phase_changed)
day_phase_tracker.on_phase_change(phase_queue_manager.on_phase_changed)

# Start both services
await day_phase_tracker.start()
await autonomous_scheduler.start()

logger.info("Autonomous scheduling system started")
```

**Tasks**:
1. Register callbacks for phase transitions
2. Add await calls for starting services
3. Add logging for startup completion

**Success**: Service starts cleanly, logs show system activated

---

### WP3: Validate Action Handlers
**Files**: 
- `/home/jaryk/cass/cass-vessel/backend/scheduling/templates.py`
- `/home/jaryk/cass/cass-vessel/backend/main_sdk.py`

**What's Missing**:
- No validation that action_sequence IDs exist
- Templates reference actions that may not be registered
- Silent failures at execution time

**Code to Add**:
```python
# In templates.py
def validate_template_actions(templates: Dict[str, WorkUnitTemplate], 
                            registry: ActionRegistry) -> List[str]:
    """Validate all template actions exist in registry."""
    errors = []
    for template_id, template in templates.items():
        for action_id in template.action_sequence:
            if not registry.get_definition(action_id):
                errors.append(f"Template '{template_id}' references unknown action '{action_id}'")
    return errors

# In main_sdk.py startup
validation_errors = validate_template_actions(WORK_TEMPLATES, action_registry)
if validation_errors:
    for error in validation_errors:
        logger.warning(f"Action validation: {error}")
else:
    logger.info("All template actions validated successfully")
```

**Tasks**:
1. Create validation function
2. Call at startup after action_registry initialized
3. Log warnings for missing actions
4. Verify all current templates pass

**Success**: Startup shows "All template actions validated successfully"

---

### WP4: Create Action Definitions JSON
**File**: `/home/jaryk/cass/cass-vessel/backend/scheduler/actions/definitions.json` (NEW)

**Structure**:
```json
{
  "actions": {
    "session.reflection": {
      "id": "session.reflection",
      "name": "Reflection Session",
      "description": "Private contemplation and self-examination",
      "category": "reflection",
      "handler": "session_handlers.reflection_action",
      "estimated_cost_usd": 0.15,
      "default_duration_minutes": 30,
      "priority": "normal",
      "requires_idle": false,
      "produces_artifact": false
    },
    ...
  }
}
```

**Actions to Define** (from templates and spec):
- **Reflection**: session.reflection, session.synthesis, session.meta_reflection
- **Research**: session.research, session.knowledge_building, web.search, wiki.create_page
- **Growth**: session.growth_edge, self.analyze_growth_edge
- **Curiosity**: session.curiosity, wonderland.explore
- **Journal**: journal.generate_daily, journal.reflect_on_work
- **Memory**: memory.summarize_idle_conversations, memory.compress_old_messages
- **System**: system.validate_state, outreach.check_contacts
- **Creative**: creative.explore_synthesis

**Cost Guidelines**:
- Light: $0.05-0.15 (reflection, journaling)
- Medium: $0.15-0.30 (research, growth work)
- Heavy: $0.30-1.00 (creative synthesis, complex research)

**Tasks**:
1. List all actions used in templates
2. Create definitions for each
3. Set reasonable cost estimates
4. Validate JSON syntax
5. Test ActionRegistry.load_definitions()

**Success**: definitions.json loads, all actions have metadata

---

### WP5: Test and Verify
**Scope**: Integration testing of entire system

**Test Sequence**:
1. Restart service: `sudo systemctl restart cass-vessel`
2. Monitor startup logs for scheduler initialization
3. Check action validation logs
4. Wait for phase transition or trigger manually
5. Monitor work planning and queuing
6. Verify work unit execution
7. Check budget tracking
8. Query work history
9. Run 24-hour simulation (optional)

**Success Criteria**:
- Service runs without crashes
- At least one work unit completes successfully
- Budget tracking is accurate
- No "Unknown action" errors
- All phases transition correctly
- Work summary is saved and queryable

**Commands**:
```bash
# Watch logs
journalctl -u cass-vessel -f | grep -i 'autonomous\|phase\|work'

# Check budget
curl http://localhost:8000/admin/scheduler/budget | jq

# Check status
curl http://localhost:8000/admin/scheduler/status | jq

# Check work history
curl http://localhost:8000/admin/scheduler/work-history | jq
```

---

## Dependency Graph

```
┌─────────────────────────────────────────┐
│ WP1: Fix Templates (runner_key)        │
│ Status: ready                          │
│ Effort: 1.5 hrs                        │
└────────────────┬────────────────────────┘
                 │
                 v
        ┌────────────────────┐
        │ WP2: Start         │ (depends on WP1)
        │ Scheduler          │
        │ Status: ready      │
        │ Effort: 1.0 hrs    │
        └─┬──────────────┬───┘
          │              │
          v              v
    ┌──────────┐    ┌──────────────┐
    │ WP3:     │    │ WP4:         │ (parallel)
    │ Validate │    │ Definitions  │
    │ Actions  │    │ JSON         │
    │ 1.5 hrs  │    │ 2.5 hrs      │
    └──────┬───┘    └────────┬─────┘
           │                 │
           └────────┬────────┘
                    v
           ┌─────────────────┐
           │ WP5: Test &     │ (gate)
           │ Verify          │
           │ 1.5 hrs         │
           │ (INTEGRATION)   │
           └─────────────────┘
```

---

## Sequential Execution Plan

### Phase 1: Startup (First 2.5 hours)
- **WP1** (1.5 hrs): Remove runner_key from templates
- **WP2** (1.0 hrs): Wire up scheduler startup

**Gate**: Can service start without crashing?

### Phase 2: Quality Assurance (Parallel, 2-4 hours)
- **WP3** (1.5 hrs): Add action validation
- **WP4** (2.5 hrs): Create definitions.json

**Gate**: Are all actions defined and validated?

### Phase 3: Integration Testing (Final 1.5 hours)
- **WP5** (1.5 hrs): End-to-end verification

**Gate**: Can system execute at least one work unit successfully?

---

## Success Metrics

When all work packages are complete:
- [ ] Service starts cleanly
- [ ] At least one work unit executes per test run
- [ ] Budget tracking is accurate to cent
- [ ] No "Unknown action" errors in logs
- [ ] All phases transition on schedule
- [ ] Work summaries are saved and queryable
- [ ] System runs stable for 24+ hours (optional)

---

## File Locations

**Work packages**: `/home/jaryk/cass/cass-vessel/.daedalus/ariadne/work-packages/`
- `wp1-fix-template-execution.json`
- `wp2-start-scheduler.json`
- `wp3-validate-actions.json`
- `wp4-action-definitions.json`
- `wp5-test-and-verify.json`

**This manifest**: `/home/jaryk/cass/cass-vessel/.daedalus/ariadne/WORK_MANIFEST.md`

**Theseus reports**: `/home/jaryk/cass/cass-vessel/.daedalus/theseus/reports/2025-12-24-autonomous-scheduler-*`

---

## Key Contacts & Resources

**Theseus Analysis**: Provides the monster taxonomy and architectural understanding
- Architecture: `.daedalus/theseus/reports/2025-12-24-autonomous-scheduler-architecture.md`
- Analysis: `.daedalus/theseus/reports/2025-12-24-autonomous-scheduler-analysis.md`
- Roadmap: `.daedalus/theseus/reports/2025-12-24-autonomous-scheduler-roadmap.md`

**Action Specification**: `spec/atomic-actions-projection.md`

**Main Code Files**:
- Scheduler: `backend/scheduling/autonomous_scheduler.py`
- Templates: `backend/scheduling/templates.py`
- Startup: `backend/main_sdk.py`
- Actions: `backend/scheduler/actions/__init__.py`

---

## Notes for Daedalus

This work plan represents a **high-confidence, low-risk path to operational capacity**. The architecture is well-designed - it just needs the integration work completed.

**Key insights**:
1. The system was 95% built, just not connected
2. Three critical fixes unlock everything (WP1, WP2, WP3)
3. WP4 is enabling but not blocking (definitions.json)
4. WP5 is validation - if 1-4 done correctly, 5 should mostly work

**Potential pitfalls**:
- Missing action handlers in registration
- Cost estimates too high (budget exhaustion)
- Phase windows don't match real time boundaries
- Silent failures if validation skipped

**Recommended approach**:
- Do WP1-2 first (2.5 hours)
- Restart and verify service runs (5 min)
- Do WP3-4 in parallel (4 hours)
- Do WP5 as final validation (1.5 hours)

**Total commitment**: 8-10 hours of focused work across 1-2 days.

---

**Created**: 2025-12-24  
**For**: Autonomous scheduler operational capacity  
**Status**: Ready for dispatch to Daedalus workers
