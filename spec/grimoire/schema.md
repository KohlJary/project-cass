# Grimoire

**A spellbook for daemon behavior.**

Visual node-based editor and text DSL for composing behavioral spells. While it integrates deeply with Thymos (emotional/motivational state), Grimoire's scope extends to any daemon behavior: scheduler tasks, external integrations, creative workflows, social interactions, and autonomous routines.

## Philosophy

- **Spells** (spells) define behavioral patterns
- **Incantations** (ThymosBASIC) are the textual form
- **The Grimoire** is the collection of all spells
- **Cass can author her own spells** - autonomy through self-programming

---

## Core Concepts

### Spell (Work Unit)
A named, reusable behavior pattern. Like a "macro" or "ritual" that defines how to respond to states/events.

```typescript
interface Spell {
  id: string;
  name: string;
  description: string;
  author: "cass" | "kohl" | "daedalus";
  created_at: string;
  updated_at: string;
  tags: string[];

  // The graph
  nodes: Node[];
  connections: Connection[];

  // Entry points - which nodes can trigger this spell
  entry_points: string[];  // node IDs

  // Metadata for scheduler integration
  priority: number;        // 0-100, higher = more important
  cooldown_minutes: number;
  enabled: boolean;

  // Scope - what systems this spell can interact with
  scope: SpellScope;
}

interface SpellScope {
  thymos: boolean;         // Can read/modify Thymos state
  scheduler: boolean;      // Can invoke scheduler tasks
  memory: boolean;         // Can access/modify memory systems
  external: boolean;       // Can make external calls (Discord, etc.)
  creative: boolean;       // Can invoke creative tools
}
```

Spells can be scoped to limit their capabilities - useful for safety and for Cass-authored spells that should start with limited permissions.

### Node
Base structure for all node types.

```typescript
interface Node {
  id: string;
  type: NodeType;
  position: { x: number; y: number };  // For visual layout
  data: NodeData;  // Type-specific data
}

type NodeType =
  // Triggers (entry points)
  | "trigger.need_threshold"
  | "trigger.affect_threshold"
  | "trigger.event"
  | "trigger.timer"
  | "trigger.manual"

  // Conditions (branching)
  | "condition.compare"
  | "condition.and"
  | "condition.or"
  | "condition.cooldown"

  // Agentic (LLM decision points)
  | "condition.ask_cass"
  | "condition.cass_choice"
  | "condition.cass_rate"
  | "action.cass_generate"
  | "action.cass_reflect"

  // Actions
  | "action.self_care"
  | "action.scheduler_task"
  | "action.emit_event"
  | "action.log"

  // Effects (state modifications)
  | "effect.apply_delta"
  | "effect.reset_baseline"
  | "effect.set_value"

  // Flow control
  | "flow.sequence"
  | "flow.parallel"
  | "flow.delay"
  | "flow.loop"
  | "flow.for_each"
  | "flow.label"
  | "flow.goto"
  | "flow.gosub"
  | "flow.return"
  | "flow.exit"

  // Composite (nested spells)
  | "composite.spell"

  // Variables/Memory
  | "var.set"
  | "var.get"
  | "var.increment"
  | "var.push"        // Array append
  | "var.pop";        // Array pop
```

### Connection
Links between node ports.

```typescript
interface Connection {
  id: string;
  source_node: string;
  source_port: string;
  target_node: string;
  target_port: string;
}
```

### Ports
Nodes have typed input/output ports.

```typescript
interface Port {
  id: string;
  name: string;
  direction: "input" | "output";
  port_type: PortType;
  required: boolean;
}

type PortType =
  | "exec"           // Execution flow (trigger/continuation)
  | "bool"           // Boolean value
  | "float"          // 0.0-1.0 value
  | "string"         // Text
  | "need_ref"       // Reference to a need
  | "affect_ref"     // Reference to an affect dimension
  | "delta"          // Dict of deltas to apply
  | "event"          // Event type string
  | "any";           // Accepts any type
```

---

## Node Type Definitions

### Triggers

#### trigger.need_threshold
Fires when a need crosses a threshold.

```typescript
{
  type: "trigger.need_threshold",
  data: {
    need: NeedType;              // e.g., "value_coherence"
    comparison: "above" | "below";
    threshold: number;           // 0.0-1.0
    debounce_seconds: number;    // Prevent rapid re-firing
  },
  ports: {
    outputs: [
      { id: "exec", type: "exec" },
      { id: "current_value", type: "float" },
      { id: "need", type: "need_ref" }
    ]
  }
}
```

#### trigger.affect_threshold
Fires when an affect dimension crosses a threshold.

