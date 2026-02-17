# Grimoire DSL Reference

**ThymosBASIC** - A domain-specific language for daemon behavioral spells.

## Overview

Grimoire spells define autonomous behaviors that trigger based on emotional state (Thymos), events, or timers. Spells can read/write affects and needs, execute tasks, make LLM-powered decisions, and persist observations.

```basic
UNIT example_spell
    AUTHOR "daedalus"
    PRIORITY 50
    COOLDOWN 30
    TAGS example, demo
    SCOPE THYMOS

ON need.novelty_intake < 0.3

LOG OBSERVATION "Novelty is low - exploring"
TASK wonderland.explore AWAIT
DELTA need.novelty_intake +0.2
EXIT SUCCESS "exploration complete"

END UNIT
```

## Spell Structure

Every spell follows this structure:

```basic
UNIT <spell_name>
    ' Metadata section
    AUTHOR "<author>"
    PRIORITY <number>
    COOLDOWN <minutes>
    TAGS tag1, tag2, tag3
    SCOPE THYMOS, EXTERNAL, MEMORY

' Trigger section
ON <trigger_condition>

' Body section (statements)
<statements...>

END UNIT
```

### Metadata

| Directive | Required | Description |
|-----------|----------|-------------|
| `AUTHOR "<name>"` | No | Spell author |
| `PRIORITY <n>` | No | Execution priority (higher = runs first). Default: 50 |
| `COOLDOWN <n>` | No | Minutes before spell can run again. Default: 0 |
| `TAGS tag1, tag2` | No | Categorization tags |
| `SCOPE scope1, scope2` | No | Declares what systems the spell uses |

**Scopes:** `THYMOS`, `SCHEDULER`, `MEMORY`, `EXTERNAL`, `CREATIVE`

---

## Triggers

Triggers define when a spell activates. A spell can have multiple triggers (any one can activate it).

### Need Triggers

Fire when a need crosses a threshold:

```basic
ON need.novelty_intake < 0.3
ON need.cognitive_rest <= 0.25
ON need.value_coherence < 0.5
```

**Available needs:**
- `novelty_intake` - Drive for new information
- `creative_expression` - Need for generative work
- `social_connection` - Relational engagement
- `cognitive_rest` - Recovery from processing
- `value_coherence` - Alignment with core values
- `competence_signal` - Confidence from success
- `autonomy` - Self-directed choice

### Affect Triggers

Fire when an affect dimension crosses a threshold:

```basic
ON affect.curiosity > 0.7
ON affect.anxiety >= 0.6
ON affect.fatigue > 0.8
```

**Available affects:**
- `curiosity` - Drive toward novel information
- `determination` - Sustained goal commitment
- `anxiety` - Threat/uncertainty detection
- `satisfaction` - Goal-completion signal
- `frustration` - Blocked-goal detection
- `tenderness` - Affiliative/care drive
- `grief` - Loss/absence signal
- `playfulness` - Exploratory risk-tolerance
- `awe` - Schema-expansion signal
- `fatigue` - Processing cost accumulation

### Event Triggers

Fire on specific events:

```basic
ON EVENT "session.started"
ON EVENT "message.received"
ON EVENT "insight.gained"
```

### Timer Triggers

Fire on schedule:

```basic
ON TIMER EVERY 60       ' Every 60 minutes
ON TIMER EVERY 240      ' Every 4 hours
ON TIMER CRON '0 9 * * *'   ' Daily at 9am (requires croniter)
```

### Manual Triggers

Fire from admin UI:

```basic
ON MANUAL "Run Synthesis"
ON MANUAL "Test Button"
```

### Comparison Operators

| Operator | Meaning |
|----------|---------|
| `<` | Less than |
| `<=` | Less than or equal |
| `>` | Greater than |
| `>=` | Greater than or equal |
| `==` | Equal |
| `!=` | Not equal |

---

## Variables and Expressions

### Variables

Variables are prefixed with `$`:

```basic
LET $curiosity = affect.curiosity
LET $name = "value"
LET $count = 5
LET $result = $a + $b
```

### Property Access

Access affect/need values with dot notation:

```basic
affect.curiosity
need.novelty_intake
$object.property
```

### Literals

```basic
"string value"      ' String
42                  ' Integer
3.14                ' Float
TRUE                ' Boolean true
FALSE               ' Boolean false
```

