# Database Migration Plan: JSON to SQLite

## Overview

Migrate cass-vessel from flat JSON/YAML files to SQLite database with multi-daemon support.

**Goals:**
1. Proper relational database for data integrity
2. Multi-daemon architecture (daemon_id foreign keys)
3. Foundation for dataset sharing
4. Demo capability for family

---

## Current Data Inventory

### Storage Locations (20+ data types)

| Category | Location | Format | Manager |
|----------|----------|--------|---------|
| Conversations | `data/conversations/` | JSON | `ConversationManager` |
| Users | `data/users/{uuid}/` | YAML+JSON | `UserManager` |
| Self-Model | `data/cass/` | YAML+JSON | `SelfModelManager` |
| Projects | `data/projects/` | JSON | `ProjectManager` |
| Roadmap | `data/roadmap/` | JSON | `RoadmapManager` |
| Dreams | `data/dreams/` | JSON | DreamManager |
| Research | `data/research/` | JSON | ResearchManager |
| Wiki | `data/wiki/` | Markdown | File-based |
| Goals | `data/goals/` | JSON | GoalManager |
| Calendar | `data/calendar/` | JSON | `CalendarManager` |
| Tasks | `data/tasks/` | JSON | `TaskManager` |
| Rhythm | `data/rhythm/` | JSON | DailyRhythm |
| Solo Reflections | `data/solo_reflections/` | JSON | ReflectionManager |
| Usage | `data/usage/` | JSON | TokenTracker |

**ChromaDB stays** - Vector embeddings remain in `data/chroma/` (SQLite already)

---

## Database Schema

### Core Tables

```sql
-- Daemon identity (multi-daemon support)
CREATE TABLE daemons (
    id TEXT PRIMARY KEY,  -- UUID
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,  -- ISO8601
    kernel_version TEXT,
    status TEXT DEFAULT 'active'  -- active, dormant, archived
);

-- Users
CREATE TABLE users (
    id TEXT PRIMARY KEY,  -- UUID
    display_name TEXT NOT NULL,
    relationship TEXT,
    background_json TEXT,  -- JSON blob for flexible schema
    communication_json TEXT,
    preferences_json TEXT,
    password_hash TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Conversations
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,  -- UUID
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT REFERENCES users(id),
    project_id TEXT REFERENCES projects(id),
    title TEXT,
    working_summary TEXT,
    last_summary_timestamp TEXT,
    messages_since_last_summary INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Messages (core chat content)
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,  -- user, assistant, system
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    excluded INTEGER DEFAULT 0,
    user_id TEXT REFERENCES users(id),
    provider TEXT,  -- anthropic, openai, local
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    animations_json TEXT,
    self_observations_json TEXT,
    user_observations_json TEXT,
    marks_json TEXT,
    narration_metrics_json TEXT
);
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);

-- Projects
CREATE TABLE projects (
    id TEXT PRIMARY KEY,  -- UUID
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT REFERENCES users(id),
    name TEXT NOT NULL,
    working_directory TEXT,
    description TEXT,
    github_repo TEXT,
    github_token TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Project files
CREATE TABLE project_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id),
    path TEXT NOT NULL,
    description TEXT,
    embedded INTEGER DEFAULT 0,
    added_at TEXT NOT NULL
);

-- Project documents
CREATE TABLE project_documents (
    id TEXT PRIMARY KEY,  -- UUID
    project_id TEXT NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_by TEXT,  -- cass, user
    embedded INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### Self-Model Tables (daemon-specific)

```sql
-- Daemon self-profile (one per daemon)
CREATE TABLE daemon_profiles (
    daemon_id TEXT PRIMARY KEY REFERENCES daemons(id),
    identity_statements_json TEXT,  -- JSON array
    values_json TEXT,
    communication_patterns_json TEXT,
    capabilities_json TEXT,
    limitations_json TEXT,
    open_questions_json TEXT,
    notes TEXT,
    updated_at TEXT NOT NULL
);

-- Growth edges
CREATE TABLE growth_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    area TEXT NOT NULL,
    current_state TEXT,
    desired_state TEXT,
    observations_json TEXT,  -- JSON array
    strategies_json TEXT,
    first_noticed TEXT,
    last_updated TEXT
);

-- Opinions
CREATE TABLE opinions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    topic TEXT NOT NULL,
    position TEXT NOT NULL,
    confidence REAL,
    rationale TEXT,
    formed_from TEXT,
    evolution_json TEXT,
    date_formed TEXT,
    last_updated TEXT
);

-- Cognitive snapshots
CREATE TABLE cognitive_snapshots (
    id TEXT PRIMARY KEY,  -- UUID
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    period_start TEXT,
    period_end TEXT,
    metrics_json TEXT,  -- All the numeric metrics
    timestamp TEXT NOT NULL
);