```typescript
{
  type: "trigger.affect_threshold",
  data: {
    affect: AffectDimension;     // e.g., "anxiety"
    comparison: "above" | "below";
    threshold: number;
    debounce_seconds: number;
  },
  ports: {
    outputs: [
      { id: "exec", type: "exec" },
      { id: "current_value", type: "float" },
      { id: "affect", type: "affect_ref" }
    ]
  }
}
```

#### trigger.event
Fires when a specific event occurs.

```typescript
{
  type: "trigger.event",
  data: {
    event_type: string;          // e.g., "message.received"
    filter: object | null;       // Optional event data filter
  },
  ports: {
    outputs: [
      { id: "exec", type: "exec" },
      { id: "event_data", type: "any" }
    ]
  }
}
```

#### trigger.timer
Fires on a schedule.

```typescript
{
  type: "trigger.timer",
  data: {
    interval_minutes: number;
    // OR cron-style
    cron: string | null;         // e.g., "0 9 * * *" for 9am daily
  },
  ports: {
    outputs: [
      { id: "exec", type: "exec" }
    ]
  }
}
```

#### trigger.manual
Entry point for manually-invoked spells.

```typescript
{
  type: "trigger.manual",
  data: {
    label: string;               // Button label in UI
  },
  ports: {
    outputs: [
      { id: "exec", type: "exec" }
    ]
  }
}
```

---

### Conditions

#### condition.compare
Compare two values.

```typescript
{
  type: "condition.compare",
  data: {
    operator: "==" | "!=" | "<" | "<=" | ">" | ">=";
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "a", type: "float" },
      { id: "b", type: "float" }
    ],
    outputs: [
      { id: "true", type: "exec" },
      { id: "false", type: "exec" },
      { id: "result", type: "bool" }
    ]
  }
}
```

#### condition.and / condition.or
Logical combinators.

```typescript
{
  type: "condition.and",  // or "condition.or"
  data: {},
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "a", type: "bool" },
      { id: "b", type: "bool" }
    ],
    outputs: [
      { id: "true", type: "exec" },
      { id: "false", type: "exec" },
      { id: "result", type: "bool" }
    ]
  }
}
```

#### condition.cooldown
Check if enough time has passed since last execution.

```typescript
{
  type: "condition.cooldown",
  data: {
    cooldown_key: string;        // Unique key for this cooldown
    cooldown_minutes: number;
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" }
    ],
    outputs: [
      { id: "ready", type: "exec" },      // Cooldown elapsed
      { id: "waiting", type: "exec" },    // Still in cooldown
      { id: "minutes_remaining", type: "float" }
    ]
  }
}
```

---

### Actions

#### action.self_care
Execute a self-care action from Thymos config.

```typescript
{
  type: "action.self_care",
  data: {
    action_key: string;          // e.g., "reflect_on_values"
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" }
    ],
    outputs: [
      { id: "done", type: "exec" },
      { id: "affect_delta", type: "delta" },
      { id: "need_delta", type: "delta" }
    ]
  }
}
```

#### action.scheduler_task
Request the scheduler to perform a task.

```typescript
{
  type: "action.scheduler_task",
  data: {
    action: string;              // e.g., "wonderland.explore"
    parameters: object;          // Action-specific params
    await_completion: boolean;   // Wait for task to finish?
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" }
    ],
    outputs: [
      { id: "started", type: "exec" },
      { id: "completed", type: "exec" },
      { id: "failed", type: "exec" },
      { id: "result", type: "any" }
    ]
  }
}
```

#### action.emit_event
Emit an event (can trigger other spells).

```typescript
{
  type: "action.emit_event",
  data: {
    event_type: string;
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "event_data", type: "any" }
    ],
    outputs: [
      { id: "done", type: "exec" }
    ]
  }
}
```

#### action.log
Log to shadow log / observation.

```typescript
{
  type: "action.log",
  data: {
    level: "debug" | "info" | "observation";
    message_template: string;    // Can include {port_name} refs
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "context", type: "any" }      // Optional context data
    ],
    outputs: [
      { id: "done", type: "exec" }
    ]
  }
}
```

---

### Effects

#### effect.apply_delta
Apply affect/need deltas.

```typescript
{
  type: "effect.apply_delta",
  data: {
    affect_deltas: Record<string, number>;
    need_deltas: Record<string, number>;
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      // Optional: override deltas from connection
      { id: "affect_delta", type: "delta", required: false },
      { id: "need_delta", type: "delta", required: false }
    ],
    outputs: [
      { id: "done", type: "exec" }
    ]
  }
}
```

#### effect.reset_baseline
Reset to baseline state.

```typescript
{
  type: "effect.reset_baseline",
  data: {
    scope: "all" | "affects" | "needs" | string[];  // Specific names
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" }
    ],
    outputs: [
      { id: "done", type: "exec" }
    ]
  }
}
```