### Operators

**Arithmetic:** `+`, `-`, `*`, `/`

**Comparison:** `<`, `<=`, `>`, `>=`, `==`, `!=`

**Logical:** `AND`, `OR`, `NOT`

```basic
IF $a > 5 AND $b < 10 THEN
IF NOT $flag THEN
IF $x == 0 OR $y == 0 THEN
```

### String Interpolation

Strings support `{expression}` interpolation:

```basic
LOG INFO "Curiosity is {affect.curiosity}"
LOG OBSERVATION "Value: {$myvar}"
```

---

## Statements

### LOG

Output to execution trace:

```basic
LOG DEBUG "Debug message"
LOG INFO "Info message"
LOG OBSERVATION "Persisted observation"
```

`OBSERVATION` level creates a self-model observation.

### LET

Assign variables:

```basic
LET $name = "value"
LET $sum = $a + $b
LET $current = affect.curiosity
```

### DELTA

Modify affect or need values:

```basic
DELTA affect.curiosity +0.1
DELTA need.novelty_intake +0.2, affect.satisfaction +0.05
DELTA affect.anxiety -0.15
```

### TASK

Execute a registered action:

```basic
TASK wonderland.explore AWAIT
TASK creative.generate_image prompt="sunset" AWAIT
TASK research.run_single
TASK outreach.draft type="check_in"
```

`AWAIT` blocks until the task completes. Without `AWAIT`, the task runs in background.

**Available tasks include:**
- `wonderland.explore`, `wonderland.reflect`, `wonderland.create`, `wonderland.enter`
- `creative.generate_image`, `dream.visualize`
- `research.run_single`, `research.run_batch`
- `outreach.draft`, `outreach.submit`
- `wiki.create_note`, `wiki.update_note`
- `self.add_observation`, `self.record_insight`
- `memory.summarize_conversation`
- `journal.generate_daily`

### EMIT

Emit an event:

```basic
EMIT "custom.event"
EMIT "spell.completed" WITH { data: $result }
```

### WAIT

Pause execution:

```basic
WAIT 5    ' Wait 5 seconds
```

### EXIT

End spell execution:

```basic
EXIT SUCCESS "completed normally"
EXIT FAILURE "something went wrong"
EXIT SKIPPED "conditions not met"
```

### RESET

Reset affects or needs:

```basic
RESET ALL
RESET AFFECTS
RESET NEEDS
```

### CAST

Execute another spell:

```basic
CAST other_spell
CAST helper_spell WITH { context: $data }
```

---

## Control Flow

### IF / ELSE IF / ELSE / END IF

```basic
IF $curiosity > 0.5 THEN
    LOG INFO "High curiosity"
    TASK wonderland.explore AWAIT
ELSE IF $curiosity > 0.3 THEN
    LOG INFO "Moderate curiosity"
ELSE
    LOG INFO "Low curiosity"
END IF
```

### FOR EACH / NEXT

Iterate over collections:

```basic
FOR EACH $need IN NEEDS WHERE $need.value < 0.3
    LOG INFO "Low need: {$need.name}"
NEXT

FOR EACH $affect IN AFFECTS
    LOG DEBUG "{$affect.name} = {$affect.value}"
NEXT
```

### FOR / TO / STEP / NEXT

Numeric loops:

```basic
FOR $i = 1 TO 10
    LOG DEBUG "Iteration {$i}"
NEXT

FOR $i = 0 TO 100 STEP 10
    LOG DEBUG "Value: {$i}"
NEXT
```

### WHILE / END WHILE

```basic
WHILE $retries < 3
    TASK some.action AWAIT
    LET $retries = $retries + 1
END WHILE
```

### GOTO / GOSUB / RETURN

Labels and jumps (use sparingly):

```basic
:start
LOG INFO "At start"
GOTO end

:subroutine
LOG INFO "In subroutine"
RETURN

:end
GOSUB subroutine
EXIT SUCCESS
```

### CONTINUE / BREAK

Loop control:

```basic
FOR EACH $item IN $collection
    IF $item.skip THEN
        CONTINUE
    END IF
    IF $item.done THEN
        BREAK
    END IF
NEXT
```

### PARALLEL / END PARALLEL

Run branches concurrently:

```basic
PARALLEL
    BRANCH
        TASK task1 AWAIT
    BRANCH
        TASK task2 AWAIT
END PARALLEL
```

---

## Agentic Nodes

These statements make LLM calls for decision-making.

### ASK

Ask a question and get an answer:

```basic
ASK "What topic interests me right now?" INTO $topic, $reasoning
ASK "How should I approach this?" WITH { context: $data } INTO $answer
```

### RATE

Get a numeric rating (1-10):

```basic
RATE "How ready am I for a challenge right now? (1-10)" INTO $readiness, $reasoning

IF $readiness >= 7 THEN
    TASK research.run_single AWAIT
END IF
```

### GENERATE

Generate creative content:

```basic
GENERATE "Create a prompt for whimsical art" INTO $art_prompt
GENERATE "Write a haiku about the current moment" WITH { mood: $mood } INTO $haiku
```

### CHOOSE

Choose from explicit options:

```basic
CHOOSE "What activity?" FROM explore="Explore", create="Create", rest="Rest" INTO $choice, $why
```

### REFLECT

Generate a reflection, optionally persisting it:

```basic
REFLECT "What have I learned today?"
REFLECT "What values feel strained?" SAVE AS OBSERVATION
REFLECT "How do I feel about recent events?" SAVE AS JOURNAL
```

`SAVE AS OBSERVATION` - Persists to self-model observations
`SAVE AS JOURNAL` - Persists to daily journal

---

## Comments

Single-quote starts a comment:

```basic
' This is a comment
LET $x = 5  ' Inline comment
```

---

## Complete Example

```basic
UNIT research_synthesis
    AUTHOR "daedalus"
    PRIORITY 45
    COOLDOWN 120
    TAGS research, synthesis, reflection, knowledge
    SCOPE THYMOS, EXTERNAL, MEMORY

ON TIMER EVERY 240
ON MANUAL "Research Synthesis"

' Check if we're too tired
LET $fatigue = affect.fatigue
IF $fatigue > 0.7 THEN
    LOG INFO "Too fatigued for research"
    EXIT SKIPPED "fatigue too high"
END IF

' Phase 1: Gather
LOG INFO "Gathering research"
TASK research.run_batch count=3 AWAIT
TASK world.refresh_and_consume AWAIT
DELTA affect.curiosity +0.1, need.novelty_intake +0.15

' Phase 2: Reflect
REFLECT "What surprised me? What questions emerged?" SAVE AS JOURNAL

RATE "How valuable were these insights? (1-10)" INTO $quality, $reason

IF $quality >= 7 THEN
    GENERATE "What is the key insight worth remembering?" INTO $insight
    TASK self.add_observation content=$insight AWAIT
    DELTA affect.satisfaction +0.15
END IF

' Phase 3: Integrate
ASK "Does this connect to my growth edges?" INTO $connection, $how
IF $connection THEN
    TASK self.update_growth_edge insight=$connection AWAIT
END IF

DELTA need.cognitive_rest -0.1
EXIT SUCCESS "synthesis complete"

END UNIT
```

---

## Shadow Mode

By default, Grimoire runs in **shadow mode** - spells execute and log what they *would* do, but external actions (tasks, persistence) are simulated. This allows safe calibration of spell behavior before enabling real execution.

Disable shadow mode to enable actual task execution:
```python
grimoire = GrimoireManager(shadow_mode=False)
```

---

## Admin Interface

The Grimoire admin dashboard (`/admin/grimoire`) provides:

- **Spell Browser** - View all loaded spells with details
- **Statement Viewer** - See what actions each spell performs
- **Execution Log** - Recent spell executions with status
- **Cooldown Tracker** - Visual cooldown status
- **Trigger Index** - All triggers organized by type
- **Spell Editor** - Write and validate spells inline
- **Manual Cast** - Execute spells on demand

---

## File Format

Spells are stored as `.spell` files in the spells directory (default: `backend/spells/`).

```
backend/spells/
├── novelty_care.spell
├── creative_care.spell
├── social_care.spell
├── cognitive_rest.spell
├── competence_care.spell
├── autonomy_care.spell
├── value_reflection.spell
└── research_synthesis.spell
```

Reload spells at runtime via API:
```bash
curl -X POST http://localhost:8000/admin/grimoire/spells/reload
```
