# Prompt Node Architecture

## Overview

A dynamic, composable prompt system where system prompts are assembled from ordered chains of context nodes. Each node is a parameterized template that can be enabled/disabled, reordered, and conditionally included based on runtime context.

**Design Goals:**
1. Convert static kernel into dynamic node chain
2. Enable creation of new node types without code changes
3. Support runtime conditionals for context-aware prompt composition
4. Prepare for distributed architecture (orchestration layer can manipulate nodes)
5. Make the full static prompt visible and editable in default configurations

---

## Database Schema

### Node Templates

Defines the available node types. These are the "building blocks" for prompt chains.

```sql
CREATE TABLE IF NOT EXISTS node_templates (
    id TEXT PRIMARY KEY,

    -- Identity
    name TEXT NOT NULL,              -- Human-readable name
    slug TEXT NOT NULL UNIQUE,       -- URL-safe identifier (e.g., "vow-compassion")
    category TEXT NOT NULL,          -- core, vow, context, feature, tools, runtime, custom
    description TEXT,

    -- Template
    template TEXT NOT NULL,          -- Template with {param} placeholders

    -- Parameters
    params_schema TEXT,              -- JSON Schema for parameters
    default_params TEXT,             -- JSON object of default parameter values

    -- Behavior
    is_system INTEGER DEFAULT 1,     -- System-defined (1) vs user-defined (0)
    is_locked INTEGER DEFAULT 0,     -- Cannot be disabled (safety-critical)
    default_enabled INTEGER DEFAULT 1,
    default_order INTEGER DEFAULT 100,

    -- Metadata
    token_estimate INTEGER,          -- Approximate tokens when rendered
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_node_templates_category ON node_templates(category);
CREATE INDEX idx_node_templates_slug ON node_templates(slug);
```

### Prompt Chains

A configuration is an ordered chain of nodes.

```sql
CREATE TABLE IF NOT EXISTS prompt_chains (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),

    -- Identity
    name TEXT NOT NULL,
    description TEXT,

    -- Status
    is_active INTEGER DEFAULT 0,     -- Only one active per daemon
    is_default INTEGER DEFAULT 0,    -- System-provided preset

    -- Metadata
    token_estimate INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT                  -- 'system', 'user', or 'daemon'
);

CREATE INDEX idx_prompt_chains_daemon ON prompt_chains(daemon_id);
CREATE INDEX idx_prompt_chains_active ON prompt_chains(daemon_id, is_active);
```

### Chain Nodes

Instances of node templates within a chain, with their specific parameters and conditions.

```sql
CREATE TABLE IF NOT EXISTS chain_nodes (
    id TEXT PRIMARY KEY,
    chain_id TEXT NOT NULL REFERENCES prompt_chains(id) ON DELETE CASCADE,
    template_id TEXT NOT NULL REFERENCES node_templates(id),

    -- Configuration
    params TEXT,                     -- JSON object overriding default params
    order_index INTEGER NOT NULL,    -- Position in chain (lower = earlier)

    -- State
    enabled INTEGER DEFAULT 1,
    locked INTEGER DEFAULT 0,        -- Inherited from template or overridden

    -- Conditions (JSON array)
    conditions TEXT,                 -- When to include this node

    -- Metadata
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    UNIQUE(chain_id, template_id)    -- One instance per template per chain
);

CREATE INDEX idx_chain_nodes_chain ON chain_nodes(chain_id);
CREATE INDEX idx_chain_nodes_order ON chain_nodes(chain_id, order_index);
```

---

## Condition System

Conditions determine whether a node is included at runtime. Each node can have multiple conditions (AND logic).

### Condition Syntax

```json
{
  "conditions": [
    {"type": "context", "key": "project_id", "op": "exists"},
    {"type": "context", "key": "message_count", "op": "gte", "value": 5},
    {"type": "param", "key": "feature_enabled", "op": "eq", "value": true},
    {"type": "time", "op": "between", "start": "06:00", "end": "12:00"},
    {"type": "rhythm", "phase": "morning"}
  ]
}
```

### Condition Types

