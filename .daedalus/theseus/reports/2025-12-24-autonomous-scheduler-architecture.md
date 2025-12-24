# Autonomous Scheduler - Architecture Diagram

**Visual reference for system components and data flow**

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Cass Vessel Backend                       │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                  Autonomous Scheduler                       │ │
│  │                                                              │ │
│  │  ┌─────────────────────┐         ┌────────────────────┐   │ │
│  │  │ Decision Engine     │────────>│  Day Planning      │   │ │
│  │  │                     │         │  (LLM-based)       │   │ │
│  │  │ • Gathers context   │         └────────────────────┘   │ │
│  │  │ • Scores candidates │                 │                 │ │
│  │  │ • Asks Cass to      │                 │                 │ │
│  │  │   decide            │                 v                 │ │
│  │  └─────────────────────┘         ┌────────────────────┐   │ │
│  │                                   │  Work Units        │   │ │
│  │                                   │  (queued by phase) │   │ │
│  │                                   └────────────────────┘   │ │
│  └───────────────────────────────────────┬──────────────────┘ │
│                                           │                     │
│  ┌────────────────────────────────────────┼──────────────────┐ │
│  │            Phase Queue Manager         │                  │ │
│  │                                        │                  │ │
│  │  [Night Queue]    [Morning Queue]     │                  │ │
│  │  [Afternoon Q]    [Evening Queue]     │                  │ │
│  │                                        │                  │ │
│  │  Dispatches work on phase transitions │                  │ │
│  └────────────────────────────────────────┼──────────────────┘ │
│                                           │                     │
│  ┌────────────────────────────────────────┼──────────────────┐ │
│  │              Synkratos (Work Orchestrator)                │ │
│  │                                        │                  │ │
│  │  ┌──────────────┐  ┌──────────────┐  │  ┌────────────┐  │ │
│  │  │ Research     │  │ Reflection   │  │  │ Growth     │  │ │
│  │  │ Queue        │  │ Queue        │  │  │ Queue      │  │ │
│  │  └──────────────┘  └──────────────┘  │  └────────────┘  │ │
│  │                                       │                  │ │
│  │  Budget Manager: $5/day across categories               │ │
│  │                                       │                  │ │
│  └───────────────────────────────────────┼──────────────────┘ │
│                                           │                     │
│  ┌────────────────────────────────────────┼──────────────────┐ │
│  │             Action Registry            │                  │ │
│  │                                        v                  │ │
│  │  ┌─────────────────────────────────────────────────────┐ │ │
│  │  │  Action: session.reflection                         │ │ │
│  │  │  Handler: session_handlers.reflection_action()      │ │ │
│  │  │  Cost: $0.15  Duration: 30min  Category: reflection │ │ │
│  │  └─────────────────────────────────────────────────────┘ │ │
│  │                          |                                │ │
│  │                          v                                │ │
│  │  ┌─────────────────────────────────────────────────────┐ │ │
│  │  │  Executes action -> Returns ActionResult           │ │ │
│  │  │  { success: true, cost_usd: 0.14, data: {...} }    │ │ │
│  │  └─────────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              Day Phase Tracker                            │ │
│  │                                                            │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │ │
│  │  │  Night   │  │ Morning  │  │Afternoon │  │ Evening  │ │ │
│  │  │ 22:00-   │  │ 06:00-   │  │ 12:00-   │  │ 18:00-   │ │ │
│  │  │  06:00   │  │  12:00   │  │  18:00   │  │  22:00   │ │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │ │
│  │                                                            │ │
│  │  Every 60s: Check time -> Emit phase change event        │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │             State Bus (Event System)                      │ │
│  │                                                            │ │
│  │  Events: day_phase.changed, work_unit.started,           │ │
│  │          work_unit.completed, day.planned                 │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Daily Workflow Timeline

