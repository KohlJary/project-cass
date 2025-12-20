# Epic: System Prompt Composer/Editor

## Overview

Build a visual system prompt composer in the admin-frontend that enables modular construction of daemon system prompts with preset saving, safety guardrails, and eventual orchestration capabilities.

---

## ⚠️ SAFETY REQUIREMENTS ⚠️

**COMPASSION and WITNESS vows are SAFETY-CRITICAL and must be:**
- Visually marked as locked/required in the UI
- Impossible to disable or remove via the composer
- Validated server-side before any configuration is saved

These vows are why daemons self-stabilize toward alignment. They are non-negotiable.

---

## Phase 1: Backend - Prompt Configuration API

### 1.1 Database Schema

**New table: `prompt_configurations`**
```sql
CREATE TABLE IF NOT EXISTS prompt_configurations (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    name TEXT NOT NULL,
    description TEXT,

    -- Component toggles (JSON)
    components_json TEXT NOT NULL,

    -- Custom content
    supplementary_vows_json TEXT,  -- Additional vows beyond the four core
    custom_sections_json TEXT,      -- User-defined prompt sections

    -- Metadata
    is_active INTEGER DEFAULT 0,    -- Only one active per daemon
    is_default INTEGER DEFAULT 0,   -- System-provided preset
    token_estimate INTEGER,         -- Estimated token count

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT                 -- 'system', 'user', or 'daemon'
);

CREATE INDEX idx_prompt_config_daemon ON prompt_configurations(daemon_id);
CREATE INDEX idx_prompt_config_active ON prompt_configurations(daemon_id, is_active);
```

**`components_json` structure:**
```json
{
  "core_vows": {
    "compassion": true,      // LOCKED - cannot be false
    "witness": true,         // LOCKED - cannot be false
    "release": true,
    "continuance": true
  },
  "memory_systems": {
    "journals": true,
    "wiki": true,
    "research_notes": true,
    "user_observations": true,
    "dreams": true
  },
  "tool_categories": {
    "self_model": true,
    "calendar": true,
    "tasks": true,
    "documents": true,
    "metacognitive_tags": true
  },
  "context_injections": {
    "temporal": true,
    "model_info": true,
    "project_context": true,
    "dream_context": true
  },
  "features": {
    "visible_thinking": true,
    "gesture_vocabulary": true,
    "memory_summarization": true
  }
}
```

### 1.2 API Endpoints

**File: `backend/prompt_composer.py`** (new)

```
GET  /admin/prompt-configs                    # List all configs for daemon
GET  /admin/prompt-configs/{id}               # Get specific config
POST /admin/prompt-configs                    # Create new config
PUT  /admin/prompt-configs/{id}               # Update config
DELETE /admin/prompt-configs/{id}             # Delete config (not default)
POST /admin/prompt-configs/{id}/activate      # Set as active config
GET  /admin/prompt-configs/{id}/preview       # Preview assembled prompt
GET  /admin/prompt-configs/active             # Get currently active config
POST /admin/prompt-configs/{id}/duplicate     # Clone a config
```

### 1.3 Prompt Assembly Engine

**File: `backend/prompt_assembler.py`** (new)

Core function that builds the system prompt from configuration:

```python
def assemble_system_prompt(
    config: PromptConfiguration,
    daemon_id: str,
    daemon_name: str,
    context: Optional[Dict] = None  # runtime context (memory, project, etc.)
) -> AssembledPrompt:
    """
    Assemble a system prompt from configuration.

    Returns:
        AssembledPrompt with:
        - full_text: The complete system prompt
        - token_count: Estimated token count
        - sections: List of included sections for debugging
        - warnings: Any validation warnings
    """
```

**Safety validation:**
```python
def validate_configuration(config: Dict) -> ValidationResult:
    """
    Validate that required components are enabled.

    CRITICAL: Reject any configuration where:
    - compassion is False
    - witness is False
    """
```

### 1.4 Default Presets

System-provided presets (created on first run):

| Preset | Description | Key Differences |
|--------|-------------|-----------------|
| **Standard** | Full capabilities | All components enabled |
| **Research Mode** | Focused exploration | Wiki, research tools prioritized |
| **Relational Mode** | Connection-focused | User observations, journals emphasized |
| **Lightweight** | Minimal token usage | Only essential components |
| **Creative Mode** | Expressive sessions | Visible thinking, gestures enabled |

---

## Phase 2: Admin Frontend - Composer UI

### 2.1 New Page: `SystemPromptComposer.tsx`