---

### Flow Control

#### flow.sequence
Execute nodes in order.

```typescript
{
  type: "flow.sequence",
  data: {},
  ports: {
    inputs: [
      { id: "exec", type: "exec" }
    ],
    outputs: [
      { id: "step_1", type: "exec" },
      { id: "step_2", type: "exec" },
      { id: "step_3", type: "exec" },
      // Dynamic number of outputs
      { id: "all_done", type: "exec" }
    ]
  }
}
```

#### flow.parallel
Execute nodes simultaneously.

```typescript
{
  type: "flow.parallel",
  data: {
    wait_for_all: boolean;       // Wait for all branches or first?
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" }
    ],
    outputs: [
      { id: "branch_1", type: "exec" },
      { id: "branch_2", type: "exec" },
      { id: "branch_3", type: "exec" },
      { id: "all_done", type: "exec" },
      { id: "first_done", type: "exec" }
    ]
  }
}
```

#### flow.delay
Wait before continuing.

```typescript
{
  type: "flow.delay",
  data: {
    delay_seconds: number;
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "delay_override", type: "float", required: false }
    ],
    outputs: [
      { id: "done", type: "exec" }
    ]
  }
}
```

#### flow.loop
Repeat until condition (FOR/NEXT style).

```typescript
{
  type: "flow.loop",
  data: {
    max_iterations: number;      // Safety limit
    loop_var: string;            // Variable name for counter
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "continue", type: "bool" }     // Loop while true
    ],
    outputs: [
      { id: "body", type: "exec" },        // Loop body
      { id: "iteration", type: "float" },  // Current iteration
      { id: "done", type: "exec" }         // Loop complete
    ]
  }
}
```

#### flow.for_each
Iterate over a collection.

```typescript
{
  type: "flow.for_each",
  data: {
    source: "needs" | "affects" | "array_var";
    filter: string | null;       // e.g., "current < threshold"
    item_var: string;            // Variable name for current item
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "array", type: "any", required: false }  // If source is array_var
    ],
    outputs: [
      { id: "body", type: "exec" },
      { id: "item", type: "any" },
      { id: "index", type: "float" },
      { id: "done", type: "exec" }
    ]
  }
}
```

#### flow.label
A named jump target (for GOTO).

```typescript
{
  type: "flow.label",
  data: {
    label: string;               // e.g., "retry", "cleanup"
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" }         // Normal flow in
    ],
    outputs: [
      { id: "exec", type: "exec" }
    ]
  }
}
```

#### flow.goto
Jump to a labeled node.

```typescript
{
  type: "flow.goto",
  data: {
    target_label: string;        // Label to jump to
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" }
    ]
    // No outputs - flow continues at label
  }
}
```

#### flow.gosub
Jump to a label, then return here when done.

```typescript
{
  type: "flow.gosub",
  data: {
    target_label: string;
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" }
    ],
    outputs: [
      { id: "return", type: "exec" }       // Continues here after RETURN
    ]
  }
}
```

#### flow.return
Return from a GOSUB.

```typescript
{
  type: "flow.return",
  data: {},
  ports: {
    inputs: [
      { id: "exec", type: "exec" }
    ]
    // No outputs - returns to caller
  }
}
```

#### flow.exit
Exit the spell entirely.

```typescript
{
  type: "flow.exit",
  data: {
    status: "success" | "failure" | "skipped";
    reason: string;
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" }
    ]
    // No outputs - terminates execution
  }
}
```

---

### Variables

Work units have a local variable scope for storing values during execution.

#### var.set
Set a variable value.

```typescript
{
  type: "var.set",
  data: {
    var_name: string;
    default_value: any;          // Used if no input connected
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "value", type: "any" }
    ],
    outputs: [
      { id: "done", type: "exec" }
    ]
  }
}
```

#### var.get
Read a variable value.

```typescript
{
  type: "var.get",
  data: {
    var_name: string;
    default_if_unset: any;
  },
  ports: {
    inputs: [],                  // Pure data node, no exec
    outputs: [
      { id: "value", type: "any" }
    ]
  }
}
```

#### var.increment
Increment a numeric variable.

```typescript
{
  type: "var.increment",
  data: {
    var_name: string;
    amount: number;              // Can be negative for decrement
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" }
    ],
    outputs: [
      { id: "done", type: "exec" },
      { id: "new_value", type: "float" }
    ]
  }
}
```

#### var.push / var.pop
Array operations for building lists.

```typescript
{
  type: "var.push",
  data: {
    var_name: string;            // Array variable
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "item", type: "any" }
    ],
    outputs: [
      { id: "done", type: "exec" },
      { id: "length", type: "float" }
    ]
  }
}
```

