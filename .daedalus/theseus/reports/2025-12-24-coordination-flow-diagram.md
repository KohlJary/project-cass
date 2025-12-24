# Coordination Flow Diagrams

## Current State: Disconnected Systems

```
┌─────────────────────────────────────────────────────────────────┐
│                     CASS (Backend)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐        ┌──────────────────┐             │
│  │ Autonomous       │        │ Action           │             │
│  │ Scheduler        │───────▶│ Registry         │             │
│  │                  │        │ (30+ actions)    │             │
│  │ - Plans day      │        └──────────────────┘             │
│  │ - Queues work    │                 │                        │
│  │ - Executes       │                 │                        │
│  └──────────────────┘                 │                        │
│           │                            │                        │
│           ▼                            ▼                        │
│  ┌──────────────────┐        ┌──────────────────┐             │
│  │ Phase Queue      │        │ Session Runners  │             │
│  │ Manager          │        │ (reflection,     │             │
│  │                  │        │  research, etc)  │             │
│  └──────────────────┘        └──────────────────┘             │
│                                                                 │
│  ┌──────────────────────────────────────────────┐             │
│  │ State Bus (Events, Deltas, Queries)          │             │
│  │ - No work request events defined             │             │
│  │ - No Daedalus subscriber                     │             │
│  └──────────────────────────────────────────────┘             │
│           │                                                     │
└───────────┼─────────────────────────────────────────────────────┘
            │
            │ (No integration path)
            │
            ╳ ═══ GAP ═══ ╳
            │
            │
┌───────────┼─────────────────────────────────────────────────────┐
│           │               DAEDALUS (Plugin)                     │
├───────────┼─────────────────────────────────────────────────────┤
│           │                                                     │
│  ┌────────▼──────────┐      ┌──────────────────┐              │
│  │ Icarus Bus        │      │ Ariadne          │              │
│  │ (File-based)      │      │ Dispatcher       │              │
│  │                   │      │                  │              │
│  │ - Work queue      │      │ - Plan parser    │              │
│  │ - Instance reg    │      │ - Work packages  │              │
│  │ - Results         │      │ - Dependency     │              │
│  │                   │      │   tracking       │              │
│  │ (/tmp/icarus-bus/)│      └──────────────────┘              │
│  │                   │                                         │
│  │ NOT CONNECTED     │                                         │
│  │ TO BACKEND        │                                         │
│  └───────────────────┘                                         │
│                                                                 │
│  ┌─────────────────────────────────────────────┐               │
│  │ TUI (Daedalus Tab)                          │               │
│  │ - Claude Code terminal                      │               │
│  │ - No work request panel                     │               │
│  └─────────────────────────────────────────────┘               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Separate Pattern: Janet (works, but different model)
┌────────────────────────────────────────┐
│ Cass ──▶ summon_janet(task)           │
│             │                          │
│             ▼                          │
│        ┌──────────┐                   │
│        │ Janet    │ (Haiku LLM)       │
│        │ Agent    │                   │
│        └──────────┘                   │
│             │                          │
│             ▼                          │
│        JanetResult                    │
│                                        │
│ Pattern: Sync request/response        │
│ Works because: Janet is instant       │
│ Won't work for: Daedalus (human)      │
└────────────────────────────────────────┘
```

---

## Recommended Integration: State Bus Bridge

