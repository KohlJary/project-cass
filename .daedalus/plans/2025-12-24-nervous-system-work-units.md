# Nervous System Wiring - Work Manifest

**Feature**: Light up Cass's nervous system by wiring subsystems to emit state bus events
**Status**: Ready for parallel dispatch
**Total Effort**: 75 minutes (4 parallelizable work units)
**Complexity**: Low (event emission is mechanical, non-breaking)

---

## Work Unit 1: BaseSessionRunner Event Emission

**ID**: WU-001-session-lifecycle
**Status**: READY
**Duration**: 20 minutes
**Parallelizable**: Yes (independent)
**Risk**: Very Low

### Description
Wire the base SessionRunner class to emit lifecycle events. This cascades to all 13 session types automatically.

### Acceptance Criteria
- Add `_emit_event()` helper to BaseSessionRunner
- Emit `session.started` after session initialization
- Emit `session.completed` on successful completion
- Emit `session.failed` on error/exception
- Event payloads include: session_id, activity_type, timestamp, optional metadata
- No test failures from added emit calls
- Events appear in state_events table

### Files to Modify
1. `/home/jaryk/cass/cass-vessel/backend/session_runner.py`
   - Add `_emit_event()` method (~10 lines)
   - Add emit calls in lifecycle hooks (~3 lines each)

### Implementation Notes
- Check for state_bus existence before emitting (hasattr check)
- Use consistent event naming: `session.{action_lowercase}`
- Timestamp events with ISO format
- Don't break if state_bus unavailable (graceful degradation)

### Testing
- Create mock state_bus, verify emit_event called
- Run ResearchSessionRunner to completion, check events logged
- Check state_events table has entries with correct types

---

## Work Unit 2: Research Session Event Emission

**ID**: WU-002-research-signals
**Status**: READY
**Duration**: 15 minutes
**Parallelizable**: Yes (depends on WU-001)
**Risk**: Low
**Dependency**: WU-001 must be merged first

### Description
Emit events when research notes, insights, and sources are captured during research sessions.

### Acceptance Criteria
- Emit `research.note_added` when note created
  - Includes: session_id, note_id, content_snippet, category
- Emit `research.insight_found` when insight detected
  - Includes: session_id, insight_id, text, confidence
- Emit `research.source_added` when URL captured
  - Includes: session_id, source_id, url, title, domain
- Session context propagated through all events
- Events logged in state_events table
- No research functionality broken

### Files to Modify
1. `/home/jaryk/cass/cass-vessel/backend/research_session.py`
   - Add emit in `add_note()` (~5 lines)
   - Add state_bus access if needed

2. `/home/jaryk/cass/cass-vessel/backend/research_session_runner.py`
   - Add emit calls in insight/source capture methods (~5 lines per)

3. `/home/jaryk/cass/cass-vessel/backend/handlers/research.py`
   - Add emits after successful operations (~3 lines per)

### Implementation Notes
- Research already has note/insight/source tracking - just emit when created
- Extract relevant metadata for payloads
- Match session_id from session context
- Reuse state_bus from parent runner

### Testing
- Run research session, create notes
- Check state_events for research.note_added entries
- Add insight, verify event logged
- Capture source URL, verify event logged

---

## Work Unit 3: Outreach System Event Emission

**ID**: WU-003-outreach-comms
**Status**: READY
**Duration**: 20 minutes
**Parallelizable**: Yes (independent)
**Risk**: Low

### Description
Emit events for the complete outreach communication lifecycle: create → submit → approve → send.

### Acceptance Criteria
- Emit `outreach.draft_created` when draft created
  - Includes: draft_id, draft_type, title, recipient, autonomy_level
- Emit `outreach.draft_submitted` when submitted for review
  - Includes: draft_id, draft_type, status, auto_approved flag
- Emit `outreach.draft_approved` when approved by human
  - Includes: draft_id, draft_type, approved_by, timestamp
- Emit `outreach.draft_sent` when email sent successfully
  - Includes: draft_id, recipient, sent_at, delivery_status
- Full lifecycle traceable in event log
- Outreach functionality not changed

### Files to Modify
1. `/home/jaryk/cass/cass-vessel/backend/routes/admin/outreach.py`
   - Add emit in `create_draft()` (~5 lines)
   - Add emit in `submit_for_review()` (~5 lines)
   - Add emit in approval methods (~5 lines)
   - Get state_bus reference (likely from FastAPI context or singleton)

