# Ariadne Work Orchestration

This directory contains work package definitions and coordination for bringing the autonomous scheduler to operational capacity.

## Quick Start

1. **Read the manifest**: `WORK_MANIFEST.md` - complete overview of all work packages and execution strategy
2. **Review individual packages**: `work-packages/wp*.json` - detailed task definitions
3. **Follow dependencies**: WP1 → WP2 → (WP3+WP4 parallel) → WP5

## Status

- **Creation Date**: 2025-12-24
- **Total Planned Work**: 8-10 hours
- **Critical Path**: 4 hours (WP1+WP2)
- **All Packages**: Ready for dispatch

## Work Packages

| Package | Title | Status | Hours | Block |
|---------|-------|--------|-------|-------|
| WP1 | Fix Template Execution Paths | ready | 1.5 | Critical |
| WP2 | Start Scheduler | ready | 1.0 | Critical |
| WP3 | Validate Action Handlers | ready | 1.5 | Quality gate |
| WP4 | Create Action Definitions JSON | ready | 2.5 | Blocking |
| WP5 | Test and Verify End-to-End | ready | 1.5 | Integration |

## Key Files

- **Manifest**: `WORK_MANIFEST.md` - Full execution plan with code samples
- **Analysis**: `.daedalus/theseus/reports/2025-12-24-autonomous-scheduler-*.md` - Architecture and problem analysis
- **Spec**: `spec/atomic-actions-projection.md` - Action definitions reference

## Architecture Context

The autonomous scheduler system is **95% built but not integrated**. Three "monsters" block operation:

1. **HYDRA** (WP1): Templates route to deprecated runner_key instead of action_sequence
2. **SPIDER** (WP2): Scheduler never starts (await calls missing)
3. **CERBERUS** (WP4): Action definitions.json doesn't exist

See Theseus reports for full analysis.

## Execution Phases

### Phase 1: Critical Path (2.5 hours)
- WP1: Remove runner_key from 15+ templates
- WP2: Wire up scheduler startup
- **Gate**: Can service start?

### Phase 2: Quality Assurance (2-4 hours, parallel)
- WP3: Add validation function
- WP4: Create definitions.json
- **Gate**: Are all actions defined?

### Phase 3: Integration Testing (1.5 hours)
- WP5: End-to-end verification
- **Gate**: Can system execute work?

## Command Reference

### Monitor Logs
```bash
journalctl -u cass-vessel -f | grep -i 'autonomous\|phase\|work'
```

### Check Status
```bash
curl http://localhost:8000/admin/scheduler/status | jq
curl http://localhost:8000/admin/scheduler/budget | jq
curl http://localhost:8000/admin/scheduler/work-history | jq
```

### Restart Service
```bash
sudo systemctl restart cass-vessel
sudo systemctl status cass-vessel
```

## Success Criteria

When complete:
- Service starts cleanly
- At least one work unit executes per test
- Budget tracking is accurate
- No "Unknown action" errors
- All phases transition on schedule

## Work Package Descriptions

### WP1: Fix Template Execution Paths
Remove `runner_key` from template definitions in `backend/scheduling/templates.py`.
Templates currently route to deprecated `_run_session()` stub that returns error.

**Files**: `backend/scheduling/templates.py`  
**Tasks**: Delete runner_key lines, verify action_sequence set  
**Effort**: 1.5 hours  

### WP2: Start Scheduler
Wire up startup code to initialize and start `DayPhaseTracker` and `AutonomousScheduler`.
Add phase change callbacks to trigger planning and work dispatch.

**Files**: `backend/main_sdk.py` (lines ~1250)  
**Tasks**: Register callbacks, add await start() calls, add logging  
**Effort**: 1.0 hours  
**Depends on**: WP1

### WP3: Validate Action Handlers
Create validation function to check that all template action sequences reference real,
registered actions. Call at startup to prevent silent failures.

**Files**: `backend/scheduling/templates.py`, `backend/main_sdk.py`  
**Tasks**: Add validation function, call at startup, verify handlers exist  
**Effort**: 1.5 hours  
**Depends on**: WP1, WP2

### WP4: Create Action Definitions JSON
Create `backend/scheduler/actions/definitions.json` with metadata for 30+ actions.
Include id, name, description, category, handler, cost, duration, priority.

**Files**: `backend/scheduler/actions/definitions.json` (NEW)  
**Tasks**: Define all actions from templates, set costs, validate JSON  
**Effort**: 2.5 hours  
**Depends on**: WP3

### WP5: Test and Verify End-to-End
Integration test of entire system. Restart service, monitor scheduling,
verify work execution, check budget tracking, query work history.

**Files**: (monitoring/testing, no code changes)  
**Tasks**: Restart service, monitor logs, trigger planning, verify execution  
**Effort**: 1.5 hours  
**Depends on**: WP1, WP2, WP3, WP4

## Theseus Analysis

Three detailed reports available:
- `2025-12-24-autonomous-scheduler-analysis.md` - Problem diagnosis, monsters identified
- `2025-12-24-autonomous-scheduler-architecture.md` - System diagrams, data flow, event sequences
- `2025-12-24-autonomous-scheduler-roadmap.md` - Tactical execution guide, checklists

## Notes

This is a **high-confidence, low-risk work plan**. The architecture is well-designed.
Main effort is integration and validation, not refactoring.

Estimated time to first successful work unit execution: **4-6 hours**  
Estimated time to production-ready: **8-10 hours**

All dependencies exist. No external blockers. Work can start immediately.

---

**Created by**: Ariadne coordination system  
**Analysis by**: Theseus code analysis agent  
**For**: Cass autonomous capability  
**Status**: Ready for dispatch