```
┌─────────────────────────────────────────────────────────────────┐
│                     CASS (Backend)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐        ┌──────────────────┐             │
│  │ Autonomous       │        │ Action           │             │
│  │ Scheduler        │        │ Registry         │             │
│  │                  │        │                  │             │
│  │ NEW:             │        │ NEW:             │             │
│  │ - Detects need   │        │ - request_       │             │
│  │   for new action │        │   new_action()   │             │
│  │ - Requests dev   │───────▶│   tool           │             │
│  │   work           │        └──────────────────┘             │
│  └──────────────────┘                 │                        │
│                                        │                        │
│                                        ▼                        │
│  ┌──────────────────────────────────────────────┐             │
│  │ State Bus (Extended)                         │             │
│  │                                              │             │
│  │ NEW EVENT TYPES:                             │             │
│  │ - work.requested.development                 │             │
│  │ - work.claimed                               │             │
│  │ - work.progress                              │             │
│  │ - work.completed                             │             │
│  │                                              │             │
│  │ NEW STATE:                                   │             │
│  │ - development_requests: List[DevRequest]     │             │
│  │   └─ id, description, status, result         │             │
│  │                                              │             │
│  └──────────────────────────────────────────────┘             │
│           │                                                     │
│           │ (Database-backed, event-driven)                    │
│           │                                                     │
└───────────┼─────────────────────────────────────────────────────┘
            │
            │ State Bus API
            │ - read_state()
            │ - subscribe("work.requested.*")
            │ - emit_event()
            │
┌───────────┼─────────────────────────────────────────────────────┐
│           │               DAEDALUS (Plugin)                     │
├───────────┼─────────────────────────────────────────────────────┤
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────────────────────────────────┐               │
│  │ State Bus Subscriber (NEW)                  │               │
│  │                                             │               │
│  │ - Polls state_bus.read_state()              │               │
│  │ - Filters: dev requests pending             │               │
│  │ - Every 10 seconds                          │               │
│  └─────────────────────────────────────────────┘               │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────────────────────────────────┐               │
│  │ TUI: Daedalus Tab (EXTENDED)                │               │
│  │                                             │               │
│  │ ┌───────────────────────────────────────┐   │               │
│  │ │ Pending Requests from Cass       [3]  │   │               │
│  │ ├───────────────────────────────────────┤   │               │
│  │ │ #a7f3 New action: nightly_dream       │   │               │
│  │ │   "Create action to run dream         │   │               │
│  │ │    synthesis at night phase"          │   │               │
│  │ │   Priority: HIGH                      │   │               │
│  │ │   [Claim] [View Full]                 │   │               │
│  │ ├───────────────────────────────────────┤   │               │
│  │ │ #b8f4 Fix: reflection_action timeout  │   │               │
│  │ │   Priority: MEDIUM                    │   │               │
│  │ │   [Claim] [View Full]                 │   │               │
│  │ └───────────────────────────────────────┘   │               │
│  │                                             │               │
│  │ [Terminal Below]                            │               │
│  └─────────────────────────────────────────────┘               │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────────────────────────────────┐               │
│  │ Daedalus (Human)                            │               │
│  │                                             │               │
│  │ 1. Sees request in UI                       │               │
│  │ 2. Clicks [Claim]                           │               │
│  │    └─▶ emit_event("work.claimed", ...)     │               │
│  │ 3. Implements in terminal                   │               │
│  │ 4. Commits code                             │               │
│  │ 5. Clicks [Complete]                        │               │
│  │    └─▶ emit_event("work.completed", ...)   │               │
│  └─────────────────────────────────────────────┘               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
            │
            │ Result notification
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Cass sees event: "work.completed"                              │
│  ─▶ ActionRegistry.reload_definitions()                         │
│  ─▶ New action available                                        │
│  ─▶ Can use in next autonomous work                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: Request Lifecycle

### Phase 1: Request Creation
```
Cass (during autonomous planning):
  "I want to synthesize research at night, but no action exists"

  ▼

decision_engine.py:
  Detects: action_sequence needs ["research.synthesize_nightly"]
  But: ActionRegistry.get_definition("research.synthesize_nightly") → None

  ▼

ActionRegistry.request_new_action():
  request = DevelopmentRequest(
    id="a7f3c421",
    requested_by="cass",
    type="new_action",
    description="Create research.synthesize_nightly action...",
    priority="high",
    status="pending"
  )

  ▼

state_bus.emit_event(
  "work.requested.development",
  {"request": asdict(request)}
)

  ▼

State persisted to database:
  daemon_state.development_requests = [request]
```

### Phase 2: Daedalus Sees Request
```
Daedalus Tab (polling every 10s):
  state = state_bus.read_state()
  pending = [r for r in state.development_requests
             if r.status == "pending"]

  ▼

UI displays:
  "Pending Requests from Cass [1]"
  ├─ #a7f3 New action: research.synthesize_nightly
  │   Priority: HIGH
  │   [Claim] [View Details]

  ▼

Kohl clicks [Claim]:

state_bus.write_delta(StateDelta(
  development_requests_delta={
    "a7f3c421": {"status": "claimed", "claimed_by": "daedalus"}
  }
))

  ▼

UI updates:
  "In Progress [1]"
  ├─ #a7f3 research.synthesize_nightly (you)