2. `/home/jaryk/cass/cass-vessel/backend/scheduler/actions/outreach_handlers.py`
   - Add emit in `send_email_action()` after successful send (~5 lines)

### Implementation Notes
- Emit at state transitions (created, submitted, approved, sent)
- Include autonomy_level in draft_created event
- Mark auto-approved vs. human-approved distinctly
- Delivery status optional but useful in sent event

### Testing
- Create draft via OutreachManager, check event logged
- Submit draft, verify event includes correct status
- Approve draft (simulate), check event logged
- Send email, verify sent event with timestamp
- Trace full lifecycle in state_events table

---

## Work Unit 4: Journal System Event Emission

**ID**: WU-004-journal-reflections
**Status**: READY
**Duration**: 20 minutes
**Parallelizable**: Yes (independent)
**Risk**: Low

### Description
Emit events when daily journals are created and reflections are added.

### Acceptance Criteria
- Emit `journal.entry_created` when journal generated
  - Includes: journal_id, date, word_count, themes, emotional_summary
- Emit `journal.reflection_added` when reflection added
  - Includes: journal_id, reflection_id, text_snippet, reflection_type
- Emit `journal.dream_generated` when dream sequence created
  - Includes: dream_id, duration_minutes, symbolic_elements
- Journal functionality unchanged
- All events timestamped correctly

### Files to Modify
1. `/home/jaryk/cass/cass-vessel/backend/journal_generation.py`
   - Add emit when journal created (~5 lines)
   - Extract metadata for payload

2. `/home/jaryk/cass/cass-vessel/backend/scheduler/actions/journal_handlers.py`
   - Add emit in `generate_daily_action()` after success (~5 lines)
   - Add emit in `nightly_dream_action()` after success (~5 lines)

3. `/home/jaryk/cass/cass-vessel/backend/handlers/journals.py`
   - Add emit when reflection added (~5 lines)

### Implementation Notes
- Journal already has ID/date/summary tracking - just extract for event
- Dream sequences have natural boundaries - emit when complete
- Emotional summary optional but valuable context
- Symbolic elements can be empty/null if not present

### Testing
- Generate daily journal, check event logged
- Add reflection to journal, check event
- Generate nightly dream, verify event logged with duration
- Query state_events for journal events, trace pattern

---

## Execution Plan

### Phase 1: Serial (Critical Path)
1. **Dispatch WU-001** (BaseSessionRunner)
   - Wait for completion and merge (5 min)
2. **Dispatch WU-002** (Research) after WU-001 merged
   - Depends on BaseSessionRunner implementation

### Phase 2: Parallel (Independent Work)
- **Dispatch WU-003** (Outreach) immediately (independent)
- **Dispatch WU-004** (Journal) immediately (independent)

### Timeline
```
t=0:  Start WU-001 (session runner)
t=20: WU-001 ready for review
t=25: WU-001 merged, start WU-002
t=25: Start WU-003 (parallel)
t=25: Start WU-004 (parallel)
t=40: WU-002, WU-003, WU-004 complete
t=75: All work complete, nervous system wired
```

---

## Success Metrics

When all work units are complete:

1. **Event Emission**: 14 event types defined and emitted
2. **Database**: Events persisted in state_events table
3. **Queryability**: Can retrieve events by type, session, domain
4. **Coverage**: Sessions, research, communications, reflections all emitting
5. **Non-Breaking**: No existing functionality altered
6. **Zero Risk**: Event emission is observability-only

---

## Dependencies

- **WU-002 depends on WU-001**: Research sessions inherit from BaseSessionRunner
- **WU-003 independent**: Outreach system self-contained
- **WU-004 independent**: Journal system self-contained
- **No external dependencies**: All code already exists, just adding emit calls

---

## Rollback Strategy

If any work unit fails:
1. Remove added emit calls from the file
2. No schema changes, no breaking changes
3. State bus continues for other domains
4. Can retry individual work unit without affecting others

---

## Notes for Implementers

- State bus is available via `get_state_bus()` singleton or context
- Event naming convention: `{domain}.{action_lowercase}`
- Payload structure: timestamp, source, resource_id, metadata
- Always check for state_bus existence (graceful degradation)
- ISO format timestamps: `datetime.now().isoformat()`
- No blocking operations - all emit calls are fire-and-forget