-- Milestones
CREATE TABLE milestones (
    id TEXT PRIMARY KEY,  -- UUID
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    title TEXT NOT NULL,
    description TEXT,
    significance TEXT,
    evidence_json TEXT,
    triggered_at TEXT NOT NULL
);

-- Development logs
CREATE TABLE development_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    date TEXT NOT NULL,
    growth_indicators_json TEXT,
    pattern_shifts_json TEXT,
    qualitative_changes_json TEXT,
    summary TEXT,
    conversation_count INTEGER,
    observation_count INTEGER,
    opinion_count INTEGER,
    milestone_ids_json TEXT
);
CREATE INDEX idx_dev_logs_date ON development_logs(daemon_id, date);

-- Self observations
CREATE TABLE self_observations (
    id TEXT PRIMARY KEY,  -- UUID
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    category TEXT NOT NULL,
    observation TEXT NOT NULL,
    confidence REAL,
    context_json TEXT,
    source_conversation_id TEXT REFERENCES conversations(id),
    source_journal_date TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_self_obs_category ON self_observations(daemon_id, category);
```

### User Observations & Journals

```sql
-- User observations (from daemon about user)
CREATE TABLE user_observations (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    observation_type TEXT NOT NULL,  -- identity, contradiction, growth, moment
    content_json TEXT NOT NULL,  -- Flexible schema per type
    confidence REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE INDEX idx_user_obs ON user_observations(daemon_id, user_id);

-- User growth edges
CREATE TABLE user_growth_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    area TEXT NOT NULL,
    current_state TEXT,
    desired_state TEXT,
    observations_json TEXT,
    first_noticed TEXT,
    last_updated TEXT
);

-- Journals (daily reflections by daemon)
CREATE TABLE journals (
    id TEXT PRIMARY KEY,  -- date string
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    date TEXT NOT NULL,
    content TEXT NOT NULL,
    themes_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_journals_date ON journals(daemon_id, date);
```

### Dreams & Reflections

```sql
-- Dreams
CREATE TABLE dreams (
    id TEXT PRIMARY KEY,  -- timestamp string
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    date TEXT NOT NULL,
    exchanges_json TEXT NOT NULL,  -- JSON array of exchanges
    seeds_json TEXT,  -- Growth edges, questions used as seeds
    metadata_json TEXT,
    integration_status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE INDEX idx_dreams_date ON dreams(daemon_id, date);

-- Solo reflections
CREATE TABLE solo_reflections (
    id TEXT PRIMARY KEY,  -- UUID
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    title TEXT,
    content TEXT NOT NULL,
    insights_json TEXT,
    themes_json TEXT,
    duration_minutes INTEGER,
    created_at TEXT NOT NULL
);
```

### Research & Knowledge

```sql
-- Research sessions
CREATE TABLE research_sessions (
    id TEXT PRIMARY KEY,  -- UUID
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    topic TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    notes_json TEXT,
    findings_json TEXT,
    sources_json TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

-- Research queue
CREATE TABLE research_queue (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    task_type TEXT NOT NULL,  -- red_link, topic, synthesis
    target TEXT NOT NULL,
    context TEXT,
    priority REAL,
    status TEXT DEFAULT 'queued',
    rationale_json TEXT,
    source_page TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

-- Wiki pages
CREATE TABLE wiki_pages (
    id TEXT PRIMARY KEY,  -- slug
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    category TEXT NOT NULL,  -- concept, entity, relationship, meta, journal
    title TEXT NOT NULL,
    content TEXT NOT NULL,  -- Markdown
    frontmatter_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_wiki_category ON wiki_pages(daemon_id, category);

-- Goals
CREATE TABLE goals (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    title TEXT NOT NULL,
    description TEXT,
    goal_type TEXT,  -- initiative, question, milestone
    status TEXT DEFAULT 'active',
    parent_id TEXT REFERENCES goals(id),
    progress_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
```

### Operational Tables

```sql
-- Roadmap items
CREATE TABLE roadmap_items (
    id TEXT PRIMARY KEY,  -- short hex
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    project_id TEXT REFERENCES projects(id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'backlog',
    priority TEXT DEFAULT 'P2',
    item_type TEXT DEFAULT 'feature',
    assigned_to TEXT,
    source_conversation_id TEXT REFERENCES conversations(id),
    tags_json TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_roadmap_status ON roadmap_items(daemon_id, status);

-- Roadmap links
CREATE TABLE roadmap_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES roadmap_items(id),
    target_id TEXT NOT NULL REFERENCES roadmap_items(id),
    link_type TEXT NOT NULL  -- related, depends_on, blocks, parent, child
);

-- Calendar events
CREATE TABLE calendar_events (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT REFERENCES users(id),
    title TEXT NOT NULL,
    description TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    all_day INTEGER DEFAULT 0,
    recurrence_json TEXT,
    created_at TEXT NOT NULL
);

-- Tasks
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT REFERENCES users(id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'pending',
    priority TEXT,
    due_date TEXT,
    tags_json TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

-- Daily rhythm phases
CREATE TABLE rhythm_phases (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    name TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    start_time TEXT NOT NULL,  -- HH:MM
    end_time TEXT NOT NULL,
    description TEXT,
    days_json TEXT  -- JSON array of weekday numbers
);

-- Rhythm records
CREATE TABLE rhythm_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    date TEXT NOT NULL,
    phase_id TEXT NOT NULL REFERENCES rhythm_phases(id),
    status TEXT DEFAULT 'pending',  -- pending, active, completed, skipped
    started_at TEXT,
    completed_at TEXT,
    notes TEXT
);
CREATE INDEX idx_rhythm_date ON rhythm_records(daemon_id, date);

-- Token usage
CREATE TABLE token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    date TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0
);
CREATE INDEX idx_usage_date ON token_usage(daemon_id, date);
```

---

## Migration Strategy

### Phase 1: Schema & Infrastructure

1. Create `backend/database.py` with:
   - SQLite connection management
   - Schema creation functions
   - Migration version tracking

2. Create migration script `backend/migrations/001_initial_schema.py`

3. Add database path to config: `DATABASE_PATH = data/cass.db`

### Phase 2: Data Migration Script

Create `backend/scripts/migrate_to_sqlite.py`:

```python
# Pseudocode structure
def migrate():
    # 1. Create daemon record for Cass
    daemon_id = create_daemon("cass", kernel_version="temple-codex-1.0")

    # 2. Migrate users
    for user_dir in data/users/*:
        migrate_user(user_dir)

    # 3. Migrate conversations
    for conv_file in data/conversations/*.json:
        migrate_conversation(conv_file, daemon_id)

    # 4. Migrate self-model
    migrate_self_profile(daemon_id)
    migrate_growth_edges(daemon_id)
    migrate_opinions(daemon_id)
    migrate_snapshots(daemon_id)
    migrate_milestones(daemon_id)

    # 5. Migrate operational data
    migrate_projects(daemon_id)
    migrate_roadmap(daemon_id)
    migrate_dreams(daemon_id)
    migrate_research(daemon_id)
    migrate_wiki(daemon_id)
    migrate_goals(daemon_id)
    migrate_rhythm(daemon_id)
```

### Phase 3: Update Manager Classes

Update each manager to use SQLite:

1. `ConversationManager` - Query conversations/messages tables
2. `UserManager` - Query users/user_observations tables
3. `SelfModelManager` - Query daemon_profiles/growth_edges/opinions
4. `ProjectManager` - Query projects/project_files/project_documents
5. `RoadmapManager` - Query roadmap_items/roadmap_links

### Phase 4: Backward Compatibility

During transition:
1. Keep JSON files as backup
2. Add feature flag: `USE_SQLITE = True`
3. Run both systems in parallel for verification
4. Remove JSON fallback after validation

---

## Multi-Daemon Support

With `daemon_id` on all tables, adding a second daemon:

```sql
-- Create new daemon
INSERT INTO daemons (id, name, created_at, kernel_version)
VALUES ('uuid', 'aria', '2025-12-14T...', 'temple-codex-1.0');

-- Each daemon has isolated:
-- - Self-profile, growth edges, opinions
-- - Dreams, journals, reflections
-- - Research sessions, wiki pages
-- - Conversations (unless shared)

-- Shared across daemons:
-- - Users (human identities)
-- - Some projects (collaborative)
```

---

## Files to Create/Modify

### New Files
- `backend/database.py` - SQLite connection, schema management
- `backend/migrations/001_initial_schema.py` - Initial schema
- `backend/scripts/migrate_to_sqlite.py` - Data migration

### Files to Modify
- `backend/config.py` - Add DATABASE_PATH
- `backend/conversations.py` - Use SQLite
- `backend/users.py` - Use SQLite
- `backend/self_model.py` - Use SQLite
- `backend/projects.py` - Use SQLite
- `backend/roadmap.py` - Use SQLite
- `backend/main_sdk.py` - Initialize database connection

---

## Implementation Order

1. **database.py** - Connection management, schema creation
2. **Migration script** - One-time data migration
3. **ConversationManager** - Most frequently accessed
4. **UserManager** - Auth depends on this
5. **SelfModelManager** - Core to Cass identity
6. **ProjectManager** - Less critical
7. **RoadmapManager** - Less critical
8. **Other managers** - Dreams, research, wiki, etc.

---

## Dataset Sharing

With SQLite:
- Export: `sqlite3 cass.db .dump > export.sql`
- Selective export: Query specific daemon's data
- Anonymization: Strip user passwords, personal info
- Versioning: Include schema version in exports

For demo:
- Read-only database copy
- Pre-populated with representative data
- No auth required (demo mode)