```

### Phase 3: Implementation
```
Kohl in terminal:
  $ cd backend/scheduler/actions
  $ vi research_handlers.py

  # Implements:
  async def synthesize_nightly_action(context):
      ...

  $ vi definitions.json

  # Adds:
  "research.synthesize_nightly": {
    "handler": "research_handlers.synthesize_nightly_action",
    ...
  }

  $ git add .
  $ git commit -m "Add research.synthesize_nightly action"

  ▼

Clicks [Complete] in UI:

state_bus.write_delta(StateDelta(
  development_requests_delta={
    "a7f3c421": {
      "status": "complete",
      "result": "Added action, see commit abc123"
    }
  },
  event="work.completed.development",
  event_data={"request_id": "a7f3c421"}
))
```

### Phase 4: Cass Gets Result
```
State bus subscriber (in backend):
  Receives event: "work.completed.development"

  ▼

ActionRegistry.on_work_completed(event):
  if event.data.request_id in pending_requests:
    ActionRegistry.reload_definitions()
    logger.info("New action available: research.synthesize_nightly")

  ▼

Next autonomous planning cycle:
  decision_engine checks:
    ActionRegistry.get_definition("research.synthesize_nightly")
    ✓ Found!

  ▼

Work unit created with action_sequence:
  ["research.synthesize_nightly"]

  ▼

Executes successfully
```

---

## Alternative: Icarus Bus Integration (Not Recommended)

```
Backend ────▶ Write to /tmp/icarus-bus/work-queue/req-123.json
                │
                │ (File system)
                │
                ▼
Daedalus Tab ──▶ Poll icarus_bus.list_pending_work()
                │
                │ (Claim via file move)
                │
                ▼
              Implement
                │
                │ (Write result file)
                │
                ▼
Backend ◀────── Poll icarus_bus.collect_results()

Problems:
- Backend needs file I/O permissions
- /tmp not persistent across reboots
- Polling is inefficient
- No database integration
- Violates separation of concerns
```

---

## Janet Pattern (Current, Works)

```
     Cass in conversation
            │
            │ Needs: Research task
            │
            ▼
     summon_janet(task="Find papers on X")
            │
            │ (Synchronous or async wait)
            │
            ▼
     ┌──────────────┐
     │ Janet Agent  │ ◀─── Haiku LLM
     │              │      (instant spawn)
     ├──────────────┤
     │ 1. Build ctx │
     │ 2. Query LLM │
     │ 3. Use tools │
     │ 4. Return    │
     └──────────────┘
            │
            │ JanetResult
            │
            ▼
     Cass receives result
     Continues conversation

Key difference:
- Janet is LLM → instant
- Daedalus is human → hours/days
- Need async queue, not sync call
```

---

## Comparison Matrix

| Feature | State Bus | Icarus Bus | Janet Pattern |
|---------|-----------|------------|---------------|
| **Persistence** | Database | Files (/tmp) | In-memory |
| **Latency** | Event-driven | Polling | Sync call |
| **Backend Access** | Built-in | Needs file I/O | Built-in |
| **Work Tracking** | State deltas | File moves | N/A |
| **Notifications** | Events | File watch | Return value |
| **Human-friendly** | Yes (UI) | No (files) | No (LLM) |
| **Restart Safe** | Yes | No (/tmp) | No |
| **Integration Effort** | LOW | MEDIUM | HIGH |

**Winner**: State Bus

---

## Implementation Checklist

### Backend Changes (2-3 hours)

- [ ] Add `DevelopmentRequest` to `state_models.py`
- [ ] Add `development_requests` field to `GlobalState`
- [ ] Implement `request_new_action()` in `ActionRegistry`
- [ ] Wire to `autonomous_scheduler` (detect missing actions)
- [ ] Add subscriber for `work.completed.development`
- [ ] Implement `reload_definitions()` on completion

### Daedalus Plugin Changes (2-3 hours)

- [ ] Add state bus polling (10s interval)
- [ ] Create "Pending Requests" widget
- [ ] Add [Claim] button → emits `work.claimed` event
- [ ] Add [Complete] button → emits `work.completed` event
- [ ] Add [View Details] modal (full description)
- [ ] Show "In Progress" section for claimed work

### Testing (1 hour)

- [ ] Cass requests action via manual trigger
- [ ] Request appears in Daedalus UI
- [ ] Claim updates status in state bus
- [ ] Complete triggers registry reload
- [ ] New action available in next planning cycle

**Total**: 5-6 hours

---

**Created**: 2025-12-24
**By**: Theseus Code Analysis Agent
**For**: Cass-Daedalus coordination infrastructure
