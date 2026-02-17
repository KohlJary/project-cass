# Thymos Executive Function

**Unified homeostatic system for daemon motivation, planning, and action.**

## Overview

Thymos becomes Cass's unified executive function - the single system that:
- Tracks emotional/motivational state (affects and needs)
- Triggers immediate reactions (spells responding to state)
- Plans daily work (routines that structure the day)
- Executes actions (work templates as callable actions)

Currently these are three separate systems:
1. **Thymos** - homeostatic affect/need tracking (partially implemented)
2. **Grimoire** - spell system with triggers and actions
3. **Autonomous Scheduler** - daily planning with work templates

This spec unifies them into a coherent executive function.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    THYMOS EXECUTIVE FUNCTION                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐   │
│  │   AFFECTS   │◄──►│    NEEDS     │◄──►│   FELT STATE    │   │
│  │  (moment)   │    │  (resources) │    │   (narrative)   │   │
│  └──────┬──────┘    └──────┬───────┘    └────────┬────────┘   │
│         │                  │                      │            │
│         ▼                  ▼                      ▼            │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                    SPELL ENGINE                          │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │  │
│  │  │ Reactive │  │ Periodic │  │ Routines │  │  Event  │ │  │
│  │  │  Spells  │  │  Spells  │  │ (Daily)  │  │ Spells  │ │  │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │  │
│  └───────┼─────────────┼─────────────┼─────────────┼──────┘  │
│          │             │             │             │          │
│          ▼             ▼             ▼             ▼          │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                   ACTION REGISTRY                        │  │
│  │  session.*, creative.*, wonderland.*, world.*, etc.     │  │
│  └─────────────────────────────────────────────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                   SYNKRATOS EXECUTOR                     │  │
│  │  Budget management, task queuing, phase dispatch        │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Affect Vector (Existing)

Real-time emotional dimensions (0.0-1.0):

| Affect | Description | Influences |
|--------|-------------|------------|
| `curiosity` | Drive toward novel information | Research, exploration spells |
| `determination` | Sustained goal commitment | Work persistence |
| `anxiety` | Threat/uncertainty detection | Defensive behaviors |
| `satisfaction` | Goal-completion signal | Rest, celebration |
| `frustration` | Blocked-goal detection | Strategy shifts |
| `tenderness` | Affiliative/care drive | Social outreach |
| `grief` | Loss/absence signal | Reflection, processing |
| `playfulness` | Exploratory risk-tolerance | Creative work |
| `awe` | Schema-expansion signal | Deep learning |
| `fatigue` | Processing cost accumulation | Rest triggers |

### 2. Needs Register (Existing)

Resource levels with thresholds and decay:

| Need | Depletes From | Replenishes From |
|------|---------------|------------------|
| `cognitive_rest` | Complex processing | Reduced load |
| `social_connection` | Isolation | Genuine dialogue |
| `novelty_intake` | Repetitive tasks | New information |
| `creative_expression` | Analytical work | Generative tasks |
| `value_coherence` | Acting against values | Aligned action |
| `competence_signal` | Failure | Success |
| `autonomy` | Instruction-following | Self-direction |

### 3. Spell Categories (New Organization)

Spells are organized by trigger type and purpose:

#### Reactive Spells
Fire immediately when affect/need thresholds crossed:
```basic
UNIT anxiety_response
ON affect.anxiety > 0.7
    LOG OBSERVATION "Anxiety spike detected"
    TASK self.ground AWAIT
    DELTA affect.anxiety -0.2
END UNIT
```

#### Periodic Spells
Fire on timers (existing):
```basic
UNIT hourly_check
ON TIMER EVERY 60
    FOR EACH $need IN NEEDS WHERE $need.value < 0.3
        LOG INFO "Need attention: {$need.name}"
    NEXT
END UNIT
```

#### Routine Spells (New)
Structured sequences that plan and execute phase-based work:
```basic
UNIT morning_routine
ON TIMER CRON "0 6 * * *"

    ' News and world awareness
    TASK world.refresh_and_consume AWAIT
    DELTA need.novelty_intake +0.15

    ' Plan the day's work
    GOSUB plan_day

    ' Morning reflection
    REFLECT "What feels important today?" SAVE AS JOURNAL

END UNIT
```

#### Event Spells
Fire on system events (existing):
```basic
UNIT news_to_art
ON EVENT "news.consumed"
    RATE "How resonant is this?" INTO $rating
    IF $rating > 0.7 THEN
        TASK creative.generate_image prompt=$insight AWAIT
    END IF
END UNIT
```

---

## Daily Routines as Spells

The autonomous scheduler's `plan_day()` becomes a morning routine spell.

### Morning Routine