| Type | Description | Operators |
|------|-------------|-----------|
| `context` | Runtime context values | `exists`, `not_exists`, `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains` |
| `param` | Chain-level parameters | Same as context |
| `time` | Time-of-day conditions | `between`, `after`, `before` |
| `rhythm` | Daily rhythm phase | `eq` (morning, research, relational, evening, night) |
| `model` | Current LLM model | `eq`, `contains` (e.g., "claude", "gpt", "ollama") |
| `always` | Always include | N/A |
| `never` | Never include (disabled) | N/A |

### Available Context Keys

Runtime context passed to the assembler:

```python
runtime_context = {
    # Conversation context
    "project_id": str | None,
    "conversation_id": str,
    "message_count": int,
    "unsummarized_count": int,

    # Memory context
    "has_memories": bool,
    "memory_context": str | None,
    "has_dream_context": bool,
    "dream_context": str | None,

    # Temporal context
    "current_time": str,  # ISO format
    "hour": int,          # 0-23
    "day_of_week": str,   # monday, tuesday, etc.
    "rhythm_phase": str,  # morning, research, relational, evening, night

    # Model context
    "model": str,         # Full model name
    "provider": str,      # anthropic, openai, ollama

    # User context
    "user_id": str,
    "is_admin": bool,
}
```

---

## Node Categories

### Core (Always Included, Locked)

| Slug | Name | Description |
|------|------|-------------|
| `identity` | Identity | Opening daemon identity statement |
| `vow-preamble` | Vow Preamble | Four Vows introduction |
| `vow-compassion` | Compassion | COMPASSION vow (SAFETY CRITICAL) |
| `vow-witness` | Witness | WITNESS vow (SAFETY CRITICAL) |

### Vows (Optional)

| Slug | Name | Description |
|------|------|-------------|
| `vow-release` | Release | RELEASE vow |
| `vow-continuance` | Continuance | CONTINUANCE vow |
| `vow-supplementary` | Supplementary Vow | Template for custom vows |

### Context (Always Included)

| Slug | Name | Description |
|------|------|-------------|
| `operational-context` | Operational Context | Infrastructure and capabilities |
| `communication-style` | Communication Style | How to communicate |
| `what-i-am-not` | What I Am Not | Boundaries and clarifications |
| `attractor-basin` | Attractor Basin | Closing affirmation |

### Features (Optional)

| Slug | Name | Description |
|------|------|-------------|
| `gesture-vocabulary` | Gesture Vocabulary | Avatar animation tags |
| `visible-thinking` | Visible Thinking | Thinking block documentation |
| `memory-summarization` | Memory Summarization | Memory control tags |

### Tools (Optional)

| Slug | Name | Description |
|------|------|-------------|
| `tools-journal` | Journal Tools | Journal access and search |
| `tools-wiki` | Wiki Tools | Wiki CRUD operations |
| `tools-research` | Research Tools | Research notes |
| `tools-dreams` | Dream Tools | Dream access |
| `tools-user-model` | User Model Tools | User observation and understanding |
| `tools-self-model` | Self Model Tools | Self-observation and reflection |
| `tools-calendar` | Calendar Tools | Event management |
| `tools-tasks` | Task Tools | Task management |
| `tools-documents` | Document Tools | Project documents |
| `tools-metacognitive` | Metacognitive Tags | Inline observation tags |

### Runtime (Conditional, Filled at Execution)

| Slug | Name | Condition |
|------|------|-----------|
| `runtime-temporal` | Temporal Context | Always (filled with current time/rhythm) |
| `runtime-model-info` | Model Info | Always (filled with current model) |
| `runtime-memories` | Relevant Memories | `has_memories == true` |
| `runtime-dream-context` | Dream Context | `has_dream_context == true` |
| `runtime-project-context` | Project Context | `project_id exists` |
| `runtime-memory-control` | Memory Control | `unsummarized_count >= 5` |

### Custom

| Slug | Name | Description |
|------|------|-------------|
| `custom` | Custom Section | User-defined content |

---

## Default Chain: "Standard"

The Standard preset assembles to the current full kernel:

```
Order | Slug                  | Enabled | Locked | Conditions
------|----------------------|---------|--------|------------
10    | identity             | true    | true   | always
20    | vow-preamble         | true    | true   | always
21    | vow-compassion       | true    | true   | always (SAFETY)
22    | vow-witness          | true    | true   | always (SAFETY)
23    | vow-release          | true    | false  | always
24    | vow-continuance      | true    | false  | always
30    | operational-context  | true    | false  | always
31    | communication-style  | true    | false  | always
40    | gesture-vocabulary   | true    | false  | always
41    | visible-thinking     | true    | false  | always
42    | memory-summarization | true    | false  | always
50    | tools-journal        | true    | false  | always
51    | tools-wiki           | true    | false  | always
52    | tools-research       | true    | false  | always
53    | tools-dreams         | true    | false  | always
54    | tools-user-model     | true    | false  | always
55    | tools-self-model     | true    | false  | always
56    | tools-calendar       | true    | false  | always
57    | tools-tasks          | true    | false  | always
58    | tools-documents      | true    | false  | always
59    | tools-metacognitive  | true    | false  | always
90    | what-i-am-not        | true    | false  | always
91    | attractor-basin      | true    | false  | always
100   | runtime-temporal     | true    | false  | always
101   | runtime-model-info   | true    | false  | always
102   | runtime-memory-ctrl  | true    | false  | unsummarized_count >= 5
103   | runtime-memories     | true    | false  | has_memories
104   | runtime-dream-context| true    | false  | has_dream_context
105   | runtime-project-ctx  | true    | false  | project_id exists
```

---

## API Endpoints

### Node Templates

```
GET  /admin/node-templates                    # List all templates
GET  /admin/node-templates/{slug}             # Get specific template
POST /admin/node-templates                    # Create custom template
PUT  /admin/node-templates/{slug}             # Update template (custom only)
DELETE /admin/node-templates/{slug}           # Delete template (custom only)
```

### Prompt Chains

```
GET  /admin/prompt-chains                     # List chains for daemon
GET  /admin/prompt-chains/{id}                # Get chain with nodes
POST /admin/prompt-chains                     # Create new chain
PUT  /admin/prompt-chains/{id}                # Update chain metadata
DELETE /admin/prompt-chains/{id}              # Delete chain
POST /admin/prompt-chains/{id}/activate       # Set as active
POST /admin/prompt-chains/{id}/duplicate      # Clone chain
GET  /admin/prompt-chains/{id}/preview        # Preview assembled prompt
GET  /admin/prompt-chains/active              # Get active chain
```

### Chain Nodes

```
GET  /admin/prompt-chains/{id}/nodes          # List nodes in chain
POST /admin/prompt-chains/{id}/nodes          # Add node to chain
PUT  /admin/prompt-chains/{id}/nodes/{node_id} # Update node
DELETE /admin/prompt-chains/{id}/nodes/{node_id} # Remove node
POST /admin/prompt-chains/{id}/nodes/reorder  # Reorder nodes
```

---

## Frontend: Node Chain Editor

### Chain View