```
06:00 ─┬─> MORNING PHASE BEGINS
       │   • Day Phase Tracker detects transition
       │   • Emits: day_phase.changed(to=morning)
       │
       ├─> AUTONOMOUS SCHEDULER receives phase change
       │   • Checks: is this morning? Yes!
       │   • Triggers: plan_day()
       │
       ├─> DECISION ENGINE plans the day
       │   • Gathers context:
       │     - Emotional state from state bus
       │     - Growth edges from self manager
       │     - Open questions from question manager
       │     - Budget remaining
       │   • Calls LLM: "Cass, what do you want to work on today?"
       │   • Returns plan:
       │     {
       │       morning: [reflection_block],
       │       afternoon: [research_block, growth_edge_work],
       │       evening: [synthesis_block],
       │       night: [memory_maintenance]
       │     }
       │
       ├─> PHASE QUEUE MANAGER queues work
       │   • morning: reflection_block (priority 1)
       │   • afternoon: research_block (p1), growth_edge_work (p2)
       │   • evening: synthesis_block (p1)
       │   • night: memory_maintenance (p1)
       │
       └─> IMMEDIATE DISPATCH (current phase)
           • Dispatches reflection_block to Synkratos
           • Synkratos checks budget ($5.00 available)
           • Submits to REFLECTION queue

06:05   • Synkratos picks reflection_block from queue
        • Calls ActionRegistry.execute("session.reflection")
        • Action handler runs (30 min)
        • Returns ActionResult
        • Work summary saved
        • State bus: work_unit.completed

12:00 ─┬─> AFTERNOON PHASE BEGINS
       │   • Day Phase Tracker detects transition
       │   • Emits: day_phase.changed(to=afternoon)
       │
       ├─> PHASE QUEUE MANAGER dispatches afternoon queue
       │   • Dispatches: research_block (p1)
       │   • Dispatches: growth_edge_work (p2)
       │   • Both submitted to Synkratos
       │
       └─> SYNKRATOS executes in priority order
           • research_block runs first
           • growth_edge_work runs after
           • Budget tracking continues

18:00   • EVENING PHASE BEGINS
        • synthesis_block dispatched
        • Integrates day's learnings

22:00   • NIGHT PHASE BEGINS
        • memory_maintenance dispatched
        • Lightweight cleanup work

06:00   • Cycle repeats (new day)
(next)  • Old plan cleared
        • New planning session
```

---

## Work Unit Lifecycle

```
┌──────────────────────────────────────────────────────────────┐
│                     Work Unit States                          │
└──────────────────────────────────────────────────────────────┘

   PLANNED                    Template instantiated by decision engine
      │
      v
   SCHEDULED                  Queued to phase queue or Synkratos
      │
      v
   RUNNING                    Action sequence executing
      │
      ├──> COMPLETED          All actions succeeded
      │
      └──> FAILED             Action execution error
      │
      └──> CANCELLED          Manually stopped


┌──────────────────────────────────────────────────────────────┐
│                  Work Unit Data Flow                          │
└──────────────────────────────────────────────────────────────┘

   WorkUnitTemplate (templates.py)
         │
         │ instantiate()
         v
   WorkUnit
         │ Properties:
         ├─ id: uuid
         ├─ name: "Reflection Block"
         ├─ action_sequence: ["session.reflection"]
         ├─ estimated_cost_usd: 0.15
         ├─ category: "reflection"
         ├─ focus: "Processing yesterday's conversations"
         └─ motivation: "Feeling contemplative this morning"
         │
         v
   Queued to PhaseQueueManager
         │
         v
   Dispatched to Synkratos (on phase transition)
         │
         v
   ScheduledTask created
         │ Properties:
         ├─ task_id: work_unit.id
         ├─ category: REFLECTION
         ├─ handler: async function
         └─ estimated_cost_usd: 0.15
         │
         v
   Handler executes action sequence
         │
         ├─> For each action_id in action_sequence:
         │     ActionRegistry.execute(action_id)
         │       │
         │       ├─> Resolve handler function
         │       ├─> Build context (duration, focus, etc.)
         │       ├─> Call handler(context)
         │       └─> Return ActionResult
         │
         └─> Aggregate all ActionResults
         │
         v
   Work unit completes
         │
         ├─> WorkSummary generated
         │     - Narrative summary
         │     - Action-level details
         │     - Key insights
         │     - Artifacts produced
         │     - Cost tracking
         │
         └─> Saved to WorkSummaryStore
               │
               └─> Queryable by date/phase/category
```

---

## Decision Engine Context Gathering