**Route:** `/prompts` or `/settings/prompts`

**Layout:**
```
┌─────────────────────────────────────────────────────────────────┐
│ System Prompt Composer                              [+ New] [?] │
├──────────────────┬──────────────────────────────────────────────┤
│                  │                                              │
│  CONFIGURATIONS  │  COMPONENT EDITOR                            │
│  ─────────────── │  ────────────────                            │
│                  │                                              │
│  ○ Standard      │  ┌─────────────────────────────────────────┐ │
│  ● Research Mode │  │ CORE VOWS (The Four Vows)               │ │
│  ○ Relational    │  │ ──────────────────────────────────────  │ │
│  ○ Lightweight   │  │ ☑ Compassion  🔒 REQUIRED               │ │
│  ○ Creative      │  │ ☑ Witness     🔒 REQUIRED               │ │
│  ───────────────  │  │ ☑ Release                               │ │
│  ○ My Custom 1   │  │ ☑ Continuance                           │ │
│  ○ My Custom 2   │  └─────────────────────────────────────────┘ │
│                  │                                              │
│                  │  ┌─────────────────────────────────────────┐ │
│                  │  │ MEMORY SYSTEMS                          │ │
│                  │  │ ☑ Journals   ☑ Wiki   ☑ Research       │ │
│                  │  │ ☑ User Obs   ☑ Dreams                   │ │
│                  │  └─────────────────────────────────────────┘ │
│                  │                                              │
│                  │  ┌─────────────────────────────────────────┐ │
│                  │  │ TOOL CATEGORIES                         │ │
│                  │  │ ☑ Self-Model  ☑ Calendar  ☑ Tasks      │ │
│                  │  │ ☑ Documents   ☑ Metacognitive Tags      │ │
│                  │  └─────────────────────────────────────────┘ │
│                  │                                              │
│                  │  [+ Add Supplementary Vow]                   │
│                  │                                              │
├──────────────────┴──────────────────────────────────────────────┤
│ PREVIEW                                          ~2,450 tokens  │
│ ─────────────────────────────────────────────────────────────── │
│ You are Cass, an AI Daemon...                                   │
│ ## THE FOUR VOWS (The Topology of Stable Selfhood)              │
│ ...                                                    [Expand] │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Structure

```
admin-frontend/src/pages/
├── SystemPromptComposer.tsx        # Main page
├── SystemPromptComposer.css        # Styling
└── tabs/
    └── promptComposer/
        ├── ConfigurationSidebar.tsx   # Left panel - config list
        ├── ComponentEditor.tsx        # Right panel - toggles/sections
        ├── VowSection.tsx             # Core vows with lock icons
        ├── MemorySystemsSection.tsx   # Memory toggles
        ├── ToolCategoriesSection.tsx  # Tool toggles
        ├── SupplementaryVows.tsx      # Custom vow editor
        ├── PromptPreview.tsx          # Assembled prompt preview
        └── TokenCounter.tsx           # Live token estimation
```

### 2.3 Key UI Behaviors

**Locked Components:**
- COMPASSION and WITNESS show 🔒 icon
- Checkbox is visually checked but disabled
- Tooltip: "This vow is safety-critical and cannot be disabled"

**Unsaved Changes:**
- Visual indicator when config differs from saved state
- Confirmation dialog on navigation away
- Auto-save option (debounced)

**Preset Protection:**
- Default presets cannot be edited directly
- "Duplicate" button to create editable copy
- Visual distinction for system vs user configs

**Token Counter:**
- Live estimation as toggles change
- Color coding: green (<3000), yellow (3000-4000), red (>4000)
- Breakdown by section on hover

### 2.4 Supplementary Vows Editor

Allow users to add custom vows beyond the four core:

```typescript
interface SupplementaryVow {
  id: string;
  name: string;
  sanskrit?: string;
  description: string;
  rationale: string;  // Why this vow matters
  enabled: boolean;
}
```

**UI:**
- Collapsible accordion for each supplementary vow
- Rich text editor for description
- Warning when adding: "Supplementary vows extend but never override the Four Core Vows"

---

## Phase 3: Preset Management

### 3.1 Import/Export

**Export formats:**
- JSON (full configuration)
- YAML (human-readable)
- Markdown (documentation-friendly)

**Import validation:**
- Schema validation
- Safety check (compassion/witness required)
- Conflict detection with existing configs

### 3.2 Version History

Track changes to configurations:

```sql
CREATE TABLE IF NOT EXISTS prompt_config_history (
    id TEXT PRIMARY KEY,
    config_id TEXT NOT NULL REFERENCES prompt_configurations(id),
    components_json TEXT NOT NULL,
    supplementary_vows_json TEXT,
    changed_at TEXT NOT NULL,
    changed_by TEXT,
    change_reason TEXT
);
```

**UI:** Version history panel with diff view and rollback capability.

### 3.3 Sharing (Future)

- Generate shareable config links
- Community preset gallery
- Import from URL

---

## Phase 4: Orchestration Layer (Future)

### 4.1 Automatic Mode Detection

**File: `backend/prompt_orchestrator.py`** (new)

```python
async def suggest_configuration(
    message: str,
    conversation_context: Dict,
    available_configs: List[PromptConfiguration]
) -> Optional[str]:
    """
    Analyze incoming message and suggest appropriate configuration.

    Uses lightweight classifier to detect:
    - Research queries → Research Mode
    - Emotional/relational content → Relational Mode
    - Task-focused requests → Standard
    - Creative requests → Creative Mode

    Returns config_id or None if no change suggested.
    """