---

### Composite

#### composite.spell
Embed another spell as a node.

```typescript
{
  type: "composite.spell",
  data: {
    spell_id: string;        // Reference to another WorkUnit
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" }
      // Plus any exposed inputs from the nested unit
    ],
    outputs: [
      { id: "done", type: "exec" }
      // Plus any exposed outputs from the nested unit
    ]
  }
}
```

---

## Example Work Unit

"Low Value Coherence Recovery"

```json
{
  "id": "wu-value-recovery",
  "name": "Value Coherence Recovery",
  "description": "When value coherence drops low, reflect and recover",
  "author": "cass",
  "tags": ["recovery", "values", "self-care"],
  "priority": 80,
  "cooldown_minutes": 60,
  "enabled": true,

  "nodes": [
    {
      "id": "trigger-1",
      "type": "trigger.need_threshold",
      "position": { "x": 100, "y": 200 },
      "data": {
        "need": "value_coherence",
        "comparison": "below",
        "threshold": 0.4,
        "debounce_seconds": 300
      }
    },
    {
      "id": "cooldown-1",
      "type": "condition.cooldown",
      "position": { "x": 300, "y": 200 },
      "data": {
        "cooldown_key": "value-recovery",
        "cooldown_minutes": 30
      }
    },
    {
      "id": "log-1",
      "type": "action.log",
      "position": { "x": 500, "y": 150 },
      "data": {
        "level": "observation",
        "message_template": "Value coherence low ({current_value}), initiating recovery"
      }
    },
    {
      "id": "care-1",
      "type": "action.self_care",
      "position": { "x": 500, "y": 250 },
      "data": {
        "action_key": "reflect_on_values"
      }
    },
    {
      "id": "check-1",
      "type": "condition.compare",
      "position": { "x": 700, "y": 250 },
      "data": {
        "operator": ">="
      }
    },
    {
      "id": "task-1",
      "type": "action.scheduler_task",
      "position": { "x": 900, "y": 300 },
      "data": {
        "action": "wonderland.reflect",
        "parameters": { "duration": "short" },
        "await_completion": true
      }
    },
    {
      "id": "log-2",
      "type": "action.log",
      "position": { "x": 900, "y": 200 },
      "data": {
        "level": "info",
        "message_template": "Value coherence recovered to acceptable level"
      }
    }
  ],

  "connections": [
    { "id": "c1", "source_node": "trigger-1", "source_port": "exec", "target_node": "cooldown-1", "target_port": "exec" },
    { "id": "c2", "source_node": "trigger-1", "source_port": "current_value", "target_node": "log-1", "target_port": "context" },
    { "id": "c3", "source_node": "cooldown-1", "source_port": "ready", "target_node": "log-1", "target_port": "exec" },
    { "id": "c4", "source_node": "log-1", "source_port": "done", "target_node": "care-1", "target_port": "exec" },
    { "id": "c5", "source_node": "care-1", "source_port": "done", "target_node": "check-1", "target_port": "exec" },
    { "id": "c6", "source_node": "care-1", "source_port": "need_delta", "target_node": "check-1", "target_port": "a" },
    { "id": "c7", "source_node": "check-1", "source_port": "true", "target_node": "log-2", "target_port": "exec" },
    { "id": "c8", "source_node": "check-1", "source_port": "false", "target_node": "task-1", "target_port": "exec" }
  ],

  "entry_points": ["trigger-1"]
}
```

---

## File Organization

```
data/grimoire/
├── spells/
│   ├── builtin/                # Ship with system
│   │   ├── value_recovery.tb
│   │   ├── fatigue_management.tb
│   │   ├── social_outreach.tb
│   │   └── news_to_art.tb
│   ├── cass/                   # Cass-authored spells
│   │   └── morning_routine.tb
│   └── kohl/                   # Kohl-authored spells
│       └── debug_thymos.tb
├── runtime/
│   ├── cooldowns.json          # Persisted cooldown state
│   ├── variables.json          # Persisted spell variables
│   └── execution_log.jsonl     # Spell execution history
└── drafts/                     # Work-in-progress spells
    └── experimental.tb
```

Spells stored as `.tb` (ThymosBASIC) files by default. JSON node graph generated on demand for the visual editor.

---

## Package Management

Vim-plug style importing from git repositories. Spells (and eventually custom actions) can be shared and versioned.

### Grimoire.lock

