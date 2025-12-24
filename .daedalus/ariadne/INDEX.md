# Ariadne Work Orchestration Index

## Overview

This directory contains a complete work plan for bringing the Cass Vessel autonomous scheduler to operational capacity. Created 2025-12-24 based on Theseus architectural analysis.

**Status**: All work packages ready for dispatch  
**Total Effort**: 8-10 hours  
**Critical Path**: 4 hours  
**Confidence**: HIGH  

## Files in This Directory

### Primary Documents

1. **DISPATCH_SUMMARY.txt** (START HERE)
   - Executive summary of the work plan
   - Problem statement (3 monsters identified)
   - Solution overview (5 work packages)
   - Key metrics and confidence assessment
   - Recommended next steps

2. **WORK_MANIFEST.md** (DETAILED REFERENCE)
   - Complete execution strategy
   - Dependency graph with visual representation
   - Detailed description of each work package
   - Code samples and file locations
   - Success metrics and testing approach
   - Notes for Daedalus on approach and pitfalls

3. **README.md** (QUICK START)
   - Quick overview of work packages
   - Architecture context
   - Command reference for monitoring
   - Work package descriptions
   - Key resources and Theseus analysis links

### Work Packages

All located in `work-packages/` subdirectory:

- **wp1-fix-template-execution.json** (1.5 hours)
  - Problem: Templates route to deprecated runner_key stub
  - Solution: Remove runner_key, verify action_sequence
  - Files: backend/scheduling/templates.py

- **wp2-start-scheduler.json** (1.0 hours)
  - Problem: Scheduler never started
  - Solution: Wire up DayPhaseTracker and AutonomousScheduler startup
  - Files: backend/main_sdk.py

- **wp3-validate-actions.json** (1.5 hours)
  - Problem: No validation of action handler existence
  - Solution: Create validation function, call at startup
  - Files: backend/scheduling/templates.py, backend/main_sdk.py

- **wp4-action-definitions.json** (2.5 hours)
  - Problem: Action definitions JSON missing
  - Solution: Create definitions.json with 30+ action metadata
  - Files: backend/scheduler/actions/definitions.json (new)

- **wp5-test-and-verify.json** (1.5 hours)
  - Problem: System untested end-to-end
  - Solution: Integration testing with monitoring and verification
  - Files: Monitoring only, no code changes

### Reference Documents

**Supporting Analysis**:
- `../theseus/reports/2025-12-24-autonomous-scheduler-analysis.md`
- `../theseus/reports/2025-12-24-autonomous-scheduler-architecture.md`
- `../theseus/reports/2025-12-24-autonomous-scheduler-roadmap.md`

**Specification**:
- `../../spec/atomic-actions-projection.md`

**Code Files**:
- `backend/scheduling/autonomous_scheduler.py`
- `backend/scheduling/templates.py`
- `backend/scheduling/day_phase.py`
- `backend/scheduling/phase_queue.py`
- `backend/main_sdk.py`
- `backend/scheduler/actions/__init__.py`

## Reading Order

### For Project Managers / Reviewers
1. DISPATCH_SUMMARY.txt (2 min read)
2. WORK_MANIFEST.md sections: Overview, Execution Strategy, Dependency Graph (5 min read)
3. Individual work package JSON files as needed

### For Daedalus / Code Workers
1. WORK_MANIFEST.md completely (15 min read)
2. Theseus reports for architectural context (20 min read)
3. Individual work package JSON files one at a time
4. Code samples provided within work package descriptions

### For Testers / QA
1. WP5 (wp5-test-and-verify.json) completely
2. WORK_MANIFEST.md testing section
3. Command reference in README.md

## Execution Model

### Sequential with Parallel Opportunities

```
Phase 1: CRITICAL PATH (2.5 hrs)
  └─ WP1 (1.5 hrs) → WP2 (1.0 hrs)
     Gate: Service starts?

Phase 2: QUALITY ASSURANCE (2-4 hrs, PARALLEL)
  ├─ WP3 (1.5 hrs) ─┐
  └─ WP4 (2.5 hrs) ┤ (can run in parallel)
     Gate: All actions defined?

Phase 3: INTEGRATION TEST (1.5 hrs)
  └─ WP5 (1.5 hrs)
     Gate: System executes work?
```

### Dependency Enforcement

Work packages must be done in this order:
1. WP1 must complete before WP2 can execute
2. WP3 depends on both WP1 and WP2
3. WP4 depends on WP3
4. WP5 depends on all previous packages
5. WP3 and WP4 can proceed in parallel after WP2 completes