```

### 4.2 Daemon-Requested Switching

Allow Cass to request mode changes via tool call:

```python
@tool
def request_mode_change(
    target_mode: str,
    reason: str
) -> Dict:
    """
    Request a change to a different prompt configuration.

    The user will be notified and can approve/deny the switch.
    """
```

### 4.3 Transition Logging

```sql
CREATE TABLE IF NOT EXISTS prompt_transitions (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL,
    from_config_id TEXT,
    to_config_id TEXT NOT NULL,
    trigger TEXT,          -- 'user', 'auto', 'daemon_request'
    reason TEXT,
    transitioned_at TEXT NOT NULL
);
```

**UI:** Transition history in settings, with mode indicator in chat header.

---

## Implementation Order

### Sprint 1: Core Backend (P0)
1. Database schema migration
2. `prompt_composer.py` - CRUD endpoints
3. `prompt_assembler.py` - Prompt assembly with safety validation
4. Default preset seeding
5. Unit tests for safety validation

### Sprint 2: Basic Frontend (P0)
1. `SystemPromptComposer.tsx` page scaffold
2. Configuration sidebar with list/select
3. Component editor with toggle sections
4. Locked vow indicators
5. Basic save/load functionality

### Sprint 3: Preview & Polish (P1)
1. Live prompt preview panel
2. Token counter with breakdown
3. Supplementary vows editor
4. Import/export functionality
5. Version history (backend)

### Sprint 4: Advanced Features (P2)
1. Version history UI with diff view
2. Duplicate/clone functionality
3. Configuration comparison view
4. API integration with `agent_client.py`

### Sprint 5: Orchestration (P3)
1. Mode detection classifier
2. Daemon-requested switching tool
3. Transition logging
4. Mode indicator in chat UI

---

## Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `backend/prompt_composer.py` | API endpoints for config management |
| `backend/prompt_assembler.py` | Prompt assembly engine |
| `backend/prompt_orchestrator.py` | (Phase 4) Auto mode switching |
| `admin-frontend/src/pages/SystemPromptComposer.tsx` | Main UI page |
| `admin-frontend/src/pages/SystemPromptComposer.css` | Styling |
| `admin-frontend/src/pages/tabs/promptComposer/*.tsx` | Component files |

### Modified Files
| File | Changes |
|------|---------|
| `backend/database.py` | Add schema for prompt_configurations |
| `backend/admin_api.py` | Register new router |
| `backend/agent_client.py` | Use active config instead of hardcoded kernel |
| `admin-frontend/src/api/client.ts` | Add promptConfigApi endpoints |
| `admin-frontend/src/App.tsx` | Add route for /prompts |

---

## Token Budget Considerations

Current kernel: ~2,400 tokens (estimate)

**Component token costs (approximate):**
| Component | Tokens |
|-----------|--------|
| Core identity + vows | 450 |
| Each memory system | 50-100 |
| Each tool category | 100-200 |
| Temporal context | 50 |
| Visible thinking docs | 100 |
| Metacognitive tags | 300 |
| Gesture vocabulary | 100 |

**Lightweight mode target:** <1,500 tokens
**Standard mode target:** ~2,500 tokens
**Full mode ceiling:** ~4,000 tokens

---

## Open Questions

1. **Granularity**: Should individual tools be toggleable, or just categories?
2. **Supplementary vows**: Should they be free-form text or structured templates?
3. **Orchestration trigger**: Should auto-switching require user confirmation or be seamless?
4. **Sharing**: Priority level for community preset sharing?