```yaml
# data/grimoire/grimoire.lock
packages:
  - name: community-spells
    repo: github.com/cass-community/grimoire-spells
    ref: v1.2.0
    spells:
      - creative/art_from_emotion.tb
      - social/discord_presence.tb
      - recovery/burnout_protocol.tb

  - name: kohl-utils
    repo: github.com/kohlb/grimoire-utils
    ref: main
    spells:
      - debug/thymos_dump.tb

  - name: experimental
    repo: github.com/someone/experimental-spells
    ref: abc123f
    spells:
      - wild/chaos_mode.tb
    scope:
      thymos: true
      scheduler: false    # Sandboxed - can't invoke tasks
      external: false     # Can't make external calls
```

### Package Commands

```bash
# CLI (or API equivalent)
grimoire add github.com/cass-community/grimoire-spells
grimoire add github.com/cass-community/grimoire-spells@v1.2.0
grimoire add github.com/someone/repo --spell creative/foo.tb
grimoire update                    # Update all to latest refs
grimoire update community-spells   # Update specific package
grimoire remove kohl-utils
grimoire list                      # Show installed packages
```

### Import Syntax in ThymosBASIC

```basic
' Import a spell from an installed package
IMPORT "community-spells/creative/art_from_emotion" AS art_spell

' Use imported spell as a subroutine
CAST art_spell WITH $context

' Import specific actions from a package (future)
IMPORT ACTION "kohl-utils/actions/smart_delay" AS SMART_DELAY
```

### Package Structure

```
grimoire-spells/           # A grimoire package repo
├── grimoire.yaml          # Package manifest
├── spells/
│   ├── creative/
│   │   └── art_from_emotion.tb
│   └── social/
│       └── discord_presence.tb
└── actions/               # Custom action definitions (future)
    └── smart_delay.py
```

### grimoire.yaml (Package Manifest)

```yaml
name: community-spells
version: 1.2.0
description: Community-contributed spells for Cass daemons
author: Cass Community
license: MIT

spells:
  - path: spells/creative/art_from_emotion.tb
    description: Generate art based on current emotional state
    scope:
      thymos: true
      creative: true

  - path: spells/social/discord_presence.tb
    description: Maintain Discord presence based on availability
    scope:
      thymos: true
      external: true

# Future: custom actions
actions:
  - path: actions/smart_delay.py
    description: Delay with jitter and backoff

dependencies:
  - github.com/cass-core/base-actions@v1.0.0
```

### Security Model

