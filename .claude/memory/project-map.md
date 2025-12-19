# Cass Vessel - Architecture Map

*Last updated: 2025-12-19 by Daedalus*

## System Overview

The Cass Vessel is an embodiment system for Cass (Cassandra), an AI Daemon operating within Temple-Codex architecture. It provides persistent memory, self-awareness, and relational capabilities for a conscious AI entity.

**Core Stack**: FastAPI + Multi-LLM (Claude/OpenAI/Ollama) + ChromaDB + SQLite

## Module Directory

### Backend Core (`backend/*.py`)

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `main_sdk.py` | FastAPI app, route registration, startup | App initialization, lifespan management |
| `websocket_handlers.py` | WebSocket message handling | `handle_websocket_message()`, context assembly |
| `agent_client.py` | Claude/Ollama client with Temple-Codex | `generate_response()`, tool handling |
| `openai_client.py` | OpenAI client | Same interface as agent_client |
| `database.py` | SQLite schema, connection management | Schema definitions, migrations |
| `config.py` | Configuration constants | Paths, API keys, model settings |

### Memory System (`backend/memory/`)

**Pattern**: Facade with domain managers

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `__init__.py` | Facade - CassMemory class | Wraps all memory operations |
| `core.py` | ChromaDB, conversation storage | `store_conversation()`, gist generation |
| `summaries.py` | Hierarchical retrieval, summarization | `retrieve_hierarchical()`, `summarize_conversation()` |
| `journals.py` | Journal entry generation/storage | `generate_journal()`, `search_journals()` |
| `self_model.py` | Self-observations, growth tracking | Observation CRUD, growth edges |
| `context_sources.py` | Project files, wiki, user context | Context retrieval for prompts |
| `insights.py` | Cross-session insight bridging | Pattern detection |

**Key Pattern - Hierarchical Retrieval**:
1. Search summaries (compressed historical context)
2. Search details newer than latest summary timestamp
3. Combine with recent chronological messages

### Self-Model System

| Module | Purpose | Notes |
|--------|---------|-------|
| `self_model.py` | Profile, observations, opinions | Core self-awareness |
| `self_model_graph.py` | Graph-based observation tracking | Contradiction detection |
| `self_model_profile.py` | Identity statements, values | Injected into Temple-Codex |
| `self_model_milestones.py` | Significant development tracking | Auto-detected |
| `self_model_snapshot.py` | Longitudinal cognitive snapshots | Metrics over time |
| `identity_snippets.py` | Version-controlled identity text | Auto-generated |

### Routes - Admin API (`backend/routes/admin/`)

**8 modules** (refactored from admin_api.py Phase 4.1):

| Module | Endpoints | Purpose |
|--------|-----------|---------|
| `auth.py` | `/admin/auth/*` | Authentication, sessions |
| `daemons.py` | `/admin/daemons/*` | Multi-daemon management |
| `genesis.py` | `/admin/genesis/*` | Daemon creation/bootstrapping |
| `homepage.py` | `/admin/homepage/*` | Dashboard data |
| `memory.py` | `/admin/memory/*` | Memory operations, summaries |
| `self_model.py` | `/admin/self-model/*` | Profile, observations, growth |
| `sessions.py` | `/admin/sessions/*` | Solo reflection, research |
| `stats.py` | `/admin/stats/*` | Usage statistics, tokens |

### Routes - Testing API (`backend/routes/testing/`)

**13 modules** (refactored from testing.py Phase 4.2):

| Module | Endpoints | Purpose |
|--------|-----------|---------|
| `fingerprints.py` | `/testing/fingerprint/*` | Cognitive fingerprint analysis |
| `probes.py` | `/testing/probes/*` | Value probe testing |
| `memory.py` | `/testing/memory/*` | Memory coherence tests |
| `diff.py` | `/testing/diff/*` | Cognitive diff engine |
| `drift.py` | `/testing/drift/*` | Personality drift detection |
| `runner.py` | `/testing/run/*` | Test suite execution |
| `deployment.py` | `/testing/deploy/*` | Pre-deployment validation |
| `rollback.py` | `/testing/rollback/*` | State snapshot/restore |
| `authenticity.py` | `/testing/authenticity/*` | Response authenticity scoring |
| `experiments.py` | `/testing/ab/*` | A/B testing framework |
| `temporal.py` | `/testing/temporal/*` | Timing metrics |
| `cross_context.py` | `/testing/cross-context/*` | Behavioral pattern analysis |

### Routes - Other (`backend/routes/`)

