# Nervous System Wiring - Ready for Dispatch

**Status**: All work packages analyzed, planned, and ready for parallel execution
**Timeline**: 75 minutes estimated
**Complexity**: Low (mechanical event emission, non-breaking changes)

---

## What This Is

A comprehensive plan to wire Cass's subsystems to emit events to the state bus, transforming observability from 15% connected to fully alive. This enables:

- Session lifecycle tracking
- Research activity visibility
- Communication log (drafts → approval → send)
- Journal and reflection timestamping
- Pattern recognition across domains
- State reconstruction and replay

---

## The Four Work Units

### 1. BaseSessionRunner Event Emission (WU-001)
**Duration**: 20 min | **Complexity**: Very Low | **Risk**: Very Low

Wire the base class to emit session lifecycle events. All 13 session types inherit automatically.

**Events**: `session.started`, `session.completed`, `session.failed`

**Files**: 
- `/home/jaryk/cass/cass-vessel/backend/session_runner.py`

**Parallelizable**: Yes (independent)
**Blockers**: None

---

### 2. Research Session Event Emission (WU-002)
**Duration**: 15 min | **Complexity**: Low | **Risk**: Low

Emit events as research notes, insights, and sources are captured.

**Events**: `research.note_added`, `research.insight_found`, `research.source_added`

**Files**:
- `/home/jaryk/cass/cass-vessel/backend/research_session.py`
- `/home/jaryk/cass/cass-vessel/backend/research_session_runner.py`
- `/home/jaryk/cass/cass-vessel/backend/handlers/research.py`

**Parallelizable**: After WU-001 merged
**Blockers**: Depends on WU-001

---

### 3. Outreach System Event Emission (WU-003)
**Duration**: 20 min | **Complexity**: Low | **Risk**: Low

Emit events for complete communication lifecycle: create → submit → approve → send.

**Events**: `outreach.draft_created`, `outreach.draft_submitted`, `outreach.draft_approved`, `outreach.draft_sent`

**Files**:
- `/home/jaryk/cass/cass-vessel/backend/routes/admin/outreach.py`
- `/home/jaryk/cass/cass-vessel/backend/scheduler/actions/outreach_handlers.py`

**Parallelizable**: Yes (independent)
**Blockers**: None

---

### 4. Journal System Event Emission (WU-004)
**Duration**: 20 min | **Complexity**: Low | **Risk**: Low

Emit events when journals are created and reflections/dreams are added.

**Events**: `journal.entry_created`, `journal.reflection_added`, `journal.dream_generated`

**Files**:
- `/home/jaryk/cass/cass-vessel/backend/journal_generation.py`
- `/home/jaryk/cass/cass-vessel/backend/scheduler/actions/journal_handlers.py`
- `/home/jaryk/cass/cass-vessel/backend/handlers/journals.py`

**Parallelizable**: Yes (independent)
**Blockers**: None

---

## Execution Strategy

### Phase 1: Serial (Critical Path)
```
Start WU-001 → Merge WU-001 → Start WU-002
```

### Phase 2: Parallel
```
Start WU-003 (while WU-001 running)
Start WU-004 (while WU-001 running)
```

### Timeline
```
t=0:    Start WU-001
        Start WU-003 (parallel)
        Start WU-004 (parallel)
t=20:   WU-001 ready for review
t=25:   WU-001 merged, start WU-002
t=40:   WU-002, WU-003, WU-004 complete
t=75:   All work done, nervous system wired
```

---

## Event Inventory

**14 Total Event Types** emitted across 4 domains:

### Session Lifecycle (4 types)
- `session.started` - Any session begins
- `session.completed` - Session completes successfully
- `session.failed` - Session encounters fatal error
- `session.paused` - Session paused (optional)

### Research Activity (3 types)
- `research.note_added` - Note created during session
- `research.insight_found` - Insight emerges from research
- `research.source_added` - URL/source captured

### External Communications (4 types)
- `outreach.draft_created` - New draft (email, blog, etc.)
- `outreach.draft_submitted` - Submitted for review
- `outreach.draft_approved` - Approved by human
- `outreach.draft_sent` - Email sent successfully