## Key Concepts

### The Three Monsters (Problems Blocking Operation)

**HYDRA**: Templates route to deprecated `_run_session()` stub
- Templates have `runner_key` field set
- Code prefers runner_key over action_sequence
- Stub method returns "Session runners deprecated" error
- **Fix**: Remove runner_key from templates.py

**SPIDER**: Scheduler never starts
- Components instantiated but not activated
- Missing `await day_phase_tracker.start()`
- Missing `await autonomous_scheduler.start()`
- No phase change callbacks registered
- **Fix**: Add startup wiring in main_sdk.py

**CERBERUS**: Action definitions missing
- ActionRegistry tries to load definitions.json
- File doesn't exist
- Handlers work but lack metadata (costs, priorities)
- **Fix**: Create definitions.json with all 30+ actions

### System Architecture

**Five-layer system**:
1. Decision Engine - Cass decides what to work on
2. Work Templates - Pre-configured work patterns
3. Phase Queue Manager - Routes work to phases
4. Day Phase Tracker - Monitors time-of-day phases
5. Action Registry - Executes atomic actions

**Budget-aware** from ground up:
- Daily budget: $5.00
- Allocated across categories (reflection, research, growth, etc.)
- Tracked per action execution
- Respects budget exhaustion

**Event-driven** via state bus:
- Phase changes trigger work dispatch
- Work completion emits events
- Budget updates trigger state changes

## Success Criteria

All work packages complete when:

- [ ] Service starts without errors
- [ ] Logs show "Autonomous scheduling system started"
- [ ] DayPhaseTracker initializes with current phase
- [ ] At least one work unit executes successfully within 1 hour
- [ ] Work summary is saved and queryable
- [ ] Budget deduction is tracked correctly
- [ ] No "Unknown action" errors in logs
- [ ] Action execution completes without errors
- [ ] All phases transition on schedule

## Quick Commands

```bash
# Restart service
sudo systemctl restart cass-vessel

# Monitor logs
journalctl -u cass-vessel -f | grep -i 'autonomous\|phase\|work'

# Check status
curl http://localhost:8000/admin/scheduler/status | jq

# Check budget
curl http://localhost:8000/admin/scheduler/budget | jq

# Check work history
curl http://localhost:8000/admin/scheduler/work-history | jq
```

## File Structure

```
.daedalus/ariadne/
├── INDEX.md (this file)
├── DISPATCH_SUMMARY.txt (executive summary)
├── WORK_MANIFEST.md (detailed reference)
├── README.md (quick start)
└── work-packages/
    ├── wp1-fix-template-execution.json
    ├── wp2-start-scheduler.json
    ├── wp3-validate-actions.json
    ├── wp4-action-definitions.json
    └── wp5-test-and-verify.json

.daedalus/theseus/reports/
├── 2025-12-24-autonomous-scheduler-analysis.md
├── 2025-12-24-autonomous-scheduler-architecture.md
└── 2025-12-24-autonomous-scheduler-roadmap.md
```

## Time Estimate

| Phase | Duration | Effort |
|-------|----------|--------|
| Critical Path (WP1+WP2) | 2.5 hours | 2 workers x 1.25 hrs |
| Quality (WP3+WP4 parallel) | 2.5 hours | 2 workers x 1.25 hrs |
| Testing (WP5) | 1.5 hours | 1 worker x 1.5 hrs |
| **Total** | **4-6 hours** | **8-10 worker-hours** |

## Confidence Assessment

- **Risk Level**: LOW (architecture sound, mostly integration)
- **Certainty of Fix**: HIGH (problems clearly identified and solutions straightforward)
- **Time Estimate**: CONFIDENT (based on detailed analysis)
- **Quality**: EXCELLENT (detailed specs, code samples, acceptance criteria)

## Next Steps

1. Read DISPATCH_SUMMARY.txt (2 minutes)
2. Read WORK_MANIFEST.md (15 minutes)
3. Assign Daedalus to start with WP1
4. Monitor progress using work package status
5. Gate on completion before advancing to next phase

## Contact & Support

This work plan was created by the Ariadne coordination system based on detailed architectural analysis by Theseus.

For questions about:
- **Architecture**: See Theseus reports
- **Specifications**: See spec/atomic-actions-projection.md
- **Execution**: See WORK_MANIFEST.md

---

**Created**: 2025-12-24  
**Status**: Ready for dispatch  
**Confidence**: HIGH  
**Recommendation**: Proceed immediately