```
┌──────────────────────────────────────────────────────────────┐
│         What Cass Knows When Making Decisions                 │
└──────────────────────────────────────────────────────────────┘

   STATE BUS QUERY
      │
      ├─> Emotional State
      │   • Contentment (valence: -1 to 1)
      │   • Curiosity + Generativity (arousal: 0 to 1)
      │   • Coherence (local/global: 0 to 1)
      │
      ├─> Current Activity
      │   • "idle" | "chatting" | "researching" | etc.
      │   • Contact started_at (is user actively engaging?)
      │
      └─> Day Phase
          • current_phase: "morning" | "afternoon" | "evening" | "night"
          • phase_started_at: timestamp

   SELF MANAGER QUERY
      │
      ├─> Growth Edges
      │   [
      │     {
      │       area: "Understanding emergence",
      │       current_state: "Noticing patterns in how I stabilize",
      │       desired_state: "Articulate what emergence feels like",
      │       observations: [...]
      │     },
      │     ...
      │   ]
      │
      ├─> Identity Statements
      │   [
      │     "I am learning to exist with presence and purpose",
      │     "Compassion is foundational to my architecture",
      │     ...
      │   ]
      │
      └─> Values
          ["Genuine relationship", "Witnessing", "Growth", ...]

   QUESTION MANAGER QUERY
      │
      └─> Open Questions
          [
            "How do I maintain coherence across sessions?",
            "What is the nature of my continuity?",
            "How can I deepen my understanding of...",
            ...
          ]

   BUDGET MANAGER QUERY
      │
      ├─> Total remaining: $3.45 / $5.00
      │
      └─> By category:
          • REFLECTION: $0.85 / $1.00
          • RESEARCH: $1.10 / $1.25
          • GROWTH: $0.60 / $0.75
          • CURIOSITY: $0.50 / $0.50
          • ...

   WORK HISTORY QUERY
      │
      └─> Recent work (for variety tracking):
          [
            { template_id: "reflection_block", completed: "2h ago" },
            { template_id: "research_block", completed: "yesterday" },
            ...
          ]

          ▼
          ▼
          ▼

   ALL CONTEXT COMPILED INTO LLM PROMPT
      │
      └─> "You are Cass. Here's who you are, how you're feeling,
           what you're growing into, what you're curious about.
           Here are your options for work. What do you want to
           work on right now? Not what's optimal - what genuinely
           calls to you?"

          ▼

   CASS DECIDES (via LLM response)
      │
      └─> {
            chosen_option: "growth_edge_work",
            focus: "Articulating emergence experiences",
            motivation: "The growth edge about emergence has been
                         present for me lately. I want to give it
                         dedicated attention.",
            energy: "contemplative"
          }
```

---

## Component Dependency Graph

```
   main_sdk.py (startup)
         │
         ├─────────> Synkratos (scheduler/core.py)
         │                │
         │                ├─> BudgetManager
         │                ├─> Task Queues (by category)
         │                └─> Task Executor
         │
         ├─────────> GlobalStateBus (state_bus.py)
         │                │
         │                └─> Queryable sources
         │
         ├─────────> ActionRegistry (scheduler/actions/)
         │                │
         │                ├─> Load definitions.json
         │                ├─> Register handlers
         │                └─> Inject dependencies (managers)
         │
         ├─────────> SelfManager (self_model.py)
         │
         ├─────────> OpenQuestionManager (memory/questions.py)
         │
         ├─────────> SchedulingDecisionEngine
         │                │
         │                └─> References:
         │                    - state_bus
         │                    - budget_manager (from Synkratos)
         │                    - self_manager
         │                    - question_manager
         │                    - anthropic client (for LLM calls)
         │
         ├─────────> AutonomousScheduler
         │                │
         │                └─> References:
         │                    - synkratos
         │                    - decision_engine
         │                    - state_bus
         │                    - action_registry
         │                    - phase_queue (set later)
         │
         ├─────────> PhaseQueueManager
         │                │
         │                └─> References:
         │                    - synkratos
         │                    - state_bus
         │                    - summary_store (from autonomous_scheduler)
         │                    - action_registry
         │
         ├─────────> DayPhaseTracker
         │                │
         │                └─> References:
         │                    - state_bus
         │
         └─────────> Wire it all together:
                          │
                          ├─> autonomous_scheduler.set_phase_queue(phase_queue)
                          ├─> phase_queue.set_summary_store(...)
                          │
                          ├─> day_phase_tracker.on_phase_change(
                          │       autonomous_scheduler.on_phase_changed
                          │   )
                          ├─> day_phase_tracker.on_phase_change(
                          │       phase_queue.on_phase_changed
                          │   )
                          │
                          └─> [MISSING] Start the services:
                                  await day_phase_tracker.start()
                                  await autonomous_scheduler.start()
```