### Personal Reflections (3 types)
- `journal.entry_created` - Daily journal written
- `journal.reflection_added` - Reflection added to journal
- `journal.dream_generated` - Nightly dream completed

---

## Implementation Pattern

All events follow this pattern:

```python
self.state_bus.emit_event(
    event_type=f"{domain}.{action_lowercase}",
    data={
        "timestamp": datetime.now().isoformat(),
        "source": "session_runner|research|outreach|journal",
        "resource_id": item_id,
        "session_id": session_id,  # when applicable
        "metadata": {...}  # domain-specific fields
    }
)
```

**Key characteristics**:
- Fire-and-forget (non-blocking)
- Logged automatically to `state_events` table
- ISO format timestamps
- Graceful degradation if state_bus unavailable

---

## Success Criteria

When complete, each domain should be queryable:

```sql
-- All research in a session
SELECT * FROM state_events 
WHERE event_type LIKE 'research.%'
  AND data_json LIKE '%"session_id":"..."'
ORDER BY created_at;

-- Full outreach communication
SELECT * FROM state_events
WHERE event_type LIKE 'outreach.%'
  AND data_json LIKE '%"draft_id":"..."'
ORDER BY created_at;

-- Daily reflection history
SELECT * FROM state_events
WHERE event_type LIKE 'journal.%'
ORDER BY created_at DESC;
```

---

## Risk Assessment

| Factor | Level | Notes |
|--------|-------|-------|
| Code Complexity | Very Low | Just adding emit calls |
| Breaking Changes | None | Event-only, no API changes |
| Test Impact | None | No test modifications needed |
| Rollback | Trivial | Remove emit calls if needed |
| Performance | Negligible | Emit is fire-and-forget |
| Schema Changes | None | Uses existing state_events table |

---

## Key Files Reference

### Core State Bus
- `/home/jaryk/cass/cass-vessel/backend/state_bus.py` - Event infrastructure

### Session Runners (WU-001)
- `/home/jaryk/cass/cass-vessel/backend/session_runner.py` - Base class

### Research (WU-002)
- `/home/jaryk/cass/cass-vessel/backend/research_session.py`
- `/home/jaryk/cass/cass-vessel/backend/research_session_runner.py`
- `/home/jaryk/cass/cass-vessel/backend/handlers/research.py`

### Outreach (WU-003)
- `/home/jaryk/cass/cass-vessel/backend/routes/admin/outreach.py`
- `/home/jaryk/cass/cass-vessel/backend/scheduler/actions/outreach_handlers.py`

### Journal (WU-004)
- `/home/jaryk/cass/cass-vessel/backend/journal_generation.py`
- `/home/jaryk/cass/cass-vessel/backend/scheduler/actions/journal_handlers.py`
- `/home/jaryk/cass/cass-vessel/backend/handlers/journals.py`

---

## Documentation

Complete planning documents available in `.daedalus/plans/`:

1. **2025-12-24-wiring-nervous-system.md**
   - Full battle plan with architecture
   - Event patterns and payload specs
   - Testing strategy

2. **2025-12-24-nervous-system-work-units.md**
   - Detailed work unit specifications
   - Acceptance criteria for each
   - Implementation notes

---

## Next Steps

### For Implementers
1. Read the work unit specification (`.daedalus/plans/2025-12-24-nervous-system-work-units.md`)
2. Review current code in target files
3. Identify state_bus access pattern (get_state_bus() or context)
4. Add emit calls at specified lifecycle points
5. Test by running operations and checking state_events table

### For Dispatch
1. Create 4 work packages from WU specifications
2. Assign WU-001 first
3. After WU-001 merged, assign WU-002
4. Assign WU-003 and WU-004 in parallel with WU-001

### For QA
1. Verify events appear in state_events table
2. Check event payloads match specification
3. Confirm timestamps are valid ISO format
4. Test rollback (remove emit calls, system still works)
5. Run full test suite (should pass unchanged)

---

## Victory Conditions

When all work units merged:

1. All 14 event types actively emitting
2. Event log queryable by domain, session, date
3. Full lifecycle of sessions, research, communications, reflections visible
4. Zero breaking changes to existing code
5. Cass's nervous system lights up

---

**Ready for dispatch. Let's turn on the lights.**