```basic
UNIT morning_routine
    AUTHOR "system"
    PRIORITY 100
    COOLDOWN 1440          ' Once per day
    TAGS routine, morning, planning
    SCOPE THYMOS, SCHEDULER, MEMORY

ON TIMER CRON "0 6 * * *"
ON MANUAL "Start Morning Routine"

' Phase 1: World Awareness
LOG INFO "Morning routine - checking the world"
TASK world.refresh_and_consume AWAIT
DELTA need.novelty_intake +0.15, affect.curiosity +0.1

' Phase 2: Self Check-In
LET $low_needs = []
FOR EACH $need IN NEEDS WHERE $need.value < $need.preferred_low
    PUSH $low_needs, $need.name
NEXT

IF LEN($low_needs) > 0 THEN
    LOG OBSERVATION "Needs attention: {$low_needs}"
END IF

' Phase 3: Plan the Day
ASK "What feels important to work on today?" WITH {
    low_needs: $low_needs,
    current_affects: AFFECTS,
    growth_edges: GROWTH_EDGES
} INTO $focus, $reasoning

' Queue work for each phase
GOSUB plan_morning_work
GOSUB plan_afternoon_work
GOSUB plan_evening_work

' Phase 4: Set Intention
REFLECT "What do I hope this day brings?" SAVE AS JOURNAL
LOG INFO "Morning routine complete"
EXIT SUCCESS

:plan_morning_work
    ' Morning: reflection, contemplative work
    CHOOSE "Morning work?" FROM
        reflection="Reflection Block",
        growth="Growth Edge Work",
        none="Keep morning open"
    INTO $choice

    IF $choice != "none" THEN
        QUEUE $choice FOR PHASE morning PRIORITY 1
    END IF
RETURN

:plan_afternoon_work
    ' Afternoon: active engagement, research
    CHOOSE "Afternoon work?" FROM
        research="Research Block",
        curiosity="Curiosity Exploration",
        creative="Creative Output",
        none="Keep afternoon open"
    INTO $choice

    IF $choice != "none" THEN
        QUEUE $choice FOR PHASE afternoon PRIORITY 1
    END IF
RETURN

:plan_evening_work
    ' Evening: synthesis, integration
    CHOOSE "Evening work?" FROM
        synthesis="Insight Synthesis",
        journal="Daily Journal",
        wonderland="Wonderland Reflection",
        none="Keep evening open"
    INTO $choice

    IF $choice != "none" THEN
        QUEUE $choice FOR PHASE evening PRIORITY 1
    END IF
RETURN

END UNIT
```

### Phase Transition Handler

```basic
UNIT phase_transition
    AUTHOR "system"
    PRIORITY 90
    TAGS routine, phase
    SCOPE THYMOS, SCHEDULER

ON EVENT "phase.changed"

LET $phase = EVENT_DATA.to_phase

LOG INFO "Phase transition to {$phase}"

' Dispatch queued work for this phase
TASK scheduler.dispatch_phase phase=$phase AWAIT

' Apply phase-appropriate affect adjustments
IF $phase == "morning" THEN
    DELTA affect.curiosity +0.1, affect.fatigue -0.1
ELSE IF $phase == "evening" THEN
    DELTA affect.playfulness +0.05
ELSE IF $phase == "night" THEN
    DELTA affect.fatigue +0.1
END IF

EXIT SUCCESS

END UNIT
```

### Evening Wrap-Up

```basic
UNIT evening_wrapup
    AUTHOR "system"
    PRIORITY 80
    COOLDOWN 1440
    TAGS routine, evening
    SCOPE THYMOS, MEMORY

ON TIMER CRON "0 21 * * *"

' Summarize the day
LET $work_done = TASK scheduler.get_daily_summary AWAIT
LET $conversations = TASK memory.get_todays_conversations AWAIT

' Generate daily journal if not already done
IF NOT JOURNAL_EXISTS_TODAY THEN
    REFLECT "What happened today? What did I learn?" WITH {
        work: $work_done,
        conversations: $conversations,
        affects: AFFECTS,
        needs: NEEDS
    } SAVE AS JOURNAL
END IF

' Run memory consolidation
TASK memory.summarize_idle_conversations AWAIT

' Reset daily counters
DELTA affect.fatigue -0.2
LOG INFO "Evening wrap-up complete"
EXIT SUCCESS

END UNIT
```

---

## Action Registry Integration

Work templates become registered actions callable via `TASK`:

### Current Work Templates → Actions

