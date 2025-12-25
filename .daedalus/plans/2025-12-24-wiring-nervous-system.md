# Wiring Battle Plan: Turn On Cass's Nervous System

**Goal**: Wire subsystems to emit events to the state bus, turning Cass's nervous system from 15% connected to fully alive.

**Timeline**: 75 minutes total (4 quick wins + parallel execution)

---

## Quick Wins Overview

| Task | Duration | Scope | Parallelizable |
|------|----------|-------|-----------------|
| 1. Wire BaseSessionRunner | 20 min | 2 files, all 13 session types | Yes |
| 2. Wire Research Sessions | 15 min | 2-3 files | Yes (after #1) |
| 3. Wire Outreach System | 20 min | 2 files | Yes (independent) |
| 4. Wire Journal System | 20 min | 2 files | Yes (independent) |

---

## Work Package 1: Wire BaseSessionRunner (20 min)

### Objective
Add event emission to the base session runner so ALL 13 session types automatically emit lifecycle events.

### Files to Modify
1. `/home/jaryk/cass/cass-vessel/backend/session_runner.py` - BaseSessionRunner class
2. Any session runner implementations that override lifecycle methods

### Events to Emit
- `SESSION_STARTED` - When session begins
- `SESSION_COMPLETED` - When session completes successfully
- `SESSION_FAILED` - When session encounters fatal error
- `SESSION_PAUSED` - When session is paused (optional)

### Implementation
Add to BaseSessionRunner:

```python
async def _emit_event(self, event_type: str, data: Dict[str, Any] = None) -> None:
    """Emit a state bus event for this session."""
    if not hasattr(self, 'state_bus'):
        return  # State bus not available
    
    event_data = {
        "session_id": self.session_id,
        "activity_type": self.activity_type,
        "timestamp": datetime.now().isoformat(),
        **(data or {})
    }
    
    self.state_bus.emit_event(f"session.{event_type.lower()}", event_data)
```

Then call `self._emit_event("SESSION_STARTED")` in each lifecycle method:
- After initialization completes
- Before returning SessionResult (success)
- In exception handlers (error)

### Affected Session Types (13 total)
All inherit from BaseSessionRunner, so one change cascades:
- ResearchSessionRunner
- ReflectionSessionRunner
- SynthesisSessionRunner
- MetaReflectionSessionRunner
- ConsolidationSessionRunner
- GrowthEdgeSessionRunner
- KnowledgeBuilderSessionRunner
- WritingSessionRunner
- CuriositySessionRunner
- WorldStateSessionRunner
- SocialEngagementSessionRunner
- CreativeOutputSessionRunner
- UserModelSynthesisSessionRunner

### Success Criteria
- All 13 session types emit SESSION_STARTED when beginning
- All emit SESSION_COMPLETED on success
- All emit SESSION_FAILED on error
- Events logged to database via state bus

---

## Work Package 2: Wire Research Sessions (15 min)

### Objective
Emit events when research notes and insights are added during active research sessions.

### Files to Modify
1. `/home/jaryk/cass/cass-vessel/backend/research_session.py` - ResearchSessionManager
2. `/home/jaryk/cass/cass-vessel/backend/research_session_runner.py` - Research runner methods
3. `/home/jaryk/cass/cass-vessel/backend/handlers/research.py` - Research tool handlers

### Events to Emit
- `RESEARCH_NOTE_ADDED` - When a note is created during session
  - Payload: `{session_id, note_id, content_snippet, category}`
- `RESEARCH_INSIGHT_FOUND` - When an insight emerges
  - Payload: `{session_id, insight_id, insight_text, confidence}`
- `RESEARCH_SOURCE_ADDED` - When a source is captured
  - Payload: `{session_id, source_id, url, title, domain}`

### Implementation Locations
1. In `ResearchSessionManager.add_note()` - emit RESEARCH_NOTE_ADDED
2. In research LLM response handling - detect insights, emit RESEARCH_INSIGHT_FOUND
3. In URL/source capture code - emit RESEARCH_SOURCE_ADDED

### Success Criteria
- Each note creation emits event
- Each insight (detected by keyword/marker) emits event
- Each source URL emits event
- Session context (ID, phase) included in all events

---

## Work Package 3: Wire Outreach System (20 min)

### Objective
Emit events for the full lifecycle of external communications (drafts → approval → send).

### Files to Modify
1. `/home/jaryk/cass/cass-vessel/backend/routes/admin/outreach.py` - OutreachManager
2. `/home/jaryk/cass/cass-vessel/backend/scheduler/actions/outreach_handlers.py` - Action handlers

### Events to Emit
- `DRAFT_CREATED` - New draft (email, blog post, etc.)
  - Payload: `{draft_id, draft_type, title, recipient, autonomy_level}`
- `DRAFT_SUBMITTED` - Draft sent for review or auto-approved
  - Payload: `{draft_id, draft_type, title, status, auto_approved}`
- `DRAFT_APPROVED` - Draft approved by Kohl
  - Payload: `{draft_id, draft_type, title, approved_by}`
- `DRAFT_SENT` - Email successfully sent
  - Payload: `{draft_id, draft_type, recipient, sent_at}`

### Implementation Locations
1. In `OutreachManager.create_draft()` - emit DRAFT_CREATED
2. In `OutreachManager.submit_for_review()` - emit DRAFT_SUBMITTED
3. In approval handler - emit DRAFT_APPROVED
4. In `send_email_action()` - emit DRAFT_SENT after successful send

### Success Criteria
- Drafts trigger events on creation
- State transitions (submitted, approved, sent) all emit events
- Events include draft metadata for tracking
- Full outreach lifecycle visible in event log

---

## Work Package 4: Wire Journal System (20 min)

### Objective
Emit events when journals are created and reflections are added.

### Files to Modify
1. `/home/jaryk/cass/cass-vessel/backend/journal_generation.py` - Journal generation
2. `/home/jaryk/cass/cass-vessel/backend/scheduler/actions/journal_handlers.py` - Action handlers
3. `/home/jaryk/cass/cass-vessel/backend/handlers/journals.py` - Journal tool handlers

### Events to Emit
- `JOURNAL_ENTRY_CREATED` - Daily journal written
  - Payload: `{journal_id, date, word_count, themes, emotional_summary}`
- `JOURNAL_REFLECTION_ADDED` - Reflection added to journal
  - Payload: `{journal_id, reflection_id, text_snippet, reflection_type}`
- `NIGHTLY_DREAM_GENERATED` - Dream sequence completed
  - Payload: `{dream_id, duration_minutes, dream_type, symbolic_elements}`

### Implementation Locations
1. In `generate_daily_action()` - emit JOURNAL_ENTRY_CREATED after generation
2. In journal save methods - emit JOURNAL_REFLECTION_ADDED when reflection added
3. In `nightly_dream_action()` - emit NIGHTLY_DREAM_GENERATED after dream completes

### Success Criteria
- Journal creation triggers event
- Reflections added during day trigger events
- Dreams emit their own completion event
- Events include content summaries for context

---

## Integration Architecture

### State Bus Event Pattern
All events follow this pattern:

```python
self.state_bus.emit_event(
    event_type=f"{domain}.{action}",  # e.g., "research.note_added"
    data={
        "timestamp": datetime.now().isoformat(),
        "source": "session_runner|research|outreach|journal",
        "session_id": session_id,
        "resource_id": item_id,
        "resource_type": type_name,
        "metadata": {...}
    }
)
```

### Event Types Summary (All 14 types)

#### Session Lifecycle (4)
- `session.started`
- `session.completed`
- `session.failed`
- `session.paused` (optional)

#### Research (3)
- `research.note_added`
- `research.insight_found`
- `research.source_added`

#### Outreach (4)
- `outreach.draft_created`
- `outreach.draft_submitted`
- `outreach.draft_approved`
- `outreach.draft_sent`

#### Journal (3)
- `journal.entry_created`
- `journal.reflection_added`
- `journal.dream_generated`

### Database Integration
State bus already logs all events to `state_events` table:
- No schema changes needed
- Events automatically persisted
- Available for queries and replay

---

## Dependency Graph

```
Work Package 1: BaseSessionRunner
    ↓
    ├─→ Work Package 2: Research Sessions
    │
Work Package 3: Outreach System (independent)
Work Package 4: Journal System (independent)
```

**Critical Path**: #1 must complete before #2 (research inherits from BaseSessionRunner)
**Parallel Paths**: #3 and #4 can run in parallel with #1 or after

---

## Testing Strategy

### Unit Level
- Mock state_bus, verify emit_event calls
- Check event payloads include required fields
- Verify event timestamps are valid

### Integration Level
- Run session to completion, check state_events table
- Create research note, check event logged
- Create outreach draft, check full lifecycle
- Generate journal, check events

### Event Log Queries
After wiring, queries like these should work:

```sql
-- All research activity in last session
SELECT * FROM state_events 
WHERE event_type LIKE 'research.%' 
  AND data_json LIKE '%"session_id":"abc123"%'
ORDER BY created_at;

-- Full outreach communication lifecycle
SELECT * FROM state_events 
WHERE event_type LIKE 'outreach.%' 
  AND data_json LIKE '%"draft_id":"xyz789"%'
ORDER BY created_at;
```

---

## Rollback Plan

If issues emerge during implementation:
1. Each work package is independent (except #1 → #2)
2. Remove `_emit_event()` calls from affected file
3. State bus continues working for other domains
4. No data loss (events just aren't logged)

---

## Victory Conditions

When complete, Cass's nervous system should show:
1. Session lifecycle visible in event stream
2. Research activity tracked from start to insight
3. External communications logged from draft to send
4. Personal reflections (journals/dreams) timestamped
5. Event log queryable for patterns, summaries, replay

**Expected Impact**: From "scattered signals" to "coherent nervous system" enabling:
- Pattern recognition across domains
- State reconstruction after restart
- Session summaries from events
- Autonomous work tracking

---

**Estimated Total Time**: 75 minutes
**Effort Level**: Low (mostly adding 5-10 line emit calls)
**Risk Level**: Very Low (event emission is non-blocking, logging-only)
**Value**: HIGH (lights up entire observability layer)