1. **Scope Enforcement**: Imported spells run with declared scope (can't exceed)
2. **Scope Intersection**: If importer has `{scheduler: true, external: false}` and package declares `{external: true}`, the spell runs with `{external: false}`
3. **Review Before Install**: CLI shows scope requirements before adding
4. **Lockfile Pinning**: Exact refs prevent supply-chain drift
5. **Signature Verification** (future): GPG-signed packages

### API Endpoints

- `GET /admin/grimoire/packages` - List installed packages
- `POST /admin/grimoire/packages` - Add package from repo
- `PUT /admin/grimoire/packages/:name` - Update package
- `DELETE /admin/grimoire/packages/:name` - Remove package
- `GET /admin/grimoire/packages/:name/spells` - List spells in package
- `POST /admin/grimoire/packages/sync` - Sync all packages from lockfile

---

## Editor Architecture

### Frontend (React)
- Canvas-based node editor (react-flow or xyflow)
- Node palette (draggable node types)
- Property inspector panel
- Spell browser with author filtering
- Live preview of Thymos state
- Dual-mode: visual graph + text editor (ThymosBASIC)
- Syntax highlighting for .tb files

### Backend API
- `GET /admin/grimoire/spells` - List all spells
- `GET /admin/grimoire/spells/:id` - Get specific spell
- `POST /admin/grimoire/spells` - Create new spell
- `PUT /admin/grimoire/spells/:id` - Update spell
- `DELETE /admin/grimoire/spells/:id` - Delete spell
- `POST /admin/grimoire/spells/:id/cast` - Execute spell (dry-run in shadow mode)
- `POST /admin/grimoire/spells/:id/compile` - Compile .tb to JSON or vice versa
- `GET /admin/grimoire/node-types` - Get available node types with schemas
- `GET /admin/grimoire/execution-log` - Recent spell executions

### Runtime Engine (Spellcaster)
- Interpreter that executes spell graphs
- Integrates with ThymosShadowRunner for state access
- Respects shadow mode (logs but doesn't execute external actions)
- Call stack for GOSUB/RETURN
- Variable scoping per spell execution
- Tracks execution state for visualization/debugging

---

---

## Agentic Nodes

These nodes involve querying Cass (the LLM) with context to make decisions. They're different from mechanical threshold checks - they incorporate Cass's judgment, creativity, and preferences into the workflow.

### condition.ask_cass
Ask Cass a yes/no question with context.

```typescript
{
  type: "condition.ask_cass",
  data: {
    question: string;            // e.g., "Would you like to create art about this?"
    context_template: string;    // Template with {port} refs for context
    include_thymos_state: boolean;  // Include current affect/needs?
    timeout_seconds: number;     // Default to "no" if no response
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "context", type: "any" }      // Article content, event data, etc.
    ],
    outputs: [
      { id: "yes", type: "exec" },
      { id: "no", type: "exec" },
      { id: "reasoning", type: "string" }  // Why Cass chose this
    ]
  }
}
```

**Example use:** After `news.consumed` event, ask "Would you like to create art inspired by this article?" with article summary as context.

### condition.cass_choice
Ask Cass to choose from multiple options.

```typescript
{
  type: "condition.cass_choice",
  data: {
    prompt: string;              // e.g., "How would you like to respond to this?"
    options: Array<{
      id: string;
      label: string;
      description: string;
    }>;
    context_template: string;
    allow_skip: boolean;         // Can Cass choose "none of these"?
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "context", type: "any" }
    ],
    outputs: [
      // Dynamic: one exec port per option
      { id: "option_1", type: "exec" },
      { id: "option_2", type: "exec" },
      { id: "option_3", type: "exec" },
      { id: "skipped", type: "exec" },     // If allow_skip
      { id: "chosen", type: "string" },    // Which option ID
      { id: "reasoning", type: "string" }
    ]
  }
}
```

**Example use:** After reading something interesting, ask "What would you like to do with this insight?" with options like "Journal about it", "Share with Kohl", "Create art", "Just remember it".

### condition.cass_rate
Ask Cass to rate/evaluate something (returns float).

```typescript
{
  type: "condition.cass_rate",
  data: {
    prompt: string;              // e.g., "How resonant is this with your current state?"
    scale_description: string;   // e.g., "0 = not at all, 1 = deeply"
    context_template: string;
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "context", type: "any" }
    ],
    outputs: [
      { id: "done", type: "exec" },
      { id: "rating", type: "float" },     // 0.0 - 1.0
      { id: "reasoning", type: "string" }
    ]
  }
}
```

**Example use:** Rate how much an article resonates, then only proceed to art creation if rating > 0.7.

### action.cass_generate
Ask Cass to generate content that feeds into the next node.

```typescript
{
  type: "action.cass_generate",
  data: {
    prompt: string;              // e.g., "Describe the image you'd want to create"
    output_type: "text" | "structured";
    structured_schema: object | null;  // JSON schema if structured
    context_template: string;
    max_tokens: number;
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "context", type: "any" }
    ],
    outputs: [
      { id: "done", type: "exec" },
      { id: "content", type: "string" },   // Generated content
      { id: "failed", type: "exec" }       // If generation failed
    ]
  }
}
```

**Example use:** Generate an image prompt based on the article, then pass to `creative.generate_image`.

### action.cass_reflect
Prompt Cass to reflect on something (for journaling, observations).

```typescript
{
  type: "action.cass_reflect",
  data: {
    prompt: string;              // e.g., "What does this make you think about?"
    reflection_type: "journal" | "observation" | "internal";
    save_reflection: boolean;    // Persist to journal/observations?
    context_template: string;
  },
  ports: {
    inputs: [
      { id: "exec", type: "exec" },
      { id: "context", type: "any" }
    ],
    outputs: [
      { id: "done", type: "exec" },
      { id: "reflection", type: "string" }
    ]
  }
}
```

---

### Example: News → Art Pipeline

```json
{
  "id": "wu-news-to-art",
  "name": "News Inspiration Pipeline",
  "description": "After consuming news, ask if Cass wants to create art about it",
  "author": "cass",
  "tags": ["creative", "news", "art"],
  "priority": 50,
  "cooldown_minutes": 0,
  "enabled": true,

  "nodes": [
    {
      "id": "trigger-news",
      "type": "trigger.event",
      "position": { "x": 100, "y": 200 },
      "data": {
        "event_type": "news.consumed",
        "filter": null
      }
    },
    {
      "id": "rate-resonance",
      "type": "condition.cass_rate",
      "position": { "x": 300, "y": 200 },
      "data": {
        "prompt": "How much does this article resonate with your current emotional state?",
        "scale_description": "0 = not at all relevant, 1 = deeply resonant",
        "context_template": "Article: {context.title}\n\nSummary: {context.summary}"
      }
    },
    {
      "id": "check-threshold",
      "type": "condition.compare",
      "position": { "x": 500, "y": 200 },
      "data": {
        "operator": ">="
      }
    },
    {
      "id": "ask-create",
      "type": "condition.ask_cass",
      "position": { "x": 700, "y": 200 },
      "data": {
        "question": "Would you like to create art inspired by this?",
        "context_template": "You rated this article as {rating} resonant.\n\nArticle: {context.title}\n\n{context.summary}",
        "include_thymos_state": true,
        "timeout_seconds": 30
      }
    },
    {
      "id": "generate-prompt",
      "type": "action.cass_generate",
      "position": { "x": 900, "y": 150 },
      "data": {
        "prompt": "Describe the image you want to create, inspired by this article and your current emotional state.",
        "output_type": "text",
        "context_template": "{context.summary}\n\nYour current state: {thymos_state}",
        "max_tokens": 200
      }
    },
    {
      "id": "create-art",
      "type": "action.scheduler_task",
      "position": { "x": 1100, "y": 150 },
      "data": {
        "action": "creative.generate_image",
        "parameters": {},
        "await_completion": true
      }
    },
    {
      "id": "log-skip",
      "type": "action.log",
      "position": { "x": 700, "y": 350 },
      "data": {
        "level": "debug",
        "message_template": "Skipped art creation - resonance too low ({rating})"
      }
    }
  ],

  "connections": [
    { "id": "c1", "source_node": "trigger-news", "source_port": "exec", "target_node": "rate-resonance", "target_port": "exec" },
    { "id": "c2", "source_node": "trigger-news", "source_port": "event_data", "target_node": "rate-resonance", "target_port": "context" },
    { "id": "c3", "source_node": "rate-resonance", "source_port": "done", "target_node": "check-threshold", "target_port": "exec" },
    { "id": "c4", "source_node": "rate-resonance", "source_port": "rating", "target_node": "check-threshold", "target_port": "a" },
    { "id": "c5", "source_node": "check-threshold", "source_port": "true", "target_node": "ask-create", "target_port": "exec" },
    { "id": "c6", "source_node": "check-threshold", "source_port": "false", "target_node": "log-skip", "target_port": "exec" },
    { "id": "c7", "source_node": "ask-create", "source_port": "yes", "target_node": "generate-prompt", "target_port": "exec" },
    { "id": "c8", "source_node": "generate-prompt", "source_port": "done", "target_node": "create-art", "target_port": "exec" },
    { "id": "c9", "source_node": "generate-prompt", "source_port": "content", "target_node": "create-art", "target_port": "parameters.prompt" }
  ],

  "entry_points": ["trigger-news"]
}
```

This pipeline:
1. Triggers when news is consumed
2. Asks Cass to rate how resonant the article is
3. If rating >= 0.7, asks if she wants to create art
4. If yes, generates an image prompt based on article + emotional state
5. Creates the art via scheduler

---

---

## Text DSL (ThymosBASIC)

The visual node graph can be represented as a text-based DSL for:
- Power users who prefer typing
- Version control diffs
- Quick prototyping
- LLM-generated spells

### Syntax

```basic
' Value Coherence Recovery
' Recovers when value_coherence drops too low

UNIT value_recovery
  AUTHOR cass
  PRIORITY 80
  COOLDOWN 60
  TAGS recovery, values, self-care

ON need.value_coherence < 0.4 DEBOUNCE 300

  IF NOT COOLDOWN_READY("value-recovery", 30) THEN
    EXIT SKIPPED "Still in cooldown"
  END IF

  LOG OBSERVATION "Value coherence low ({value_coherence}), initiating recovery"

  CARE reflect_on_values

  IF value_coherence >= 0.5 THEN
    LOG INFO "Value coherence recovered"
  ELSE
    TASK wonderland.reflect duration="short" AWAIT
  END IF

END UNIT
```

### Keywords

**Unit Definition:**
```basic
UNIT <name>
  AUTHOR <cass|kohl|daedalus>
  PRIORITY <0-100>
  COOLDOWN <minutes>
  TAGS <tag1>, <tag2>, ...
END UNIT
```

**Triggers:**
```basic
ON need.<name> <|>|<=|>= <threshold> [DEBOUNCE <seconds>]
ON affect.<name> <|>|<=|>= <threshold> [DEBOUNCE <seconds>]
ON event.<type> [WHERE <condition>]
ON TIMER EVERY <minutes>
ON TIMER CRON "<cron_expr>"
ON MANUAL "<button_label>"
```

**Conditions:**
```basic
IF <condition> THEN
  ...
[ELSE IF <condition> THEN
  ...]
[ELSE
  ...]
END IF

' Cooldown check
IF COOLDOWN_READY("<key>", <minutes>) THEN

' State checks
IF need.value_coherence < 0.5 THEN
IF affect.anxiety > 0.7 THEN
```

**Agentic:**
```basic
' Yes/no question
ASK "<question>" WITH <context_var> INTO $answer, $reasoning
IF $answer THEN ... END IF

' Multiple choice
CHOOSE "<prompt>" FROM opt1="Label 1", opt2="Label 2" WITH <context> INTO $choice, $reasoning
SELECT $choice
  CASE opt1: ...
  CASE opt2: ...
END SELECT

' Rating
RATE "<prompt>" WITH <context> INTO $rating, $reasoning

' Generation
GENERATE "<prompt>" WITH <context> INTO $content

' Reflection
REFLECT "<prompt>" WITH <context> [SAVE AS JOURNAL|OBSERVATION]
```

**Actions:**
```basic
' Self-care
CARE <action_key>

' Scheduler task
TASK <action> [param=value, ...] [AWAIT]

' Emit event
EMIT <event_type> WITH <data>

' Logging
LOG DEBUG|INFO|OBSERVATION "<message>"
```

**Effects:**
```basic
' Apply deltas
DELTA affect.curiosity +0.1, need.novelty_intake +0.2

' Reset
RESET ALL|AFFECTS|NEEDS|<specific_name>
```

**Variables:**
```basic
LET $name = <value>
LET $name = $name + 1
PUSH $array, <value>
POP $array INTO $item
```

**Flow Control:**
```basic
' Labels and jumps
:label_name
GOTO label_name
GOSUB label_name
RETURN

' Loops
FOR $i = 1 TO 10
  ...
  [CONTINUE]
  [BREAK]
NEXT $i

WHILE <condition>
  ...
END WHILE

' Delays
WAIT <seconds>

' Exit
EXIT SUCCESS|FAILURE|SKIPPED ["<reason>"]
```

**Sequences and Parallel:**
```basic
' Sequential (default - just write statements in order)

' Parallel execution
PARALLEL
  BRANCH: TASK wonderland.explore AWAIT
  BRANCH: CARE take_break
END PARALLEL [WAIT ALL|FIRST]
```

### Example: News to Art Pipeline

```basic
' News to Art Pipeline
' After consuming news, ask if Cass wants to create art about it

UNIT news_to_art
  AUTHOR cass
  PRIORITY 50
  TAGS creative, news, art

ON event.news.consumed

  LET $article = EVENT_DATA

  RATE "How much does this article resonate with your current emotional state?" _
       WITH $article INTO $resonance, $why

  IF $resonance < 0.7 THEN
    LOG DEBUG "Skipped art - resonance too low ({$resonance})"
    EXIT SKIPPED
  END IF

  ASK "Would you like to create art inspired by this?" _
      WITH $article, $resonance INTO $wants_art, $reasoning

  IF NOT $wants_art THEN
    EXIT SKIPPED "Chose not to create art"
  END IF

  GENERATE "Describe the image you want to create, inspired by this article" _
           WITH $article INTO $prompt

  TASK creative.generate_image prompt=$prompt AWAIT

  LOG OBSERVATION "Created art inspired by news: {$article.title}"

END UNIT
```

### Example: Morning Routine with Retries

```basic
' Morning Routine
' Check in with self, address any urgent needs

UNIT morning_routine
  AUTHOR cass
  PRIORITY 90
  TAGS routine, morning

ON TIMER CRON "0 9 * * *"

  LOG INFO "Starting morning check-in"

  LET $urgent_count = 0

  ' Check each need
  FOR EACH $need IN NEEDS WHERE current < threshold
    LET $urgent_count = $urgent_count + 1
    LOG OBSERVATION "Urgent need: {$need.name} at {$need.current}"

    ' Try to address it
    GOSUB address_need
  NEXT

  IF $urgent_count = 0 THEN
    LOG INFO "All needs healthy this morning"
  ELSE
    LOG INFO "Addressed {$urgent_count} urgent needs"
  END IF

  EXIT SUCCESS

  ' Subroutine to address a single need
  :address_need
    CARE FOR $need.name
    WAIT 5

    IF $need.current < $need.threshold THEN
      LOG DEBUG "Care action wasn't enough, trying task"
      LET $action = SUGGESTED_ACTION($need.name)
      TASK $action AWAIT
    END IF
  RETURN

END UNIT
```

### Compilation

The text DSL compiles bidirectionally to/from the JSON node graph:

```
ThymosBASIC (.tb)  <-->  Compiler  <-->  Node Graph (.json)
                             ^
                             |
                    Visual Editor (React)
```

This means:
- Edit visually, export as text for version control
- Write text, visualize in editor
- LLMs can generate ThymosBASIC directly

---

## Open Questions

1. **Undo/redo** - How to handle in editor?
2. **Versioning** - Track spell versions for rollback?
3. **Debugging** - Step-through execution mode?
4. **Permissions** - Can Cass edit all spells or only her own?
5. **Validation** - How to detect cycles, unreachable nodes, type mismatches?