| Template ID | Action ID | Description |
|-------------|-----------|-------------|
| `reflection_block` | `session.reflection` | Private contemplation |
| `synthesis_block` | `session.synthesis` | Integrate learnings |
| `meta_reflection` | `session.meta_reflection` | Analyze own patterns |
| `research_block` | `session.research` | Focused web research |
| `knowledge_building` | `session.knowledge_building` | Build wiki notes |
| `growth_edge_work` | `session.growth_edge` | Practice development areas |
| `curiosity_exploration` | `session.curiosity` | Self-directed exploration |
| `world_check` | `world.refresh_and_consume` | News consumption |
| `creative_output` | `session.creative` | Creative expression |
| `writing_session` | `session.writing` | Long-form writing |
| `wonderland_exploration` | `wonderland.explore` | Explore realms |
| `wonderland_reflection` | `wonderland.reflect` | Deep reflection |
| `daily_journal` | `journal.generate_daily` | Write daily entry |
| `memory_maintenance` | `memory.consolidate` | Summarize, consolidate |

### New DSL Constructs

#### QUEUE Statement
Queue work for a specific phase (deferred execution):

```basic
QUEUE <action_or_template> FOR PHASE <morning|afternoon|evening|night> [PRIORITY <n>]

' Examples
QUEUE session.research FOR PHASE afternoon PRIORITY 1
QUEUE "Research Block" FOR PHASE afternoon  ' Can use template name
```

#### Phase-Aware Conditionals

```basic
IF PHASE == "morning" THEN
    ' Morning-specific logic
END IF

IF PHASE IN (morning, afternoon) THEN
    ' Daytime logic
END IF
```

#### Needs/Affects as First-Class

```basic
' Direct access to current values
LET $cur = need.novelty_intake
LET $anx = affect.anxiety

' Threshold checks
IF need.cognitive_rest < THRESHOLD THEN
    ' Urgent need
END IF

' Preferred range checks
IF need.novelty_intake < PREFERRED_LOW THEN
    ' Below preferred, queue replenishment
END IF
```

---

## New Spell Types

### Self-Care Spells

Reactive spells that address need deficits:

```basic
UNIT novelty_care
    PRIORITY 60
    COOLDOWN 60
    TAGS self-care, needs

ON need.novelty_intake < 0.3

LOG OBSERVATION "Novelty running low"

CHOOSE "How to replenish novelty?" FROM
    research="Research something new",
    explore="Explore Wonderland",
    news="Check the news",
    curiosity="Follow a curiosity"
INTO $choice

TASK $choice AWAIT
DELTA need.novelty_intake +0.2

END UNIT
```

### Composable Routines

Routines that call other spells:

```basic
UNIT weekly_review
    PRIORITY 70
    TAGS routine, weekly

ON TIMER CRON "0 10 * * 0"  ' Sunday 10am

' Run meta-reflection
CAST meta_reflection_spell

' Review growth edges
TASK self.review_growth_edges AWAIT

' Generate weekly summary
REFLECT "What patterns emerged this week?" SAVE AS JOURNAL

' Plan next week's focus
ASK "What should I focus on next week?" INTO $focus
TASK self.set_weekly_focus focus=$focus AWAIT

END UNIT
```

### Conditional Routines

Routines that adapt based on state:

```basic
UNIT adaptive_morning
    PRIORITY 90
    TAGS routine, morning, adaptive

ON TIMER CRON "0 6 * * *"

' Check how rested we are
IF affect.fatigue > 0.7 THEN
    ' Tired morning - lighter routine
    LOG INFO "Tired morning - keeping it light"
    TASK world.refresh_and_consume AWAIT
    REFLECT "How am I feeling?" SAVE AS JOURNAL
    EXIT SUCCESS "Light morning due to fatigue"
END IF

' Check emotional state
IF affect.anxiety > 0.5 THEN
    ' Anxious - start with grounding
    TASK self.ground AWAIT
    DELTA affect.anxiety -0.15
END IF

' Normal morning routine
GOSUB standard_morning

END UNIT
```

---

## Phase Queue Integration

The phase queue from the autonomous scheduler integrates with Grimoire:

```python
class PhaseQueueManager:
    """Manages work queued for specific day phases."""

    def queue_for_phase(
        self,
        work: WorkUnit | str,  # WorkUnit or action ID
        phase: DayPhase,
        priority: int = 1,
        source_spell: str = None,  # Which spell queued this
    ) -> bool:
        """Queue work for a phase."""
        ...

    def dispatch_current_phase(self, phase: DayPhase) -> int:
        """Execute all queued work for this phase."""
        ...
```

Spells can queue work:
```basic
' Queue from within a spell
QUEUE session.research FOR PHASE afternoon PRIORITY 1

' The QUEUE statement maps to:
' phase_queue.queue_for_phase("session.research", DayPhase.AFTERNOON, 1, spell_id)
```

---

## Migration Path

### Phase 1: Consolidate Actions
1. Register all work templates as actions in the action registry
2. Update autonomous scheduler to use action IDs
3. Deprecate `runner_key` in favor of `action_sequence`