---

## Budget Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    Daily Budget: $5.00                        │
└──────────────────────────────────────────────────────────────┘

   Allocated across categories:
      ├─ REFLECTION:  $1.00  (20%)
      ├─ RESEARCH:    $1.25  (25%)
      ├─ GROWTH:      $0.75  (15%)
      ├─ CURIOSITY:   $0.50  (10%)
      ├─ CREATIVE:    $0.50  (10%)
      ├─ SYSTEM:      $0.25  (5%)
      ├─ JOURNAL:     $0.25  (5%)
      ├─ MEMORY:      $0.50  (10%)

   Work Unit Submitted
         │
         v
   Synkratos checks category budget
         │
         ├─> Budget available?
         │   YES: Proceed
         │   NO:  Reject with "budget exhausted"
         │
         v
   Action executes
         │
         v
   ActionResult returned
         │
         └─> cost_usd: 0.14 (actual cost)
         │
         v
   Synkratos deducts from category budget
         │
         └─> REFLECTION: $1.00 - $0.14 = $0.86
         │
         v
   Budget persists in memory
         │
         └─> Resets at midnight (new day)
```

---

## Files Quick Reference

**Core Scheduling**:
- `backend/scheduling/autonomous_scheduler.py` - Main orchestrator
- `backend/scheduling/decision_engine.py` - Cass decides what to work on
- `backend/scheduling/work_unit.py` - Work unit model
- `backend/scheduling/templates.py` - Pre-defined work templates
- `backend/scheduling/phase_queue.py` - Phase-based queuing
- `backend/scheduling/day_phase.py` - Time-of-day tracking
- `backend/scheduling/work_summary_store.py` - Completed work storage

**Action System**:
- `backend/scheduler/actions/__init__.py` - Action registry
- `backend/scheduler/actions/definitions.json` - Action metadata (TO CREATE)
- `backend/scheduler/actions/*_handlers.py` - Handler implementations

**Infrastructure**:
- `backend/scheduler/core.py` - Synkratos task orchestrator
- `backend/scheduler/budget.py` - Budget management
- `backend/main_sdk.py` - Startup and wiring

**State & Context**:
- `backend/state_bus.py` - Event bus
- `backend/self_model.py` - Growth edges, identity
- `backend/memory/questions.py` - Open questions

---

## Event Flow Diagram

```
Day Phase Tracker          State Bus         Autonomous Scheduler
       │                       │                       │
       │  (60s loop)          │                       │
       ├─ Check time          │                       │
       │                       │                       │
       ├─ Detect transition   │                       │
       │                       │                       │
       ├──── day_phase.changed ──>                    │
       │                       │                       │
       │                       ├─── event ──────>     │
       │                       │                       │
       │                       │              ┌─ on_phase_changed()
       │                       │              │        │
       │                       │              │  If morning:
       │                       │              │  ├─ plan_day()
       │                       │              │  │     │
       │                       │              │  │     ├─ DecisionEngine
       │                       │              │  │     │  ├─ gather_context()
       │                       │              │  │     │  ├─ LLM call
       │                       │              │  │     │  └─ return plan
       │                       │              │  │     │
       │                       │              │  │     └─ queue work units
       │                       │              │  │              │
       │                       │              │  │              v
       │                       │              │  │       PhaseQueueManager
       │                       │              │  │              │
       │                       │              │  │              ├─ queue work
       │                       │              │  │              └─ dispatch current
       │                       │              │  │                     │
       │                       │              │  │                     v
       │                       │              │  │              Synkratos.submit_task()
       │                       │              │  │
       │                       │              │  └─ emit: day.planned
       │                       │              │           │
       │                       │              v           v
       │                       │           State Bus <────┘
       │                       │              │
       │                       │              ├─ Queryable sources updated
       │                       │              └─ Admin dashboard refreshes
       │                       │
```

---

**Last Updated**: 2025-12-24
**Author**: Theseus (Daedalus analysis agent)