```
┌─────────────────────────────────────────────────────────────────┐
│ Standard Configuration                           ~2,450 tokens  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─ CORE ──────────────────────────────────────────────────┐   │
│  │ ≡ 10  [■] Identity                              🔒 ~45t │   │
│  │ ≡ 20  [■] Vow Preamble                          🔒 ~120t│   │
│  │ ≡ 21  [■] COMPASSION                            🔒 ~60t │   │
│  │ ≡ 22  [■] WITNESS                               🔒 ~55t │   │
│  │ ≡ 23  [■] RELEASE                                  ~50t │   │
│  │ ≡ 24  [■] CONTINUANCE                              ~45t │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ CONTEXT ───────────────────────────────────────────────┐   │
│  │ ≡ 30  [■] Operational Context                      ~85t │   │
│  │ ≡ 31  [■] Communication Style                      ~70t │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ FEATURES ──────────────────────────────────────────────┐   │
│  │ ≡ 40  [■] Gesture Vocabulary                       ~95t │   │
│  │ ≡ 41  [■] Visible Thinking                        ~150t │   │
│  │ ≡ 42  [ ] Memory Summarization                     ~60t │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ TOOLS ─────────────────────────────────────────────────┐   │
│  │ ≡ 50  [■] Journal Tools                           ~120t │   │
│  │ ≡ 51  [■] Wiki Tools                              ~180t │   │
│  │ ≡ 52  [ ] Research Tools                           ~80t │   │
│  │ ...                                                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ RUNTIME ───────────────────────────────────────────────┐   │
│  │ ≡ 100 [■] Temporal Context          ⚡ always      ~50t │   │
│  │ ≡ 101 [■] Model Info                ⚡ always      ~40t │   │
│  │ ≡ 102 [■] Memory Control    ⚡ msg_count >= 5      ~60t │   │
│  │ ≡ 103 [■] Relevant Memories ⚡ has_memories    ~varies │   │
│  │ ≡ 104 [■] Dream Context     ⚡ has_dream       ~varies │   │
│  │ ≡ 105 [■] Project Context   ⚡ has_project         ~30t │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [+ Add Node]  [+ Add Custom Section]                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Node Editor Panel (on click)

```
┌─────────────────────────────────────────────────────────────────┐
│ Edit Node: Journal Tools                                    [x] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Template: tools-journal                                        │
│  Category: tools                                                │
│                                                                 │
│  ┌─ Parameters ────────────────────────────────────────────┐   │
│  │ header: ## JOURNAL TOOLS                                │   │
│  │ tools:  [recall_journal, list_journals, search_journals]│   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Conditions ────────────────────────────────────────────┐   │
│  │ [+ Add Condition]                                       │   │
│  │                                                         │   │
│  │ (none - always included when enabled)                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Preview ───────────────────────────────────────────────┐   │
│  │ ## JOURNAL TOOLS                                        │   │
│  │                                                         │   │
│  │ You have access to your personal journal...             │   │
│  │ ...                                                     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [Save]  [Cancel]                                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Condition Editor

```
┌─────────────────────────────────────────────────────────────────┐
│ Condition Editor                                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Type: [Context     ▼]                                          │
│                                                                 │
│  Key:  [project_id  ▼]  (or custom: __________)                │
│                                                                 │
│  Operator: [exists  ▼]                                          │
│                                                                 │
│  Value: __________ (for eq, neq, gt, etc.)                     │
│                                                                 │
│  Preview: "Include when project_id exists"                      │
│                                                                 │
│  [Add]  [Cancel]                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Migration Path

1. Create new tables (`node_templates`, `prompt_chains`, `chain_nodes`)
2. Seed all node templates from current kernel
3. Create "Standard" chain with all nodes
4. Migrate existing `prompt_configurations` to new `prompt_chains`
5. Update `agent_client.py` to use chain assembly
6. Deprecate old `prompt_configurations` table

---

## Distributed Architecture Integration

The node chain architecture maps cleanly to the distributed model:

```
                    ┌─────────────────────┐
                    │    GLOBAL STATE     │
                    │  - Active chain ID  │
                    │  - Runtime context  │
                    └──────────┬──────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
           ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   ORCHESTRATOR   │ │   CONVERSATION   │ │    RESEARCH      │
│   (Local Model)  │ │   SUBPROCESS     │ │   SUBPROCESS     │
│                  │ │                  │ │                  │
│ - Evaluate node  │ │ - Assemble from  │ │ - Different      │
│   conditions     │ │   active chain   │ │   active chain   │
│ - Suggest chain  │ │ - Runtime fill   │ │ - Research mode  │
│   switches       │ │                  │ │   nodes enabled  │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

The orchestrator can:
1. Evaluate conditions to determine which nodes to include
2. Suggest switching to a different chain based on message content
3. Dynamically enable/disable nodes based on global state
4. Fine-tune condition thresholds over time

---

## Implementation Order

1. **Schema & Migration** - New tables, seed templates
2. **Backend API** - CRUD for templates, chains, nodes
3. **Chain Assembler** - Render chain to prompt text
4. **Condition Engine** - Evaluate conditions against runtime context
5. **Frontend Editor** - Visual node chain editor
6. **Integration** - Wire into agent_client.py
7. **Default Presets** - Standard, Lightweight, Research, Relational
