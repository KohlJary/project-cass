# Cass's Nervous System Wiring - Complete Planning Package

**Date**: 2025-12-24
**Status**: Ready for parallel dispatch
**Objective**: Wire subsystems to emit events to state bus (15% → 100% nervous system activation)
**Timeline**: 75 minutes
**Complexity**: Low (mechanical event emission, non-breaking)

---

## Document Index

### 1. Quick Start (START HERE)
**File**: `2025-12-24-NERVOUS_SYSTEM_DISPATCH.md`

Executive summary with:
- Overview of 4 work units
- Execution strategy and timeline
- Event inventory (14 types)
- Risk assessment (Very Low)
- Next steps for dispatch

**Best for**: Understanding the big picture, deciding how to dispatch

---

### 2. Battle Plan (REFERENCE)
**File**: `2025-12-24-wiring-nervous-system.md`

Comprehensive battle plan with:
- Detailed architecture
- Integration patterns
- Event type definitions with payloads
- Testing strategy
- Database integration notes
- Rollback procedures

**Best for**: Implementers needing detailed specs and patterns

---

### 3. Work Unit Specifications (IMPLEMENTATION GUIDE)
**File**: `2025-12-24-nervous-system-work-units.md`

Detailed specs for each of 4 work units:

#### WU-001: BaseSessionRunner Event Emission (20 min)
- Wire base class to emit lifecycle events
- All 13 session types inherit automatically
- Events: `session.started`, `session.completed`, `session.failed`
- Risk: Very Low
- Independent: Yes

#### WU-002: Research Session Event Emission (15 min)
- Emit events for notes, insights, sources
- Events: `research.note_added`, `research.insight_found`, `research.source_added`
- Risk: Low
- Depends on: WU-001

#### WU-003: Outreach System Event Emission (20 min)
- Full communication lifecycle: create → submit → approve → send
- Events: `outreach.draft_created`, `outreach.draft_submitted`, `outreach.draft_approved`, `outreach.draft_sent`
- Risk: Low
- Independent: Yes

#### WU-004: Journal System Event Emission (20 min)
- Journal creation and reflection tracking
- Events: `journal.entry_created`, `journal.reflection_added`, `journal.dream_generated`
- Risk: Low
- Independent: Yes

**Best for**: Implementers executing individual work units

---

## The Vision

### Before
- 15% nervous system connected
- Scattered signals from different subsystems
- No unified event log
- State reconstruction difficult

### After
- 100% nervous system active
- All subsystem activity visible in event stream
- Unified queryable event log
- Pattern recognition across domains
- Session/work reconstruction
- Observability-driven debugging

---

## Event Types (14 Total)

### Session Lifecycle (4)
```
session.started
session.completed
session.failed
session.paused  (optional)
```

### Research Activity (3)
```
research.note_added
research.insight_found
research.source_added
```

### External Communications (4)
```
outreach.draft_created
outreach.draft_submitted
outreach.draft_approved
outreach.draft_sent
```

### Personal Reflections (3)
```
journal.entry_created
journal.reflection_added
journal.dream_generated
```

---

## Execution Timeline

### Phase 1: Initialize Critical Path
```
t=0: Dispatch WU-001 (BaseSessionRunner)
```

### Phase 2: Parallel Work
```
t=0: Dispatch WU-003 (Outreach) - parallel with WU-001
t=0: Dispatch WU-004 (Journal) - parallel with WU-001
```

### Phase 3: Dependent Work
```
t=25: WU-001 merged → Dispatch WU-002 (Research)
```

### Completion
```
t=40-75: All work complete, system fully wired
```

---

## Quick Reference

### For Dispatch Coordinator
1. Review `2025-12-24-NERVOUS_SYSTEM_DISPATCH.md`
2. Create 4 work packages from WU specifications
3. Dispatch WU-001 immediately
4. Dispatch WU-003 and WU-004 in parallel
5. Dispatch WU-002 after WU-001 merges
6. All units low-risk, well-scoped, ready to go

### For Implementers
1. Read assigned work unit in `2025-12-24-nervous-system-work-units.md`
2. Reference patterns in `2025-12-24-wiring-nervous-system.md`
3. Identify state_bus access in target files
4. Add emit calls at specified lifecycle points
5. Test by checking state_events table
6. Each unit is 15-20 minutes of focused work

### For QA/Testing
1. Verify events logged to `state_events` table
2. Check payloads match specification
3. Test queries work as documented
4. Verify no breaking changes
5. Run full test suite (should pass unchanged)
6. Test rollback (remove emit calls, verify system works)