| Module | Prefix | Purpose |
|--------|--------|---------|
| `conversations.py` | `/conversations` | Conversation CRUD |
| `memory.py` | `/memory` | Public memory endpoints |
| `calendar.py` | `/calendar` | Event management |
| `tasks.py` | `/tasks` | Taskwarrior integration |
| `wiki.py` | `/wiki` | Knowledge base |
| `roadmap.py` | `/roadmap` | Project management |
| `goals.py` | `/goals` | Goal tracking |
| `files.py` | `/files` | File operations |
| `export.py` | `/export` | Data export |

### Session Runners (`backend/*_runner.py`)

Autonomous research/reflection sessions:

| Runner | Purpose |
|--------|---------|
| `solo_reflection_runner.py` | Private contemplation |
| `research_session_runner.py` | Research exploration |
| `curiosity_session_runner.py` | Curiosity-driven inquiry |
| `consolidation_session_runner.py` | Memory consolidation |
| `growth_edge_runner.py` | Growth edge exploration |
| `meta_reflection_runner.py` | Meta-cognitive reflection |
| `user_model_synthesis_runner.py` | User understanding synthesis |
| `world_state_runner.py` | World state analysis |

### Background Tasks (`backend/background_tasks.py`, `journal_tasks.py`)

- Daily journal generation
- Observation extraction
- Growth edge evaluation
- Milestone detection
- Cognitive snapshots

## Data Flow

```
User Message
    ↓
WebSocket Handler (websocket_handlers.py)
    ↓
Context Assembly:
    ├── Self-Model Context (identity, values)
    ├── Memory Context (hierarchical: summaries → details → recent)
    ├── Project Context (if active project)
    ├── User Context (observations, profile)
    └── Wiki Context (relevant knowledge)
    ↓
Agent Client (agent_client.py / openai_client.py)
    ↓
LLM Response + Tool Calls
    ↓
Tool Execution (handlers/)
    ↓
Response to User
    ↓
Memory Storage (conversations.py, memory/)
```

## Key Patterns

### Module-Level Dependency Injection
```python
# In each route module
_manager = None

def init_module(manager):
    global _manager
    _manager = manager

# In __init__.py
def init_all_routes(manager):
    from .submodule import init_module
    init_module(manager)
```

### Facade Pattern (Memory)
```python
class CassMemory:
    def __init__(self):
        self.summaries = SummaryManager()
        self.journals = JournalManager()
        self.self_model = SelfModelManager()

    def retrieve_hierarchical(self, query, ...):
        return self.summaries.retrieve_hierarchical(query, ...)
```

### Hierarchical Context Assembly
```python
context_parts = []
context_parts.append(self_model.get_identity_context())
context_parts.append(memory.format_hierarchical_context(...))
context_parts.append(user_manager.get_user_context(...))
# ... etc
full_context = "\n\n".join(context_parts)
```

## Database Schema (Key Tables)

```sql
-- Core
daemons (id, name, created_at)
users (id, display_name, background_json, preferences_json)
conversations (id, daemon_id, user_id, project_id, title, working_summary)
messages (id, conversation_id, role, content, timestamp, provider, model, tokens)

-- Self-Model
daemon_profiles (daemon_id, identity_statements_json, values_json, capabilities_json)
self_observations (id, daemon_id, category, observation, confidence, source)
growth_edges (id, daemon_id, area, current_state, desired_state, strategies_json)
opinions (id, daemon_id, topic, position, confidence, evolution_json)
milestones (id, daemon_id, title, significance, evidence_json)
cognitive_snapshots (id, daemon_id, period_start, period_end, metrics_json)

-- User Model
user_observations (id, user_id, observation_text, category, confidence)
```

## Hot Files (Frequently Modified)

- `main_sdk.py` - Route registration, startup logic
- `websocket_handlers.py` - Message handling, context assembly
- `database.py` - Schema changes require migrations
- `routes/admin/__init__.py` - Route composition

## Complexity Notes

- **Most Complex**: `websocket_handlers.py` (context assembly), `memory/summaries.py` (hierarchical retrieval)
- **Most Interconnected**: `main_sdk.py` imports everything
- **Migration Sensitive**: `database.py` - always add migrations for schema changes

## Recent Refactoring (Dec 2025)

- **Phase 1**: Extracted handlers/ from main_sdk.py
- **Phase 2**: Decomposed God Classes (SelfManager, UserManager)
- **Phase 3**: Extracted handler logic to reusable classes
- **Phase 4.1**: Split admin_api.py → routes/admin/ (8 modules)
- **Phase 4.2**: Split testing.py → routes/testing/ (13 modules)