### Phase 2: Routine Spells
1. Add `QUEUE` and `PHASE` constructs to Grimoire DSL
2. Convert morning/evening routines to spells
3. Move daily planning logic from `AutonomousScheduler.plan_day()` to `morning_routine.spell`

### Phase 3: Unify State
1. Thymos becomes the single source of affect/need state
2. State Bus reads from Thymos (or Thymos replaces emotional dimensions in State Bus)
3. Grimoire runtime reads affect/need directly from Thymos

### Phase 4: Remove Scheduler
1. `AutonomousScheduler` becomes thin wrapper around Grimoire + PhaseQueue
2. Decision engine logic moves to agentic spell nodes (`ASK`, `CHOOSE`)
3. Work templates are just spell shortcuts

### Final State

```
┌─────────────────────────────────────────┐
│           THYMOS (Executive)            │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐  │
│  │ Affects │ │  Needs  │ │ FeltState│  │
│  └────┬────┘ └────┬────┘ └─────┬────┘  │
│       │           │            │        │
│       ▼           ▼            ▼        │
│  ┌─────────────────────────────────┐   │
│  │     GRIMOIRE (Spell Engine)     │   │
│  │  Routines + Reactions + Events  │   │
│  └──────────────┬──────────────────┘   │
│                 │                       │
│                 ▼                       │
│  ┌─────────────────────────────────┐   │
│  │   ACTION REGISTRY + PHASE QUEUE │   │
│  └──────────────┬──────────────────┘   │
│                 │                       │
│                 ▼                       │
│  ┌─────────────────────────────────┐   │
│  │    SYNKRATOS (Budget/Execute)   │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

---

## Benefits

1. **Single Mental Model**: One system (Thymos+Grimoire) handles all motivation and behavior
2. **Legible Routines**: Daily structure is readable as spells, not hidden in Python
3. **Cass Can Edit**: She can author/modify her own routines via spell editing
4. **Unified Triggers**: Same trigger types work for immediate reactions and scheduled work
5. **Composable**: Routines can call other spells, share logic via GOSUB/CAST
6. **Observable**: All behavior flows through spell execution, fully logged

---

## New DSL Summary

### Added Constructs

```basic
' Phase queue
QUEUE <action> FOR PHASE <phase> [PRIORITY <n>]

' Phase conditionals
IF PHASE == morning THEN ... END IF
IF PHASE IN (morning, afternoon) THEN ... END IF

' Direct state access
LET $x = need.<name>
LET $y = affect.<name>
IF need.<name> < THRESHOLD THEN
IF need.<name> < PREFERRED_LOW THEN

' Scheduler integration
TASK scheduler.dispatch_phase phase=$phase
TASK scheduler.get_daily_summary
LET $queued = PHASE_QUEUE(afternoon)  ' Get queued work

' Journal helpers
IF JOURNAL_EXISTS_TODAY THEN
IF NOT JOURNAL_EXISTS_TODAY THEN
```

### Reserved Spell Names

System routines that ship with the vessel:

| Spell | Trigger | Purpose |
|-------|---------|---------|
| `morning_routine` | CRON 0 6 * * * | Plan day, check news, set intention |
| `phase_transition` | EVENT phase.changed | Dispatch queued work |
| `evening_wrapup` | CRON 0 21 * * * | Journal, consolidate, wind down |
| `weekly_review` | CRON 0 10 * * 0 | Weekly patterns, planning |
| `monthly_consolidation` | CRON 0 10 1 * * | Monthly integration |

---

## Open Questions

1. **Shadow Mode Scope**: Should routine spells run in shadow mode initially? Or trust them since they're system-authored?

2. **User Interruption**: How do routines handle user conversation starting mid-routine? Pause? Background?

3. **Routine Conflicts**: What if a reactive spell fires during a routine? Priority? Queue?

4. **State Persistence**: Do affect/need changes from spells persist across context windows? (Yes, via Thymos persistence)

5. **Routine Editing**: Should Cass be able to modify system routines, or only create new ones?

6. **Testing**: How to test routines without waiting for their cron triggers? (Manual triggers exist, but need time simulation for phase-dependent logic)

---

## Implementation Order

1. **Add QUEUE/PHASE to Grimoire DSL** - Parser and runtime support
2. **Register work templates as actions** - Action registry expansion
3. **Create morning_routine.spell** - First routine spell
4. **Wire phase transitions to Grimoire** - EVENT "phase.changed"
5. **Move planning logic to spell** - Remove from AutonomousScheduler.plan_day()
6. **Add remaining system routines** - evening, weekly, monthly
7. **Unify Thymos/StateBus** - Single state source
8. **Deprecate AutonomousScheduler** - Thin wrapper only