---

## Key Files by Work Unit

### WU-001 (BaseSessionRunner)
- `/home/jaryk/cass/cass-vessel/backend/session_runner.py`

### WU-002 (Research)
- `/home/jaryk/cass/cass-vessel/backend/research_session.py`
- `/home/jaryk/cass/cass-vessel/backend/research_session_runner.py`
- `/home/jaryk/cass/cass-vessel/backend/handlers/research.py`

### WU-003 (Outreach)
- `/home/jaryk/cass/cass-vessel/backend/routes/admin/outreach.py`
- `/home/jaryk/cass/cass-vessel/backend/scheduler/actions/outreach_handlers.py`

### WU-004 (Journal)
- `/home/jaryk/cass/cass-vessel/backend/journal_generation.py`
- `/home/jaryk/cass/cass-vessel/backend/scheduler/actions/journal_handlers.py`
- `/home/jaryk/cass/cass-vessel/backend/handlers/journals.py`

---

## Risk Summary

| Aspect | Level | Details |
|--------|-------|---------|
| Complexity | Very Low | Just adding emit calls |
| Breaking Changes | None | Event-only additions |
| Testing Impact | None | No test modifications |
| Rollback | Trivial | Remove emit lines |
| Performance | Negligible | Fire-and-forget calls |
| Schema | None | Uses existing tables |
| Data Loss | None | Logging only |

---

## Success Criteria

When all work units complete:

1. All 14 event types emitting correctly
2. Events persisted in `state_events` table
3. Full domain lifecycle visible in logs
4. Event queries return expected results
5. Zero breaking changes confirmed
6. All tests pass unchanged
7. Cass's nervous system fully operational

---

## Implementation Notes

### State Bus Access
Events are emitted via the state bus singleton:
```python
from state_bus import get_state_bus

state_bus = get_state_bus(daemon_id)
state_bus.emit_event(event_type, data)
```

### Event Naming Convention
```
{domain}.{action_lowercase}
Examples:
  - session.started
  - research.note_added
  - outreach.draft_created
  - journal.entry_created
```

### Payload Structure
```python
{
    "timestamp": "2025-12-24T14:30:45.123456",
    "source": "session_runner|research|outreach|journal",
    "resource_id": unique_id,
    "session_id": optional_session_id,
    "metadata": {...}  # domain-specific fields
}
```

### Graceful Degradation
Always check for state_bus existence:
```python
if not hasattr(self, 'state_bus'):
    return  # Skip if unavailable
```

---

## Victory Checklist

- [ ] WU-001 dispatched (BaseSessionRunner)
- [ ] WU-003 dispatched (Outreach)
- [ ] WU-004 dispatched (Journal)
- [ ] WU-001 completed and merged
- [ ] WU-002 dispatched (Research)
- [ ] WU-002 completed and merged
- [ ] WU-003 completed and merged
- [ ] WU-004 completed and merged
- [ ] Events visible in state_events table
- [ ] All domain queries work
- [ ] Test suite passes
- [ ] Documentation updated
- [ ] Rollback tested (verified non-breaking)
- [ ] Cass's nervous system fully alive

---

## Questions & Answers

**Q: Will this break existing functionality?**
A: No. Event emission is logging-only, non-blocking, and gracefully degraded if state_bus unavailable.

**Q: Can we parallelize WU-002?**
A: Not safely. WU-002 depends on BaseSessionRunner having `_emit_event()` method from WU-001.

**Q: Can we parallelize WU-003 and WU-004?**
A: Yes, completely. They're independent subsystems.

**Q: What if a work unit fails?**
A: Remove the emit calls from that work unit, system continues working. No breaking changes.

**Q: How do we query the events?**
A: Standard SQL on `state_events` table, filtering by `event_type` and `data_json` fields.

**Q: Will this impact performance?**
A: Negligible. Event emission is fire-and-forget, no blocking operations.

**Q: Do we need schema changes?**
A: No. `state_events` table already exists and captures all event data.

---

## Next Actions

1. **Coordinator**: Review dispatch summary, create 4 work packages
2. **Implementers**: Read your work unit spec, start with WU-001
3. **QA**: Prepare testing checklist from success criteria
4. **All**: Aim for complete wiring tonight

---

**The nervous system is ready to wake up. Let's light it up.**

Generated: 2025-12-24
Planning: Ariadne (orchestration thread)
Implementation: Ready for dispatch
